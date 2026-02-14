# Plan: Full Migration to Raspberry Pi

**Summary**: Migrate the complete Object-Love-Interface system from Windows laptop to Raspberry Pi. This includes the Node.js server (image_to_voice), Python pipeline scripts, and all connected hardware (Brio webcam with mic, SenseCAP Indicator via USB). Only the M5Core1 audio player remains on WiFi at its current IP. The primary change is updating `HOST_IP` in .env to the RPi's DHCP address and changing all serial port references from `COM6` to `/dev/ttyUSB0` or `/dev/ttyACM0`. This consolidates everything on one device, eliminating cross-machine HTTP calls and simplifying the deployment.

**Decision**: Full migration chosen over partial migration because keeping Python on Windows while moving Node to RPi would create audio file serving complexity (M5 fetching from RPi but Python generating on Windows).

## Steps

1. **Prepare RPi System**
   - Install Node.js 18+: `curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install nodejs`
   - Install Python 3.8+ (usually pre-installed): `python3 --version`
   - Install system dependencies: `sudo apt-get update && sudo apt-get install -y ffmpeg python3-pip git`
   - Add user to dialout group for serial access: `sudo usermod -a -G dialout $USER` then logout/login or reboot

2. **Transfer Project Files**
   - Copy entire project to RPi using git: `git clone <repo_url>` OR rsync from Windows: `rsync -avz /path/to/Object-Love-Interface/ pi@<rpi_ip>:~/Object-Love-Interface/`
   - Copy .env file (contains API keys): Manually transfer since it's gitignored
   - Verify all files present: `ls -la ~/Object-Love-Interface/`

3. **Install Dependencies**
   - Node packages: `cd ~/Object-Love-Interface/image_to_voice && npm install`
   - Python packages: `cd ~/Object-Love-Interface && pip3 install -r pipeline/requirements.txt`
   - Test ffmpeg: `ffmpeg -version` (should show version from 2014+)

4. **Configure Network Settings**
   - Find RPi IP: `hostname -I` (first IP is LAN address, e.g., `10.216.64.XXX`)
   - Edit .env line 9: Change `HOST_IP=10.216.64.90` to `HOST_IP=<RPi_IP_from_above>`
   - Keep other values: `M5CORE2_URL=http://10.216.64.147:8082/play` unchanged (M5 stays at same IP)
   - Verify: `cat image_to_voice/.env | grep HOST_IP`

5. **Connect Hardware to RPi**
   - Unplug Brio webcam from Windows, connect to RPi USB port
   - Unplug SenseCAP Indicator USB from Windows (COM6), connect to RPi USB port
   - Wait 5 seconds for devices to enumerate
   - Check serial ports: `ls -l /dev/tty* | grep USB` (look for `/dev/ttyUSB0` or `/dev/ttyACM0`)
   - Test webcam: `python3 -c "import cv2; cap=cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'FAIL')"`
   - Test mic: `python3 -c "import pyaudio; pa=pyaudio.PyAudio(); print([pa.get_device_info_by_index(i)['name'] for i in range(pa.get_device_count())])"`

6. **Update Python Script Defaults** (Optional - can use command-line args instead)
   - conversation.py line 365: Change default `port="COM6"` to `port="/dev/ttyUSB0"` if desired
   - date_pipeline.py line 463: Change default `"COM6"` to `"/dev/ttyUSB0"` if desired
   - OR always pass `--port /dev/ttyUSB0` when running scripts (recommended for flexibility)

7. **Test Node.js Server**
   - Start server: `cd ~/Object-Love-Interface/image_to_voice && node index.js`
   - Verify console output shows: `Detected LAN IP: <RPi_IP>`, `Listening on 0.0.0.0:3000`
   - Check audio host URL matches RPi IP: Should show `http://<RPi_IP>:3000`
   - Test from Windows browser: `http://<RPi_IP>:3000` (should see "image_to_voice server")
   - Leave running in terminal for integration test

8. **Test Python Pipeline**
   - Open new SSH session or terminal tab on RPi
   - Run date pipeline: `cd ~/Object-Love-Interface && python3 pipeline/date_pipeline.py --port /dev/ttyUSB0 --camera 0 --server http://localhost:3000`
   - Verify SenseCAP display shows webcam feed
   - Press physical "Date ♥" button on SenseCAP
   - Check for: Image capture → personality generation → TTS audio → M5 playback → face display → mouth sync
   - Monitor Node terminal for: POST /generate-personality, TTS generation, audio file creation

9. **Test Voice Conversation**
   - In Python terminal, hold SenseCAP button to record voice
   - Release button, verify: STT transcription → POST /respond → TTS generation → M5 playback + mouth sync
   - Check timing: Mouth animation should stop ~0.7x through audio playback
   - Test multiple interactions to verify stability

10. **Network Verification from M5 Perspective**
    - Confirm M5Core1 can reach RPi: From another device on `espTest` WiFi, test `curl http://<RPi_IP>:3000/tmp/` 
    - Check M5 serial monitor (if accessible): Should show successful HTTP GET for audio files
    - If M5 restarts or fails to play: Check WiFi routing, ensure RPi and M5 on same subnet or routable networks

## Verification

- **Functionality tests**:
  - Capture image → personality generation completes in <10s
  - TTS audio files appear in `~/Object-Love-Interface/image_to_voice/tmp/` directory
  - M5Core1 plays audio clearly without restarts
  - Mouth animation syncs with audio and stops at ~70% of audio duration
  - Recording voice → STT → AI response cycle works end-to-end
  
- **Debug commands**:
  - Check serial port: `python3 -m serial.tools.list_ports`
  - List cameras: `v4l2-ctl --list-devices` or `ls /dev/video*`
  - Test Node API: `curl http://localhost:3000` from RPi
  - Monitor M5 connectivity: `ping 10.216.64.147` from RPi
  - Check audio files: `ls -lh ~/Object-Love-Interface/image_to_voice/tmp/`

- **Error checking**:
  - If "ENOENT ./tmp/" error: Node should auto-create, check file permissions with `ls -ld image_to_voice/tmp/`
  - If M5 doesn't play: Check Node console for POST /play response status code
  - If mouth doesn't move: Check Python console for `[mouth_sync]` debug output
  - If camera fails: Try `--camera 1` or check `DATE_CAMERA_INDEX` environment variable
  - If mic not found: Check `pyaudio.PyAudio().get_device_count()` and adjust `MIC_NAME` pattern

## Decisions

- **Chose full migration over partial**: Moving only Node.js would require Python to generate files on Windows but M5 to fetch from RPi, creating unnecessary network complexity and latency
- **Using command-line args for serial port**: Rather than hardcoding `/dev/ttyUSB0` in Python files, pass `--port` argument for flexibility (device name may vary as ttyUSB0 vs ttyACM0)
- **Keeping localhost for Python→Node**: Since both run on RPi, Python can use `http://localhost:3000` instead of RPi IP (reduces config complexity)
- **No systemd autostart initially**: Manual start gives flexibility for debugging; can add systemd services later if stable
- **DHCP acceptable for testing**: Static IP recommended for production but DHCP sufficient for initial migration; HOST_IP in .env can be updated later if IP changes

---

## Architecture Overview

### Current State (Windows Laptop)
- **Windows Laptop (10.216.64.90)**
  - Node.js server on port 3000
  - Python pipeline scripts
  - Brio webcam (USB) for video + microphone
  - SenseCAP Indicator (COM6 USB serial) for display + buttons
- **M5Core1 (10.216.64.147:8082)**
  - Audio player firmware
  - Fetches MP3 from laptop via HTTP
- **Network**: All on WiFi "espTest"

### Target State (Raspberry Pi)
- **Raspberry Pi (<DHCP_IP>)**
  - Node.js server on port 3000
  - Python pipeline scripts
  - Brio webcam (USB) for video + microphone
  - SenseCAP Indicator (/dev/ttyUSB0) for display + buttons
- **M5Core1 (10.216.64.147:8082)**
  - No changes to firmware
  - Fetches MP3 from RPi instead
- **Network**: All on WiFi "espTest"

### Communication Flows After Migration
```
┌─────────────────────────────────────────┐
│         Raspberry Pi (<RPi_IP>)         │
│  ┌──────────┐        ┌──────────────┐  │
│  │ Node.js  │◄───────┤ Python       │  │
│  │ :3000    │ HTTP   │ - capture    │  │
│  │          │        │ - STT        │  │
│  │ Serves   │        │ - mouth_sync │  │
│  │ /tmp/*.  │        └──────┬───────┘  │
│  │ mp3      │               │          │
│  └────┬─────┘               │          │
│       │                     │          │
│       │ POST /play          │ Serial   │
│       │ {url:audio}         │ USB      │
│       ▼                     ▼          │
└───────┼─────────────────────┼──────────┘
        │                     │
        │ WiFi                │ USB
        ▼                     ▼
  ┌──────────┐    ┌───────────────────┐
  │ M5Core1  │    │ SenseCAP Display  │
  │ :8082    │    │ /dev/ttyUSB0      │
  │          │    │                   │
  │ HTTP GET │    │ LCD + Touch       │
  │ MP3 from │    │ Button Events     │
  │ RPi      │    │ Mouth Animation   │
  └──────────┘    └───────────────────┘
```

---

## Files Requiring Updates

### Critical Changes

**image_to_voice/.env** (Line 9)
```diff
- HOST_IP=10.216.64.90
+ HOST_IP=<RPi_IP>
```

### Optional Changes (Can use CLI args instead)

**pipeline/conversation.py** (Line 365)
```diff
- def main(port="COM6", mic_device=None, server_url=None):
+ def main(port="/dev/ttyUSB0", mic_device=None, server_url=None):
```

**pipeline/date_pipeline.py** (Line 463)
```diff
- parser.add_argument("--port", default="COM6", help="SenseCAP serial port")
+ parser.add_argument("--port", default="/dev/ttyUSB0", help="SenseCAP serial port")
```

**Alternative**: Always use `--port /dev/ttyUSB0` in commands (recommended)

---

## Rollback Procedure

If migration fails or needs to revert:

1. Stop all services on RPi (Ctrl+C in terminals)
2. Disconnect Brio webcam from RPi, reconnect to Windows
3. Disconnect SenseCAP from RPi, reconnect to Windows (COM6)
4. On Windows: Edit `.env` line 9 back to `HOST_IP=10.216.64.90`
5. On Windows: Restart Node server: `cd image_to_voice && node index.js`
6. On Windows: Run Python: `python pipeline/date_pipeline.py --port COM6 --camera 1 --server http://localhost:3000`
7. System returns to original working state

**No changes to M5Core1 firmware required for rollback.**

---

## Troubleshooting Guide

### Serial Port Issues
- **Symptom**: "Permission denied" on `/dev/ttyUSB0`
- **Fix**: Add user to dialout group: `sudo usermod -a -G dialout $USER` then logout/login
- **Alt Fix**: Run with sudo (not recommended for production)

### Camera Not Found
- **Symptom**: `cv2.VideoCapture(0).isOpened()` returns False
- **Fix**: Try different index: `--camera 1` or `--camera 2`
- **Check**: `v4l2-ctl --list-devices` to see available cameras
- **Set env**: `export DATE_CAMERA_INDEX=1` if needed

### Microphone Not Detected
- **Symptom**: "No external mic found" warning
- **Fix**: List devices: `python3 -c "import pyaudio; pa=pyaudio.PyAudio(); [print(i, pa.get_device_info_by_index(i)) for i in range(pa.get_device_count())]"`
- **Update**: Set `MIC_NAME` env var to match device name pattern

### M5 Cannot Reach RPi
- **Symptom**: M5Core1 restarts or audio doesn't play
- **Check**: From device on espTest WiFi: `curl http://<RPi_IP>:3000/`
- **Fix**: Ensure RPi on same subnet or routable network
- **Debug**: Check RPi firewall: `sudo ufw status` (disable if needed for testing)

### ffmpeg Errors
- **Symptom**: "Decoding failed. ffmpeg returned error code: 1"
- **Fix**: Install ffmpeg: `sudo apt-get install ffmpeg`
- **Check**: `which ffmpeg` should return `/usr/bin/ffmpeg`

### Node Server Won't Start
- **Symptom**: Port 3000 already in use
- **Fix**: Kill existing process: `sudo lsof -ti:3000 | xargs kill -9`
- **Alt Port**: Set `PORT=3001` in .env

### TTS Files Not Created
- **Symptom**: "ENOENT: no such file or directory './tmp/audio_*.mp3'"
- **Fix**: Node should auto-create, check: `ls -ld ~/Object-Love-Interface/image_to_voice/tmp/`
- **Manual**: `mkdir -p ~/Object-Love-Interface/image_to_voice/tmp`

---

## Environment Variables Reference

### Node.js (.env file)
```bash
# API Keys (copy from Windows)
GEMINI_API_KEY="..."
ELEVENLABS_API_KEY="..."

# Network (UPDATE THIS)
HOST_IP=<RPi_IP>              # ← REQUIRED CHANGE

# M5Core1 (no change)
M5CORE2_URL=http://10.216.64.147:8082/play
M5_PLAY_URL=http://10.216.64.147:8082/play

# Server (no change)
IMAGE_TO_VOICE_URL="http://localhost:3000"
PORT=3000
```

### Python (shell exports - optional)
```bash
# If not using command-line args
export IMAGE_TO_VOICE_URL="http://localhost:3000"  # Same machine
export M5_PLAY_URL="http://10.216.64.147:8082/play"
export SENSECAP_PORT="/dev/ttyUSB0"
export DATE_CAMERA_INDEX=0
export MIC_NAME="Brio"  # Or pattern from pyaudio device list
```

---

## Post-Migration Validation Checklist

- [ ] RPi Node server starts without errors
- [ ] Console shows correct RPi IP address
- [ ] Windows can access `http://<RPi_IP>:3000` via browser
- [ ] SenseCAP displays webcam feed when Python runs
- [ ] Pressing Date button triggers image capture
- [ ] Gemini personality generation completes
- [ ] TTS audio file appears in tmp/ directory
- [ ] M5Core1 plays audio without restarting
- [ ] SenseCAP face animation displays correctly
- [ ] Mouth sync animation matches audio timing
- [ ] Button hold records voice successfully
- [ ] STT transcription appears in console
- [ ] AI response generates and speaks
- [ ] Full conversation loop works end-to-end
- [ ] System stable after 5+ interaction cycles

---

## Future Enhancements (Post-Migration)

### Systemd Services (if auto-start desired)

**Node.js Service**: `/etc/systemd/system/image-to-voice.service`
```ini
[Unit]
Description=Image to Voice Node Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Object-Love-Interface/image_to_voice
EnvironmentFile=/home/pi/Object-Love-Interface/image_to_voice/.env
ExecStart=/usr/bin/node index.js
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Python Pipeline Service**: `/etc/systemd/system/date-pipeline.service`
```ini
[Unit]
Description=Date Pipeline
After=network.target image-to-voice.service
Requires=image-to-voice.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Object-Love-Interface
ExecStart=/usr/bin/python3 pipeline/date_pipeline.py --port /dev/ttyUSB0 --camera 0 --server http://localhost:3000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable image-to-voice
sudo systemctl enable date-pipeline
sudo systemctl start image-to-voice
sudo systemctl start date-pipeline
```

### Static IP Configuration
If DHCP causes issues, assign static IP in `/etc/dhcpcd.conf`:
```
interface wlan0
static ip_address=10.216.64.XX/24
static routers=10.216.64.1
static domain_name_servers=8.8.8.8
```

### Performance Monitoring
```bash
# CPU/Memory usage
htop

# Network traffic
sudo iftop -i wlan0

# Service logs
sudo journalctl -u image-to-voice -f
sudo journalctl -u date-pipeline -f
```
