/*
 * LCD Panel Initialization for SenseCAP Indicator
 *
 * ST7701S init sequence ported from the official Seeed SDK:
 * Seeed-Solution/SenseCAP_Indicator_ESP32/components/bsp/src/boards/lcd_panel_config.c
 *
 * Uses 3-wire 9-bit SPI (bit-banged) with:
 *   - CS via TCA9535 IO expander (I2C)
 *   - CLK and MOSI via direct ESP32-S3 GPIOs
 */

#pragma once

#include "tca9535.h"

// Initialize the ST7701S LCD panel controller
// Must be called after TCA9535 is initialized
void lcd_panel_st7701s_init(TCA9535 &expander);
