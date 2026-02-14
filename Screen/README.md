# SenseCAP Indicator Serial Display Controller

Control the SenseCAP Indicator D1101 display and buzzer in real-time from a Raspberry Pi (or any host) via USB serial.

## Architecture

```
┌──────────────┐     USB Serial     ┌──────────────────────────────────────┐
│  Raspberry Pi│◄──────────────────►│  SenseCAP Indicator                  │
│  (or PC)     │   JSON commands    │  ┌──────────┐    UART   ┌─────────┐ │
│              │                    │  │ ESP32-S3 │◄────────►│ RP2040  │ │
│  Python      │                    │  │ (Display)│           │ (Buzzer)│ │
│  Controller  │                    │  └──────────┘           └─────────┘ │
└──────────────┘                    └──────────────────────────────────────┘
```

- **ESP32-S3**: Drives the 4" 480x480 LCD via LVGL, receives serial commands
- **RP2040**: Controls the built-in buzzer, receives audio commands from ESP32-S3 via internal UART
- **Python Controller**: Sends JSON commands over USB serial

## Project Structure

```
Screen/
├── esp32s3_firmware/      # PlatformIO project for ESP32-S3 (display)
├── rp2040_firmware/       # PlatformIO project for RP2040 (buzzer)
├── controller/            # Python scripts for host control
│   ├── sensecap_controller.py   # Controller API library
│   └── test_live_update.py      # Demo / test script
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

### 4. Run the Test Script
```bash
python test_live_update.py COM5    # Windows - use your actual port
python test_live_update.py /dev/ttyACM0  # Linux/Pi
```

## Serial Protocol

Commands are JSON objects terminated by `\n`. Each command receives a JSON response.

### Display Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `clear` | `color` | Clear screen with background color |
| `text` | `id, x, y, text, color, size` | Create/update text label |
| `rect` | `id, x, y, w, h, color, radius` | Create/update rectangle |
| `bar` | `id, x, y, w, h, value, color` | Create/update progress bar (0-100) |
| `arc` | `id, x, y, r, start, end, color, width` | Create/update arc gauge |
| `remove` | `id` | Remove widget by ID |
| `bl` | `level` | Set backlight (0-100) |
| `tone` | `freq, dur` | Play buzzer tone (Hz, ms) |

### Example Commands
```json
{"cmd":"clear","color":"#000000"}
{"cmd":"text","id":"t1","x":100,"y":50,"text":"Hello!","color":"#FFFFFF","size":24}
{"cmd":"bar","id":"b1","x":20,"y":200,"w":440,"h":30,"value":75,"color":"#00FF00"}
{"cmd":"tone","freq":1000,"dur":500}
```

### Response Format
```json
{"status":"ok"}
{"status":"error","msg":"unknown command"}
{"status":"ready"}
```

## Pin Reference (SenseCAP Indicator D1101)

### ESP32-S3 GPIOs
| Function | GPIO | Notes |
|----------|------|-------|
| LCD Backlight | 45 | Active HIGH, shared with RGB data after init |
| LCD SPI CS | 15 | 3-wire SPI for ST7701S init |
| LCD SPI SCK | 16 | 3-wire SPI clock |
| LCD SPI SDA | 17 | Shared with LCD DE after init |
| LCD PCLK | 9 | RGB pixel clock |
| LCD HSYNC | 46 | Horizontal sync |
| LCD VSYNC | 3 | Vertical sync |
| LCD DE | 17 | Data enable |
| UART TX (→RP2040) | 19 | Internal UART |
| UART RX (←RP2040) | 20 | Internal UART |

### RP2040 GPIOs
| Function | GPIO |
|----------|------|
| Buzzer | 19 |
| UART TX (→ESP32) | 20 |
| UART RX (←ESP32) | 21 |

## Troubleshooting

- **No display**: Check ST7701S init sequence pin definitions in `pins.h` match your hardware revision
- **Garbled display**: Adjust RGB timing parameters in `display.cpp`
- **No serial response**: Ensure you're connected to the ESP32-S3 COM port (not RP2040)
- **No audio**: Flash RP2040 firmware separately; check UART wiring
