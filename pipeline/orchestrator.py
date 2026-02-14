"""
Object-Love-Interface Pipeline Orchestrator

Main loop:
  1. Capture image + audio from webcam/mic
  2. Send to Gemini API for multimodal understanding
  3. Get text response from Gemini
  4. Send text to ElevenLabs TTS → receive MP3 audio
  5. Display relevant image on SenseCAP Indicator (serial)
  6. Play TTS audio on M5Core2 (WiFi via audio_server)

Environment variables required:
  GEMINI_API_KEY      — Google AI Studio / Vertex AI key
  ELEVENLABS_API_KEY  — ElevenLabs API key
  ELEVENLABS_VOICE_ID — ElevenLabs voice ID (default: "Rachel")
  M5CORE2_IP          — M5Core2 IP address on LAN
  SENSECAP_PORT       — Serial port for SenseCAP (default: COM6 / /dev/ttyUSB0)
  AUDIO_SERVER_URL    — URL of audio_server.py (default: http://localhost:8080)
"""

import os
import sys
import io
import time
import json
import base64
import struct
import tempfile
from pathlib import Path

import cv2
import requests
from PIL import Image

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "Screen" / "controller"))
from sensecap_controller import SenseCapController

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
M5CORE2_IP = os.environ.get("M5CORE2_IP", "")
SENSECAP_PORT = os.environ.get("SENSECAP_PORT", "COM6")
AUDIO_SERVER_URL = os.environ.get("AUDIO_SERVER_URL", "http://localhost:8080")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_PROMPT = """You are a friendly, observant AI assistant embedded in a physical device.
You can see through a camera. Describe what you see concisely and warmly.
Keep responses under 3 sentences — they will be spoken aloud via text-to-speech.
Be conversational and natural."""


# ---------------------------------------------------------------------------
# Webcam Capture
# ---------------------------------------------------------------------------

def capture_frame(camera_index: int = 0) -> Image.Image | None:
    """Capture a single frame from the webcam."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return None
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("ERROR: Cannot read frame")
        return None
    # Convert BGR → RGB → PIL
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def image_to_base64(img: Image.Image, max_size: int = 1024) -> str:
    """Resize and encode image as base64 JPEG for Gemini."""
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

def ask_gemini(image: Image.Image, prompt: str = "What do you see?") -> str:
    """Send image + prompt to Gemini and return text response."""
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY not set"

    img_b64 = image_to_base64(image)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": f"{SYSTEM_PROMPT}\n\nUser: {prompt}"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_b64
                    }
                }
            ]
        }]
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()
    except Exception as e:
        return f"Gemini error: {e}"


# ---------------------------------------------------------------------------
# ElevenLabs TTS
# ---------------------------------------------------------------------------

def text_to_speech(text: str) -> bytes | None:
    """Convert text to MP3 audio bytes via ElevenLabs API."""
    if not ELEVENLABS_API_KEY:
        print("ERROR: ELEVENLABS_API_KEY not set")
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"ElevenLabs error: {e}")
        return None


# ---------------------------------------------------------------------------
# Output: Display + Audio
# ---------------------------------------------------------------------------

def send_to_display(ctrl: SenseCapController, image: Image.Image):
    """Send the captured frame to the SenseCAP Indicator display."""
    try:
        resp = ctrl.show_image(image, quality=80)
        print(f"  Display: {resp}")
    except Exception as e:
        print(f"  Display error: {e}")


def send_to_speaker(audio_bytes: bytes):
    """Upload audio to the audio server, which forwards to M5Core2."""
    try:
        resp = requests.post(
            f"{AUDIO_SERVER_URL}/upload_and_play",
            data=audio_bytes,
            headers={"Content-Type": "audio/mpeg"},
            timeout=10,
        )
        print(f"  Audio: {resp.json()}")
    except Exception as e:
        print(f"  Audio error: {e}")


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def run_once(ctrl: SenseCapController, camera_index: int = 0):
    """Run one cycle of the pipeline."""
    print("\n--- Capturing frame ---")
    frame = capture_frame(camera_index)
    if frame is None:
        return

    # Show the raw camera frame on display
    print("Sending frame to display...")
    send_to_display(ctrl, frame)

    # Ask Gemini
    print("Asking Gemini...")
    response_text = ask_gemini(frame)
    print(f"  Gemini: {response_text}")

    # Convert to speech
    print("Generating speech...")
    audio = text_to_speech(response_text)
    if audio:
        print(f"  Got {len(audio)} bytes of audio")
        send_to_speaker(audio)
    else:
        print("  No audio generated")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Object-Love-Interface Pipeline")
    parser.add_argument("--port", default=SENSECAP_PORT, help="SenseCAP serial port")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between captures in loop mode")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    print("=== Object-Love-Interface Pipeline ===")
    print(f"SenseCAP port: {args.port}")
    print(f"Camera index:  {args.camera}")
    print(f"Audio server:  {AUDIO_SERVER_URL}")
    print(f"M5Core2 IP:    {M5CORE2_IP or 'not set'}")
    print(f"Gemini model:  {GEMINI_MODEL}")
    print()

    # Check API keys
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not ELEVENLABS_API_KEY:
        missing.append("ELEVENLABS_API_KEY")
    if missing:
        print(f"WARNING: Missing env vars: {', '.join(missing)}")
        print("Set them before running the full pipeline.\n")

    # Connect to SenseCAP display
    try:
        ctrl = SenseCapController(args.port)
        print(f"Connected to SenseCAP on {args.port}")
    except Exception as e:
        print(f"Cannot connect to SenseCAP: {e}")
        print("Running without display output.")
        ctrl = None

    if args.once or not args.loop:
        run_once(ctrl or _DummyCtrl(), args.camera)
    else:
        print(f"\nRunning every {args.interval}s. Press Ctrl+C to stop.\n")
        try:
            while True:
                run_once(ctrl or _DummyCtrl(), args.camera)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")

    if ctrl:
        ctrl.close()


class _DummyCtrl:
    """Stub when display is not connected."""
    def show_image(self, *a, **kw):
        return {"status": "skipped (no display)"}
    def close(self):
        pass


if __name__ == "__main__":
    main()
