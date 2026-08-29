import os
import random
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# --- Configuration ---
NUM_IMAGES = 50000  # Default to 500 for a quick test. Scale up to 50000 for actual training.
OUTPUT_DIR = Path("data/synthetic_plates")
FONT_PATH = "data/fonts/CharlesWright-Bold.otf" # Standard HSRP-like font

STATES = ["GJ", "MH", "DL", "KA", "TN", "UP", "HR", "WB"]
# We specifically inject hard-to-read letters to force the model to learn the difference
HARD_LETTERS = ['W', 'M', 'O', 'D', 'B', '8', '0', 'Q', 'C']

def generate_random_plate() -> str:
    """Generate a valid Indian license plate string heavily weighted with confusing characters."""
    state = random.choice(STATES)
    district = f"{random.randint(1, 99):02d}"
    
    series_len = random.randint(1, 2)
    series = "".join(random.choice(HARD_LETTERS) for _ in range(series_len))
    
    # Make sure we occasionally inject 8s and 0s into the digits
    number = ""
    for _ in range(4):
        if random.random() > 0.7:
            number += random.choice(['8', '0'])
        else:
            number += str(random.randint(1, 9))
            
    return f"{state}{district}{series}{number}"

def apply_cctv_degradation(img: np.ndarray) -> np.ndarray:
    """Simulate bad CCTV conditions: blur, noise, and harsh shadows."""
    # 1. Random Motion/Gaussian Blur
    if random.random() > 0.3:
        k = random.choice([3, 5])
        img = cv2.GaussianBlur(img, (k, k), 0)
        
    # 2. Sensor Grain (Gaussian Noise)
    if random.random() > 0.4:
        row, col, ch = img.shape
        mean = 0
        sigma = random.randint(15, 35)
        gauss = np.random.normal(mean, sigma, (row, col, ch)).reshape(row, col, ch)
        img = np.clip(img + gauss, 0, 255).astype(np.uint8)
        
    # 3. Harsh Shadows / Gradient Lighting
    if random.random() > 0.3:
        shadow = np.zeros_like(img, dtype=np.float32)
        alpha = random.uniform(0.4, 0.9)
        for i in range(img.shape[1]):
            shadow[:, i] = alpha * (i / img.shape[1])
            
        # 50% chance the shadow comes from the left instead of right
        if random.random() > 0.5:
            shadow = np.fliplr(shadow)
            
        img = np.clip(img * (1 - shadow), 0, 255).astype(np.uint8)
        
    return img

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    images_dir = OUTPUT_DIR / "images"
    images_dir.mkdir(exist_ok=True)
    
    label_file = OUTPUT_DIR / "rec_gt.txt"
    
    # Try to load the HSRP font, fallback to default if not downloaded yet
    try:
        font = ImageFont.truetype(FONT_PATH, 80)
        print(f"Loaded custom font: {FONT_PATH}")
    except IOError:
        print(f"WARNING: Font not found at {FONT_PATH}.")
        print("Using default font. For actual training, please download a 'Charles Wright' TTF font!")
        font = ImageFont.load_default()
        
    print(f"Generating {NUM_IMAGES} synthetic plates...")
    
    with open(label_file, "w", encoding="utf-8") as f:
        for i in range(NUM_IMAGES):
            plate_text = generate_random_plate()
            
            # Create a blank white or yellow plate
            bg_color = (255, 204, 0) if random.random() > 0.5 else (255, 255, 255)
            width, height = 420, 110
            img_pil = Image.new('RGB', (width, height), color=bg_color)
            draw = ImageDraw.Draw(img_pil)
            
            # Center the text
            try:
                bbox = font.getbbox(plate_text)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except AttributeError:
                # Fallback for older PIL versions
                text_w, text_h = draw.textsize(plate_text, font=font)
                
            x = (width - text_w) / 2
            y = (height - text_h) / 2 - 5
            
            # Draw black text
            draw.text((x, y), plate_text, fill=(0, 0, 0), font=font)
            
            # Convert PIL RGB to OpenCV BGR
            img_cv = np.array(img_pil)[:, :, ::-1].copy()
            
            # Apply mathematical damage (blur/shadows)
            img_cv = apply_cctv_degradation(img_cv)
            
            # Save the image
            filename = f"synthetic_{i:05d}.jpg"
            filepath = images_dir / filename
            cv2.imwrite(str(filepath), img_cv)
            
            # Write to PaddleOCR label file: filename[tab]label
            f.write(f"images/{filename}\t{plate_text}\n")
            
            if (i + 1) % 100 == 0:
                print(f"  -> Generated {i + 1}/{NUM_IMAGES} images...")
                
    print(f"\nDONE! {NUM_IMAGES} synthetic plates saved in: {OUTPUT_DIR}")
    print(f"PaddleOCR training label file saved at: {label_file}")

if __name__ == "__main__":
    main()
