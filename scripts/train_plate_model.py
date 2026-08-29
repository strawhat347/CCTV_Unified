import os
from ultralytics import YOLO

def main():
    # Get absolute path to the project root (one folder up from 'scripts')
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # Define reliable absolute paths
    data_yaml_path = os.path.join(project_root, 'data', 'unified_dataset', 'dataset.yaml')
    project_run_dir = os.path.join(project_root, 'runs', 'detect')

    model = YOLO('yolov8n.pt')
    model.train(
        data=data_yaml_path,
        epochs=50,
        imgsz=640,
        batch=16,
        device=0,
        project=project_run_dir,
        name='unified_alpr_v1',
        save_period=5,       # <-- Saves a backup checkpoint every 5 epochs!
        workers=4,
    )

if __name__ == '__main__':
    main()