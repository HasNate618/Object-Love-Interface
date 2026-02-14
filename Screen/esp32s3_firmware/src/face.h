/*
 * Animated Face Renderer for SenseCAP Indicator
 *
 * Draws a minimal animated face with:
 *   - Floating eyes with automatic blinking
 *   - Controllable mouth (for lip sync)
 *   - Love hearts that appear based on love value
 *
 * All elements gently float around their reference points
 * for an organic, animated feel.
 */

#pragma once

#include <Arduino.h>

// Initialize the face renderer (allocates PSRAM framebuffer).
// Call after display_init(). Returns false on allocation failure.
bool face_init();

// Enable/disable face rendering mode.
// When enabled, face_update() renders each frame.
// Enabling face mode takes over the display from image mode.
void face_set_enabled(bool enabled);
bool face_is_enabled();

// Set mouth openness: 0.0 = closed smile, 1.0 = fully open.
// For lip sync, send rapid updates from the controller.
void face_set_mouth(float open);
float face_get_mouth();

// Set love level: 0.0 = no hearts, 1.0 = max hearts (6).
void face_set_love(float value);
float face_get_love();

// Trigger a manual blink.
void face_blink();

// Call every loop() iteration. Renders a frame and pushes
// to display if face mode is enabled. Rate-limited internally.
void face_update();
