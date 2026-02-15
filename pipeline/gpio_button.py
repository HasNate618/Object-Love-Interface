"""
GPIO Reset Button & Limit Switch — Listen for Pi GPIO button presses.

Wiring:
  Reset Button (2-pin button):
    - One leg to GPIO pin (default GPIO17, physical pin 11)
    - One leg to GND (physical pin 6)
  
  Limit Switch (3-state switch):
    - One leg to GPIO pin (default GPIO17, physical pin 11)
    - One leg to GND (physical pin 6)
    - Uses internal pull-up, reads HIGH (open) and LOW (closed)
"""

from __future__ import annotations
import time

try:
    from gpiozero import Button
except ImportError:  # Allows running on non-Pi systems
    Button = None

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class GpioResetButton:
    """Latch a reset request when the GPIO button is pressed."""

    def __init__(self, pin: int = 17, bounce_time: float = 0.1):
        if Button is None:
            raise ImportError("gpiozero is required for GPIO button support")
        self._flag = False
        self._button = Button(pin, pull_up=True, bounce_time=bounce_time)
        self._button.when_pressed = self._on_press

    def _on_press(self):
        self._flag = True

    def consume_reset(self) -> bool:
        """Return True once per press, then clear the flag."""
        if self._flag:
            self._flag = False
            return True
        return False

    def close(self):
        if self._button:
            self._button.close()


class GpioLimitSwitch:
    """Monitor a GPIO limit switch using interrupt-based edge detection.

    Runs independently of the main loop — RPi.GPIO fires a callback on
    a background thread whenever the switch opens or closes.
    """

    def __init__(
        self,
        pin: int = 17,
        bounce_time_ms: int = 200,
        on_open=None,
        on_close=None,
    ):
        """
        Args:
            pin:            GPIO pin number (BCM mode).
            bounce_time_ms: Software debounce in milliseconds.
            on_open:        Optional callback when switch opens  (HIGH).
            on_close:       Optional callback when switch closes (LOW).
        """
        if GPIO is None:
            raise ImportError("RPi.GPIO is required for GPIO limit switch support")

        self.pin = pin
        self._on_open = on_open
        self._on_close = on_close
        self._closed = False          # current latched state
        self._state_changed = False   # flag for poll-style consumers

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Read initial state (LOW = closed / pressed)
        initial = GPIO.input(self.pin)
        self._closed = (initial == 0)
        print(f"  [limit_switch] Initial state: {'closed' if self._closed else 'open'}")

        # Register interrupt on both edges — runs on a background thread
        GPIO.add_event_detect(
            self.pin,
            GPIO.BOTH,
            callback=self._edge_callback,
            bouncetime=bounce_time_ms,
        )

    # ---- interrupt handler (runs on RPi.GPIO background thread) ----------
    def _edge_callback(self, channel):
        state = GPIO.input(self.pin)
        now_closed = (state == 0)

        if now_closed == self._closed:
            return  # duplicate after bounce filter

        self._closed = now_closed
        self._state_changed = True
        label = "closed" if now_closed else "open"
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [limit_switch] Switch {label}")

        if now_closed and self._on_close:
            self._on_close()
        elif not now_closed and self._on_open:
            self._on_open()

    # ---- public API ------------------------------------------------------
    @property
    def is_closed(self) -> bool:
        """True when the limit switch is currently closed (pressed)."""
        return self._closed

    @property
    def is_open(self) -> bool:
        """True when the limit switch is currently open (released)."""
        return not self._closed

    def consume_state_change(self) -> bool:
        """Return True once per state change, then clear.  Poll-friendly."""
        if self._state_changed:
            self._state_changed = False
            return True
        return False

    def close(self):
        """Remove edge detection and clean up GPIO."""
        GPIO.remove_event_detect(self.pin)
        GPIO.cleanup(self.pin)
