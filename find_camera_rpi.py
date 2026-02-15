#!/usr/bin/env python3
"""Identify USB camera on Raspberry Pi"""

import cv2
import sys

print("Probing cameras on Raspberry Pi...")
print()

for idx in range(8):
    cap = cv2.VideoCapture(idx)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            h, w = frame.shape[:2]
            print(f"✓ Camera {idx}: {w}x{h} (device: /dev/video{idx})")
        else:
            print(f"✗ Camera {idx}: Opened but no frames")
        cap.release()

print()
print("Use the index above with --camera flag:")
print("  python pipeline/date_pipeline.py --wifi sensecap.local --camera 1")
