# SenseCAP Indicator Display + Buzzer Control

Control the SenseCAP Indicator D1101 display and buzzer in real time from a Raspberry Pi (or any host) via USB serial.

## Architecture

```
┌──────────────┐     USB Serial     ┌──────────────────────────────────────┐
│  Raspberry Pi│◄──────────────────►│  SenseCAP Indicator                  │
│  (or PC)     │   JSON commands    │  ┌──────────┐    UART   ┌─────────┐ │
│              │                    │  │ ESP32-S3 │◄────────►│ RP2040  │ │
│  Python      │                    │  │ (Display)│           │ (Buzzer)│ │
│  Controller  │                    │  └──────────┘           └─────────┘ │tt
└──────────────┘                    └──────────────────────────────────────┘
```

- **ESP32-S3**: Drives the 4" 480x480 LCD via direct RGB panel, decodes JPEGs
- **RP2040**: Controls the built-in buzzer, receives commands via internal UART
- **Python Controller**: Sends JSON commands and JPEGs over USB serial

## Project Structure

```
Screen/
├── esp32s3_firmware/      # PlatformIO project for ESP32-S3 (display)
├── rp2040_firmware/       # PlatformIO project for RP2040 (buzzer)
├── controller/            # Python scripts for host control
│   ├── sensecap_controller.py   # Controller API library
│   ├── test_display.py          # RGB color cycle test
│   ├── test_image.py            # JPEG test pattern
│   └── quick_test.py            # Short smoke test
└── README.md
```

## Setup

### Prerequisites
- [PlatformIO](https://platformio.org/) (CLI or VS Code extension)
- Python 3.8+ with `pyserial`
- USB-C cable

### 1. Flash RP2040 Firmware (Buzzer)
```bash
cd Screen/rp2040_firmware
pio run --target upload
```
**Note:** To enter RP2040 bootloader mode, hold the BOOT button while pressing RESET on the SenseCAP Indicator.

### 2. Flash ESP32-S3 Firmware (Display)
```bash
cd Screen/esp32s3_firmware
pio run --target upload
```
**Note:** To enter ESP32-S3 download mode, hold the BOOT button while pressing RESET. The ESP32-S3 appears as a separate COM port from the RP2040.

### 3. Install Python Dependencies
```bash
cd Screen/controller
pip install -r requirements.txt
```

### 4. Run a Test Script
```bash
python test_display.py COM6           # Windows - use your actual port
python test_image.py /dev/ttyACM0     # Linux/Pi
```

## Serial Protocol

Commands are JSON objects terminated by `\n`. Each command receives a JSON response.

### Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `image` | `len` | Start JPEG transfer (bytes). Device replies `{"status":"ready"}` before raw bytes are sent. |
| `clear` | `color` | Fill screen with background color (hex). |
| `tone` | `freq, dur` | Play buzzer tone (Hz, ms) via RP2040. |
| `melody` | `notes` | Play comma-separated `freq:dur` pairs. |
| `stop` | - | Stop buzzer. |
| `bl` | `on` | Backlight control (true/false). |

### JPEG Transfer Flow

1. Send header command:
```json
{"cmd":"image","len":123456}
```
2. Wait for:
```json
{"status":"ready"}
```
3. Send raw JPEG bytes.
4. Device responds:
```json
{"status":"ok"}
```

### Example Commands
```json
{"cmd":"clear","color":"#000000"}
{"cmd":"tone","freq":1000,"dur":500}
{"cmd":"melody","notes":"440:200,554:200,659:400"}
{"cmd":"bl","on":true}
```

### Response Format
```json
{"status":"ok"}
{"status":"error","msg":"unknown command"}
{"status":"ready"}
```

## Pin Reference (SenseCAP Indicator D1101)

### ESP32-S3 GPIOs (from official Seeed SDK)
| Function | GPIO | Notes |
|----------|------|-------|
| I2C SDA | 39 | Shared with TCA9535 + touch |
| I2C SCL | 40 | Shared with TCA9535 + touch |
| LCD SPI CLK | 41 | 3-wire SPI for ST7701S init |
| LCD SPI MOSI | 48 | 3-wire SPI for ST7701S init |
| LCD VSYNC | 17 | RGB panel |
| LCD HSYNC | 16 | RGB panel |
| LCD DE | 18 | RGB panel |
| LCD PCLK | 21 | 18 MHz pixel clock |
| LCD Backlight | 45 | Active HIGH |
| RGB Data D0..D15 | 15..0 | RGB565 mapping |
| UART TX (→RP2040) | 19 | Internal UART |
| UART RX (←RP2040) | 20 | Internal UART |

### RP2040 GPIOs
| Function | GPIO |
|----------|------|
| Buzzer | 19 |
| UART TX (→ESP32) | 20 |
| UART RX (←ESP32) | 21 |

## Troubleshooting

- **No display**: Verify ST7701S init and pin mapping in `pins.h`.
- **Garbled colors**: Check RGB timing parameters in `display.cpp`.
- **No serial response**: Ensure you are on the ESP32-S3 COM port (CH340).
- **No buzzer**: Flash RP2040 firmware separately and confirm UART wiring.
