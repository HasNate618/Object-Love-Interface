/*
 * SenseCAP Indicator - Animated Face + Image Display + Touch
 * Main firmware for ESP32-S3
 *
 * Receives JSON commands over CH340 UART (Serial) and/or WiFi TCP socket.
 * Responses and events are sent to BOTH serial and the TCP client (if connected).
 * Binary JPEG data is read from whichever transport sent the image command.
 *
 *   Display modes (mutually exclusive):
 *     {"cmd":"face","on":true/false}          → animated face mode
 *     {"cmd":"image","len":N}                 → JPEG display (disables face)
 *     {"cmd":"clear","color":"#RRGGBB"}       → fill screen with color
 *
 *   Face controls (while face mode is active):
 *     {"cmd":"mouth","open":0.0-1.0}          → mouth openness (lip sync)
 *     {"cmd":"love","value":0.0-1.0}          → love level → floating hearts
 *     {"cmd":"blink"}                         → trigger a manual blink
 *
 *   Audio (via RP2040):
 *     {"cmd":"tone","freq":F,"dur":D}         → buzzer tone
 *     {"cmd":"melody","notes":"..."}          → melody
 *     {"cmd":"stop"}                          → stop buzzer
 *
 *   Hardware:
 *     {"cmd":"bl","on":true/false}            → backlight control
 *
 *   WiFi info:
 *     {"cmd":"wifi"}                          → returns IP/status
 *
 * Emits asynchronous events:
 *     {"event":"touch","x":X,"y":Y}  → touch detected on screen
 *     {"event":"button_down"}         → physical button pressed (GPIO38)
 *     {"event":"button_up"}           → physical button released (GPIO38)
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <JPEGDEC.h>
#include "esp_heap_caps.h"
#include "display.h"
#include "pins.h"
#include "face.h"
#include "touch.h"
#include "wifi_link.h"

// ============================================================================
// Constants
// ============================================================================

#define MAX_JPEG_SIZE   (512 * 1024)
#define FRAME_BYTES     (LCD_H_RES * LCD_V_RES * 2)
#define SERIAL_BAUD     921600
#define CMD_BUF_SIZE    512

// Touch debounce: ignore repeated touches for this many ms
#define TOUCH_COOLDOWN_MS  500
static unsigned long s_last_touch_event = 0;

// ============================================================================
// Globals (PSRAM-backed)
// ============================================================================

static uint8_t  *jpeg_buf   = NULL;   // Incoming JPEG data
static uint16_t *decode_buf = NULL;   // Decoded 480x480 RGB565 frame
static JPEGDEC   jpeg;

// WiFi TCP server
static WiFiLink wifi;
static bool s_wifi_ok = false;

// Track which transport sent the current command:
//   0 = Serial (USB), 1 = WiFi TCP
static int s_cmd_source = 0;

// ============================================================================
// Dual Output Helpers (Serial + WiFi)
// ============================================================================

static void dualPrintln(const char* str) {
    Serial.println(str);
    wifi.println(str);
}

static void dualPrintf(const char* fmt, ...) {
    char buf[256];
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    Serial.write((const uint8_t*)buf, n);
    if (wifi.connected && wifi.client.connected()) {
        wifi.client.write((const uint8_t*)buf, n);
    }
}

// ============================================================================
// JPEG Decode Callback
// ============================================================================

static int jpegDrawCB(JPEGDRAW *pDraw) {
    for (int y = 0; y < pDraw->iHeight; y++) {
        int row = pDraw->y + y;
        if (row >= LCD_V_RES) break;
        int w = pDraw->iWidth;
        if (pDraw->x + w > LCD_H_RES) w = LCD_H_RES - pDraw->x;
        if (pDraw->x < LCD_H_RES && w > 0) {
            memcpy(&decode_buf[row * LCD_H_RES + pDraw->x],
                   &pDraw->pPixels[y * pDraw->iWidth],
                   w * sizeof(uint16_t));
        }
    }
    return 1;
}

// ============================================================================
// RP2040 Communication (buzzer)
// ============================================================================

static void rp2040_tone(int freq, int dur) {
    char buf[64];
    snprintf(buf, sizeof(buf), "TONE %d %d\n", freq, dur);
    Serial1.print(buf);
}

static void rp2040_melody(const char *notes) {
    Serial1.print("MELODY ");
    Serial1.println(notes);
}

static void rp2040_stop() {
    Serial1.println("STOP");
}

// ============================================================================
// Color Helpers
// ============================================================================

static uint16_t hexToRGB565(const char *hex) {
    if (hex[0] == '#') hex++;
    uint32_t rgb = strtoul(hex, NULL, 16);
    uint8_t r = (rgb >> 16) & 0xFF;
    uint8_t g = (rgb >>  8) & 0xFF;
    uint8_t b =  rgb        & 0xFF;
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
}

// ============================================================================
// Image Handler
// ============================================================================

static void handleImage(uint32_t len) {
    if (len == 0 || len > MAX_JPEG_SIZE) {
        dualPrintf("{\"status\":\"error\",\"msg\":\"bad len %u\"}\n", len);
        return;
    }

    // Signal ready
    dualPrintln("{\"status\":\"ready\"}");
    Serial.flush();
    wifi.flush();

    // Receive raw JPEG bytes from whichever transport sent the command
    uint32_t received = 0;
    unsigned long deadline = millis() + 30000;

    if (s_cmd_source == 1) {
        // WiFi TCP source
        while (received < len && millis() < deadline) {
            int avail = wifi.availableBytes();
            if (avail > 0) {
                uint32_t want = len - received;
                if ((uint32_t)avail < want) want = avail;
                size_t got = wifi.readBytes(jpeg_buf + received, want);
                received += got;
                if (got > 0) deadline = millis() + 5000;
            }
            yield();
        }
    } else {
        // Serial USB source
        while (received < len && millis() < deadline) {
            int avail = Serial.available();
            if (avail > 0) {
                uint32_t want = len - received;
                if ((uint32_t)avail < want) want = avail;
                size_t got = Serial.readBytes(jpeg_buf + received, want);
                received += got;
                if (got > 0) deadline = millis() + 5000;
            }
            yield();
        }
    }

    if (received != len) {
        dualPrintf("{\"status\":\"error\",\"msg\":\"got %u/%u\"}\n", received, len);
        return;
    }

    // Decode JPEG to RGB565
    if (!jpeg.openRAM(jpeg_buf, len, jpegDrawCB)) {
        dualPrintln("{\"status\":\"error\",\"msg\":\"jpeg open fail\"}");
        return;
    }
    jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
    memset(decode_buf, 0, FRAME_BYTES);

    if (!jpeg.decode(0, 0, 0)) {
        dualPrintln("{\"status\":\"error\",\"msg\":\"jpeg decode fail\"}");
        jpeg.close();
        return;
    }
    jpeg.close();

    // Push to display
    display_draw_fullscreen(decode_buf);
    dualPrintln("{\"status\":\"ok\"}");
}

// ============================================================================
// Command Dispatcher
// ============================================================================

static void handleCommand(const char *line) {
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, line)) {
        dualPrintln("{\"status\":\"error\",\"msg\":\"bad json\"}");
        return;
    }

    const char *cmd = doc["cmd"];
    if (!cmd) {
        dualPrintln("{\"status\":\"error\",\"msg\":\"no cmd\"}");
        return;
    }

    if (strcmp(cmd, "image") == 0) {
        face_set_enabled(false);  // Image mode takes over from face
        handleImage(doc["len"] | (uint32_t)0);
    }
    else if (strcmp(cmd, "clear") == 0) {
        display_fill(hexToRGB565(doc["color"] | "#000000"));
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "tone") == 0) {
        rp2040_tone(doc["freq"] | 1000, doc["dur"] | 200);
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "melody") == 0) {
        rp2040_melody(doc["notes"] | "");
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "stop") == 0) {
        rp2040_stop();
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "bl") == 0) {
        display_backlight(doc["on"] | true);
        dualPrintln("{\"status\":\"ok\"}");
    }
    // ---- WiFi info ----
    else if (strcmp(cmd, "wifi") == 0) {
        if (s_wifi_ok) {
            dualPrintf("{\"status\":\"ok\",\"ip\":\"%s\",\"port\":%d}\n",
                       wifi.ipAddress().c_str(), TCP_PORT);
        } else {
            dualPrintln("{\"status\":\"ok\",\"ip\":\"none\",\"msg\":\"wifi not connected\"}");
        }
    }
    // ---- Face mode commands ----
    else if (strcmp(cmd, "face") == 0) {
        bool on = doc["on"] | false;
        face_set_enabled(on);
        if (!on) display_fill(0x0000);  // Clear to black when leaving face mode
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "mouth") == 0) {
        face_set_mouth(doc["open"] | 0.0f);
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "love") == 0) {
        face_set_love(doc["value"] | 0.0f);
        dualPrintln("{\"status\":\"ok\"}");
    }
    else if (strcmp(cmd, "blink") == 0) {
        face_blink();
        dualPrintln("{\"status\":\"ok\"}");
    }
    else {
        dualPrintln("{\"status\":\"error\",\"msg\":\"unknown cmd\"}");
    }
}

// ============================================================================
// Arduino Entry Points
// ============================================================================

void setup() {
    Serial.setRxBufferSize(4096);
    Serial.begin(SERIAL_BAUD);
    delay(500);

    // Internal UART to RP2040 (buzzer control)
    Serial1.begin(UART_RP2040_BAUD, SERIAL_8N1, PIN_UART_RP2040_RX, PIN_UART_RP2040_TX);

    Serial.println("{\"status\":\"booting\"}");

    // Connect WiFi and start TCP server
    s_wifi_ok = wifi.begin();
    if (s_wifi_ok) {
        Serial.printf("{\"status\":\"wifi\",\"ip\":\"%s\",\"port\":%d}\n",
                      wifi.ipAddress().c_str(), TCP_PORT);
    }

    // Allocate PSRAM buffers
    jpeg_buf   = (uint8_t  *)heap_caps_malloc(MAX_JPEG_SIZE, MALLOC_CAP_SPIRAM);
    decode_buf = (uint16_t *)heap_caps_malloc(FRAME_BYTES,   MALLOC_CAP_SPIRAM);
    if (!jpeg_buf || !decode_buf) {
        Serial.println("{\"status\":\"error\",\"msg\":\"PSRAM alloc failed\"}");
        return;
    }

    // Initialize display hardware
    if (!display_init()) {
        Serial.println("{\"status\":\"error\",\"msg\":\"display init failed\"}");
        return;
    }

    // Initialize face renderer
    if (!face_init()) {
        Serial.println("{\"status\":\"warning\",\"msg\":\"face init failed (PSRAM?)\"}");
    } else {
        face_set_enabled(true);  // Start in face mode by default
    }

    // Initialize touch controller (FT6336U) + physical button
    if (touch_init()) {
        Serial.println("{\"status\":\"info\",\"msg\":\"touch ready\"}");
    }
    button_init();

    dualPrintln("{\"status\":\"ready\"}");
}

void loop() {
    // --- Poll WiFi TCP server ---
    if (s_wifi_ok) {
        wifi.poll();
    }

    // --- Check USB serial ---
    if (Serial.available()) {
        s_cmd_source = 0;
        String line = Serial.readStringUntil('\n');
        line.trim();
        if (line.length() > 0) {
            handleCommand(line.c_str());
        }
    }

    // --- Check WiFi TCP ---
    if (s_wifi_ok && wifi.available()) {
        String line = wifi.readLine();
        if (line.length() > 0) {
            s_cmd_source = 1;
            handleCommand(line.c_str());
        }
    }

    // --- Touch / button event detection ---
    unsigned long now = millis();

    // Poll capacitive touch
    TouchPoint tp = touch_read();
    if (tp.touched && (now - s_last_touch_event) > TOUCH_COOLDOWN_MS) {
        s_last_touch_event = now;
        dualPrintf("{\"event\":\"touch\",\"x\":%d,\"y\":%d}\n", tp.x, tp.y);
        rp2040_tone(1500, 60);
    }

    // Poll physical user button (GPIO38) — emit down/up events
    int btn = button_edge();
    if (btn == 1) {
        dualPrintln("{\"event\":\"button_down\"}");
        rp2040_tone(1000, 60);
    } else if (btn == -1) {
        dualPrintln("{\"event\":\"button_up\"}");
        rp2040_tone(800, 40);
    }

    // Render face animation (rate-limited internally)
    if (face_is_enabled()) {
        face_update();
    } else {
        delay(1);
    }
}
