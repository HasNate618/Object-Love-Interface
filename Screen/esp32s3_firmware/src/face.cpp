/*
 * Animated Face Renderer - Implementation
 *
 * Renders a clean, minimal face on the 480x480 SenseCAP display.
 * Uses scanline-based drawing to a PSRAM framebuffer, pushed
 * to the RGB panel at ~40fps.
 *
 * Visual design:
 *   - Dark navy background
 *   - Two large white oval eyes with dark pupils and highlights
 *   - Coral-pink mouth (smile arc when closed, oval when open)
 *   - Vibrant pink floating hearts based on love value
 *   - All elements gently bob around their reference positions
 *   - Automatic eye blinking every 3-7 seconds
 */

#include "face.h"
#include "display.h"
#include "pins.h"
#include "esp_heap_caps.h"
#include <math.h>

// ============================================================================
// Color Palette (RGB565)
// ============================================================================

#define RGB565(r, g, b) \
    (((uint16_t)((r) >> 3) << 11) | ((uint16_t)((g) >> 2) << 5) | ((uint16_t)((b) >> 3)))

static const uint16_t COL_BG         = RGB565(18, 18, 40);    // Dark navy
static const uint16_t COL_EYE_WHITE  = RGB565(255, 255, 255); // Pure white
static const uint16_t COL_PUPIL      = RGB565(8, 8, 18);      // Near-black
static const uint16_t COL_HIGHLIGHT  = RGB565(255, 255, 255); // Sparkle
static const uint16_t COL_MOUTH      = RGB565(230, 100, 120); // Soft coral lips
static const uint16_t COL_MOUTH_DARK = RGB565(80, 25, 40);    // Dark mouth interior
static const uint16_t COL_HEART_A    = RGB565(255, 70, 110);  // Vibrant pink
static const uint16_t COL_HEART_B    = RGB565(255, 120, 155); // Lighter pink

// ============================================================================
// Layout Constants (reference positions on 480x480 screen)
// ============================================================================

#define SCR_W  480
#define SCR_H  480

// Eyes
#define EYE_L_X    165       // Left eye center X
#define EYE_L_Y    195       // Left eye center Y
#define EYE_R_X    315       // Right eye center X
#define EYE_R_Y    195       // Right eye center Y
#define EYE_RX     32        // Eye ellipse horizontal radius
#define EYE_RY     40        // Eye ellipse vertical radius
#define PUPIL_R    14        // Pupil radius
#define HIGHLIGHT_R 5        // Eye highlight radius

// Mouth
#define MOUTH_X    240       // Mouth center X
#define MOUTH_Y    310       // Mouth center Y
#define MOUTH_RX   48        // Mouth horizontal radius (width)
#define MOUTH_RY_CLOSED  4   // Mouth vertical radius when closed
#define MOUTH_RY_OPEN    34  // Mouth vertical radius when fully open
#define SMILE_DEPTH      10  // Depth of smile curve (pixels)

// Hearts
#define MAX_HEARTS  6
#define HEART_SIZE  18       // Base heart size in pixels

// Animation
#define FLOAT_AMP    5.0f    // Maximum floating amplitude (pixels)
#define BLINK_DUR_MS 250     // Blink duration (milliseconds)
#define FRAME_MS     25      // Target frame interval (40fps)

// ============================================================================
// State
// ============================================================================

static uint16_t *face_fb = NULL;       // Framebuffer in PSRAM
static bool      s_enabled = false;
static float     s_mouth_open = 0.0f;  // 0.0 - 1.0
static float     s_love = 0.0f;        // 0.0 - 1.0
static unsigned long s_start_ms = 0;
static unsigned long s_last_frame_ms = 0;

// Blink state
static bool          s_blinking = false;
static unsigned long s_blink_start = 0;
static unsigned long s_next_blink = 0;

// Heart objects
struct Heart {
    float baseX;    // Reference X for sway calculation
    float x, y;     // Current screen position
    float phase;    // Sway phase offset
    float speed;    // Upward speed (pixels per frame)
    float size;     // Heart radius
    bool  active;   // Currently alive and on screen
};
static Heart s_hearts[MAX_HEARTS];

// ============================================================================
// Drawing Primitives
// ============================================================================

// Set a single pixel (bounds-checked)
static inline void setPixel(int x, int y, uint16_t color) {
    if ((unsigned)x < SCR_W && (unsigned)y < SCR_H) {
        face_fb[y * SCR_W + x] = color;
    }
}

// Draw a horizontal span [x1..x2] at row y (clipped)
static inline void hLine(int x1, int x2, int y, uint16_t color) {
    if (y < 0 || y >= SCR_H) return;
    if (x1 > x2) { int t = x1; x1 = x2; x2 = t; }
    if (x1 < 0)      x1 = 0;
    if (x2 >= SCR_W)  x2 = SCR_W - 1;
    uint16_t *row = &face_fb[y * SCR_W];
    for (int x = x1; x <= x2; x++) {
        row[x] = color;
    }
}

// Filled ellipse via scanline
static void fillEllipse(int cx, int cy, int rx, int ry, uint16_t color) {
    if (rx <= 0 || ry <= 0) return;
    float inv_ry2 = 1.0f / ((float)ry * (float)ry);
    for (int dy = -ry; dy <= ry; dy++) {
        float ratio = 1.0f - (float)(dy * dy) * inv_ry2;
        if (ratio <= 0.0f) continue;
        int dx = (int)(rx * sqrtf(ratio));
        hLine(cx - dx, cx + dx, cy + dy, color);
    }
}

// Filled circle
static void fillCircle(int cx, int cy, int r, uint16_t color) {
    fillEllipse(cx, cy, r, r, color);
}

// Filled heart using implicit equation: (x²+y²-1)³ - x²y³ ≤ 0
// Heart has bumps at top, point at bottom (conventional orientation).
static void fillHeart(int cx, int cy, float size, uint16_t color) {
    int sz = (int)(size + 0.5f);
    float inv_sz = 1.0f / size;
    for (int dy = -sz; dy <= sz; dy++) {
        for (int dx = -sz; dx <= sz; dx++) {
            float nx = (float)dx * inv_sz;
            float ny = -(float)dy * inv_sz;  // Flip Y: screen-down → math-up
            float x2 = nx * nx;
            float y2 = ny * ny;
            float inner = x2 + y2 - 1.0f;
            if (inner * inner * inner - x2 * y2 * ny <= 0.0f) {
                setPixel(cx + dx, cy + dy, color);
            }
        }
    }
}

// ============================================================================
// Floating Animation Helper
// ============================================================================

// Computes organic floating offsets using layered sine waves.
// Each element uses different freq/phase for independent motion.
static void calcFloat(float t, float freqX, float freqY,
                      float phaseX, float phaseY, float amp,
                      float *outX, float *outY) {
    *outX = sinf(t * freqX + phaseX) * amp
          + sinf(t * freqX * 1.7f + phaseX * 2.3f) * amp * 0.3f;
    *outY = sinf(t * freqY + phaseY) * amp
          + cosf(t * freqY * 1.3f + phaseY * 1.7f) * amp * 0.3f;
}

// ============================================================================
// Heart System
// ============================================================================

static void spawnHeart(Heart &h, float t) {
    h.baseX  = 50.0f + (float)(random(380));
    h.y      = (float)SCR_H + (float)(random(60));
    h.phase  = t + (float)(random(628)) / 100.0f;
    h.speed  = 0.7f + (float)(random(50)) / 100.0f;
    h.size   = (float)(HEART_SIZE - 3 + random(7));
    h.x      = h.baseX;
    h.active = true;
}

static void updateHearts(float t) {
    int num_wanted = (int)(s_love * MAX_HEARTS + 0.5f);
    if (num_wanted > MAX_HEARTS) num_wanted = MAX_HEARTS;

    for (int i = 0; i < MAX_HEARTS; i++) {
        Heart &h = s_hearts[i];
        bool should_be_active = (i < num_wanted);

        if (should_be_active) {
            if (!h.active) {
                // Newly activated — spawn at bottom
                spawnHeart(h, t);
            }
            // Float upward
            h.y -= h.speed;
            // Horizontal sway
            h.x = h.baseX + sinf(t * 0.8f + h.phase) * 22.0f;
            // Respawn when off top
            if (h.y < -40.0f) {
                spawnHeart(h, t);
            }
        } else {
            // Not wanted — let it drift off if still on screen
            if (h.active) {
                h.y -= h.speed;
                h.x = h.baseX + sinf(t * 0.8f + h.phase) * 22.0f;
                if (h.y < -40.0f) {
                    h.active = false;  // Truly deactivated after exiting top
                }
            }
        }
    }
}

static void drawHearts() {
    for (int i = 0; i < MAX_HEARTS; i++) {
        Heart &h = s_hearts[i];
        if (!h.active) continue;
        if (h.y < -35.0f || h.y > SCR_H + 35.0f) continue;

        // Gentle size pulse
        float pulse = 1.0f + sinf((float)millis() / 500.0f + h.phase) * 0.08f;
        float sz = h.size * pulse;

        // Alternate color shades for variety
        uint16_t col = (i % 2 == 0) ? COL_HEART_A : COL_HEART_B;
        fillHeart((int)h.x, (int)h.y, sz, col);
    }
}

// ============================================================================
// Face Element Drawing
// ============================================================================

static void drawEye(int baseX, int baseY, float fx, float fy, float blinkFactor) {
    int cx = baseX + (int)fx;
    int cy = baseY + (int)fy;

    // Blink squishes the eye vertically
    int ry = (int)(EYE_RY * (1.0f - blinkFactor * 0.93f));
    if (ry < 2) ry = 2;

    // White sclera
    fillEllipse(cx, cy, EYE_RX, ry, COL_EYE_WHITE);

    // Pupil and highlight only when eye is sufficiently open
    if (ry > 10) {
        // Pupil — sits slightly below center for a natural look
        // Subtle slow drift in a lissajous pattern (eyes "looking around")
        float t = (float)(millis() - s_start_ms) / 1000.0f;
        float lookX = sinf(t * 0.3f) * 3.0f;
        float lookY = cosf(t * 0.22f) * 2.0f;
        int pupilRy = (int)((float)PUPIL_R * (float)ry / (float)EYE_RY);
        if (pupilRy < 4) pupilRy = 4;
        fillCircle(cx + (int)lookX, cy + 2 + (int)lookY,
                   min(PUPIL_R, pupilRy), COL_PUPIL);

        // Highlight sparkle — upper-left of eye
        fillCircle(cx - 7, cy - 8, HIGHLIGHT_R, COL_HIGHLIGHT);
    }
}

static void drawMouth(int baseX, int baseY, float fx, float fy, float openness) {
    int cx = baseX + (int)fx;
    int cy = baseY + (int)fy;
    int rx = MOUTH_RX;

    if (openness < 0.12f) {
        // === Smile mode: bottom arc of a large circle ===
        // Traces a downward curve from left to right — a gentle smile.
        int thickness = 3;
        for (int dx = -rx; dx <= rx; dx++) {
            float frac = (float)dx / (float)rx;
            float curve = sqrtf(fmaxf(0.0f, 1.0f - frac * frac));
            int dy = (int)(curve * SMILE_DEPTH);
            for (int t = 0; t < thickness; t++) {
                setPixel(cx + dx, cy + dy + t, COL_MOUTH);
            }
        }
    } else {
        // === Open mouth: filled ellipse ===
        int ry = MOUTH_RY_CLOSED + (int)((float)(MOUTH_RY_OPEN - MOUTH_RY_CLOSED) * openness);
        if (ry < 4) ry = 4;

        // Outer lips
        fillEllipse(cx, cy, rx, ry, COL_MOUTH);

        // Dark interior (only when mouth is open enough)
        if (ry > 8) {
            fillEllipse(cx, cy, rx - 5, ry - 5, COL_MOUTH_DARK);
        }
    }
}

// ============================================================================
// Public API
// ============================================================================

bool face_init() {
    size_t fb_size = SCR_W * SCR_H * sizeof(uint16_t);
    face_fb = (uint16_t *)heap_caps_malloc(fb_size, MALLOC_CAP_SPIRAM);
    if (!face_fb) return false;

    // Seed RNG with hardware random
    randomSeed(esp_random());

    s_start_ms = millis();
    s_next_blink = s_start_ms + 3000 + random(4000);

    // Initialize hearts as inactive
    for (int i = 0; i < MAX_HEARTS; i++) {
        s_hearts[i].active = false;
    }

    return true;
}

void face_set_enabled(bool en) {
    s_enabled = en;
    if (en) {
        s_start_ms = millis();
        s_last_frame_ms = 0;
        s_next_blink = millis() + 2000 + random(3000);
    }
}

bool face_is_enabled() {
    return s_enabled;
}

void face_set_mouth(float open) {
    s_mouth_open = constrain(open, 0.0f, 1.0f);
}

float face_get_mouth() {
    return s_mouth_open;
}

void face_set_love(float value) {
    s_love = constrain(value, 0.0f, 1.0f);
}

float face_get_love() {
    return s_love;
}

void face_blink() {
    if (!s_blinking) {
        s_blinking = true;
        s_blink_start = millis();
    }
}

void face_update() {
    if (!s_enabled || !face_fb) return;

    // Frame rate limiter
    unsigned long now = millis();
    if (now - s_last_frame_ms < FRAME_MS) return;
    s_last_frame_ms = now;

    float t = (float)(now - s_start_ms) / 1000.0f;

    // --- Blink logic ---
    float blink_factor = 0.0f;
    if (s_blinking) {
        float bt = (float)(now - s_blink_start) / (float)BLINK_DUR_MS;
        if (bt >= 1.0f) {
            s_blinking = false;
            s_next_blink = now + 2500 + random(4500);
        } else if (bt < 0.25f) {
            blink_factor = bt / 0.25f;          // Closing
        } else if (bt < 0.45f) {
            blink_factor = 1.0f;                // Held shut
        } else {
            blink_factor = 1.0f - (bt - 0.45f) / 0.55f;  // Opening (slower)
        }
    } else if (now >= s_next_blink) {
        s_blinking = true;
        s_blink_start = now;
    }

    // --- Clear framebuffer (fast 32-bit fill) ---
    {
        uint32_t fill32 = ((uint32_t)COL_BG << 16) | COL_BG;
        uint32_t *p = (uint32_t *)face_fb;
        int count = SCR_W * SCR_H / 2;
        for (int i = 0; i < count; i++) {
            p[i] = fill32;
        }
    }

    // --- Calculate floating offsets for each element ---
    float leX, leY;  // Left eye float offset
    float reX, reY;  // Right eye float offset
    float mX, mY;    // Mouth float offset
    calcFloat(t, 0.71f, 0.53f, 0.0f,  0.5f,  FLOAT_AMP,        &leX, &leY);
    calcFloat(t, 0.71f, 0.53f, 1.05f, 1.55f, FLOAT_AMP,        &reX, &reY);
    calcFloat(t, 0.62f, 0.41f, 2.1f,  2.6f,  FLOAT_AMP * 0.7f, &mX,  &mY);

    // --- Draw face elements (back to front) ---

    // Eyes
    drawEye(EYE_L_X, EYE_L_Y, leX, leY, blink_factor);
    drawEye(EYE_R_X, EYE_R_Y, reX, reY, blink_factor);

    // Mouth
    drawMouth(MOUTH_X, MOUTH_Y, mX, mY, s_mouth_open);

    // Hearts (drawn on top of everything)
    updateHearts(t);
    drawHearts();

    // --- Push framebuffer to display ---
    display_draw_fullscreen(face_fb);
}
