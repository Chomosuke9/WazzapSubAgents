# Stage 1: Build (install dependencies once)
FROM python:3.11-slim AS builder
WORKDIR /app

# Install system deps required for building Python packages
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    python3-dev \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libblas-dev \
    liblapack-dev \
    libopenblas-dev \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-dev \
    libcairo2-dev \
    poppler-utils \
    tesseract-ocr \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly (Docker-specific libraries)
RUN pip install --no-cache-dir --user \
    Flask==3.0.0 \
    langchain==0.1.20 \
    langchain-openai==0.1.0 \
    openai==1.30.0 \
    python-dotenv==1.0.0 \
    requests==2.31.0 \
    httpx==0.27.2 \
    docker==7.0.0 \
    python-json-logger==2.0.7 \
    pytest==7.4.3 \
    pytest-asyncio==0.21.1 \
    pdfplumber \
    pdf2image \
    pdfminer.six \
    pypdf \
    pytesseract \
    Pillow \
    opencv-python-headless \
    scikit-image \
    imageio \
    numpy \
    pandas \
    beautifulsoup4 \
    lxml \
    openpyxl \
    xlsxwriter \
    python-docx \
    python-pptx \
    reportlab \
    markdownify \
    scipy \
    sympy \
    py7zr \
    rarfile

# Stage 2: Runtime (copy pre-installed packages only)
FROM python:3.11-slim
WORKDIR /app

# Install runtime system libs (only what's needed from requirements.txt)
RUN apt-get update && apt-get install -y \
    curl \
    libssl3 \
    libffi8 \
    libxml2 \
    libxslt1.1 \
    libblas3 \
    liblapack3 \
    libopenblas0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libglib2.0-0 \
    libcairo2 \
    poppler-utils \
    tesseract-ocr \
    ghostscript \
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