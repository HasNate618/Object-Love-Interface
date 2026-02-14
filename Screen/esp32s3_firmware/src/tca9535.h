/*
 * TCA9535 I2C 16-bit IO Expander - Minimal Driver
 *
 * Used on SenseCAP Indicator to control LCD CS/RESET and touch panel RESET.
 * Only implements output functionality (no input reading).
 *
 * Register Map:
 *   0x02 = Output Port 0 (pins 0-7)
 *   0x03 = Output Port 1 (pins 8-15)
 *   0x06 = Configuration Port 0 (0=output, 1=input)
 *   0x07 = Configuration Port 1
 */

#pragma once

#include <Arduino.h>
#include <Wire.h>

class TCA9535 {
public:
    bool begin(uint8_t addr, int sda_pin, int scl_pin) {
        _addr = addr;
        Wire.begin(sda_pin, scl_pin, 400000);  // 400 kHz I2C

        // Verify device is present
        Wire.beginTransmission(_addr);
        if (Wire.endTransmission() != 0) {
            return false;
        }

        // Read current output states (default after reset is all high)
        _out0 = 0xFF;
        _out1 = 0xFF;

        // Write initial output values
        writeReg(0x02, _out0);
        writeReg(0x03, _out1);

        return true;
    }

    // Set pin direction: true = output, false = input
    void setDirection(uint8_t pin, bool output) {
        if (pin < 8) {
            uint8_t cfg = readReg(0x06);
            if (output) cfg &= ~(1 << pin);
            else        cfg |=  (1 << pin);
            writeReg(0x06, cfg);
        } else if (pin < 16) {
            uint8_t cfg = readReg(0x07);
            pin -= 8;
            if (output) cfg &= ~(1 << pin);
            else        cfg |=  (1 << pin);
            writeReg(0x07, cfg);
        }
    }

    // Set output pin level
    void setLevel(uint8_t pin, bool level) {
        if (pin < 8) {
            if (level) _out0 |=  (1 << pin);
            else       _out0 &= ~(1 << pin);
            writeReg(0x02, _out0);
        } else if (pin < 16) {
            pin -= 8;
            if (level) _out1 |=  (1 << pin);
            else       _out1 &= ~(1 << pin);
            writeReg(0x03, _out1);
        }
    }

private:
    uint8_t _addr = 0;
    uint8_t _out0 = 0xFF;
    uint8_t _out1 = 0xFF;

    void writeReg(uint8_t reg, uint8_t val) {
        Wire.beginTransmission(_addr);
        Wire.write(reg);
        Wire.write(val);
        Wire.endTransmission();
    }

    uint8_t readReg(uint8_t reg) {
        Wire.beginTransmission(_addr);
        Wire.write(reg);
        Wire.endTransmission(false);
        Wire.requestFrom(_addr, (uint8_t)1);
        return Wire.available() ? Wire.read() : 0xFF;
    }
};
