"""Quick test: verify display + buzzer are working."""
import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
baud = 921600

print(f"Connecting to {port} @ {baud}...")
s = serial.Serial(port, baud, timeout=3)
time.sleep(2)

# Read boot messages
print("--- Boot messages ---")
while s.in_waiting:
    line = s.readline().decode("utf-8", errors="ignore").strip()
    if line:
        print(f"  {line}")

# Clear screen red
print("\nClearing screen to RED...")
s.write(b'{"cmd":"clear","color":"#FF0000"}\n')
time.sleep(1)
if s.in_waiting:
    print(f"  Response: {s.readline().decode("utf-8", errors="ignore").strip()}")

time.sleep(1)

# Clear screen green
print("Clearing screen to GREEN...")
s.write(b'{"cmd":"clear","color":"#00FF00"}\n')
time.sleep(1)
if s.in_waiting:
    print(f"  Response: {s.readline().decode("utf-8", errors="ignore").strip()}")

time.sleep(1)

# Clear screen blue
print("Clearing screen to BLUE...")
s.write(b'{"cmd":"clear","color":"#0000FF"}\n')
time.sleep(1)
if s.in_waiting:
    print(f"  Response: {s.readline().decode("utf-8", errors="ignore").strip()}")

# Beep
print("\nSending tone...")
s.write(b'{"cmd":"tone","freq":1000,"dur":300}\n')
time.sleep(0.5)
if s.in_waiting:
    print(f"  Response: {s.readline().decode("utf-8", errors="ignore").strip()}")

time.sleep(1)

# Clear to black
print("\nClearing to black...")
s.write(b'{"cmd":"clear","color":"#000000"}\n')
time.sleep(1)
if s.in_waiting:
    print(f"  Response: {s.readline().decode("utf-8", errors="ignore").strip()}")

s.close()
print("\nQuick test complete!")
