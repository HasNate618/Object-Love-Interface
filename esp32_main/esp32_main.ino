#include <Wire.h>
#include <ESP32Servo.h>
#include "rgb_lcd.h"

rgb_lcd lcd;
Servo myServo;

// servo constants
const int servoPin = 13;
const int minPulse = 500;
const int maxPulse = 2500;

// colour variables
float currentR = 255, currentG = 255, currentB = 255; // Starts White
int targetR = 255, targetG = 255, targetB = 255;
float fadeSpeed = 0.05; // Adjust this (0.01 to 0.1) for speed. Lower = Slower.

unsigned long lastFadeTime = 0;
const int fadeInterval = 15; // Smooth 60fps-ish update (15ms)

void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22);
    lcd.begin(16, 2);
    
    ESP32PWM::allocateTimer(0);
    myServo.setPeriodHertz(50);
    myServo.attach(servoPin, minPulse, maxPulse);
    
    lcd.setRGB(currentR, currentG, currentB);
    Serial.println("--- system ready ---");
}

void loop() {
    // 1. LISTEN FOR COMMANDS (Immediate)
    if (Serial.available() > 0) {
        char cmdType = Serial.read();

        if (cmdType == 'S') {
            int angle = Serial.parseInt();
            if (angle >= 0 && angle <= 270) {
                myServo.writeMicroseconds(map(angle, 0, 270, minPulse, maxPulse));
                Serial.print("SERVO -> "); Serial.println(angle);
            }
        } 
        else if (cmdType == 'C') {
            targetR = Serial.parseInt();
            targetG = Serial.parseInt();
            targetB = Serial.parseInt();
            Serial.print("COLOR -> ");
            Serial.print(targetR); Serial.print(","); Serial.print(targetG); Serial.print(","); Serial.println(targetB);
        }
        while(Serial.available() > 0) { Serial.read(); }
    }

    // 2. SMOOTH FADE LOGIC (Background)
    unsigned long now = millis();
    if (now - lastFadeTime >= fadeInterval) {
        lastFadeTime = now;

        // Move current color closer to target color slightly
        currentR += (targetR - currentR) * fadeSpeed;
        currentG += (targetG - currentG) * fadeSpeed;
        currentB += (targetB - currentB) * fadeSpeed;

        // Update the LCD
        lcd.setRGB((int)currentR, (int)currentG, (int)currentB);
    }
}