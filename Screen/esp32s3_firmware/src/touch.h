/*
 * Capacitive Touch Driver for SenseCAP Indicator
 *
 * Touch controller on I2C bus (shared with TCA9535).
 * Auto-detects FT6336U (0x38) and CST816S (0x15/0x14).
 * Touch panel reset is handled by display_init() (TCA9535 pin 7).
 *
 * Also supports the physical user button on GPIO38 as a fallback.
 */

#pragma once

#include <Arduino.h>

struct TouchPoint {
    int  x;
    int  y;
    bool touched;
};

// Initialize touch controller. Call after display_init() (which resets TP).
// Returns true if touch IC found on I2C.
bool touch_init();

// Read current touch state. Non-blocking.
TouchPoint touch_read();

// Initialize the physical user button (GPIO38, active low).
void button_init();

// Read physical button state (debounced). Returns true on press edge.
bool button_pressed();

// Returns true while button is held down (after debounce).
bool button_held();

// Button edge events: call in loop(), returns 1=just pressed, -1=just released, 0=no change
int button_edge();
