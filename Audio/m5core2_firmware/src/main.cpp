/*
 * M5Stack Core Audio Streaming Firmware
 *
 * Connects to WiFi, runs a simple HTTP control API.
 * The Raspberry Pi tells the M5Core2 to play audio from a URL
 * (typically an MP3 served by the Pi's audio server).
 *
 * HTTP API (M5Core2 listens on port 8082):
 *   POST /play   body: {"url":"http://pi:8080/audio/latest.mp3"}
 *   POST /stop
 *   POST /volume body: {"level":5}  (0-10)
 *   GET  /status
 *
 * Audio path:
 *   HTTP URL → ESP8266Audio ICY Stream → MP3 Decoder → I2S → Speaker
 *
 * Core1 audio output uses INTERNAL_DAC (GPIO25/26)
 */

#include <M5Stack.h>
#include <driver/i2s.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>

#include <AudioFileSourceHTTPStream.h>
#include <AudioFileSourceBuffer.h>
#include <AudioGeneratorMP3.h>
#include <AudioGeneratorWAV.h>
#include <AudioOutputI2S.h>

#include "wifi_config.h"

// ============================================================================
// Audio objects
// ============================================================================

static AudioGeneratorMP3        *mp3       = nullptr;
static AudioGeneratorWAV        *wav       = nullptr;
static AudioFileSourceHTTPStream *httpSrc   = nullptr;
static AudioFileSourceBuffer    *bufSrc    = nullptr;
static AudioOutputI2S           *audioOut  = nullptr;

// Stream buffer (Core1 has less RAM than Core2)
static const int BUF_SIZE = 64 * 1024;
static void *preallocateBuffer = nullptr;

static float gainLevel = 0.3;  // matching working repo default
static const float gainFactor = 0.08;  // from working repo
static bool  isPlaying = false;
static String currentUrl = "";
static String playFormat = "mp3";  // "mp3" or "wav"

// Deferred play: HTTP handler sets these, loop() picks them up
static String pendingUrl = "";
static String pendingFmt = "";
static bool  pendingPlay = false;

// ============================================================================
// HTTP control server
// ============================================================================

static WebServer server(HTTP_PORT);

// ============================================================================
// Display helpers
// ============================================================================

static void lcd(const char *line1, const char *line2 = "", uint16_t color = TFT_WHITE) {
    M5.Lcd.fillScreen(TFT_BLACK);
    M5.Lcd.setTextColor(color, TFT_BLACK);
    M5.Lcd.setTextDatum(MC_DATUM);
    M5.Lcd.setTextSize(2);
    M5.Lcd.drawString(line1, 160, 100);
    M5.Lcd.setTextSize(1);
    M5.Lcd.drawString(line2, 160, 140);
}

static void lcdStatus() {
    M5.Lcd.fillScreen(TFT_BLACK);
    M5.Lcd.setTextColor(TFT_GREEN, TFT_BLACK);
    M5.Lcd.setTextDatum(TC_DATUM);
    M5.Lcd.setTextSize(2);
    M5.Lcd.drawString("Audio Player", 160, 10);
    M5.Lcd.setTextSize(1);
    M5.Lcd.setTextColor(TFT_WHITE, TFT_BLACK);
    M5.Lcd.drawString("IP: " + WiFi.localIP().toString(), 160, 50);
    M5.Lcd.drawString("Port: " + String(HTTP_PORT), 160, 70);
    M5.Lcd.drawString(isPlaying ? "Playing..." : "Idle", 160, 100);
    M5.Lcd.drawString("Vol: " + String((int)(gainLevel * 10)), 160, 120);
    if (currentUrl.length() > 0) {
        String shortUrl = currentUrl;
        if (shortUrl.length() > 40) shortUrl = shortUrl.substring(0, 40) + "...";
        M5.Lcd.drawString(shortUrl, 160, 150);
    }
}

// ============================================================================
// Audio control
// ============================================================================

static void stopAudio() {
    if (mp3) { mp3->stop(); delete mp3; mp3 = nullptr; }
    if (wav) { wav->stop(); delete wav; wav = nullptr; }
    if (bufSrc) { bufSrc->close(); delete bufSrc; bufSrc = nullptr; }
    if (httpSrc) { httpSrc->close(); delete httpSrc; httpSrc = nullptr; }
    if (audioOut) { delete audioOut; audioOut = nullptr; }
    isPlaying = false;
    Serial.println("Audio stopped");
    lcdStatus();
}

static bool startAudio(const String &url, const String &fmt) {
    stopAudio();

    Serial.printf("Playing: %s (format: %s)\n", url.c_str(), fmt.c_str());
    currentUrl = url;
    playFormat = fmt;

    // Create I2S output using internal DAC (Core1 speaker path)
    audioOut = new AudioOutputI2S(0, AudioOutputI2S::INTERNAL_DAC);
    audioOut->SetOutputModeMono(true);
    audioOut->SetGain(gainLevel);
    Serial.printf("I2S output created (gain=%.2f)\n", gainLevel);

    // Create HTTP source
    Serial.printf("Connecting to stream: %s\n", url.c_str());
    httpSrc = new AudioFileSourceHTTPStream(url.c_str());
    if (!httpSrc) {
        Serial.println("ERROR: Failed to create HTTP source");
        stopAudio();
        return false;
    }
    Serial.println("HTTP source created");

    // Buffer with pre-allocated memory (matching working repo pattern)
    bufSrc = new AudioFileSourceBuffer(httpSrc, preallocateBuffer, BUF_SIZE);
    Serial.println("Buffer source created");

    bool ok = false;
    if (fmt == "wav") {
        wav = new AudioGeneratorWAV();
        ok = wav->begin(bufSrc, audioOut);
        Serial.printf("WAV begin: %s\n", ok ? "OK" : "FAIL");
    } else {
        // Default to MP3
        mp3 = new AudioGeneratorMP3();
        ok = mp3->begin(bufSrc, audioOut);
        Serial.printf("MP3 begin: %s\n", ok ? "OK" : "FAIL");
    }

    if (!ok) {
        Serial.println("ERROR: Failed to start audio playback");
        stopAudio();
        return false;
    }

    isPlaying = true;
    lcd("Playing", url.c_str(), TFT_GREEN);
    return true;
}

// ============================================================================
// HTTP route handlers
// ============================================================================

static void handlePlay() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"error\":\"no body\"}");
        return;
    }
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, server.arg("plain"))) {
        server.send(400, "application/json", "{\"error\":\"bad json\"}");
        return;
    }
    const char *url = doc["url"];
    if (!url) {
        server.send(400, "application/json", "{\"error\":\"no url\"}");
        return;
    }
    String fmt = doc["format"] | "mp3";
    // Defer actual playback to loop() so HTTP responds immediately
    pendingUrl = String(url);
    pendingFmt = fmt;
    pendingPlay = true;
    server.send(200, "application/json", "{\"status\":\"queued\"}");
}

static void handleStop() {
    stopAudio();
    server.send(200, "application/json", "{\"status\":\"stopped\"}");
}

static void handleTone() {
    int freq = 440;
    int durationMs = 300;
    if (server.hasArg("plain")) {
        StaticJsonDocument<128> doc;
        if (!deserializeJson(doc, server.arg("plain"))) {
            freq = doc["freq"] | freq;
            durationMs = doc["duration"] | durationMs;
        }
    }
    M5.Speaker.setVolume(255);
    M5.Speaker.tone(freq, durationMs);
    server.send(200, "application/json", "{\"status\":\"ok\"}");
}

static void handleVolume() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"error\":\"no body\"}");
        return;
    }
    StaticJsonDocument<64> doc;
    if (deserializeJson(doc, server.arg("plain"))) {
        server.send(400, "application/json", "{\"error\":\"bad json\"}");
        return;
    }
    int level = doc["level"] | 5;
    if (level < 0) level = 0;
    if (level > 10) level = 10;
    gainLevel = level * gainFactor;  // Working repo: level * 0.08
    if (audioOut) audioOut->SetGain(gainLevel);
    Serial.printf("Volume: %d (gain: %.2f)\n", level, gainLevel);
    server.send(200, "application/json", "{\"status\":\"ok\",\"level\":" + String(level) + "}");
    lcdStatus();
}

static void handleStatus() {
    StaticJsonDocument<256> doc;
    doc["playing"] = isPlaying;
    doc["volume"] = (int)(gainLevel / gainFactor);
    doc["url"] = currentUrl;
    doc["ip"] = WiFi.localIP().toString();
    String out;
    serializeJson(doc, out);
    server.send(200, "application/json", out);
}

static void handleNotFound() {
    server.send(404, "application/json", "{\"error\":\"not found\"}");
}

// ============================================================================
// Arduino entry points
// ============================================================================

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n\n=== M5Core2 Audio Player ===");

    // Initialize M5Stack Core1
    M5.begin(true, false, true, false);
    Serial.println("M5.begin() done (Core1)");

    // Turn off the always-on WLED / RGB lights
    M5.Power.setPowerWLEDSet(false);

    // Initialize speaker for Core1
    M5.Speaker.begin();
    M5.Speaker.setVolume(255);

    // Test LCD
    M5.Lcd.fillScreen(TFT_BLACK);
    M5.Lcd.setTextColor(TFT_YELLOW, TFT_BLACK);
    M5.Lcd.setTextSize(2);
    M5.Lcd.setCursor(10, 10);
    M5.Lcd.println("Audio Player");
    M5.Lcd.setTextSize(1);
    M5.Lcd.println();
    M5.Lcd.printf("Connecting to: %s\n", WIFI_SSID);
    Serial.printf("Connecting to WiFi: %s\n", WIFI_SSID);

    // Connect WiFi
    WiFi.disconnect();
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int retries = 0;
    while (!WiFi.isConnected()) {
        delay(500);
        Serial.print(".");
        M5.Lcd.print(".");
        retries++;
        if (retries > 30) {
            M5.Lcd.println("\nWiFi FAILED - restarting...");
            Serial.println("\nWiFi FAILED - restarting");
            delay(3000);
            ESP.restart();
        }
    }
    Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
    M5.Lcd.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());

    // Allocate stream buffer (matching working repo: malloc, not ps_malloc)
    preallocateBuffer = malloc(BUF_SIZE);
    if (!preallocateBuffer) {
        Serial.println("ERROR: Failed to allocate stream buffer!");
    } else {
        Serial.printf("Stream buffer allocated: %d bytes\n", BUF_SIZE);
    }

    // Setup HTTP control server
    server.on("/play", HTTP_POST, handlePlay);
    server.on("/stop", HTTP_POST, handleStop);
    server.on("/tone", HTTP_POST, handleTone);
    server.on("/volume", HTTP_POST, handleVolume);
    server.on("/status", HTTP_GET, handleStatus);
    server.onNotFound(handleNotFound);
    server.begin();

    Serial.printf("HTTP server on port %d\n", HTTP_PORT);
    lcdStatus();
}

void loop() {
    // Handle HTTP requests
    server.handleClient();

    // Start deferred playback (set by HTTP handler)
    if (pendingPlay) {
        pendingPlay = false;
        String url = pendingUrl;
        String fmt = pendingFmt;
        pendingUrl = "";
        pendingFmt = "";
        startAudio(url, fmt);
    }

    // Feed audio decoder
    if (isPlaying) {
        bool running = false;
        if (mp3 && mp3->isRunning()) {
            running = mp3->loop();
        } else if (wav && wav->isRunning()) {
            running = wav->loop();
        }

        if (!running) {
            Serial.println("Playback finished");
            stopAudio();
        }
    }

    // M5 button handling
    M5.update();
    if (M5.BtnA.wasPressed()) {
        // Volume down
        int level = (int)(gainLevel * 10) - 1;
        if (level < 0) level = 0;
        gainLevel = level / 10.0f;
        if (audioOut) audioOut->SetGain(gainLevel);
        lcdStatus();
    }
    if (M5.BtnB.wasPressed()) {
        // Stop/Play toggle
        if (isPlaying) stopAudio();
    }
    if (M5.BtnC.wasPressed()) {
        // Volume up
        int level = (int)(gainLevel * 10) + 1;
        if (level > 10) level = 10;
        gainLevel = level / 10.0f;
        if (audioOut) audioOut->SetGain(gainLevel);
        lcdStatus();
    }

    delay(1);
}
