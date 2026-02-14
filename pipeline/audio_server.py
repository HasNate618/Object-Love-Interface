"""
Audio file server — serves generated MP3/WAV files to the M5Core2.

Runs on the Raspberry Pi. The orchestrator saves ElevenLabs audio to
the `audio_files/` directory, and this server makes them available
over HTTP so the M5Core2 can stream them.

Also provides a convenience endpoint to tell the M5Core2 to play.
"""

import os
import json
import time
import threading
from pathlib import Path

import requests
from flask import Flask, send_from_directory, jsonify, request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUDIO_DIR = Path(__file__).parent / "audio_files"
AUDIO_DIR.mkdir(exist_ok=True)

HOST = "0.0.0.0"
PORT = 8080

# M5Core2 address — set via env or auto-discovered
M5_HOST = os.environ.get("M5CORE2_IP", "")
M5_PORT = int(os.environ.get("M5CORE2_PORT", "8082"))

app = Flask(__name__)

# Track latest audio file
_latest_file = None
_latest_lock = threading.Lock()


def set_latest(filename: str):
    global _latest_file
    with _latest_lock:
        _latest_file = filename


def get_latest() -> str | None:
    with _latest_lock:
        return _latest_file


# ---------------------------------------------------------------------------
# HTTP routes (served to M5Core2)
# ---------------------------------------------------------------------------

@app.route("/audio/<path:filename>")
def serve_audio(filename):
    """Serve an audio file from the audio_files directory."""
    return send_from_directory(str(AUDIO_DIR), filename)


@app.route("/audio/latest")
def serve_latest():
    """Redirect to the latest generated audio file."""
    latest = get_latest()
    if not latest:
        return jsonify({"error": "no audio available"}), 404
    return send_from_directory(str(AUDIO_DIR), latest)


@app.route("/status")
def status():
    return jsonify({
        "latest": get_latest(),
        "files": sorted(os.listdir(AUDIO_DIR)),
        "m5core2": M5_HOST or "not configured",
    })


# ---------------------------------------------------------------------------
# M5Core2 control helpers
# ---------------------------------------------------------------------------

def tell_m5_play(url: str, fmt: str = "mp3") -> dict:
    """Send a play command to the M5Core2."""
    if not M5_HOST:
        return {"error": "M5CORE2_IP not configured"}
    try:
        resp = requests.post(
            f"http://{M5_HOST}:{M5_PORT}/play",
            json={"url": url, "format": fmt},
            timeout=5,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def tell_m5_stop() -> dict:
    if not M5_HOST:
        return {"error": "M5CORE2_IP not configured"}
    try:
        resp = requests.post(f"http://{M5_HOST}:{M5_PORT}/stop", timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def tell_m5_volume(level: int) -> dict:
    if not M5_HOST:
        return {"error": "M5CORE2_IP not configured"}
    try:
        resp = requests.post(
            f"http://{M5_HOST}:{M5_PORT}/volume",
            json={"level": level},
            timeout=5,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# API for the orchestrator to push audio + trigger playback
# ---------------------------------------------------------------------------

@app.route("/play_latest", methods=["POST"])
def play_latest():
    """Tell M5Core2 to play the latest audio file."""
    latest = get_latest()
    if not latest:
        return jsonify({"error": "no audio available"}), 404

    # Determine local IP for the M5Core2 to reach us
    pi_ip = request.host.split(":")[0]
    if pi_ip in ("127.0.0.1", "localhost", "0.0.0.0"):
        # Try to figure out actual LAN IP
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            pi_ip = s.getsockname()[0]
        finally:
            s.close()

    audio_url = f"http://{pi_ip}:{PORT}/audio/{latest}"
    fmt = "wav" if latest.endswith(".wav") else "mp3"
    result = tell_m5_play(audio_url, fmt)
    return jsonify({"audio_url": audio_url, "m5_response": result})


@app.route("/upload_and_play", methods=["POST"])
def upload_and_play():
    """
    Upload audio bytes and immediately tell M5Core2 to play.
    Content-Type: audio/mpeg or audio/wav
    """
    content_type = request.content_type or ""
    ext = ".wav" if "wav" in content_type else ".mp3"
    filename = f"tts_{int(time.time())}{ext}"
    filepath = AUDIO_DIR / filename

    filepath.write_bytes(request.data)
    set_latest(filename)

    # Determine our LAN IP
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        pi_ip = s.getsockname()[0]
    finally:
        s.close()

    audio_url = f"http://{pi_ip}:{PORT}/audio/{filename}"
    fmt = ext.lstrip(".")
    result = tell_m5_play(audio_url, fmt)
    return jsonify({"file": filename, "url": audio_url, "m5_response": result})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Audio server starting on {HOST}:{PORT}")
    print(f"Audio directory: {AUDIO_DIR}")
    print(f"M5Core2 target: {M5_HOST}:{M5_PORT}" if M5_HOST else "M5Core2 IP not set (use M5CORE2_IP env var)")
    app.run(host=HOST, port=PORT, threaded=True)
