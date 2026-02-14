/*
 * Pin definitions for SenseCAP Indicator D1101
 * ESP32-S3 GPIO assignments
 *
 * Source: Official Seeed SenseCAP_Indicator_ESP32 SDK
 * (components/bsp/src/boards/sensecap_indicator_board.c)
 */

#pragma once

// ============================================================================
// I2C Bus (shared: IO expander TCA9535 + touch panel)
// ============================================================================
#define PIN_I2C_SDA       39
#define PIN_I2C_SCL       40

// ============================================================================
// TCA9535 IO Expander (I2C address 0x20)
// Pins on the expander used for LCD control:
//   Pin 4 = LCD CS (active low)
//   Pin 5 = LCD RESET (active low reset)
//   Pin 7 = Touch Panel RESET
// ============================================================================
#define TCA9535_ADDR      0x20
#define EXPANDER_LCD_CS   4
#define EXPANDER_LCD_RST  5
#define EXPANDER_TP_RST   7

// ============================================================================
// LCD - 3-Wire SPI (for ST7701S initialization, bit-banged GPIOs)
// CS and RESET go through the TCA9535 IO expander (I2C).
// CLK and MOSI are direct ESP32-S3 GPIOs.
// ============================================================================
#define PIN_LCD_SPI_CLK   41    // GPIO bit-bang SPI clock
#define PIN_LCD_SPI_MOSI  48    // GPIO bit-bang SPI data

// ============================================================================
// LCD - RGB Parallel Interface (16-bit, RGB565)
// Pin mapping from official SDK board description
// ============================================================================
#define PIN_LCD_VSYNC     17
#define PIN_LCD_HSYNC     16
#define PIN_LCD_DE        18
#define PIN_LCD_PCLK      21
#define PIN_LCD_BL        45    // Backlight enable
#define LCD_BL_ON_LEVEL   1

// RGB data pins: DATA0..15  →  B[4:0], G[5:0], R[4:0]
#define PIN_LCD_D0        15    // B0
#define PIN_LCD_D1        14    // B1
#define PIN_LCD_D2        13    // B2
#define PIN_LCD_D3        12    // B3
#define PIN_LCD_D4        11    // B4
#define PIN_LCD_D5        10    // G0
#define PIN_LCD_D6         9    // G1
#define PIN_LCD_D7         8    // G2
#define PIN_LCD_D8         7    // G3
#define PIN_LCD_D9         6    // G4
#define PIN_LCD_D10        5    // G5
#define PIN_LCD_D11        4    // R0
#define PIN_LCD_D12        3    // R1
#define PIN_LCD_D13        2    // R2
#define PIN_LCD_D14        1    // R3
#define PIN_LCD_D15        0    // R4

// ============================================================================
// LCD Display Parameters
// ============================================================================
#define LCD_H_RES         480
#define LCD_V_RES         480
#define LCD_PIXEL_CLK_HZ  (18 * 1000 * 1000)   // 18 MHz pixel clock

// RGB timing parameters (from official SDK)
#define LCD_HSYNC_BACK_PORCH    50
#define LCD_HSYNC_FRONT_PORCH   10
#define LCD_HSYNC_PULSE_WIDTH    8
#define LCD_VSYNC_BACK_PORCH    20
#define LCD_VSYNC_FRONT_PORCH   10
#define LCD_VSYNC_PULSE_WIDTH    8
#define LCD_PCLK_ACTIVE_NEG      0   // Data sampled on rising edge

// ============================================================================
// Internal UART (ESP32-S3 <-> RP2040)
// ============================================================================
#define PIN_UART_RP2040_TX  19  // ESP32-S3 TX -> RP2040 RX
#define PIN_UART_RP2040_RX  20  // ESP32-S3 RX <- RP2040 TX
#define UART_RP2040_BAUD    115200

// ============================================================================
// User Button
// ============================================================================
#define PIN_BUTTON_USER   38
