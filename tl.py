#!/usr/bin/env python3

import os
import re
import cv2
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "timelapse")
OUTPUT_VIDEO_DIR = os.path.join(IMAGES_DIR, "video")
OUTPUT_VIDEO = os.path.join(OUTPUT_VIDEO_DIR, "timelapse.mp4")
FPS = 10

font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 1.5
font_color = (0, 255, 0)
thickness = 3
margin = 10

# Filename format: 01-06-2025-11:30:21_GrowName_21.3C_67.0p.jpg
filename_pattern = re.compile(
    r"(?P<ts>\d{2}-\d{2}-\d{4}-\d{2}:\d{2}:\d{2})_(?P<grow>.*?)_(?P<temp>[\d.]+C)_(?P<hum>[\d.]+p)"
)

def main():
    print("🚀 Starting timelapse generation...")

    if not os.path.exists(IMAGES_DIR):
        print(f"❌ Directory not found: {IMAGES_DIR}")
        return

    os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)

    images = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.lower().endswith(".jpg")
    ])

    print(f"📸 {len(images)} images found.")

    if not images:
        print("❌ No JPG images found in directory.")
        return

    first_path = os.path.join(IMAGES_DIR, images[0])
    first_frame = cv2.imread(first_path)
    if first_frame is None:
        print(f"❌ Error loading first image: {first_path}")
        return

    height, width, _ = first_frame.shape
    print(f"🖼️ Resolution detected: {width}x{height}")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, FPS, (width, height))

    for filename in images:
        filepath = os.path.join(IMAGES_DIR, filename)
        frame = cv2.imread(filepath)

        if frame is None:
            print(f"⚠️ Error loading: {filename}")
            continue

        match = filename_pattern.search(filename)
        if match:
            try:
                dt = datetime.strptime(match.group("ts"), "%d-%m-%Y-%H:%M:%S")
                timestamp_str = dt.strftime("%d.%m.%Y %H:%M:%S")
                temp = match.group("temp") if match.group("temp") else "??C"
                hum = match.group("hum").replace("p", "%") if match.group("hum") else "??%"
                text_lines = [timestamp_str, f"{temp} | {hum}"]
            except:
                text_lines = [filename]
        else:
            text_lines = [filename]

        for i, line in enumerate(reversed(text_lines)):
            text_size, _ = cv2.getTextSize(line, font, font_scale, thickness)
            text_x = width - text_size[0] - margin
            text_y = height - margin - (i * (text_size[1] + margin))

            cv2.putText(frame, line, (text_x + 2, text_y + 2),
                        font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)

            cv2.putText(frame, line, (text_x, text_y),
                        font, font_scale, font_color, thickness, cv2.LINE_AA)

        video.write(frame)

    video.release()
    print(f"✅ Timelapse saved: {OUTPUT_VIDEO}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Script error: {e}")
