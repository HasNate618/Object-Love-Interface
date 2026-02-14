"""Generate a test image and send it to the SenseCAP Indicator display."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sensecap_controller import SenseCapController
from PIL import Image, ImageDraw, ImageFont

port = sys.argv[1] if len(sys.argv) > 1 else "COM6"

# Generate a 480x480 test pattern
img = Image.new("RGB", (480, 480), "#1a1a2e")
draw = ImageDraw.Draw(img)

# Color bars
colors = ["#FF0000", "#FF8800", "#FFFF00", "#00FF00", "#0088FF", "#8800FF", "#FF00FF"]
bar_h = 40
for i, c in enumerate(colors):
    y = 60 + i * bar_h
    draw.rectangle([40, y, 440, y + bar_h - 4], fill=c)

# Gradient circle
for r in range(120, 0, -1):
    shade = int(255 * r / 120)
    draw.ellipse([240-r, 360-r, 240+r, 360+r], fill=(shade, 0, 255-shade))

# Text (using default font)
try:
    font = ImageFont.truetype("arial.ttf", 28)
except:
    font = ImageFont.load_default()
draw.text((100, 10), "SenseCAP Display Test", fill="#FFFFFF", font=font)
draw.text((120, 440), "480x480 JPEG Image", fill="#AAAAAA", font=font)

# Save test image
test_path = os.path.join(os.path.dirname(__file__), "..", "Media", "test_pattern.jpg")
os.makedirs(os.path.dirname(test_path), exist_ok=True)
img.save(test_path, quality=90)
print(f"Test image saved to {test_path}")

# Send to display
print(f"Connecting to {port}...")
ctrl = SenseCapController(port)
print("Sending image...")
resp = ctrl.show_image(img, quality=90)
print(f"Response: {resp}")
ctrl.close()
print("Done!")
