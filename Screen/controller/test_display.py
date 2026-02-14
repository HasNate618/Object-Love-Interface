"""Test the new display firmware - sends clear color commands."""
import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
baud = 921600

print(f"Connecting to {port} @ {baud}...")
s = serial.Serial(port, baud, timeout=3)
time.sleep(1)
s.reset_input_buffer()

def send_and_read(cmd_bytes, label=""):
    print(f"  Sending: {label or cmd_bytes}")
    s.write(cmd_bytes)
    time.sleep(2)
    while s.in_waiting:
        line = s.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"  Response: {line}")

# Test color fills
for color, name in [("#FF0000", "RED"), ("#00FF00", "GREEN"), ("#0000FF", "BLUE"), ("#FFFFFF", "WHITE")]:
    send_and_read(f'{{"cmd":"clear","color":"{color}"}}\n'.encode(), f"Clear {name}")
    time.sleep(1)

# Tone
send_and_read(b'{"cmd":"tone","freq":1000,"dur":300}\n', "Tone 1kHz")

# Back to black
time.sleep(1)
send_and_read(b'{"cmd":"clear","color":"#000000"}\n', "Clear BLACK")

s.close()
print("\nTest complete! Did you see RED, GREEN, BLUE, WHITE flashes on the display?")
