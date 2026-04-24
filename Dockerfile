# Stage 1: Build (install dependencies once)
FROM python:3.11-slim as builder

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime (copy pre-installed packages only)
FROM python:3.11-slim

WORKDIR /app

# Copy system curl from builder if needed (optional)
COPY --from=builder /usr/bin/curl /usr/bin/curl

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
