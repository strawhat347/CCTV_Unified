from ultralytics import YOLO
import sys
model = YOLO(r'runs\detect\unified_alpr_v2_medium\weights\best.pt')
print('Classes:', model.names)
