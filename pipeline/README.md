# Pipeline (Camera -> Gemini -> ElevenLabs -> Display + Audio)

This folder contains the host-side pipeline that captures a camera frame, sends it to Gemini for a caption, generates speech via ElevenLabs, then plays the audio on the M5Stack Core speaker and shows the image on the SenseCAP display.

## Components

- [pipeline/orchestrator.py](orchestrator.py)
  - Captures a webcam frame (OpenCV)
  - Sends image + prompt to Gemini
  - Converts response to speech via ElevenLabs
  - Sends image to SenseCAP (serial)
  - Sends audio to M5Stack via the audio server

- [pipeline/audio_server.py](audio_server.py)
  - Flask server that stores audio files and serves them to the M5Stack
  - Convenience endpoint `/upload_and_play` for the orchestrator

- [pipeline/requirements.txt](requirements.txt)
  - Python dependencies for the pipeline

## Environment Variables

Set these before running:

- `GEMINI_API_KEY`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID` (optional, default Rachel)
- `M5CORE2_IP` (Core1 IP address; name kept for compatibility)
- `SENSECAP_PORT` (default `COM6` or `/dev/ttyUSB0`)
- `AUDIO_SERVER_URL` (default `http://localhost:8080`)
- `GEMINI_MODEL` (default `gemini-2.0-flash`)

## Install

```bash
pip install -r pipeline/requirements.txt
```

## Run Audio Server

```bash
python pipeline/audio_server.py
```

The server listens on port 8080 and stores audio files in `pipeline/audio_files/`.

## Run Orchestrator

Single run:

```bash
python pipeline/orchestrator.py --once
```

Continuous loop:

```bash
python pipeline/orchestrator.py --loop --interval 10
```

## Network Notes

- The M5Stack must be able to reach the host machine running `audio_server.py`.
- `audio_server.py` auto-detects the host LAN IP when serving audio URLs.
- If the M5Stack is on a different subnet, use a reachable host IP and adjust firewall rules.
