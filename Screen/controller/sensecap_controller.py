"""
SenseCAP Indicator Controller

Python API for displaying images and playing buzzer tones on the
SenseCAP Indicator from a Raspberry Pi or PC via USB serial (CH340).

Usage:
    from sensecap_controller import SenseCapController

    ctrl = SenseCapController("COM6")    # or "/dev/ttyUSB0" on Linux
    ctrl.show_image("photo.jpg")         # display a 480x480 JPEG
    ctrl.clear("#FF0000")                # fill screen red
    ctrl.tone(1000, 500)                 # 1 kHz beep for 500 ms
    ctrl.close()
"""

import io
import json
import time
import serial
import serial.tools.list_ports

try:
    from PIL import Image
except ImportError:
    Image = None  # Pillow optional; needed only for show_image()

# Display resolution
DISPLAY_W = 480
DISPLAY_H = 480
BAUD = 921600


class SenseCapController:
    """Controller for SenseCAP Indicator via CH340 UART."""

    def __init__(self, port=None, baud=BAUD, timeout=3, wait_ready=False):
        """
        Connect to the SenseCAP Indicator.

        Args:
            port:  Serial port (e.g., "COM6" or "/dev/ttyUSB0").
                   If None, auto-detects CH340.
            baud:  Baud rate (default 921600).
            timeout: Serial read timeout in seconds.
            wait_ready: If True, block until device sends "ready".
        """
        if port is None:
            port = self._auto_detect_port()

        self.port = port
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.5)
        self.ser.reset_input_buffer()

        if wait_ready:
            self._wait_ready()

    # ------------------------------------------------------------------
    # Port detection
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_detect_port():
        """Auto-detect the ESP32-S3 CH340 serial port."""
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").upper()
            # CH340 adapter on the SenseCAP Indicator
            if "ch340" in desc or "CH340" in hwid:
                return p.device
            # Espressif VID
            if "303A:" in hwid:
                return p.device
        if ports:
            return ports[0].device
        raise RuntimeError("No serial port found. Specify port manually.")

    def _wait_ready(self, timeout_sec=15):
        """Block until the device sends {"status":"ready"}."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self.ser.in_waiting:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("status") == "ready":
                        return True
                    # Print boot messages for debugging
                    print(f"[device] {msg}")
                except json.JSONDecodeError:
                    print(f"[device] {line}")
            time.sleep(0.05)
        print("Warning: device did not send 'ready' within timeout.")
        return False

    # ------------------------------------------------------------------
    # Low-level communication
    # ------------------------------------------------------------------

    def send_cmd(self, cmd_dict):
        """Send a JSON command and return the parsed response dict."""
        data = json.dumps(cmd_dict, separators=(",", ":")) + "\n"
        self.ser.write(data.encode("utf-8"))
        self.ser.flush()
        return self._read_response()

    def _read_response(self, timeout=5):
        """Read one JSON line from device."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ser.in_waiting:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        return {"status": "error", "msg": f"bad response: {line}"}
            time.sleep(0.01)
        return {"status": "timeout"}

    # ------------------------------------------------------------------
    # Image display
    # ------------------------------------------------------------------

    def show_image(self, path_or_pil, quality=85):
        """
        Display an image on the 480x480 screen.

        Args:
            path_or_pil: File path (str) or PIL.Image object.
            quality:     JPEG compression quality (1-100).

        Returns:
            Response dict from device.
        """
        if Image is None:
            raise RuntimeError("Pillow is required: pip install Pillow")

        # Load image
        if isinstance(path_or_pil, str):
            img = Image.open(path_or_pil)
        else:
            img = path_or_pil

        # Convert to RGB, resize to 480x480 (cover + center crop)
        img = img.convert("RGB")
        img = self._resize_cover(img, DISPLAY_W, DISPLAY_H)

        # Encode as JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        jpeg_bytes = buf.getvalue()

        return self.send_jpeg(jpeg_bytes)

    def send_jpeg(self, jpeg_bytes: bytes):
        """
        Send raw JPEG bytes to the device for display.

        The JPEG should be 480x480; other sizes will be decoded
        to whatever fits (clipped or padded with black).
        """
        length = len(jpeg_bytes)

        # Step 1: send image command with length
        resp = self.send_cmd({"cmd": "image", "len": length})
        if resp.get("status") != "ready":
            return resp

        # Step 2: send raw JPEG bytes
        self.ser.write(jpeg_bytes)
        self.ser.flush()

        # Step 3: wait for decode result
        return self._read_response(timeout=15)

    @staticmethod
    def _resize_cover(img, w, h):
        """Resize image to exactly w×h using cover (crop) strategy."""
        src_w, src_h = img.size
        scale = max(w / src_w, h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        return img.crop((left, top, left + w, top + h))

    # ------------------------------------------------------------------
    # Display commands
    # ------------------------------------------------------------------

    def clear(self, color="#000000"):
        """Fill the screen with a solid color (hex string)."""
        return self.send_cmd({"cmd": "clear", "color": color})

    # ------------------------------------------------------------------
    # Face mode commands
    # ------------------------------------------------------------------

    def face_on(self):
        """Enable animated face mode (disables image mode)."""
        return self.send_cmd({"cmd": "face", "on": True})

    def face_off(self):
        """Disable face mode. Returns to static display."""
        return self.send_cmd({"cmd": "face", "on": False})

    def set_mouth(self, openness):
        """
        Set mouth openness for lip sync.

        Args:
            openness: 0.0 (closed smile) to 1.0 (fully open).
                      For lip sync, send rapid updates (~30/sec).
        """
        val = max(0.0, min(1.0, float(openness)))
        return self.send_cmd({"cmd": "mouth", "open": val})

    def set_love(self, value):
        """
        Set love level — controls floating hearts.

        Args:
            value: 0.0 (no hearts) to 1.0 (6 floating hearts).
        """
        val = max(0.0, min(1.0, float(value)))
        return self.send_cmd({"cmd": "love", "value": val})

    def blink(self):
        """Trigger a manual eye blink."""
        return self.send_cmd({"cmd": "blink"})

    def backlight(self, on=True):
        """Turn backlight on or off."""
        return self.send_cmd({"cmd": "bl", "on": on})

    # ------------------------------------------------------------------
    # Audio commands (buzzer via RP2040)
    # ------------------------------------------------------------------

    def tone(self, freq, duration=200):
        """Play a tone on the buzzer (freq Hz for duration ms)."""
        return self.send_cmd({"cmd": "tone", "freq": freq, "dur": duration})

    def melody(self, notes):
        """
        Play a melody string.

        Format: "C4:4 D4:4 E4:4 ..." (note:duration pairs).
        """
        return self.send_cmd({"cmd": "melody", "notes": notes})

    def stop_audio(self):
        """Stop any playing tone/melody."""
        return self.send_cmd({"cmd": "stop"})

    def beep(self):
        """Short beep."""
        return self.tone(1000, 100)

    def alert(self):
        """Three quick beeps."""
        for _ in range(3):
            self.tone(2000, 100)
            time.sleep(0.15)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def close(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def list_ports():
        """List all available serial ports."""
        return [
            {"device": p.device, "description": p.description, "hwid": p.hwid}
            for p in serial.tools.list_ports.comports()
        ]
