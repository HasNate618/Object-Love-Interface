"""
Date Pipeline — Webcam → SenseCAP Display → Date Button → Face Mode

Streams webcam video to the SenseCAP Indicator with a pink "Date" button
overlay. When the user taps the button (touch) or presses the physical
button (GPIO38), the pipeline:

  1. Captures the current webcam frame
  2. Saves it for the Pi/pipeline to process
  3. Calls on_capture() callback (override for Gemini, etc.)
  4. Switches the SenseCAP to animated face mode

Usage:
    python pipeline/date_pipeline.py
    python pipeline/date_pipeline.py --port COM6 --camera 1
    python pipeline/date_pipeline.py --wifi sensecap.local --camera 1

Environment:
    Requires: opencv-python, Pillow, pyserial
"""

import io
import os
import sys
import json
import time
import argparse
from pathlib import Path

import cv2

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is required: pip install Pillow")
    sys.exit(1)

import serial

# ============================================================================
# Configuration
# ============================================================================

DISPLAY_W = 480
DISPLAY_H = 480
BAUD = 921600

# Button region on the 480×480 display (left, top, right, bottom)
BUTTON_LEFT   = 150
BUTTON_TOP    = 400
BUTTON_RIGHT  = 330
BUTTON_BOTTOM = 455

# Visual style
BUTTON_COLOR  = (255, 105, 180)   # Hot pink
BUTTON_BORDER = (255, 20, 147)    # Deeper pink border
TEXT_COLOR     = (255, 255, 255)   # White

# JPEG quality for streaming (lower = faster transfer, more artifacts)
STREAM_QUALITY = 50

# Output directory for captured frames
CAPTURE_DIR = Path(__file__).parent / "captures"


# ============================================================================
# Image Processing
# ============================================================================

def resize_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Resize image to exactly w×h using cover (crop) strategy."""
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def overlay_button(img: Image.Image) -> Image.Image:
    """Draw a pink 'Date' button on the bottom of the image."""
    draw = ImageDraw.Draw(img)

    # Rounded rectangle background
    draw.rounded_rectangle(
        [BUTTON_LEFT, BUTTON_TOP, BUTTON_RIGHT, BUTTON_BOTTOM],
        radius=20,
        fill=BUTTON_COLOR,
        outline=BUTTON_BORDER,
        width=3,
    )

    # "Date ♥" text — try to load a nice font, fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        except (IOError, OSError):
            font = ImageFont.load_default()

    label = "Date  \u2665"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (BUTTON_LEFT + BUTTON_RIGHT - tw) // 2
    ty = (BUTTON_TOP + BUTTON_BOTTOM - th) // 2 - 2
    draw.text((tx, ty), label, fill=TEXT_COLOR, font=font)

    return img


def image_to_jpeg(img: Image.Image, quality: int = STREAM_QUALITY) -> bytes:
    """Compress PIL image to JPEG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ============================================================================
# Serial Protocol (event-aware)
# ============================================================================

class EventSerial:
    """
    Wraps pyserial to handle both command responses and async events.

    Events ({"event":...}) are collected into self.events.
    Command responses ({"status":...}) are returned by read_response().
    """

    def __init__(self, port: str, baud: int = BAUD, timeout: float = 0.5):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.events: list[dict] = []

    def drain_boot(self, wait: float = 1.5):
        """Wait for device to boot and drain startup messages."""
        time.sleep(wait)
        self.ser.reset_input_buffer()

    def send_cmd(self, cmd: dict) -> dict:
        """Send a JSON command and return the response, collecting events."""
        data = json.dumps(cmd, separators=(",", ":")) + "\n"
        self.ser.write(data.encode("utf-8"))
        self.ser.flush()
        return self._read_until_status(timeout=5)

    def send_jpeg(self, jpeg_bytes: bytes) -> dict:
        """Send a JPEG frame using the image protocol. Returns final status."""
        length = len(jpeg_bytes)

        # Send image command
        cmd = json.dumps({"cmd": "image", "len": length}, separators=(",", ":")) + "\n"
        self.ser.write(cmd.encode("utf-8"))
        self.ser.flush()

        # Wait for "ready"
        resp = self._read_until_status(timeout=3)
        if resp.get("status") != "ready":
            return resp

        # Send raw JPEG bytes
        self.ser.write(jpeg_bytes)
        self.ser.flush()

        # Wait for "ok"
        return self._read_until_status(timeout=5)

    def collect_events(self) -> list[dict]:
        """Read any buffered serial data and return collected events."""
        self._drain_lines()
        events = list(self.events)
        self.events.clear()
        return events

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    # --- Internal ---

    def _drain_lines(self):
        """Read all available lines, sorting into events vs responses."""
        while self.ser.in_waiting:
            line = self.ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if "event" in msg:
                    self.events.append(msg)
                # Discard stale status responses during drain
            except json.JSONDecodeError:
                pass

    def _read_until_status(self, timeout: float = 5) -> dict:
        """Read lines until a status response is found, collecting events."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ser.in_waiting:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if "event" in msg:
                        self.events.append(msg)
                    elif "status" in msg:
                        return msg
                except json.JSONDecodeError:
                    pass
            time.sleep(0.002)
        return {"status": "timeout"}


# ============================================================================
# Touch Hit Test
# ============================================================================

def is_button_touch(event: dict, touch_anywhere: bool) -> bool:
    """Check if a touch event falls within the Date button region."""
    if event.get("event") in ("button", "button_down"):
        return True  # Physical button always counts
    if event.get("event") == "touch":
        if touch_anywhere:
            return True
        x = event.get("x", -1)
        y = event.get("y", -1)
        return (BUTTON_LEFT <= x <= BUTTON_RIGHT and
                BUTTON_TOP <= y <= BUTTON_BOTTOM)
    return False


# ============================================================================
# Pipeline
# ============================================================================

def probe_cameras(max_index: int = 6) -> list[tuple[int, int, int]]:
    """Probe camera indices and return list of (index, width, height)."""
    results: list[tuple[int, int, int]] = []
    seen: set[int] = set()
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF]
    for idx in range(max_index):
        for backend in backends:
            cap = cv2.VideoCapture(idx, backend)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and idx not in seen:
                    h, w = frame.shape[:2]
                    results.append((idx, w, h))
                    seen.add(idx)
            cap.release()
    return results


def auto_select_camera() -> int:
    """Pick a camera index, preferring external (non-zero) when available."""
    cams = probe_cameras()
    if not cams:
        return 0

    # Prefer highest non-zero index (often the external USB camera)
    non_zero = [c for c in cams if c[0] != 0]
    if non_zero:
        return non_zero[-1][0]
    return cams[0][0]


def run_pipeline(
    port: str = "COM6",
    camera_index: int | str = -1,
    touch_anywhere: bool = False,
    on_capture=None,
    m5_url: str | None = None,
    server_url: str | None = None,
    wifi_host: str | None = None,
    servo_port: str | None = None,
):
    """
    Main pipeline loop.

    Args:
        port:         Serial port for SenseCAP Indicator.
        camera_index: OpenCV camera index (-1 = auto-detect).
        on_capture:   Callback(frame_path: str) called after capture.
                      Pipeline waits for it to return before switching to face.
                      If None, just saves and switches immediately.
        wifi_host:    If set, connect via WiFi TCP instead of serial.
                      Can be IP address or mDNS hostname (e.g. "sensecap.local").
    """
    # --- Setup ---
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

    if wifi_host:
        from wifi_link import WiFiLink
        print(f"Connecting to SenseCAP via WiFi at {wifi_host}...")
        link = WiFiLink(wifi_host)
        link.drain_boot(1.5)
    else:
        print(f"Connecting to SenseCAP on {port}...")
        link = EventSerial(port)
        link.drain_boot(1.5)

    # Disable face mode to start streaming video
    print("Disabling face mode...")
    link.send_cmd({"cmd": "face", "on": False})

    cam_index: int | None = None
    cam_path: str | None = None
    if isinstance(camera_index, str):
        if camera_index.strip().isdigit():
            cam_index = int(camera_index.strip())
        elif camera_index.startswith("/dev/"):
            cam_path = camera_index
        else:
            print(f"WARNING: Unknown camera value '{camera_index}', using auto-detect")
    else:
        cam_index = camera_index

    if cam_index is not None and cam_index < 0:
        env_idx = os.environ.get("DATE_CAMERA_INDEX")
        if env_idx and env_idx.isdigit():
            cam_index = int(env_idx)
        else:
            cam_index = auto_select_camera()

    if cam_path:
        print(f"Opening camera device {cam_path}...")
        cap = cv2.VideoCapture(cam_path, cv2.CAP_V4L2)
    else:
        print(f"Opening camera index {cam_index}...")
        cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        if cam_path:
            cap = cv2.VideoCapture(cam_path, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(cam_index, cv2.CAP_MSMF)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {camera_index}")
        link.close()
        return

    # Set camera resolution (request 640x480 for speed)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("\n  Streaming webcam to SenseCAP display.")
    print("  Tap the pink 'Date' button on screen (or press the side button).")
    print("  Press Ctrl+C to quit.\n")

    frame_count = 0
    last_pil_frame = None

    try:
        while True:
            # 1. Capture webcam frame
            ret, cv_frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            # 2. Convert to PIL, resize to 480×480
            rgb = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)
            pil_frame = Image.fromarray(rgb)
            pil_frame = resize_cover(pil_frame, DISPLAY_W, DISPLAY_H)
            last_pil_frame = pil_frame.copy()

            # 3. Overlay button
            display_frame = pil_frame.copy()
            overlay_button(display_frame)

            # 4. Send to SenseCAP
            jpeg = image_to_jpeg(display_frame)
            resp = link.send_jpeg(jpeg)

            frame_count += 1
            if frame_count % 30 == 0:
                fps_est = "~2-3" if resp.get("status") == "ok" else "?"
                print(f"  Streamed {frame_count} frames ({fps_est} fps)")

            # 5. Check for button/touch events
            events = link.collect_events()
            for ev in events:
                if ev.get("event") == "touch":
                    print(f"  Touch: x={ev.get('x')}, y={ev.get('y')}")
                elif ev.get("event") == "button":
                    print("  Button: physical press")

            date_pressed = any(is_button_touch(ev, touch_anywhere) for ev in events)

            if date_pressed:
                print("\n>>> Date button pressed! <<<")
                break

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        cap.release()
        link.close()
        return

    # --- Date Button Pressed ---
    cap.release()

    # Save captured frame
    timestamp = int(time.time())
    frame_path = str(CAPTURE_DIR / f"date_{timestamp}.jpg")
    if last_pil_frame:
        last_pil_frame.save(frame_path, quality=90)
        print(f"  Saved capture: {frame_path}")
    else:
        print("  Warning: No frame captured")
        frame_path = ""

    # Call the processing callback (e.g., send to Gemini on Pi)
    capture_result = {}
    if on_capture and frame_path:
        print("  Processing capture (waiting for Pi response)...")
        try:
            capture_result = on_capture(frame_path) or {}
        except Exception as e:
            print(f"  Callback error: {e}")
    elif frame_path:
        print("  No callback set — skipping remote processing.")

    # Switch to face mode
    print("  Switching to face mode...")
    link.send_cmd({"cmd": "face", "on": True})
    print("  Face mode active! \u2665")

    # Set initial love value from personality response (interest starts at 5)
    initial_interest = capture_result.get("interest", 5) if isinstance(capture_result, dict) else 5
    initial_love = max(0.0, min(1.0, initial_interest / 10.0))
    try:
        link.send_cmd({"cmd": "love", "value": initial_love})
        print(f"  [love] Initial interest={initial_interest} → love={initial_love:.2f}")
    except Exception as e:
        print(f"  [love] Initial screen update failed: {e}")

    # Play personality starter audio with mouth sync
    audio_url = capture_result.get("audioUrl") if isinstance(capture_result, dict) else None
    if audio_url:
        try:
            from mouth_sync import play_with_mouth_sync, wait_for_animation
            print("  Playing starter with mouth sync...")
            # Use passed m5_url or fall back to env vars
            final_m5_url = m5_url or os.environ.get("M5_PLAY_URL", os.environ.get("M5CORE2_URL", "")) or None
            anim = play_with_mouth_sync(link, audio_url, final_m5_url)
            wait_for_animation(anim)
        except Exception as e:
            print(f"  Mouth sync error: {e}")

    # Enter conversation loop if conversation module available
    servo = None
    try:
        if servo_port:
            from servo_serial import ServoSerial
            servo = ServoSerial(servo_port)
    except Exception as e:
        print(f"  WARNING: Could not open servo on {servo_port}: {e}")
        servo = None

    try:
        from conversation import run_conversation, find_mic_device, MIC_NAME_PATTERN
        mic_device = find_mic_device(MIC_NAME_PATTERN)
        if mic_device is not None:
            print(f"  Mic detected: device {mic_device}")
        else:
            print("  WARNING: No external mic found, using default.")
        # Use passed m5_url or fall back to env vars
        final_m5_url = m5_url or os.environ.get("M5_PLAY_URL", os.environ.get("M5CORE2_URL", ""))
        final_server_url = server_url or "http://localhost:3000"
        run_conversation(link, mic_device=mic_device, m5_play_url=final_m5_url, server_url=final_server_url, servo=servo)
    except ImportError:
        print("  conversation.py not available — skipping conversation loop.")
    except KeyboardInterrupt:
        print("\n  Done.")

    if servo:
        servo.close()

    link.close()


# ============================================================================
# Default capture callback (stub)
# ============================================================================

def default_on_capture(frame_path: str):
    """
    Default callback: prints path and returns immediately.
    Replace this with your Gemini/Pi processing logic.
    """
    print(f"  [default_on_capture] Frame saved at: {frame_path}")
    print(f"  [default_on_capture] Send this to your Pi or Gemini pipeline.")


def personality_on_capture(frame_path: str, server_url: str = "") -> dict:
    """
    Send captured image to the Node.js server to generate personality + TTS.
    Returns the server response dict (includes audioUrl for mouth sync).
    """
    from conversation import generate_personality
    result = generate_personality(frame_path, server_url)
    if result:
        print(f"  Personality generated: {result.get('personality', {}).get('identity', {}).get('name', '?')}")
    else:
        print("  WARNING: Personality generation failed.")
    return result or {}


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Webcam → SenseCAP Date Button → Face Mode Pipeline"
    )
    parser.add_argument("--port", default="COM6", help="SenseCAP serial port")
    parser.add_argument("--wifi", default=None, metavar="HOST",
                        help="Connect via WiFi TCP instead of serial (IP or hostname, e.g. sensecap.local)")
    parser.add_argument("--camera", default="-1",
                        help="Camera index or device path (e.g. 0, 1, /dev/video0; -1 = auto-detect)")
    parser.add_argument("--touch-anywhere", action="store_true",
                        help="Treat any touch as a Date button press")
    parser.add_argument("--server", default="http://localhost:3000",
                        help="Node.js image_to_voice server URL")
    parser.add_argument("--m5-url", dest="m5_url", default="",
                        help="M5Core1 play endpoint (e.g. http://IP:8082/play)")
    parser.add_argument("--servo-port", dest="servo_port", default=None,
                        help="Serial port for the ESP32 servo controller (e.g. /dev/ttyUSB0 or COM7)")
    args = parser.parse_args()

    print("=" * 50)
    print("  Date Pipeline")
    print("=" * 50)
    print(f"  Serial port: {args.port}")
    if args.wifi:
        print(f"  WiFi host:   {args.wifi}")
    
    # Parse camera argument: convert to int if numeric, keep as string if device path
    camera_arg = args.camera
    if isinstance(camera_arg, str) and camera_arg.strip().lstrip('-').isdigit():
        camera_index = int(camera_arg)
    else:
        camera_index = camera_arg  # Keep as string for device paths like /dev/video0
    
    cam_label = camera_arg
    if isinstance(camera_index, int) and camera_index < 0:
        cam_label = "auto"
    print(f"  Camera:      {cam_label}")
    print(f"  Server:      {args.server}")
    if os.environ.get("DATE_CAMERA_INDEX"):
        print(f"  DATE_CAMERA_INDEX: {os.environ.get('DATE_CAMERA_INDEX')}")
    print()

    # Use personality callback if server is configured
    def capture_cb(path):
        return personality_on_capture(path, args.server)

    run_pipeline(
        port=args.port,
        camera_index=camera_index,
        touch_anywhere=args.touch_anywhere,
        on_capture=capture_cb,
        m5_url=args.m5_url or None,
        server_url=args.server,
        wifi_host=args.wifi,
        servo_port=args.servo_port,
    )


if __name__ == "__main__":
    main()
