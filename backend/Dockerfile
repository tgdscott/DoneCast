FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    PATH="/usr/local/bin:${PATH}"

WORKDIR /app

# Minimal OS deps; add more as your app needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy app
COPY . /app

# Default command (Cloud Run will pass $PORT)
CMD ["sh","-c","exec python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
