"""
Mouth Sync — Animate SenseCAP mouth from ElevenLabs audio amplitude

Downloads the TTS MP3 from the Node.js server, extracts an amplitude
envelope, then simultaneously tells the M5Core1 to play the audio AND
sends timed mouth‐open commands to the SenseCAP face.

Usage (called from conversation.py):
    play_with_mouth_sync(link, audio_url, m5_play_url)

Requires:
    pip install pydub requests numpy
    ffmpeg must be on PATH (pydub uses it to decode MP3)
"""

import io
import json
import math
import os
import struct
import tempfile
import time
import threading
from typing import TYPE_CHECKING

import numpy as np
import requests

try:
    from pydub import AudioSegment
except ImportError:
    raise ImportError("pydub is required: pip install pydub")

if TYPE_CHECKING:
    from date_pipeline import EventSerial

# ============================================================================
# Configuration
# ============================================================================

# How often we send a mouth command (ms). Must match face render rate (~25ms).
FRAME_MS = 30

# Smoothing factor for amplitude (0 = no smoothing, 1 = frozen).
# Applied as exponential moving average.
SMOOTH_ALPHA = 0.35

# Power curve exponent — values < 1 make small amplitudes more visible,
# values > 1 emphasize loud peaks.
POWER_CURVE = 0.6

# Fixed delay (seconds) after sending the M5 play command, before starting
# mouth animation. Compensates for M5's HTTP fetch + buffer latency.
M5_BUFFER_DELAY = 0.4

# Minimum openness sent (keeps lips slightly parted during speech)
MIN_OPEN = 0.0

# Maximum openness cap
MAX_OPEN = 1.0

# Silence threshold — below this RMS the mouth closes
SILENCE_THRESHOLD = 0.02


# ============================================================================
# Audio Analysis
# ============================================================================

def analyze_audio(mp3_bytes: bytes, frame_ms: int = FRAME_MS) -> tuple[list[float], float]:
    """
    Decode MP3 to mono PCM and compute a per-frame amplitude envelope.

    Returns (amplitudes, duration_seconds) where amplitudes is a list of
    float values in [0.0, 1.0] — one per frame_ms window.
    """
    # Write to temp file to avoid ffmpeg pipe options incompatible with older ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = tmp.name
    
    try:
        # Decode MP3 → mono 16-bit PCM
        seg = AudioSegment.from_file(tmp_path, format="mp3")
        seg = seg.set_channels(1).set_sample_width(2)  # mono, 16-bit
        audio_duration_s = len(seg) / 1000.0  # pydub duration is in ms
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
    samples /= 32768.0  # Normalize to [-1, 1]

    sample_rate = seg.frame_rate
    frame_samples = int(sample_rate * frame_ms / 1000)

    if frame_samples == 0 or len(samples) == 0:
        return [], audio_duration_s

    # Compute RMS per frame
    num_frames = len(samples) // frame_samples
    amplitudes = []

    for i in range(num_frames):
        start = i * frame_samples
        end = start + frame_samples
        frame = samples[start:end]
        rms = np.sqrt(np.mean(frame ** 2))
        amplitudes.append(float(rms))

    if not amplitudes:
        return [], audio_duration_s

    # Normalize to [0, 1] based on the peak RMS in this clip
    peak = max(amplitudes)
    if peak > 0:
        amplitudes = [a / peak for a in amplitudes]

    # Apply power curve for more natural mouth movement
    amplitudes = [pow(a, POWER_CURVE) for a in amplitudes]

    # Apply silence threshold
    amplitudes = [a if a > SILENCE_THRESHOLD else 0.0 for a in amplitudes]

    # Exponential moving average smoothing
    smoothed = []
    prev = 0.0
    for a in amplitudes:
        val = SMOOTH_ALPHA * prev + (1 - SMOOTH_ALPHA) * a
        smoothed.append(val)
        prev = val

    # Clamp to [MIN_OPEN, MAX_OPEN]
    smoothed = [max(MIN_OPEN, min(MAX_OPEN, v)) for v in smoothed]

    # Trim trailing silence to prevent mouth moving after audio ends
    # Find last non-zero frame
    last_sound = len(smoothed) - 1
    while last_sound > 0 and smoothed[last_sound] < 0.01:
        last_sound -= 1
    
    # Keep a few extra frames after last sound for natural close
    last_sound = min(len(smoothed) - 1, last_sound + 3)
    smoothed = smoothed[:last_sound + 1]

    # Scale down animation duration to 0.7x audio duration to compensate
    # for SenseCAP mouth rendering being slower than audio playback
    target_duration_s = audio_duration_s * 0.7
    target_frames = int(target_duration_s * 1000 / frame_ms)
    if len(smoothed) > target_frames and target_frames > 0:
        smoothed = smoothed[:target_frames]

    return smoothed, audio_duration_s


def get_audio_duration_ms(mp3_bytes: bytes) -> float:
    """Return the duration of the MP3 in milliseconds."""
    seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
    return len(seg)


# ============================================================================
# Mouth Animation Thread
# ============================================================================

def _send_mouth(link: "EventSerial", openness: float):
    """Send a mouth command to the SenseCAP (fire-and-forget, no response wait)."""
    cmd = json.dumps({"cmd": "mouth", "open": round(openness, 2)},
                     separators=(",", ":")) + "\n"
    try:
        link.ser.write(cmd.encode("utf-8"))
        link.ser.flush()
    except Exception:
        pass  # Serial glitches shouldn't crash the animation


def animate_mouth(
    link: "EventSerial",
    amplitudes: list[float],
    frame_ms: int = FRAME_MS,
    stop_event: threading.Event | None = None,
):
    """
    Send mouth commands to SenseCAP timed to the amplitude envelope.

    Runs synchronously — call from a thread if you don't want to block.
    Optionally pass a threading.Event to stop early.
    """
    if not amplitudes:
        return

    start_time = time.perf_counter()
    frame_sec = frame_ms / 1000.0
    expected_duration = len(amplitudes) * frame_sec
    print(f"  [mouth_sync] Animating {len(amplitudes)} frames over {expected_duration:.2f}s")

    for i, openness in enumerate(amplitudes):
        if stop_event and stop_event.is_set():
            break

        _send_mouth(link, openness)

        # Sleep until the next frame time
        next_time = start_time + (i + 1) * frame_sec
        sleep_dur = next_time - time.perf_counter()
        if sleep_dur > 0:
            time.sleep(sleep_dur)

    # Close mouth when done
    _send_mouth(link, 0.0)
    actual_duration = time.perf_counter() - start_time
    print(f"  [mouth_sync] Animation complete ({actual_duration:.2f}s actual)")


# ============================================================================
# Orchestrator — Play Audio + Animate Mouth
# ============================================================================

def play_with_mouth_sync(
    link: "EventSerial",
    audio_url: str,
    m5_play_url: str | None = None,
    buffer_delay: float = M5_BUFFER_DELAY,
) -> threading.Thread | None:
    """
    Download audio, analyse amplitude, trigger M5 playback, animate mouth.

    1. Downloads the MP3 from audio_url
    2. Extracts amplitude envelope
    3. Sends play command to M5Core1 (if m5_play_url is set)
    4. Waits buffer_delay seconds for M5 to start playing
    5. Sends timed mouth commands to SenseCAP

    Returns the animation thread (already started) so caller can join() if needed.
    Returns None if the audio download fails.
    """
    # 1. Download the MP3
    try:
        resp = requests.get(audio_url, timeout=10)
        resp.raise_for_status()
        mp3_bytes = resp.content
    except Exception as e:
        print(f"  [mouth_sync] Failed to download audio: {e}")
        return None

    if len(mp3_bytes) < 100:
        print("  [mouth_sync] Audio too small, skipping animation.")
        return None

    # 2. Analyse amplitude
    try:
        amplitudes, audio_duration = analyze_audio(mp3_bytes)
    except Exception as e:
        print(f"  [mouth_sync] Audio analysis failed: {e}")
        return None

    if not amplitudes:
        print("  [mouth_sync] No amplitude data extracted.")
        return None

    anim_duration_s = len(amplitudes) * FRAME_MS / 1000
    scale_factor = anim_duration_s / audio_duration if audio_duration > 0 else 1.0
    print(f"  [mouth_sync] Audio: {audio_duration:.2f}s (file), {anim_duration_s:.2f}s (animation at {scale_factor:.2f}x), {len(amplitudes)} frames")

    # 3. Tell M5Core1 to play
    if m5_play_url:
        try:
            print(f"  [mouth_sync] Sending play command to: {m5_play_url}")
            print(f"  [mouth_sync] Audio URL: {audio_url}")
            resp = requests.post(m5_play_url, json={
                "url": audio_url,
                "format": "mp3",
            }, timeout=5)
            print(f"  [mouth_sync] M5 response status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"  [mouth_sync] M5 response body: {resp.text}")
        except Exception as e:
            print(f"  [mouth_sync] M5 play failed: {e}")
    else:
        print("  [mouth_sync] WARNING: No M5 play URL configured!")

    # 4. Wait for M5 to buffer
    if buffer_delay > 0:
        time.sleep(buffer_delay)

    # 5. Animate mouth in a background thread
    stop_event = threading.Event()
    anim_thread = threading.Thread(
        target=animate_mouth,
        args=(link, amplitudes, FRAME_MS, stop_event),
        daemon=True,
    )
    anim_thread.stop_event = stop_event  # Attach for external cancellation
    anim_thread.start()

    return anim_thread


def wait_for_animation(thread: threading.Thread | None, timeout: float = 60):
    """Wait for a mouth animation thread to finish."""
    if thread is not None:
        thread.join(timeout=timeout)
