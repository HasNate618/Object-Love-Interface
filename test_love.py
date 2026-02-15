#!/usr/bin/env python3
"""Quick test: send love value over WiFi"""

from pipeline.wifi_link import WiFiLink

link = WiFiLink("sensecap.local")
link.connect()

print("[Test] Sending love value = 1...")
resp = link.send_cmd({"cmd": "love", "value": 1})
print(f"[Test] Response: {resp}")

link.close()
print("[Test] Done!")
