# syntax=docker/dockerfile:1
FROM python:3.12-slim

# System dependencies for Pillow, WeasyPrint/cairo/pango if needed, and TrueType fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libfreetype6 \
    fonts-dejavu-core \
    fonts-liberation \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy backend source code
COPY backend/app ./app

# Create persistent storage directories
RUN mkdir -p /app/data/uploads /app/data/generated

# Environment variables defaults
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    MONGODB_URI=mongodb://localhost:27017 \
    MONGODB_DB_NAME=certloop \
    PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
