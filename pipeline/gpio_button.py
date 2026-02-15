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
import threading
from collections import deque

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
    """
    Monitor a GPIO limit switch state in a background thread (async/independent).
    
    Runs continuously in a separate thread without blocking the main pipeline.
    State changes are queued and can be polled non-blockingly.
    """

    def __init__(self, pin: int = 17, debounce_delay: float = 0.1, 
                 on_opened=None, on_closed=None):
        """
        Initialize limit switch monitoring with background thread.
        
        Args:
            pin: GPIO pin number (BCM mode)
            debounce_delay: Debounce delay in seconds
            on_opened: Optional callback(timestamp) when switch opens
            on_closed: Optional callback(timestamp) when switch closes
        
        Raises:
            ImportError: If RPi.GPIO is not available
        """
        if GPIO is None:
            raise ImportError("RPi.GPIO is required for GPIO limit switch support")
        
        self.pin = pin
        self.debounce_delay = debounce_delay
        self.on_opened = on_opened
        self.on_closed = on_closed
        
        # State tracking
        self._current_state = None
        self._state_change_time = None
        self._state_queue = deque(maxlen=10)  # Keep last 10 state changes
        self._state_lock = threading.Lock()
        
        # Background thread control
        self._running = True
        self._monitor_thread = None
        
        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Read initial state
        self._current_state = GPIO.input(self.pin)
        
        # Start monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _monitor_loop(self):
        """
        Background thread loop: continuously monitor switch and queue state changes.
        Runs independently and doesn't block the main pipeline.
        """
        prev_state = self._current_state
        debounce_start = None
        
        while self._running:
            current_state = GPIO.input(self.pin)
            current_time = time.time()
            
            if current_state != prev_state:
                # Potential state change detected
                if debounce_start is None:
                    debounce_start = current_time
                elif (current_time - debounce_start) >= self.debounce_delay:
                    # State confirmed after debounce
                    prev_state = current_state
                    debounce_start = None
                    
                    # Queue the state change
                    state_info = {
                        'state': bool(current_state),
                        'state_name': 'open' if current_state else 'closed',
                        'timestamp': current_time
                    }
                    
                    with self._state_lock:
                        self._current_state = current_state
                        self._state_queue.append(state_info)
                    
                    # Trigger callbacks if provided
                    if current_state and self.on_opened:
                        try:
                            self.on_opened(current_time)
                        except Exception as e:
                            print(f"[limit_switch] on_opened callback error: {e}")
                    elif not current_state and self.on_closed:
                        try:
                            self.on_closed(current_time)
                        except Exception as e:
                            print(f"[limit_switch] on_closed callback error: {e}")
            else:
                # State is stable
                debounce_start = None
            
            # Polling interval (short to be responsive, but not too fast)
            time.sleep(0.01)

    def get_state(self) -> bool:
        """
        Get current limit switch state without blocking.
        
        Returns:
            True if switch is open (HIGH), False if closed (LOW)
        """
        with self._state_lock:
            return bool(self._current_state)

    def get_state_changes(self) -> list[dict]:
        """
        Retrieve all queued state changes since last call.
        Non-blocking; cleared after retrieval.
        
        Returns:
            List of state change dicts with 'state', 'state_name', 'timestamp'
        """
        with self._state_lock:
            changes = list(self._state_queue)
            self._state_queue.clear()
        return changes

    def consume_state_change(self) -> dict | None:
        """
        Pop the next state change from the queue (like reset button's consume_reset).
        Non-blocking; returns None if no changes pending.
        
        Returns:
            Single state change dict or None
        """
        with self._state_lock:
            if self._state_queue:
                return self._state_queue.popleft()
        return None

    def close(self):
        """Stop monitoring thread and clean up GPIO resources."""
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        GPIO.cleanup()

