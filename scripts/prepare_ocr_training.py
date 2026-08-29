import os
import shutil
import urllib.request
import tarfile
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data" / "synthetic_plates"
    models_dir = project_root / "models"
    models_dir.mkdir(exist_ok=True)
    
    gt_file = data_dir / "rec_gt.txt"
    if not gt_file.exists():
        print(f"Error: {gt_file} not found.")
        print("Please run 'python scripts/generate_synthetic_plates.py' first with NUM_IMAGES = 20000.")
        return

    print("1. Splitting synthetic data into Train and Validation sets...")
    with open(gt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Split 90% train, 10% val
    split_idx = int(len(lines) * 0.9)
    train_lines = lines[:split_idx]
    val_lines = lines[split_idx:]
    
    train_file = data_dir / "train.txt"
    val_file = data_dir / "val.txt"
    
    with open(train_file, 'w', encoding='utf-8') as f:
        f.writelines(train_lines)
    with open(val_file, 'w', encoding='utf-8') as f:
        f.writelines(val_lines)
        
    print(f"   Train: {len(train_lines)} images | Val: {len(val_lines)} images.")

    print("\n2. Downloading pre-trained PP-OCRv4 English Recognizer model for fine-tuning...")
    model_url = "https://paddleocr.bj.bcebos.com/PP-OCRv4/english/en_PP-OCRv4_rec_train.tar"
    tar_path = models_dir / "en_PP-OCRv4_rec_train.tar"
    extracted_model_dir = models_dir / "en_PP-OCRv4_rec_train"
    
    if not extracted_model_dir.exists():
        print(f"   Downloading {model_url}...")
        urllib.request.urlretrieve(model_url, tar_path)
        print("   Extracting...")
        with tarfile.open(tar_path) as tar:
            tar.extractall(path=models_dir)
        tar_path.unlink()  # Clean up tar file
    else:
        print("   Pre-trained model already downloaded.")

    print("\n3. Generating PaddleOCR Training Configuration (YAML)...")
    yaml_content = f"""Global:
  use_gpu: true
  epoch_num: 50
  log_smooth_window: 20
  print_batch_step: 10
  save_model_dir: ./output/custom_indian_plates/
  save_epoch_step: 10
  eval_batch_step: [0, 500]
  cal_metric_during_train: true
  pretrained_model: {extracted_model_dir.as_posix()}/best_accuracy
  checkpoints:
  save_inference_dir:
  use_visualdl: false
  infer_img: 
  character_dict_path: ppocr/utils/en_dict.txt
  max_text_length: 25
  infer_mode: false
  use_space_char: false
  save_res_path: ./output/predicts_custom.txt

Optimizer:
  name: Adam
  beta1: 0.9
  beta2: 0.999
  lr:
    name: Cosine
    learning_rate: 0.001

Architecture:
  model_type: rec
  algorithm: SVTR_LCNet
  Transform:
  Backbone:
    name: MobileNetV1Enhance
    scale: 0.5
  Head:
    name: MultiHead
    head_list:
      - CTCHead:
          Dictionary:
            dictionary_config:
              dict_path: ppocr/utils/en_dict.txt
  
Loss:
  name: MultiLoss
  loss_config_list:
    - CTCLoss:

PostProcess:
  name: CTCLabelDecode

Metric:
  name: RecMetric
  main_indicator: acc

Train:
  dataset:
    name: SimpleDataSet
    data_dir: {data_dir.as_posix()}
    label_file_list: ["{train_file.as_posix()}"]
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - RecAug: 
      - MultiLabelEncode:
      - RecResizeImg:
          image_shape: [3, 48, 320]
      - KeepKeys:
          keep_keys: ['image', 'label_ctc', 'length']
  loader:
    shuffle: true
    batch_size_per_card: 128
    drop_last: true
    num_workers: 4

Eval:
  dataset:
    name: SimpleDataSet
    data_dir: {data_dir.as_posix()}
    label_file_list: ["{val_file.as_posix()}"]
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - MultiLabelEncode:
      - RecResizeImg:
          image_shape: [3, 48, 320]
      - KeepKeys:
          keep_keys: ['image', 'label_ctc', 'length']
  loader:
    shuffle: false
    drop_last: false
    batch_size_per_card: 128
    num_workers: 4
"""
    yaml_path = project_root / "scripts" / "custom_rec_indian_plates.yml"
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    print(f"   Configuration saved to: {yaml_path}")

    print("\n" + "="*80)
    print("ALL SET! To start training whenever you are ready, follow these exact steps:")
    print("="*80)
    print("1. Open your terminal and navigate to this project folder.")
    print("2. Clone the official PaddleOCR repository (if you haven't already):")
    print("   git clone https://github.com/PaddlePaddle/PaddleOCR.git")
    print("3. Enter the PaddleOCR folder:")
    print("   cd PaddleOCR")
    print("4. Start the training by running this command:")
    print(f"   python tools/train.py -c ../scripts/{yaml_path.name}")
    print("="*80)

if __name__ == "__main__":
    main()
