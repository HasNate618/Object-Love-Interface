#!/usr/bin/env python3
"""
Quick test to monitor serial output and touch events from SenseCAP.
"""
import serial
import time
import sys


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
    
    print(f"Connecting to {port}...")
    ser = serial.Serial(port, 921600, timeout=0.1)
    time.sleep(2)  # Wait for serial to stabilize
    
    # Flush any old data
    ser.reset_input_buffer()
    
    print("Monitoring serial output. Touch the screen...")
    print("Press Ctrl+C to exit.\n")
    
    try:
        while True:
            if ser.in_waiting:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    print(line)
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nExiting.")
        ser.close()


if __name__ == "__main__":
    main()
