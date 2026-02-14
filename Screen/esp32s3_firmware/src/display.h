/*
 * Display Driver for SenseCAP Indicator
 *
 * Initializes the RGB panel via ESP-IDF lcd driver.
 * Provides framebuffer access for direct pixel writes.
 * No LVGL dependency - direct framebuffer approach.
 */

#pragma once

#include <Arduino.h>
#include "esp_lcd_panel_ops.h"

// Initialize display hardware (I2C expander, ST7701S, RGB panel, backlight)
// Returns true on success
bool display_init();

// Get the RGB panel handle for draw_bitmap calls
esp_lcd_panel_handle_t display_get_panel();

// Draw a full-screen RGB565 image (480x480 = 460800 bytes)
void display_draw_fullscreen(const uint16_t *pixels);

// Draw a rectangular region of RGB565 pixels
void display_draw_rect(int x, int y, int w, int h, const uint16_t *pixels);

// Fill the entire screen with a solid RGB565 color
void display_fill(uint16_t color);

// Set backlight on/off
void display_backlight(bool on);
