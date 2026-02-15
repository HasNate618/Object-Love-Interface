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
    """Monitor a GPIO limit switch state using RPi.GPIO."""

    def __init__(self, pin: int = 17, debounce_delay: float = 0.1):
        """
        Initialize limit switch monitoring.
        
        Args:
            pin: GPIO pin number (BCM mode)
            debounce_delay: Debounce delay in seconds
        
        Raises:
            ImportError: If RPi.GPIO is not available
        """
        if GPIO is None:
            raise ImportError("RPi.GPIO is required for GPIO limit switch support")
        
        self.pin = pin
        self.debounce_delay = debounce_delay
        self._prev_state = None
        self._state_change_time = None
        
        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Read initial state
        self._prev_state = GPIO.input(self.pin)

    def get_state(self) -> bool:
        """
        Get current limit switch state.
        
        Returns:
            True if switch is open (HIGH), False if closed (LOW)
        """
        return bool(GPIO.input(self.pin))

    def check_state_change(self) -> dict | None:
        """
        Check if the limit switch state has changed.
        Includes simple debouncing.
        
        Returns:
            dict with 'state' and 'timestamp' if changed, None otherwise
            state: True (open), False (closed)
        """
        current_state = self.get_state()
        current_time = time.time()
        
        if current_state != self._prev_state:
            # State changed, check if debounce time has passed
            if self._state_change_time is None:
                self._state_change_time = current_time
            elif (current_time - self._state_change_time) >= self.debounce_delay:
                # State confirmed after debounce
                self._prev_state = current_state
                self._state_change_time = None
                return {
                    'state': current_state,
                    'state_name': 'open' if current_state else 'closed',
                    'timestamp': current_time
                }
        else:
            # State is stable
            self._state_change_time = None
        
        return None

    def close(self):
        """Clean up GPIO resources."""
        GPIO.cleanup()
