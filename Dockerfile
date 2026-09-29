# syntax=docker/dockerfile:1

# --- Stage 1: build the static web interface -------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: the Python server, serving the built interface ---------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KAVACH_DATA_DIR=/data \
    KAVACH_HOST=0.0.0.0 \
    KAVACH_PORT=8050 \
    KAVACH_FRONTEND_DIR=/app/web

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY kavach ./kavach
COPY manage.py ./
COPY --from=web /web/out ./web

# Run as an unprivileged user; /data holds kavach.db and server.key.
RUN useradd --system --uid 10001 --no-create-home kavach \
    && mkdir /data && chown kavach:kavach /data
USER kavach
VOLUME /data
EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8050/api/auth/status', timeout=4)"

CMD ["python", "-m", "kavach"]
