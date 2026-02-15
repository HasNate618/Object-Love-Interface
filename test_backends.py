#!/usr/bin/env python3
"""Test both backends: Node.js Express + WiFi SenseCAP"""

import sys
import requests
from pipeline.wifi_link import WiFiLink

print("=" * 60)
print("  BACKEND VERIFICATION TEST")
print("=" * 60)

# Test 1: Node.js Express server
print("\n[1] Testing Node.js Express server on http://localhost:3000...")
try:
    resp = requests.get("http://localhost:3000", timeout=3)
    print(f"    ✓ Server responded with status {resp.status_code}")
except requests.exceptions.ConnectionError:
    print(f"    ✗ Cannot connect to Node.js server")
    print(f"      Make sure 'node index.js' is running in image_to_voice/")
    sys.exit(1)
except Exception as e:
    print(f"    ✗ Error: {e}")
    sys.exit(1)

# Test 2: WiFi SenseCAP
print("\n[2] Testing WiFi SenseCAP on sensecap.local:7777...")
try:
    link = WiFiLink("sensecap.local", timeout=2)
    link.connect()
    resp = link.send_cmd({"cmd": "wifi"})
    ip = resp.get("ip", "?")
    print(f"    ✓ SenseCAP connected at {ip}")
    link.close()
except Exception as e:
    print(f"    ✗ Cannot connect to SenseCAP: {e}")
    print(f"      Make sure firmware is flashed and WiFi configured")
    sys.exit(1)

print("\n" + "=" * 60)
print("  ✓ ALL BACKENDS RUNNING")
print("=" * 60)
print("\nReady to run:")
print("  python pipeline/date_pipeline.py --wifi sensecap.local")
print("  python pipeline/conversation.py --wifi sensecap.local")
print()
