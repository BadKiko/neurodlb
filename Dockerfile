# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for video processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Create temp directory
RUN mkdir -p temp

# Set environment variables
ENV PYTHONPATH=/app
ENV TEMP_DIR=/app/temp

# Run the application
CMD ["python", "src/main.py"]
