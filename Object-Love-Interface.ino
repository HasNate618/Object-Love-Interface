#include <SPI.h>
#include <Adafruit_PN532.h>

#define PN532_SCK  (18)
#define PN532_MISO (19)
#define PN532_MOSI (23)
#define PN532_SS   (5)

Adafruit_PN532 nfc(PN532_SS);

void setup(void) {
  Serial.begin(115200);
  nfc.begin();
  
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.print("PN532 not found!");
    while (1);
  }
  nfc.SAMConfig();
}

void loop(void) {
  uint8_t success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };
  uint8_t uidLength;

  Serial.println("Waiting for card to write text...");
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength);

  if (success) {
    // 1. Authenticate Block 4 (First data block) with default Key A (0xFF...)
    uint8_t keya[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
    success = nfc.mifareclassic_AuthenticateBlock(uid, uidLength, 4, 0, keya);

    if (success) {
      // 2. Prepare 16 bytes of text (Mifare blocks are exactly 16 bytes)
      // "Plain Text Data " (16 chars)
      uint8_t data[16] = "Hello ESP32 SPI"; 

      // 3. Write data to Block 4
      success = nfc.mifareclassic_WriteDataBlock(4, data);

      if (success) {
        Serial.println("Successfully wrote text to Block 4!");
      } else {
        Serial.println("Write failed.");
      }
    } else {
      Serial.println("Authentication failed. Is the key correct?");
    }
    delay(3000);
  }
}