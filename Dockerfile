# Use Intel's official image with GPU drivers for OpenVINO
FROM intel/intel-extension-for-pytorch:2.3.110-xpu

# Set user to root for installations
USER root

# Install system dependencies including FFmpeg and Intel VAAPI drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mkvtoolnix \
    aria2 \
    curl \
    intel-media-va-driver-non-free \
    libva-drm2 \
    libva2 \
    vainfo \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/downloads /app/data/temp /app/data/output /app/models

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
