import cv2
import numpy as np
import os
from pathlib import Path

base = str(Path(__file__).resolve().parent.parent / "data" / "mock_videos")
os.makedirs(base, exist_ok=True)

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
fps = 15
width, height = 640, 480
frames = int(3 * fps)  # 3 seconds

for name in ['camera_1_gate.mp4', 'camera_2_lobby.mp4', 'camera_3_test.mp4']:
    out_path = os.path.join(base, name)
    out = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
    for _ in range(frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)  # black frame
        out.write(frame)
    out.release()
    print('created', out_path)
