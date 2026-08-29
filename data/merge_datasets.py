import os
import shutil

extracted_dir = 'd:/Hackathon/CCTV_Unified/data/extracted_datasets'
unified_dir = 'd:/Hackathon/CCTV_Unified/data/unified_dataset'

# Class mapping logic
# We want: 0 -> number_plate, 1 -> vehicle
dataset_mappings = {
    '0.5k dataset': {0: 0},
    '10.1k dataset': {0: 0},
    '10k dataset': {0: 0},
    '10_2 dataset': {0: 0},
    '20k dataset': {0: 0, 1: 0}, # Both Placa and licenseplate to number_plate
    '418 dataset': {0: 0},
    'Indian Vehicle plate.v1i.yolov8': {0: 0, 1: 1} # 0 is plate, 1 is vehicle
}

# Create unified directories
splits = ['train', 'valid', 'test']
for split in splits:
    split_name = 'val' if split == 'valid' else split
    os.makedirs(os.path.join(unified_dir, 'images', split_name), exist_ok=True)
    os.makedirs(os.path.join(unified_dir, 'labels', split_name), exist_ok=True)

# Loop through each dataset
for dataset_name, mapping in dataset_mappings.items():
    dataset_path = os.path.join(extracted_dir, dataset_name)
    if not os.path.exists(dataset_path):
        print(f"Skipping {dataset_name}, path not found.")
        continue
    
    print(f"Processing {dataset_name}...")
    
    for split in splits:
        split_name = 'val' if split == 'valid' else split
        
        images_dir = os.path.join(dataset_path, split, 'images')
        labels_dir = os.path.join(dataset_path, split, 'labels')
        
        if not os.path.exists(images_dir) or not os.path.exists(labels_dir):
            continue
            
        for img_name in os.listdir(images_dir):
            # Formulate new names to avoid conflicts
            # Replace spaces with underscores in dataset name for cleaner filenames
            prefix = dataset_name.replace(' ', '_').replace('.', '_')
            new_img_name = f"{prefix}_{img_name}"
            
            # Copy image
            src_img = os.path.join(images_dir, img_name)
            dst_img = os.path.join(unified_dir, 'images', split_name, new_img_name)
            shutil.copy2(src_img, dst_img)
            
            # Find and process corresponding label file
            base_name = os.path.splitext(img_name)[0]
            label_name = f"{base_name}.txt"
            src_label = os.path.join(labels_dir, label_name)
            
            new_label_name = f"{prefix}_{label_name}"
            dst_label = os.path.join(unified_dir, 'labels', split_name, new_label_name)
            
            if os.path.exists(src_label):
                with open(src_label, 'r') as f_in, open(dst_label, 'w') as f_out:
                    for line in f_in:
                        parts = line.strip().split()
                        if not parts:
                            continue
                        class_id = int(parts[0])
                        if class_id in mapping:
                            new_class_id = mapping[class_id]
                            parts[0] = str(new_class_id)
                            f_out.write(' '.join(parts) + '\n')
            else:
                # Some images might not have labels (empty backgrounds)
                # Create an empty label file just in case, though YOLO handles missing txts
                pass

# Create dataset.yaml
yaml_content = f"""path: {unified_dir}
train: images/train
val: images/val
test: images/test

nc: 2
names: ['number_plate', 'vehicle']
"""

with open(os.path.join(unified_dir, 'dataset.yaml'), 'w') as f:
    f.write(yaml_content)

print("Merging complete. YAML generated.")
