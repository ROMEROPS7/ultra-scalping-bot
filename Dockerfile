# Ultra Scalping Bot - Docker Configuration
# Build: docker build -t ultra-scalping-bot .
# Run: docker run --env-file .env ultra-scalping-bot

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for data and models
RUN mkdir -p data models logs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import ccxt; print('healthy')" || exit 1

# Default command: run in paper trading mode
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "paper"]
