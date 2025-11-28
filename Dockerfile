# Use python slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (FFmpeg is required)
# We clean up apt lists to keep the image size down
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories to ensure permissions are correct
RUN mkdir -p downloads temp

# Expose Flask port
EXPOSE 5000

# Run the application
# Host 0.0.0.0 is required to make Flask accessible outside the container
CMD ["python", "app.py"]