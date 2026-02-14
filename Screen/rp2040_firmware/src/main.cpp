/*
 * SenseCAP Indicator RP2040 - Buzzer Controller
 *
 * Receives simple text commands from ESP32-S3 via internal UART
 * and drives the built-in buzzer.
 *
 * Commands (via UART from ESP32-S3):
 *   TONE:<freq>:<duration_ms>\n   - Play a tone
 *   STOP\n                        - Stop current tone
 *   MELODY:<notes>\n              - Play a sequence of notes
 *
 * Pin Assignments:
 *   Buzzer: GP19
 *   UART TX (to ESP32-S3): GP20
 *   UART RX (from ESP32-S3): GP21
 */

#include <Arduino.h>

// ============================================================================
// Pin Definitions
// ============================================================================
#define BUZZER_PIN  19
#define UART_TX_PIN 20
#define UART_RX_PIN 21

// ============================================================================
// Static Variables
// ============================================================================
static char line_buf[256];
static size_t line_pos = 0;
static unsigned long tone_end_time = 0;

// ============================================================================
// Buzzer Control
// ============================================================================

void buzzer_play_tone(int freq, int duration_ms) {
    if (freq > 0 && duration_ms > 0) {
        tone(BUZZER_PIN, freq, duration_ms);
        tone_end_time = millis() + duration_ms;
    }
}

void buzzer_stop() {
    noTone(BUZZER_PIN);
    tone_end_time = 0;
}

// Play a simple melody: comma-separated "freq:dur" pairs
// Example: "440:200,554:200,659:400"
void buzzer_melody(const char *notes) {
    char buf[256];
    strncpy(buf, notes, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char *note = strtok(buf, ",");
    while (note != NULL) {
        int freq = 0, dur = 0;
        if (sscanf(note, "%d:%d", &freq, &dur) == 2) {
            if (freq > 0) {
                tone(BUZZER_PIN, freq, dur);
                delay(dur + 20);  // Small gap between notes
            } else {
                delay(dur);  // Rest note (freq=0)
            }
        }
        note = strtok(NULL, ",");
    }
    noTone(BUZZER_PIN);
}

// ============================================================================
// Command Processing
// ============================================================================

void process_command(const char *cmd) {
    if (strncmp(cmd, "TONE:", 5) == 0) {
        int freq = 0, dur = 0;
        if (sscanf(cmd + 5, "%d:%d", &freq, &dur) == 2) {
            buzzer_play_tone(freq, dur);
        }
    } else if (strcmp(cmd, "STOP") == 0) {
        buzzer_stop();
    } else if (strncmp(cmd, "MELODY:", 7) == 0) {
        buzzer_melody(cmd + 7);
    }
}

// ============================================================================
// Setup & Loop
// ============================================================================

void setup() {
    // USB CDC serial (for debugging / direct PC control)
    Serial.begin(115200);

    // Internal UART to ESP32-S3 (UART1 = Serial2, GP20/GP21 are UART1 pins)
    Serial2.setTX(UART_TX_PIN);
    Serial2.setRX(UART_RX_PIN);
    Serial2.begin(115200);

    // Buzzer pin
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);

    // Startup beep
    buzzer_play_tone(1000, 100);
    delay(150);
    buzzer_play_tone(1500, 100);

    Serial.println("RP2040 Buzzer Controller Ready");
    Serial2.println("RP2040_READY");
}

void loop() {
    // Check internal UART (from ESP32-S3)
    while (Serial2.available()) {
        char c = Serial2.read();
        if (c == '\n' || c == '\r') {
            if (line_pos > 0) {
                line_buf[line_pos] = '\0';
                process_command(line_buf);
                line_pos = 0;
            }
        } else if (line_pos < sizeof(line_buf) - 1) {
            line_buf[line_pos++] = c;
        }
    }

    // Also accept commands via USB serial (for direct testing)
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (line_pos > 0) {
                line_buf[line_pos] = '\0';
                process_command(line_buf);
                line_pos = 0;
            }
        } else if (line_pos < sizeof(line_buf) - 1) {
            line_buf[line_pos++] = c;
        }
    }

    // Auto-stop tone when duration expires
    if (tone_end_time > 0 && millis() >= tone_end_time) {
        noTone(BUZZER_PIN);
        tone_end_time = 0;
    }
}
