/*
 * Capacitive Touch Driver - Implementation
 *
 * FT6336U registers (subset):
 *   0x00: Device Mode
 *   0x02: Number of touch points (bits 3:0)
 *   0x03: Touch1 X high (bits 3:0) + event flag (bits 7:6)
 *   0x04: Touch1 X low  (bits 7:0)
 *   0x05: Touch1 Y high (bits 3:0)
 *   0x06: Touch1 Y low  (bits 7:0)
 *
 * CST816S registers (subset):
 *   0x03: Number of touch points
 *   0x04: Touch1 X high (bits 3:0)
 *   0x05: Touch1 X low  (bits 7:0)
 *   0x06: Touch1 Y high (bits 3:0)
 *   0x07: Touch1 Y low  (bits 7:0)
 *
 * Physical button on GPIO38 is active-low with internal pull-up.
 */

#include "touch.h"
#include "pins.h"
#include <Wire.h>

// ============================================================================
// Touch Controller Auto-Detect
// ============================================================================

#define FT6336_ADDR         0x38
#define REG_NUM_TOUCHES     0x02
#define REG_TOUCH1_XH       0x03

#define CST816_ADDR         0x15
#define CST816_ADDR_ALT     0x14
#define REG_CST_TP_NUM      0x03

enum TouchIcType {
    TOUCH_NONE = 0,
    TOUCH_FT6336,
    TOUCH_CST816,
};

static TouchIcType s_touch_type = TOUCH_NONE;
static uint8_t s_touch_addr = 0x00;

static void scan_i2c_bus() {
    Serial.println("I2C scan (touch + expander):");
    for (uint8_t addr = 0x08; addr < 0x78; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            Serial.printf("  found 0x%02X\n", addr);
        }
    }
}

static bool probe_addr(uint8_t addr) {
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

bool touch_init() {
    // Touch panel was already reset by display_init() via TCA9535 pin 7.
    // Wait a bit for the controller to come up after reset.
    delay(100);

    // Probe FT6336U first
    if (probe_addr(FT6336_ADDR)) {
        s_touch_type = TOUCH_FT6336;
        s_touch_addr = FT6336_ADDR;
        Serial.println("FT6336U touch controller found at 0x38");
        return true;
    }

    // Probe CST816S (common on Seeed displays)
    if (probe_addr(CST816_ADDR)) {
        s_touch_type = TOUCH_CST816;
        s_touch_addr = CST816_ADDR;
        Serial.println("CST816S touch controller found at 0x15");
        return true;
    }

    if (probe_addr(CST816_ADDR_ALT)) {
        s_touch_type = TOUCH_CST816;
        s_touch_addr = CST816_ADDR_ALT;
        Serial.println("CST816S touch controller found at 0x14");
        return true;
    }

    Serial.println("Touch controller not found. Scanning I2C...");
    scan_i2c_bus();
    Serial.println("Using physical button fallback only.");
    return false;
}

TouchPoint touch_read() {
    TouchPoint tp = {0, 0, false};
    if (s_touch_type == TOUCH_NONE) return tp;

    if (s_touch_type == TOUCH_FT6336) {
        // Read 5 bytes: numTouches, xH, xL, yH, yL
        Wire.beginTransmission(s_touch_addr);
        Wire.write(REG_NUM_TOUCHES);
        if (Wire.endTransmission(false) != 0) return tp;

        uint8_t n = Wire.requestFrom(s_touch_addr, (uint8_t)5);
        if (n < 5) return tp;

        uint8_t numTouches = Wire.read() & 0x0F;
        uint8_t xHigh      = Wire.read();
        uint8_t xLow       = Wire.read();
        uint8_t yHigh      = Wire.read();
        uint8_t yLow       = Wire.read();

        if (numTouches == 0 || numTouches > 2) return tp;

        tp.x = ((xHigh & 0x0F) << 8) | xLow;
        tp.y = ((yHigh & 0x0F) << 8) | yLow;
        tp.touched = true;
        return tp;
    }

    // CST816S path
    Wire.beginTransmission(s_touch_addr);
    Wire.write(REG_CST_TP_NUM);
    if (Wire.endTransmission(false) != 0) return tp;

    uint8_t n = Wire.requestFrom(s_touch_addr, (uint8_t)5);
    if (n < 5) return tp;

    uint8_t numTouches = Wire.read() & 0x0F;
    uint8_t xHigh      = Wire.read();
    uint8_t xLow       = Wire.read();
    uint8_t yHigh      = Wire.read();
    uint8_t yLow       = Wire.read();

    if (numTouches == 0 || numTouches > 2) return tp;

    tp.x = ((xHigh & 0x0F) << 8) | xLow;
    tp.y = ((yHigh & 0x0F) << 8) | yLow;
    tp.touched = true;
    return tp;
}

// ============================================================================
// Physical User Button (GPIO38)
// ============================================================================

static bool     s_btn_last = false;
static bool     s_btn_state = false;   // debounced held state
static uint32_t s_btn_debounce = 0;

void button_init() {
    pinMode(PIN_BUTTON_USER, INPUT_PULLUP);
    s_btn_last = digitalRead(PIN_BUTTON_USER);
    s_btn_state = !s_btn_last;  // active low
}

bool button_pressed() {
    // Legacy: returns true on press edge only
    int e = button_edge();
    return e == 1;
}

bool button_held() {
    return s_btn_state;
}

int button_edge() {
    bool level = digitalRead(PIN_BUTTON_USER);
    uint32_t now = millis();

    // Debounce: 50ms
    if (level != s_btn_last && (now - s_btn_debounce) > 50) {
        s_btn_debounce = now;
        s_btn_last = level;
        bool pressed = !level;  // active low
        if (pressed != s_btn_state) {
            s_btn_state = pressed;
            return pressed ? 1 : -1;
        }
    }
    return 0;
}
