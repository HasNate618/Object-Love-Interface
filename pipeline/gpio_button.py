"""
GPIO Reset Button — Listen for a Pi GPIO button press.

Wiring (2-pin button):
  - One leg to GPIO pin (default GPIO17, physical pin 11)
  - One leg to GND (physical pin 6)

Uses internal pull-up, so the input reads HIGH and goes LOW on press.
"""

from __future__ import annotations

try:
    from gpiozero import Button
except ImportError:  # Allows running on non-Pi systems
    Button = None


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
