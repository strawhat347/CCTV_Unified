import os
import random
import string
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import multiprocessing
from functools import partial
from pathlib import Path
from tqdm import tqdm

# --- Configuration ---
NUM_IMAGES = 60000  # 30k GJ + 10k BH + 20k Other
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic_plates" / "images"
GT_FILE = PROJECT_ROOT / "data" / "synthetic_plates" / "rec_gt.txt"
FONT_PATH = PROJECT_ROOT / "data" / "fonts" / "CharlesWright-Bold.otf"

# Ensure directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load Font globally for worker processes
try:
    plate_font = ImageFont.truetype(str(FONT_PATH), 70)
except Exception as e:
    print(f"Error loading Charles Wright font: {e}")
    plate_font = ImageFont.load_default()

def generate_text():
    """Generates strictly compliant Indian plate syntaxes based on true RTO limits."""
    # Exact RTO max limits per state
    state_rto_limits = {
        'MH': 50, 'DL': 13, 'KA': 71, 'HR': 99, 
        'UP': 96, 'RJ': 58, 'TN': 99, 'KL': 86, 'MP': 74
    }
    
    # Weights: GJ (50%), BH (16.6%), Other (33.4%)
    plate_type = random.choices(['GJ', 'BH', 'OTHER'], weights=[50, 16.6, 33.4], k=1)[0]
    
    # 'I' and 'O' are legally banned in Indian plate series letters, so we remove them
    valid_letters = [c for c in string.ascii_uppercase if c not in ('I', 'O')]
    
    # Only keep legal confounding pairs (I and O are banned in series)
    # Added extended pairs to cover all common OCR failure cases in Charles Wright font
    confounding_pairs = [
        ('8', 'B'), ('3', 'E'), ('2', 'Z'), ('5', 'S'), ('0', 'D'),
        ('6', 'G'), ('7', 'T'), ('0', 'Q'), ('0', 'C'), ('1', 'T'),
        ('9', 'P'), ('4', 'A'), ('8', 'R')
    ]
    use_confusing = random.random() > 0.5
    num_char, let_char = random.choice(confounding_pairs)

    if plate_type == 'BH':
        year = random.randint(21, 24)
        
        number_chars = []
        for _ in range(4):
            if use_confusing and random.random() > 0.4:
                number_chars.append(num_char)
            else:
                number_chars.append(str(random.randint(0,9)))
        number = "".join(number_chars)
        
        # Enforce strict 2-letter series
        series_len = 2
        series_chars = []
        for _ in range(series_len):
            if use_confusing and random.random() > 0.4:
                series_chars.append(let_char)
            else:
                series_chars.append(random.choice(valid_letters))
        series = "".join(series_chars)
        
        return f"{year} BH {number} {series}"
        
    else:
        if plate_type == 'GJ':
            state = "GJ"
            rto_max = 38
        else:
            state = random.choice(list(state_rto_limits.keys()))
            rto_max = state_rto_limits[state]
            
        rto = f"{random.randint(1, rto_max):02d}"
        
        # Enforce strict 2-letter series
        series_len = 2
        series_chars = []
        for _ in range(series_len):
            if use_confusing and random.random() > 0.4:
                series_chars.append(let_char)
            else:
                series_chars.append(random.choice(valid_letters))
        series = "".join(series_chars)
        
        number_chars = []
        for _ in range(4):
            if use_confusing and random.random() > 0.4:
                number_chars.append(num_char)
            else:
                number_chars.append(str(random.randint(0,9)))
        number = "".join(number_chars)
            
        return f"{state} {rto} {series} {number}"

def apply_real_world_degradation(cv_img):
    h, w = cv_img.shape[:2]

    # 1. Perspective Warp (Simulating camera angle)
    src_pts = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    max_shift = 15
    dst_pts = np.float32([
        [random.randint(0, max_shift), random.randint(0, max_shift)],
        [w - random.randint(0, max_shift), random.randint(0, max_shift)],
        [random.randint(0, max_shift), h - random.randint(0, max_shift)],
        [w - random.randint(0, max_shift), h - random.randint(0, max_shift)]
    ])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    cv_img = cv2.warpPerspective(cv_img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    # 2. Shadows (Bumper overhang or uneven lighting)
    if random.random() > 0.3:
        shadow = np.zeros((h, w, 3), dtype=np.uint8)
        # Create a random dark polygon
        pt1 = (random.randint(0, w), 0)
        pt2 = (random.randint(0, w), h)
        pt3 = (0, h)
        pt4 = (0, 0)
        pts = np.array([pt1, pt2, pt3, pt4])
        cv2.fillPoly(shadow, [pts], (1, 1, 1))
        
        alpha = random.uniform(0.3, 0.7)
        # Apply shadow only where polygon is
        cv_img = np.where(shadow == 1, cv2.addWeighted(cv_img, alpha, np.zeros_like(cv_img), 0, 0), cv_img)

    # 3. Brightness & Contrast (Night vs Sun Glare)
    is_night = random.random() > 0.5
    if is_night:
        alpha_c = random.uniform(0.4, 0.8) # Lower contrast
        beta_c = random.randint(-60, -10)  # Darker
    else:
        alpha_c = random.uniform(1.0, 1.4) # Higher contrast
        beta_c = random.randint(10, 60)    # Brighter (Glare)
    cv_img = cv2.convertScaleAbs(cv_img, alpha=alpha_c, beta=beta_c)

    # 4. Dirt, Mud, & Covered Edges
    if random.random() > 0.4:
        for _ in range(random.randint(2, 8)):
            cx, cy = random.randint(0, w), random.randint(0, h)
            radius = random.randint(3, 12)
            color = (random.randint(20,50), random.randint(30,60), random.randint(40,70)) # Dirt brown/grey
            cv2.circle(cv_img, (cx, cy), radius, color, -1)
            # Blur the dirt so it looks organic
            cv_img = cv2.GaussianBlur(cv_img, (5, 5), 0)

    # 5. Gaussian Noise (Cheap Camera Static) & Motion Blur
    mean = 0
    var = random.randint(5, 30)
    sigma = var**0.5
    gauss = np.random.normal(mean, sigma, (h, w, 3)).astype(np.float32)
    cv_img = cv_img.astype(np.float32) + gauss
    cv_img = np.clip(cv_img, 0, 255).astype(np.uint8)

    # Motion Blur
    if random.random() > 0.5:
        k_size = random.choice([3, 5, 7])
        kernel = np.zeros((k_size, k_size))
        kernel[int((k_size-1)/2), :] = np.ones(k_size)
        kernel /= k_size
        cv_img = cv2.filter2D(cv_img, -1, kernel)

    return cv_img

def generate_single_image(idx):
    text = generate_text()
    
    # Standard elongated plate dimensions (matches OCR input size aspect ratio)
    width, height = 700, 150
    
    # 70% White (Private), 30% Yellow (Commercial)
    bg_color = (255, 255, 255) if random.random() > 0.3 else (255, 215, 0)
    
    img_pil = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img_pil)
    
    # Draw standard black border
    draw.rectangle([0, 0, width-1, height-1], outline="black", width=4)
    
    # Center text
    bbox = draw.textbbox((0,0), text, font=plate_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    # Sometimes fonts have negative offsets (bearings) that shift them left
    x = (width - text_w) / 2 - bbox[0]
    y = (height - text_h) / 2 - bbox[1] - 8 # Slight vertical offset adjustment for Charles Wright
    
    draw.text((x, y), text, fill="black", font=plate_font)
    
    # Convert to OpenCV for advanced degradation
    cv_img = np.array(img_pil)
    cv_img = cv_img[:, :, ::-1].copy() # RGB to BGR
    
    # Apply heavy real-world effects
    final_cv_img = apply_real_world_degradation(cv_img)
    
    # Save Image
    filename = f"syn_{idx:06d}.jpg"
    filepath = OUTPUT_DIR / filename
    cv2.imwrite(str(filepath), final_cv_img)
    
    # Return formatted ground truth line for PaddleOCR
    # Format: relative_path\tLABEL\n
    return f"images/{filename}\t{text}\n"

def main():
    print(f"Starting advanced synthetic generation of {NUM_IMAGES} images...")
    print(f"Using font: {FONT_PATH.name}")
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Multiprocessing for speed
    num_cores = max(1, multiprocessing.cpu_count() - 1)
    print(f"Running on {num_cores} CPU cores...")
    
    gt_lines = []
    
    # Use ProcessPoolExecutor for massive parallelism
    with multiprocessing.Pool(processes=num_cores) as pool:
        # Wrap with tqdm for a beautiful progress bar
        for result in tqdm(pool.imap(generate_single_image, range(NUM_IMAGES)), total=NUM_IMAGES):
            gt_lines.append(result)
            
    # Save Ground Truth text file
    with open(GT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(gt_lines)
        
    print(f"\nDone! Generated {NUM_IMAGES} images.")
    print(f"Ground truth saved to: {GT_FILE}")

if __name__ == "__main__":
    main()
