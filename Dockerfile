### Stage 1: build frontend (node)
FROM node:20.19-alpine as frontend-builder
WORKDIR /app/frontend

# Copy only frontend sources needed for install/build to leverage caching
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/ ./

RUN npm ci --production=false || npm install
RUN npm run build

### Stage 2: python runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# System deps (ffmpeg, build-essentials for some wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg build-essential libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application source
COPY . /app

# Copy built frontend from builder into static_ui directory expected by app
RUN mkdir -p /app/static_ui
COPY --from=frontend-builder /app/frontend/dist /app/static_ui

# Install python deps
RUN python -m pip install --upgrade pip setuptools wheel     && pip install --no-cache-dir -r /app/backend/requirements.txt     && pip check     && python -c "import importlib; [importlib.import_module(m) for m in ('jose','passlib','feedparser','stripe','celery','google.cloud.storage','authlib','psycopg')]"

ENV PYTHONPATH=/app/backend

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]

