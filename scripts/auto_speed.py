#!/usr/bin/env python3
"""自动变速：静止段 8x 加速，活动段保持原速，拼接输出紧凑演示视频。"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

INPUT = "/workspace/demo/paykeeper_demo_full.mp4"
OUTPUT = "/workspace/demo/paykeeper_demo_final.mp4"
FRAMES_DIR = "/tmp/vspeed_frames"
THRESHOLD = 0.8  # 相邻帧平均像素差阈值
BUFFER = 1.0      # 活动段前后缓冲秒数
STATIC_SPEED = 8  # 静止段加速倍数
FPS = 24

# 1) 逐秒抽帧
os.makedirs(FRAMES_DIR, exist_ok=True)
subprocess.run(
    ["ffmpeg", "-y", "-v", "quiet", "-i", INPUT, "-vf", "fps=1",
     f"{FRAMES_DIR}/f_%03d.png"],
    check=True,
)
import glob
files = sorted(glob.glob(f"{FRAMES_DIR}/f_*.png"))
total = len(files)
print(f"总秒数: {total}")

# 2) 检测活动秒
active = set()
prev = None
for i, f in enumerate(files):
    img = np.array(Image.open(f).convert("L"), dtype=float)
    if prev is not None and np.abs(img - prev).mean() > THRESHOLD:
        active.add(i)
        active.add(i - 1)
    prev = img

if not active:
    print("未检测到活动段，输出原视频")
    sys.exit(0)

# 3) 活动段 + 缓冲，合并成区间
active_with_buffer = set()
for s in active:
    for t in np.arange(max(0, s - BUFFER), min(total, s + BUFFER + 1)):
        active_with_buffer.add(int(t))
active_with_buffer = sorted(active_with_buffer)

segments = []  # (start_sec, end_sec, speed)
i = 0
while i < len(active_with_buffer):
    start = active_with_buffer[i]
    j = i
    while j + 1 < len(active_with_buffer) and active_with_buffer[j + 1] == active_with_buffer[j] + 1:
        j += 1
    end = active_with_buffer[j]
    segments.append((start, end + 1, 1.0))  # 活动段原速
    i = j + 1

# 中间插入静止段（加速）
merged = []
cursor = 0
for start, end, speed in segments:
    if start > cursor:
        merged.append((cursor, start, STATIC_SPEED))
    merged.append((start, end, speed))
    cursor = end
if cursor < total:
    merged.append((cursor, total, STATIC_SPEED))

print("分段计划: [start-end, speed]")
for start, end, speed in merged:
    print(f"  [{start:3d}-{end:3d}] x{speed}")

# 4) 逐段变速
part_files = []
for idx, (start, end, speed) in enumerate(merged):
    out = f"/tmp/seg_{idx}.mp4"
    part_files.append(out)
    if speed == 1.0:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(end - start),
             "-i", INPUT, "-c:v", "libopenh264", "-pix_fmt", "yuv420p",
             "-b:v", "3M", "-r", str(FPS), out], check=True)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(end - start),
             "-i", INPUT, "-filter:v", f"setpts=PTS/{speed}",
             "-c:v", "libopenh264", "-pix_fmt", "yuv420p", "-b:v", "3M",
             "-r", str(FPS), out], check=True)

# 5) 拼接
list_file = "/tmp/seg_list.txt"
with open(list_file, "w") as f:
    for p in part_files:
        f.write(f"file '{p}'\n")
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
     "-i", list_file, "-c", "copy", OUTPUT], check=True)

# 6) 时长统计
probe = subprocess.run(
    ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", OUTPUT],
    capture_output=True, text=True, check=True)
import json
dur = json.loads(probe.stdout)["format"]["duration"]
print(f"\n✅ 输出: {OUTPUT}  时长 {round(float(dur),1)} 秒")
