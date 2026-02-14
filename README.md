# Object-Love-Interface

A multi-device system that pairs a SenseCAP Indicator display with an M5Stack Core speaker, driven by a camera-based AI pipeline.

## Components

- **SenseCAP Indicator (Display + Buzzer)**
  - ESP32-S3 firmware renders JPEGs to the 480x480 LCD
  - RP2040 firmware drives the buzzer
  - Python controller sends images and buzzer commands over serial
  - See [Screen/README.md](Screen/README.md)

- **M5Stack Core (Audio over WiFi)**
  - Core1 firmware receives audio URLs and plays via internal DAC
  - HTTP control API: `/play`, `/stop`, `/volume`, `/status`, `/tone`
  - See [Audio/README.md](Audio/README.md)

- **AI Pipeline (Camera -> Gemini -> ElevenLabs)**
  - Captures webcam frames, asks Gemini, generates speech
  - Sends images to SenseCAP and audio to M5Stack
  - See [pipeline/README.md](pipeline/README.md)

## Quick Start

1. Flash the SenseCAP ESP32-S3 + RP2040 firmware
2. Flash the M5Stack Core firmware
3. Run the audio server and orchestrator

Each component has detailed setup steps in its README.
