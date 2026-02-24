"""
Servo Serial — Talk to the ESP32 servo controller over USB serial.

The ESP32 accepts two commands:
    S<angle>        Set servo angle (0 to 270)
    C<r>,<g>,<b>    Set LCD backlight colour

This module maps an interest level (0–10) to:
    - Love value for SenseCAP screen (0.0 – 1.0)
    - Servo angle for the arm (120 – 150)
        - Servo angle for the arm (120 – 150)

Usage:
    servo = ServoSerial("/dev/ttyUSB0")     # or "COM7", etc.
    servo.set_interest(7.5)                 # drives servo + returns love value
    servo.close()
"""

import serial
import time

# Servo angle range that maps to interest 0..10
SERVO_MIN = 120
SERVO_MAX = 150


class ServoSerial:
    """Persistent serial connection to the ESP32 servo board."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 1.0, init_angle: int = 135):
        self.port = port
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.5)  # Let ESP32 finish boot
        # Drain any boot messages
        while self.ser.in_waiting:
            self.ser.read(self.ser.in_waiting)
        print(f"  [servo] Connected to {port}")
        # Initialize servo to a known starting angle.
        self.send_servo(init_angle)
        print(f"  [servo] Init angle S{int(init_angle)}")

    # ------------------------------------------------------------------
    # Low-level commands
    # ------------------------------------------------------------------

    def send_servo(self, angle: int):
        """Send an S<angle> command (clamped to SERVO_MIN–SERVO_MAX)."""
        angle = max(SERVO_MIN, min(SERVO_MAX, int(angle)))
        cmd = f"S{angle}\n"
        self.ser.write(cmd.encode())
        self.ser.flush()

    def send_color(self, r: int, g: int, b: int):
        """Send a C<r>,<g>,<b> command."""
        cmd = f"C{r},{g},{b}\n"
        self.ser.write(cmd.encode())
        self.ser.flush()

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def interest_to_love(interest: float) -> float:
        """Map interest (0–10) → love value (0.0–1.0)."""
        return max(0.0, min(1.0, interest / 10.0))

    @staticmethod
    def interest_to_servo(interest: float) -> int:
        """Map interest (0–10) → servo angle (SERVO_MIN–SERVO_MAX)."""
        t = max(0.0, min(10.0, interest)) / 10.0
        return int(SERVO_MIN + t * (SERVO_MAX - SERVO_MIN))

    def set_interest(self, interest: float) -> float:
        """Apply interest (0–10) to servo and return love value (0.0–1.0)."""
        angle = self.interest_to_servo(float(interest))
        self.send_servo(angle)
        print(f"  [servo] interest={interest} -> angle={angle}")
        return self.interest_to_love(float(interest))

    # ------------------------------------------------------------------

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"  [servo] Closed {self.port}")
