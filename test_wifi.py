#!/usr/bin/env python3
"""Quick test of WiFiLink communication with SenseCAP"""

import sys
from pipeline.wifi_link import WiFiLink

print("[Test] Connecting to sensecap.local...")
try:
    link = WiFiLink("sensecap.local")
    link.connect()
    print("[Test] Connected!")
    
    # Test 1: Get WiFi info
    print("\n[Test] Sending wifi command...")
    resp = link.send_cmd({"cmd": "wifi"})
    print(f"[Test] Response: {resp}")
    
    # Test 2: Face on
    print("\n[Test] Enabling face mode...")
    resp = link.send_cmd({"cmd": "face", "on": True})
    print(f"[Test] Response: {resp}")
    
    # Test 3: Mouth movement
    print("\n[Test] Testing mouth control...")
    resp = link.send_cmd({"cmd": "mouth", "open": 0.5})
    print(f"[Test] Response: {resp}")
    
    # Test 4: Check events
    print("\n[Test] Collecting events...")
    events = link.collect_events()
    print(f"[Test] Events: {events}")
    
    link.close()
    print("\n[Test] ✓ SUCCESS: WiFi communication with SenseCAP is working!")
    
except Exception as e:
    print(f"[Test] ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
