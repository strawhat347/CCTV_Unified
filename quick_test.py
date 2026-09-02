import cv2
import config
from pathlib import Path
import sys

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from detection.hierarchical_detector import HierarchicalDetector
from detection.paddle_ocr_engine import PaddleOcrEngine

# 1. Define where your test image is saved
# Save a picture of an Indian car or motorcycle from Google to your desktop, and paste the path here:
IMAGE_PATH = r"D:\Projects\CCTV_Unified\test_images\IMG-20260822-WA0001.jpg" 

def main():
    print(f"\n--- Loading image from: {IMAGE_PATH} ---")
    frame = cv2.imread(IMAGE_PATH)
    if frame is None:
        print("Error: Could not find the image! Check the path in IMAGE_PATH.")
        return

    # 2. Load the AI Brains (Pointing to the newly trained Medium model!)
    print("Loading YOLO AI (Medium Model)...")
    detector = HierarchicalDetector(vehicle_model_path=config.VEHICLE_MODEL_PATH)
    detector.load_model(r"D:\Projects\CCTV_Unified\runs\detect\unified_alpr_v2_medium\weights\best.pt")
    
    print("Loading PaddleOCR Engine...")
    ocr = PaddleOcrEngine()
    ocr.load_model()

    # 3. Detect the Plates
    print("\nScanning image for plates...")
    plate_boxes = detector.detect(frame)

    if not plate_boxes:
        print("No plates found in this image.")
        return

    print(f"Found {len(plate_boxes)} plate(s)! Reading text...")
    
    # 4. Read the text with OCR
    for i, box in enumerate(plate_boxes):
        crop = frame[int(box.y1):int(box.y2), int(box.x1):int(box.x2)]
        
        # Pass the cropped picture of the plate to OCR
        ocr_result = ocr.read_text(crop)
        
        print(f"\n--- Plate {i+1} ---")
        print(f"YOLO Confidence: {box.confidence:.2f}")
        
        if ocr_result:
            print(f"OCR Read: {ocr_result.text}")
            print(f"OCR Confidence: {ocr_result.confidence:.2f}")
        else:
            print("OCR Read: [No text found]")
            print("OCR Confidence: N/A")
        
        # Save the crop so you can look at it
        crop_path = f"plate_crop_{i+1}.jpg"
        cv2.imwrite(crop_path, crop)
        print(f"Saved cropped plate picture to: D:\\Projects\\CCTV_Unified\\{crop_path}")

if __name__ == "__main__":
    main()
