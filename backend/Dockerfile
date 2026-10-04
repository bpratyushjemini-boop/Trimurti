# =============================================================================
# NARAD Production Backend Dockerfile (Vendor-Neutral)
# Lightweight, reproducible, production-ready container image
# =============================================================================
FROM python:3.12-slim

# 1. System dependencies for health check & native builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    APP_ENV=production \
    ENVIRONMENT=CLOUD \
    NARAD_RUNTIME_MODE=cloud

WORKDIR /app

# 3. Create unprivileged service user
RUN addgroup --gid 1000 narad && \
    adduser --uid 1000 --gid 1000 --disabled-password --gecos "" narad

# 4. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy backend application source
COPY --chown=narad:narad app/ ./app/
COPY --chown=narad:narad Procfile .

# Ensure data directory exists with write permissions
RUN mkdir -p /app/data && chown -R narad:narad /app

# 6. Switch to unprivileged user
USER narad

# 7. Expose default port
EXPOSE 8000

# 8. Container health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# 9. Start command
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
