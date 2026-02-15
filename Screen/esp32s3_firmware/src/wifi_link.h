/*
 * wifi_link.h — WiFi TCP server for SenseCAP Indicator
 *
 * Provides a TCP socket server that accepts one client at a time.
 * The client can send JSON commands and receive responses/events,
 * exactly like the USB serial interface.
 *
 * Binary JPEG data for the "image" command flows over the same
 * TCP connection — the protocol is identical to serial:
 *   1. Client sends: {"cmd":"image","len":N}\n
 *   2. Server replies: {"status":"ready"}\n
 *   3. Client sends N raw JPEG bytes
 *   4. Server replies: {"status":"ok"}\n
 */

#pragma once

#include <WiFi.h>
#include <WiFiClient.h>
#include <ESPmDNS.h>
#include "wifi_config.h"

// ============================================================================
// WiFi Link — singleton TCP server
// ============================================================================

class WiFiLink {
public:
    WiFiServer server;
    WiFiClient client;
    bool connected = false;
    String lineBuffer;

    WiFiLink() : server(TCP_PORT) {
        lineBuffer.reserve(512);
    }

    // Connect to WiFi, start TCP server, register mDNS
    bool begin() {
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

        Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);

        unsigned long start = millis();
        while (WiFi.status() != WL_CONNECTED) {
            delay(500);
            Serial.print(".");
            if (millis() - start > 15000) {
                Serial.println("\n[WiFi] Connection FAILED — continuing serial-only");
                return false;
            }
        }

        Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());

        // Start TCP server
        server.begin();
        server.setNoDelay(true);
        Serial.printf("[WiFi] TCP server on port %d\n", TCP_PORT);

        // Register mDNS so clients can find us at sensecap.local
        if (MDNS.begin(MDNS_HOSTNAME)) {
            MDNS.addService("sensecap", "tcp", TCP_PORT);
            Serial.printf("[WiFi] mDNS: %s.local\n", MDNS_HOSTNAME);
        }

        return true;
    }

    // Call from loop() — accept new clients, detect disconnects
    void poll() {
        // Accept new client if none connected
        if (!connected || !client.connected()) {
            WiFiClient newClient = server.accept();
            if (newClient) {
                if (connected && client.connected()) {
                    client.stop();  // Drop old client
                }
                client = newClient;
                client.setNoDelay(true);
                connected = true;
                Serial.printf("[WiFi] Client connected from %s\n",
                              client.remoteIP().toString().c_str());
                client.println("{\"status\":\"connected\"}");
            } else if (connected && !client.connected()) {
                connected = false;
                Serial.println("[WiFi] Client disconnected");
            }
        }
    }

    // Check if data is available from TCP client
    bool available() {
        return connected && client.connected() && client.available();
    }

    // Read bytes available count
    int availableBytes() {
        if (!connected || !client.connected()) return 0;
        return client.available();
    }

    // Read raw bytes (for JPEG binary transfer)
    size_t readBytes(uint8_t *buf, size_t len) {
        if (!connected || !client.connected()) return 0;
        return client.read(buf, len);
    }

    // Read one text line (returns empty string if no complete line yet)
    String readLine() {
        while (connected && client.connected() && client.available()) {
            char c = client.read();
            if (c == '\n') {
                String result = lineBuffer;
                lineBuffer = "";
                result.trim();
                return result;
            } else if (c != '\r') {
                lineBuffer += c;
            }
        }
        return "";  // No complete line yet
    }

    // Send text line to TCP client
    void println(const char *str) {
        if (connected && client.connected()) {
            client.println(str);
        }
    }

    // Printf to TCP client
    void printf(const char *fmt, ...) {
        if (!connected || !client.connected()) return;
        char buf[256];
        va_list args;
        va_start(args, fmt);
        int n = vsnprintf(buf, sizeof(buf), fmt, args);
        va_end(args);
        client.write((const uint8_t*)buf, n);
    }

    // Flush TCP output
    void flush() {
        if (connected && client.connected()) {
            client.flush();
        }
    }

    // Check WiFi connection status
    bool isWiFiConnected() {
        return WiFi.status() == WL_CONNECTED;
    }

    // Get IP address as string
    String ipAddress() {
        return WiFi.localIP().toString();
    }
};
