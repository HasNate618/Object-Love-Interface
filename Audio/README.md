# M5Stack Core Audio (WiFi Speaker)

This component runs on an M5Stack Core (gen1, ESP32) and exposes a small HTTP API for playing audio URLs over WiFi. It uses ESP8266Audio to decode MP3/WAV and outputs through the Core1 internal DAC (GPIO25/26).

## Hardware

- Device: M5Stack Core (gen1)
- Output: Internal DAC speaker path
- Network: WiFi (HTTP control)

## Firmware Layout

```
Audio/
├── m5core2_firmware/   # PlatformIO project (Core1-targeted)
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp
│       └── wifi_config.h
└── README.md
```

## Build + Flash

1. Edit WiFi credentials in [Audio/m5core2_firmware/src/wifi_config.h](m5core2_firmware/src/wifi_config.h).
2. Flash from PlatformIO:

```bash
cd Audio/m5core2_firmware
pio run --target upload --upload-port COM9
```

## HTTP API

The device listens on port 8082 (configurable in `wifi_config.h`).

### POST /play
Play an audio URL.

```json
{"url":"http://host:8080/audio/file.mp3","format":"mp3"}
```

### POST /stop
Stop playback.

### POST /volume
Set volume on a 0-10 scale.

```json
{"level":10}
```

### POST /tone
Simple speaker test (useful to verify audio path).

```json
{"freq":880,"duration":800}
```

### GET /status
Returns playback state and current URL.

```json
{"playing":true,"volume":10,"url":"http://...","ip":"10.x.x.x"}
```

## Notes

- The folder name is historical (`m5core2_firmware`), but the build targets Core1 hardware.
- Output uses `AudioOutputI2S(INTERNAL_DAC)` for Core1 speaker audio.
- `/play` is non-blocking; playback starts in the main loop to avoid HTTP timeouts.

## Quick Test

1. Start a local HTTP server in the Media folder:

```bash
cd Media
python -m http.server 8080
```

2. Trigger playback:

```python
import requests
requests.post("http://<core_ip>:8082/play", json={
    "url": "http://<host_ip>:8080/kittenstrike1-quothello-therequot-158832.mp3",
    "format": "mp3",
})
```

3. Use `/tone` if you only want to verify speaker output.
