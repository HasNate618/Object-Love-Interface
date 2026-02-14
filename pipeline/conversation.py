"""
Conversation Pipeline — Push-to-Talk via SenseCAP button + webcam mic

After the date pipeline captures an image and generates a personality
(via the Node.js image_to_voice server), this module handles the
ongoing conversation loop:

  1. User holds the physical button on SenseCAP → records from webcam mic
    2. User releases button → audio transcribed via SpeechRecognition
  3. Transcribed text sent to Node.js /respond → Gemini response + TTS
  4. Loop until Ctrl+C

Usage:
    Called by date_pipeline.py after image capture, or standalone:
        python pipeline/conversation.py --port COM6

Requires:
    - Node.js image_to_voice server running on IMAGE_TO_VOICE_URL
    - pyaudio, requests, pyserial, speechrecognition
"""

import io
import os
import sys
import json
import time
import wave
import threading
import argparse
from pathlib import Path

import pyaudio
import requests
import speech_recognition as sr

# Reuse EventSerial from date_pipeline
sys.path.insert(0, str(Path(__file__).parent))
from date_pipeline import EventSerial, BAUD

# ============================================================================
# Configuration
# ============================================================================

IMAGE_TO_VOICE_URL = os.environ.get("IMAGE_TO_VOICE_URL", "http://localhost:3000")

# Audio recording settings (match webcam mic capabilities)
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
FORMAT = pyaudio.paInt16  # 16-bit PCM

# Mic device name pattern to auto-detect external webcam mic
MIC_NAME_PATTERN = os.environ.get("MIC_NAME", "Brio")


# ============================================================================
# Microphone Helpers
# ============================================================================

def find_mic_device(name_pattern: str = MIC_NAME_PATTERN) -> int | None:
    """Find a microphone device index matching the name pattern."""
    pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if (info["maxInputChannels"] > 0 and
                    name_pattern.lower() in info["name"].lower()):
                return i
        return None
    finally:
        pa.terminate()


def list_input_devices():
    """Print all input devices for debugging."""
    pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                print(f"  [{i}] {info['name']} ({info['maxInputChannels']}ch)")
    finally:
        pa.terminate()


class PushToTalkRecorder:
    """
    Records audio from a microphone while a flag is set.

    Usage:
        rec = PushToTalkRecorder(device_index=1)
        rec.start()          # Begin recording
        ...                   # (button held)
        wav_bytes = rec.stop()  # Stop and get WAV bytes
    """

    def __init__(self, device_index: int | None = None,
                 sample_rate: int = SAMPLE_RATE,
                 channels: int = CHANNELS):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._frames: list[bytes] = []
        self._recording = False
        self._thread: threading.Thread | None = None

    def start(self):
        """Start recording in a background thread."""
        if self._recording:
            return
        self._frames = []
        self._recording = True
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=FORMAT,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=CHUNK,
        )
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def _record_loop(self):
        """Continuously read from mic until stopped."""
        while self._recording and self._stream:
            try:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self._frames.append(data)
            except Exception:
                break

    def stop(self) -> bytes:
        """Stop recording and return WAV bytes."""
        self._recording = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None

        # Encode as WAV
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(self._frames))
        return buf.getvalue()

    @property
    def duration(self) -> float:
        """Approximate recording duration in seconds."""
        num_frames = len(self._frames) * CHUNK
        return num_frames / self.sample_rate if self.sample_rate else 0


# ============================================================================
# SpeechRecognition STT (Google Web Speech)
# ============================================================================

def speech_to_text(wav_bytes: bytes) -> str:
    """
    Transcribe WAV audio using SpeechRecognition (Google Web Speech API).
    Returns transcribed text.
    """
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"  STT error: {e}")
        return ""


# ============================================================================
# Node.js Server Communication
# ============================================================================

def generate_personality(image_path: str, server_url: str = "") -> dict:
    """
    Send captured image to the Node.js /generate-personality endpoint.
    Returns {personality, starter} dict.
    """
    url = (server_url or IMAGE_TO_VOICE_URL).rstrip("/")

    with open(image_path, "rb") as f:
        files = {"image": (Path(image_path).name, f, "image/jpeg")}
        try:
            print(f"  Sending image to {url}/generate-personality ...")
            resp = requests.post(f"{url}/generate-personality", files=files, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            print(f"  Personality: {data.get('personality', {}).get('identity', {}).get('name', '?')}")
            print(f"  Starter: {data.get('starter', '')[:80]}")
            return data
        except Exception as e:
            print(f"  Personality generation error: {e}")
            return {}


def send_user_message(text: str, server_url: str = "") -> dict:
    """
    Send user text to the Node.js /respond endpoint.
    The server handles Gemini response + ElevenLabs TTS + robot playback.
    Returns {response} dict.
    """
    url = (server_url or IMAGE_TO_VOICE_URL).rstrip("/")

    try:
        resp = requests.post(
            f"{url}/respond",
            json={"input": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Respond error: {e}")
        return {}


# ============================================================================
# Conversation Loop
# ============================================================================

def run_conversation(
    link: EventSerial,
    mic_device: int | None = None,
    server_url: str = "",
):
    """
    Push-to-talk conversation loop.

    - Hold button → record from webcam mic
    - Release button → STT → send to /respond → TTS plays on robot
    - Repeat until Ctrl+C
    """
    recorder = PushToTalkRecorder(device_index=mic_device)
    recording = False

    print("\n  Conversation mode active!")
    print("  Hold the button to speak, release to send.")
    print("  Press Ctrl+C to quit.\n")

    try:
        while True:
            events = link.collect_events()
            for ev in events:
                if ev.get("event") == "button_down" and not recording:
                    recording = True
                    recorder.start()
                    print("  [REC] Recording... (hold button)")

                elif ev.get("event") == "button_up" and recording:
                    recording = False
                    wav_bytes = recorder.stop()
                    duration = recorder.duration
                    print(f"  [REC] Stopped ({duration:.1f}s)")

                    if duration < 0.3:
                        print("  Too short, ignoring.")
                        continue

                    # STT
                    print("  Transcribing...")
                    text = speech_to_text(wav_bytes)
                    if not text.strip():
                        print("  (no speech detected)")
                        continue
                    print(f"  You: {text}")

                    # Send to Gemini via Node.js
                    print("  Thinking...")
                    result = send_user_message(text, server_url)
                    response = result.get("response", "")
                    if response:
                        print(f"  AI: {response[:120]}")
                    else:
                        print("  (no response)")

                    # Legacy button event support
                elif ev.get("event") == "button":
                    # Treat single press as a toggle if firmware hasn't been updated
                    if not recording:
                        recording = True
                        recorder.start()
                        print("  [REC] Recording... (press again to stop)")
                    else:
                        recording = False
                        wav_bytes = recorder.stop()
                        duration = recorder.duration
                        print(f"  [REC] Stopped ({duration:.1f}s)")
                        if duration < 0.3:
                            print("  Too short, ignoring.")
                            continue
                        print("  Transcribing...")
                        text = speech_to_text(wav_bytes)
                        if not text.strip():
                            print("  (no speech detected)")
                            continue
                        print(f"  You: {text}")
                        print("  Thinking...")
                        result = send_user_message(text, server_url)
                        response = result.get("response", "")
                        if response:
                            print(f"  AI: {response[:120]}")

            time.sleep(0.01)  # Small sleep to avoid busy-wait

    except KeyboardInterrupt:
        if recording:
            recorder.stop()
        print("\n  Conversation ended.")


# ============================================================================
# CLI Entry Point (standalone testing)
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Push-to-Talk Conversation via SenseCAP button + webcam mic"
    )
    parser.add_argument("--port", default="COM6", help="SenseCAP serial port")
    parser.add_argument("--server", default=IMAGE_TO_VOICE_URL,
                        help="Node.js image_to_voice server URL")
    parser.add_argument("--mic", type=int, default=None,
                        help="Mic device index (None = auto-detect)")
    parser.add_argument("--mic-name", default=MIC_NAME_PATTERN,
                        help="Mic device name pattern for auto-detect")
    parser.add_argument("--list-mics", action="store_true",
                        help="List input devices and exit")
    parser.add_argument("--image", default=None,
                        help="Image path to send to /generate-personality first")
    args = parser.parse_args()

    if args.list_mics:
        print("Available input devices:")
        list_input_devices()
        return

    # Auto-detect mic
    mic_device = args.mic
    if mic_device is None:
        mic_device = find_mic_device(args.mic_name)
        if mic_device is not None:
            print(f"  Auto-detected mic: device {mic_device}")
        else:
            print(f"  WARNING: No mic matching '{args.mic_name}' found. Using default.")
            print("  Available devices:")
            list_input_devices()

    print("=" * 50)
    print("  Conversation Pipeline")
    print("=" * 50)
    print(f"  Serial port: {args.port}")
    print(f"  Server:      {args.server}")
    print(f"  Mic device:  {mic_device or 'default'}")
    print()

    # Connect to SenseCAP
    link = EventSerial(args.port)
    link.drain_boot(1.0)

    # Optionally generate personality from image first
    if args.image:
        result = generate_personality(args.image, args.server)
        if not result:
            print("  Failed to generate personality. Continuing anyway...")

    # Enable face mode
    link.send_cmd({"cmd": "face", "on": True})
    print("  Face mode enabled.")

    run_conversation(link, mic_device=mic_device, server_url=args.server)

    link.close()


if __name__ == "__main__":
    main()
