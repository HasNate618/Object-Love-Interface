#!/usr/bin/env python3
"""Find working camera indices and basic stream info (Raspberry Pi + USB cams)."""

import os
import sys

try:
    import cv2
except ImportError:
    print("OpenCV not installed. Run: pip install opencv-python")
    sys.exit(1)


def try_open(index: int, backend: int) -> tuple[bool, str]:
    cap = cv2.VideoCapture(index, backend)
    ok = cap.isOpened()
    info = ""
    if ok:
        ret, frame = cap.read()
        if ret and frame is not None:
            h, w = frame.shape[:2]
            info = f"{w}x{h}"
        else:
            ok = False
    cap.release()
    return ok, info


def main():
    max_index = 8
    backends = [(cv2.CAP_V4L2, "V4L2"), (cv2.CAP_GSTREAMER, "GStreamer"), (cv2.CAP_FFMPEG, "FFmpeg")]

    print("Scanning /dev/video*:")
    for name in sorted([n for n in os.listdir("/dev") if n.startswith("video")]):
        print(f"  /dev/{name}")

    print("\nProbing camera indices...")
    found = []
    for idx in range(max_index):
        for backend, label in backends:
            ok, info = try_open(idx, backend)
            if ok:
                found.append((idx, label, info))
                print(f"  idx={idx} backend={label} OK {info}")
                break
        else:
            print(f"  idx={idx} not open")

    if not found:
        print("\nNo cameras opened. Try:")
        print("  sudo usermod -aG video $USER ; newgrp video")
        print("  sudo apt install v4l-utils")
        sys.exit(1)

    print("\nSuggested command:")
    print(f"  python pipeline/date_pipeline.py --wifi sensecap.local --camera {found[0][0]}")


if __name__ == "__main__":
    main()
