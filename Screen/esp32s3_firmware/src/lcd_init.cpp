/*
 * LCD Panel Initialization - ST7701S via 3-wire 9-bit SPI
 *
 * Ported from official Seeed SDK:
 * Seeed-Solution/SenseCAP_Indicator_ESP32/components/bsp/src/boards/lcd_panel_config.c
 *
 * The SenseCAP Indicator uses an IO expander (TCA9535) for LCD CS and RESET pins,
 * while CLK and MOSI are direct ESP32-S3 GPIOs (bit-banged SPI).
 */

#include "lcd_init.h"
#include "pins.h"
#include <Arduino.h>

// ============================================================================
// Module-level references
// ============================================================================

static TCA9535 *s_expander = nullptr;

// ============================================================================
// Low-level SPI helpers (matching SDK protocol exactly)
// ============================================================================

static inline void spi_cs(int level) {
    s_expander->setLevel(EXPANDER_LCD_CS, level);
}

static inline void spi_clk(int level) {
    if (level) GPIO.out1_w1ts.val = (1 << (PIN_LCD_SPI_CLK - 32));
    else       GPIO.out1_w1tc.val = (1 << (PIN_LCD_SPI_CLK - 32));
}

static inline void spi_sdo(int level) {
    if (level) GPIO.out1_w1ts.val = (1 << (PIN_LCD_SPI_MOSI - 32));
    else       GPIO.out1_w1tc.val = (1 << (PIN_LCD_SPI_MOSI - 32));
}

// Send 9 bits MSB first: bit[8] = DC, bit[7:0] = data
static void SPI_SendData(uint16_t i) {
    for (int n = 0; n < 9; n++) {
        if (i & 0x0100) spi_sdo(1);
        else            spi_sdo(0);
        i <<= 1;
        spi_clk(1);
        delayMicroseconds(10);
        spi_clk(0);
        delayMicroseconds(10);
    }
}

// Write a command byte (DC=0)
static void SPI_WriteComm(uint8_t c) {
    spi_cs(0);
    delayMicroseconds(10);
    spi_clk(0);
    delayMicroseconds(10);
    SPI_SendData((uint16_t)c);  // bit 8 = 0 → command
    spi_cs(1);
    delayMicroseconds(10);
}

// Write a data byte (DC=1)
static void SPI_WriteData(uint8_t d) {
    spi_cs(0);
    delayMicroseconds(10);
    spi_clk(0);
    delayMicroseconds(10);
    SPI_SendData(0x0100 | (uint16_t)d);  // bit 8 = 1 → data
    spi_clk(1);
    delayMicroseconds(10);
    spi_clk(0);
    delayMicroseconds(10);
    spi_cs(1);
    delayMicroseconds(10);
}

// ============================================================================
// GPIO initialization for SPI pins
// ============================================================================

static void init_spi_gpios() {
    // Configure CLK and MOSI as GPIO outputs
    pinMode(PIN_LCD_SPI_CLK, OUTPUT);
    pinMode(PIN_LCD_SPI_MOSI, OUTPUT);
    digitalWrite(PIN_LCD_SPI_CLK, LOW);
    digitalWrite(PIN_LCD_SPI_MOSI, LOW);

    // Configure IO expander pins for LCD
    s_expander->setDirection(EXPANDER_LCD_CS, true);    // output
    s_expander->setDirection(EXPANDER_LCD_RST, true);  // output
    s_expander->setLevel(EXPANDER_LCD_CS, 1);
    s_expander->setLevel(EXPANDER_LCD_RST, 1);
}

// ============================================================================
// ST7701S Initialization Sequence
// Exact copy from official Seeed SDK lcd_panel_st7701s_init()
// ============================================================================

void lcd_panel_st7701s_init(TCA9535 &expander) {
    s_expander = &expander;
    init_spi_gpios();

    // ---- Command2 BK0 Selection ----
    SPI_WriteComm(0xFF);
    SPI_WriteData(0x77); SPI_WriteData(0x01); SPI_WriteData(0x00);
    SPI_WriteData(0x00); SPI_WriteData(0x10);

    // Display Line Setting: 480 lines
    SPI_WriteComm(0xC0);
    SPI_WriteData(0x3B); SPI_WriteData(0x00);

    // Porch Control
    SPI_WriteComm(0xC1);
    SPI_WriteData(0x0D); SPI_WriteData(0x02);

    // Inversion selection & frame rate
    SPI_WriteComm(0xC2);
    SPI_WriteData(0x31); SPI_WriteData(0x05);

    // Register C7
    SPI_WriteComm(0xC7);
    SPI_WriteData(0x04);

    // Register CD
    SPI_WriteComm(0xCD);
    SPI_WriteData(0x08);

    // Positive Gamma Control
    SPI_WriteComm(0xB0);
    SPI_WriteData(0x00); SPI_WriteData(0x11); SPI_WriteData(0x18);
    SPI_WriteData(0x0E); SPI_WriteData(0x11); SPI_WriteData(0x06);
    SPI_WriteData(0x07); SPI_WriteData(0x08); SPI_WriteData(0x07);
    SPI_WriteData(0x22); SPI_WriteData(0x04); SPI_WriteData(0x12);
    SPI_WriteData(0x0F); SPI_WriteData(0xAA); SPI_WriteData(0x31);
    SPI_WriteData(0x18);

    // Negative Gamma Control
    SPI_WriteComm(0xB1);
    SPI_WriteData(0x00); SPI_WriteData(0x11); SPI_WriteData(0x19);
    SPI_WriteData(0x0E); SPI_WriteData(0x12); SPI_WriteData(0x07);
    SPI_WriteData(0x08); SPI_WriteData(0x08); SPI_WriteData(0x08);
    SPI_WriteData(0x22); SPI_WriteData(0x04); SPI_WriteData(0x11);
    SPI_WriteData(0x11); SPI_WriteData(0xA9); SPI_WriteData(0x32);
    SPI_WriteData(0x18);

    // ---- Command2 BK1 Selection ----
    SPI_WriteComm(0xFF);
    SPI_WriteData(0x77); SPI_WriteData(0x01); SPI_WriteData(0x00);
    SPI_WriteData(0x00); SPI_WriteData(0x11);

    // Vop Amplitude
    SPI_WriteComm(0xB0);
    SPI_WriteData(0x60);

    // VCOM Amplitude
    SPI_WriteComm(0xB1);
    SPI_WriteData(0x32);

    // VGH Voltage
    SPI_WriteComm(0xB2);
    SPI_WriteData(0x07);

    // TEST Command
    SPI_WriteComm(0xB3);
    SPI_WriteData(0x80);

    // VGL Voltage
    SPI_WriteComm(0xB5);
    SPI_WriteData(0x49);

    // Power Control 1
    SPI_WriteComm(0xB7);
    SPI_WriteData(0x85);

    // Power Control 2
    SPI_WriteComm(0xB8);
    SPI_WriteData(0x21);

    // Source pre_drive timing
    SPI_WriteComm(0xC1);
    SPI_WriteData(0x78);

    // Source EQ2
    SPI_WriteComm(0xC2);
    SPI_WriteData(0x78);

    delay(20);

    // GIP Setting
    SPI_WriteComm(0xE0);
    SPI_WriteData(0x00); SPI_WriteData(0x1B); SPI_WriteData(0x02);

    SPI_WriteComm(0xE1);
    SPI_WriteData(0x08); SPI_WriteData(0xA0); SPI_WriteData(0x00);
    SPI_WriteData(0x00); SPI_WriteData(0x07); SPI_WriteData(0xA0);
    SPI_WriteData(0x00); SPI_WriteData(0x00); SPI_WriteData(0x00);
    SPI_WriteData(0x44); SPI_WriteData(0x44);

    SPI_WriteComm(0xE2);
    SPI_WriteData(0x11); SPI_WriteData(0x11); SPI_WriteData(0x44);
    SPI_WriteData(0x44); SPI_WriteData(0xED); SPI_WriteData(0xA0);
    SPI_WriteData(0x00); SPI_WriteData(0x00); SPI_WriteData(0xEC);
    SPI_WriteData(0xA0); SPI_WriteData(0x00); SPI_WriteData(0x00);

    SPI_WriteComm(0xE3);
    SPI_WriteData(0x00); SPI_WriteData(0x00);
    SPI_WriteData(0x11); SPI_WriteData(0x11);

    SPI_WriteComm(0xE4);
    SPI_WriteData(0x44); SPI_WriteData(0x44);

    SPI_WriteComm(0xE5);
    SPI_WriteData(0x0A); SPI_WriteData(0xE9); SPI_WriteData(0xD8);
    SPI_WriteData(0xA0); SPI_WriteData(0x0C); SPI_WriteData(0xEB);
    SPI_WriteData(0xD8); SPI_WriteData(0xA0); SPI_WriteData(0x0E);
    SPI_WriteData(0xED); SPI_WriteData(0xD8); SPI_WriteData(0xA0);
    SPI_WriteData(0x10); SPI_WriteData(0xEF); SPI_WriteData(0xD8);
    SPI_WriteData(0xA0);

    SPI_WriteComm(0xE6);
    SPI_WriteData(0x00); SPI_WriteData(0x00);
    SPI_WriteData(0x11); SPI_WriteData(0x11);

    SPI_WriteComm(0xE7);
    SPI_WriteData(0x44); SPI_WriteData(0x44);

    SPI_WriteComm(0xE8);
    SPI_WriteData(0x09); SPI_WriteData(0xE8); SPI_WriteData(0xD8);
    SPI_WriteData(0xA0); SPI_WriteData(0x0B); SPI_WriteData(0xEA);
    SPI_WriteData(0xD8); SPI_WriteData(0xA0); SPI_WriteData(0x0D);
    SPI_WriteData(0xEC); SPI_WriteData(0xD8); SPI_WriteData(0xA0);
    SPI_WriteData(0x0F); SPI_WriteData(0xEE); SPI_WriteData(0xD8);
    SPI_WriteData(0xA0);

    SPI_WriteComm(0xEB);
    SPI_WriteData(0x02); SPI_WriteData(0x00); SPI_WriteData(0xE4);
    SPI_WriteData(0xE4); SPI_WriteData(0x88); SPI_WriteData(0x00);
    SPI_WriteData(0x40);

    SPI_WriteComm(0xEC);
    SPI_WriteData(0x3C); SPI_WriteData(0x00);

    SPI_WriteComm(0xED);
    SPI_WriteData(0xAB); SPI_WriteData(0x89); SPI_WriteData(0x76);
    SPI_WriteData(0x54); SPI_WriteData(0x02); SPI_WriteData(0xFF);
    SPI_WriteData(0xFF); SPI_WriteData(0xFF); SPI_WriteData(0xFF);
    SPI_WriteData(0xFF); SPI_WriteData(0xFF); SPI_WriteData(0x20);
    SPI_WriteData(0x45); SPI_WriteData(0x67); SPI_WriteData(0x98);
    SPI_WriteData(0xBA);

    // MADCTL - Memory Access Control (flip horizontal)
    SPI_WriteComm(0x36);
    SPI_WriteData(0x10);

    // ---- Command2 BK3 Selection (from SDK) ----
    SPI_WriteComm(0xFF);
    SPI_WriteData(0x77); SPI_WriteData(0x01); SPI_WriteData(0x00);
    SPI_WriteData(0x00); SPI_WriteData(0x13);

    SPI_WriteComm(0xE5);
    SPI_WriteData(0xE4);

    // ---- Exit Command2 mode ----
    SPI_WriteComm(0xFF);
    SPI_WriteData(0x77); SPI_WriteData(0x01); SPI_WriteData(0x00);
    SPI_WriteData(0x00); SPI_WriteData(0x00);

    // Pixel Format: RGB666 (matches 16-bit data bus)
    SPI_WriteComm(0x3A);
    SPI_WriteData(0x60);

    // Display Inversion On
    SPI_WriteComm(0x21);

    // Sleep Out
    SPI_WriteComm(0x11);
    delay(120);

    // Display On
    SPI_WriteComm(0x29);
    delay(120);

    // Leave SPI lines in idle state
    spi_cs(1);
    spi_clk(1);
    spi_sdo(1);
}
