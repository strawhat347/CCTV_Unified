FROM python:3.11-slim

# Install system libraries needed by OpenCV and FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (leverages Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Ensure data directories exist for persistence
RUN mkdir -p data/crops data/mock_videos data/db

# The API port
EXPOSE 8002

# Run the central pipeline and API
CMD ["python", "main.py"]
