/*
 * Display Driver Implementation for SenseCAP Indicator
 *
 * 1. Initializes I2C and TCA9535 IO expander
 * 2. Runs ST7701S LCD panel init via 3-wire SPI (through IO expander)
 * 3. Creates ESP-IDF RGB panel with correct pin mapping
 * 4. Provides direct framebuffer drawing functions
 *
 * Pin mapping and init sequence from official Seeed SDK.
 */

#include "display.h"
#include "pins.h"
#include "tca9535.h"
#include "lcd_init.h"

#include "esp_lcd_panel_rgb.h"
#include "esp_heap_caps.h"

// ============================================================================
// Static Variables
// ============================================================================

static TCA9535 s_expander;
static esp_lcd_panel_handle_t s_panel = NULL;

// ============================================================================
// Backlight Control
// ============================================================================

void display_backlight(bool on) {
    pinMode(PIN_LCD_BL, OUTPUT);
    digitalWrite(PIN_LCD_BL, on ? LCD_BL_ON_LEVEL : !LCD_BL_ON_LEVEL);
}

// ============================================================================
// RGB Panel Initialization (correct pins from official SDK)
// ============================================================================

static esp_err_t rgb_panel_init() {
    esp_lcd_rgb_panel_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));

    cfg.clk_src = LCD_CLK_SRC_PLL160M;

    // Timing
    cfg.timings.pclk_hz            = LCD_PIXEL_CLK_HZ;
    cfg.timings.h_res              = LCD_H_RES;
    cfg.timings.v_res              = LCD_V_RES;
    cfg.timings.hsync_back_porch   = LCD_HSYNC_BACK_PORCH;
    cfg.timings.hsync_front_porch  = LCD_HSYNC_FRONT_PORCH;
    cfg.timings.hsync_pulse_width  = LCD_HSYNC_PULSE_WIDTH;
    cfg.timings.vsync_back_porch   = LCD_VSYNC_BACK_PORCH;
    cfg.timings.vsync_front_porch  = LCD_VSYNC_FRONT_PORCH;
    cfg.timings.vsync_pulse_width  = LCD_VSYNC_PULSE_WIDTH;
    cfg.timings.flags.pclk_active_neg = LCD_PCLK_ACTIVE_NEG;

    // 16-bit RGB565 bus
    cfg.data_width = 16;

    // Control signals
    cfg.hsync_gpio_num = PIN_LCD_HSYNC;
    cfg.vsync_gpio_num = PIN_LCD_VSYNC;
    cfg.de_gpio_num    = PIN_LCD_DE;
    cfg.pclk_gpio_num  = PIN_LCD_PCLK;
    cfg.disp_gpio_num  = -1;

    // Data pins: B[4:0] G[5:0] R[4:0]
    cfg.data_gpio_nums[0]  = PIN_LCD_D0;   // B0 = GPIO 15
    cfg.data_gpio_nums[1]  = PIN_LCD_D1;   // B1 = GPIO 14
    cfg.data_gpio_nums[2]  = PIN_LCD_D2;   // B2 = GPIO 13
    cfg.data_gpio_nums[3]  = PIN_LCD_D3;   // B3 = GPIO 12
    cfg.data_gpio_nums[4]  = PIN_LCD_D4;   // B4 = GPIO 11
    cfg.data_gpio_nums[5]  = PIN_LCD_D5;   // G0 = GPIO 10
    cfg.data_gpio_nums[6]  = PIN_LCD_D6;   // G1 = GPIO 9
    cfg.data_gpio_nums[7]  = PIN_LCD_D7;   // G2 = GPIO 8
    cfg.data_gpio_nums[8]  = PIN_LCD_D8;   // G3 = GPIO 7
    cfg.data_gpio_nums[9]  = PIN_LCD_D9;   // G4 = GPIO 6
    cfg.data_gpio_nums[10] = PIN_LCD_D10;  // G5 = GPIO 5
    cfg.data_gpio_nums[11] = PIN_LCD_D11;  // R0 = GPIO 4
    cfg.data_gpio_nums[12] = PIN_LCD_D12;  // R1 = GPIO 3
    cfg.data_gpio_nums[13] = PIN_LCD_D13;  // R2 = GPIO 2
    cfg.data_gpio_nums[14] = PIN_LCD_D14;  // R3 = GPIO 1
    cfg.data_gpio_nums[15] = PIN_LCD_D15;  // R4 = GPIO 0

    // Framebuffer in PSRAM
    cfg.flags.fb_in_psram = true;

    // Create the RGB panel
    esp_err_t ret = esp_lcd_new_rgb_panel(&cfg, &s_panel);
    if (ret != ESP_OK) return ret;

    ret = esp_lcd_panel_reset(s_panel);
    if (ret != ESP_OK) return ret;

    ret = esp_lcd_panel_init(s_panel);
    return ret;
}

// ============================================================================
// Public API
// ============================================================================

bool display_init() {
    // Step 1: Enable backlight
    display_backlight(true);

    // Step 2: Initialize I2C IO expander (TCA9535)
    if (!s_expander.begin(TCA9535_ADDR, PIN_I2C_SDA, PIN_I2C_SCL)) {
        Serial.println("ERROR: TCA9535 IO expander not found at 0x20");
        return false;
    }
    Serial.println("TCA9535 IO expander initialized");

    // Step 3: Reset touch panel (via IO expander)
    s_expander.setDirection(EXPANDER_TP_RST, true);
    s_expander.setLevel(EXPANDER_TP_RST, 0);
    delay(5);
    s_expander.setLevel(EXPANDER_TP_RST, 1);

    // Step 4: Create RGB panel (this configures DMA + GPIO for parallel data)
    esp_err_t err = rgb_panel_init();
    if (err != ESP_OK) {
        Serial.printf("ERROR: RGB panel init failed: 0x%x\n", err);
        return false;
    }
    Serial.println("RGB panel created");

    // Step 5: Initialize ST7701S LCD controller via SPI
    lcd_panel_st7701s_init(s_expander);
    Serial.println("ST7701S initialized");

    // Step 6: Fill screen with a test color (blue) to verify display works
    display_fill(0x001F);  // Blue in RGB565
    delay(500);
    display_fill(0x0000);  // Then clear to black

    Serial.println("Display initialized successfully");
    return true;
}

esp_lcd_panel_handle_t display_get_panel() {
    return s_panel;
}

void display_draw_fullscreen(const uint16_t *pixels) {
    if (s_panel && pixels) {
        esp_lcd_panel_draw_bitmap(s_panel, 0, 0, LCD_H_RES, LCD_V_RES, pixels);
    }
}

void display_draw_rect(int x, int y, int w, int h, const uint16_t *pixels) {
    if (s_panel && pixels) {
        esp_lcd_panel_draw_bitmap(s_panel, x, y, x + w, y + h, pixels);
    }
}

void display_fill(uint16_t color) {
    // Allocate a single row buffer
    uint16_t *row = (uint16_t *)heap_caps_malloc(LCD_H_RES * sizeof(uint16_t), MALLOC_CAP_SPIRAM);
    if (!row) return;

    for (int i = 0; i < LCD_H_RES; i++) {
        row[i] = color;
    }

    // Draw row by row
    for (int y = 0; y < LCD_V_RES; y++) {
        esp_lcd_panel_draw_bitmap(s_panel, 0, y, LCD_H_RES, y + 1, row);
    }

    free(row);
}
