FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    HOST=0.0.0.0

# Install required system packages:
# - ffmpeg: Required by yt-dlp to merge high-res video + audio streams & extract audio
# - nodejs / npm: Required by yt-dlp JS runtime for YouTube cipher/n-challenge resolution
# - git / curl: Required to install latest yt-dlp master branch and network tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create downloads directory with write permissions
RUN mkdir -p /app/downloads && chmod 777 /app/downloads

# Expose service port
EXPOSE 5000

# Start production server
CMD ["python", "app.py"]
