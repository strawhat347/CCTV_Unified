from ultralytics import YOLO
import sys
model = YOLO(r'runs\detect\unified_alpr_v1-6\weights\best.pt')
print('Classes:', model.names)
