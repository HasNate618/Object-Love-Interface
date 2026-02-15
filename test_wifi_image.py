#!/usr/bin/env python3
"""Test JPEG image transfer over WiFi"""

import sys
from pathlib import Path
from pipeline.wifi_link import WiFiLink
from PIL import Image, ImageDraw

# Generate a simple test image
print("[Test] Generating test JPEG...")
img = Image.new("RGB", (480, 480), color=(50, 100, 200))
draw = ImageDraw.Draw(img)
draw.text((200, 220), "WiFi Test", fill=(255, 255, 255))

# Convert to JPEG bytes
import io
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=85)
jpeg_bytes = buf.getvalue()
print(f"[Test] Generated {len(jpeg_bytes)} bytes of JPEG")

# Connect and send
print("\n[Test] Connecting to sensecap.local...")
try:
    link = WiFiLink("sensecap.local")
    link.connect()
    print("[Test] Connected!")
    
    # Send the test image
    print(f"\n[Test] Sending {len(jpeg_bytes)} byte JPEG image...")
    resp = link.send_jpeg(jpeg_bytes)
    print(f"[Test] Response: {resp}")
    
    if resp.get("status") == "ok":
        print("\n[Test] ✓ SUCCESS: Image transferred over WiFi!")
    else:
        print(f"\n[Test] ✗ FAILED: {resp}")
        sys.exit(1)
    
    link.close()
    
except Exception as e:
    print(f"[Test] ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
