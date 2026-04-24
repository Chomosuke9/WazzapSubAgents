# Stage 1: Build (install dependencies once)
FROM python:3.11-slim as builder

WORKDIR /app

# Install system deps required for building & runtime libraries
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-dev \
    libgirepository1.0-dev \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libssl-dev \
    libblas-dev \
    liblapack-dev \
    libportaudio2 \
    poppler-utils \
    tesseract-ocr \
    ghostscript \
    libmagic1 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# PyGObject requires system cairo/gobject libs (installed above)
RUN pip install --no-cache-dir --user PyGObject

# Stage 2: Runtime (copy pre-installed packages only)
FROM python:3.11-slim

WORKDIR /app

# Install runtime system deps (same set minus build tools)
RUN apt-get update && apt-get install -y \
    curl \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-dev \
    libgirepository1.0-dev \
    libcairo2-dev \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libssl-dev \
    libblas-dev \
    liblapack-dev \
    libportaudio2 \
    poppler-utils \
    tesseract-ocr \
    ghostscript \
    libmagic1 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY main.py .

EXPOSE 5000 5001

# Two entry points (via CMD arg):
# - python main.py (main service)
# - python -m src.executor_server (in-container executor)
CMD ["python", "main.py"]
