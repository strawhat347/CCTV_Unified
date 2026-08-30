import sys
from pathlib import Path
import cv2
import os

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.yolo_plate_detector import YoloPlateDetector
from detection.paddle_ocr_engine import PaddleOcrEngine
from detection.frame_sampler import FrameSampler

def main():
    base_dir = Path(__file__).parent.parent
    test_dir = base_dir / "test_images"
    output_dir = test_dir / "output"
    output_dir.mkdir(exist_ok=True)
    
    model_path = base_dir / "weights" / "yolo26n.pt"
    
    print(f"Loading YOLO model from: {model_path}")
    detector = YoloPlateDetector()
    detector.load_model(str(model_path))
    
    print("Loading OCR Engine...")
    ocr = PaddleOcrEngine()
    ocr.load_model()
    
    images = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
    if not images:
        print(f"No images found in {test_dir}")
        return
        
    print(f"Found {len(images)} images to test.")
    
    for img_path in images:
        print(f"\n--- Processing {img_path.name} ---")
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"Failed to read {img_path}")
            continue
            
        # Detect plates
        boxes = detector.detect(frame, imgsz=1280)  # using higher resolution for better detection
        print(f"Detected {len(boxes)} plates.")
        
        annotated = frame.copy()
        
        for i, box in enumerate(boxes):
            # Crop with padding
            crop = FrameSampler.crop_region(
                frame, box.x1, box.y1, box.x2, box.y2, padding=12
            )
            
            if crop.size == 0:
                continue
                
            # Read text
            ocr_result = ocr.read_text(crop)
            
            text = "No Text"
            conf = 0.0
            if ocr_result:
                text = ocr_result.text
                conf = ocr_result.confidence
                
            print(f"  Plate {i+1}: '{text}' (OCR Conf: {conf:.2f}, Det Conf: {box.confidence:.2f})")
            
            # Annotate image
            x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)
            
            # Draw text with background
            label = f"{text} ({conf:.2f})"
            (text_width, text_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
            cv2.rectangle(annotated, (x1, y1 - text_height - 10), (x1 + text_width, y1), (0, 255, 0), cv2.FILLED)
            cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
            
            # Save crop for reference
            crop_path = output_dir / f"{img_path.stem}_crop_{i}.jpg"
            cv2.imwrite(str(crop_path), crop)
            
        out_path = output_dir / img_path.name
        cv2.imwrite(str(out_path), annotated)
        print(f"Saved annotated image to {out_path}")

if __name__ == "__main__":
    main()
