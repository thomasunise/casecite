# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.11

# Install Python dependencies separately so the source and frontend changes do
# not invalidate the dependency layer.
FROM python:${PYTHON_VERSION}-slim AS python-deps
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
RUN python -m venv "${VIRTUAL_ENV}"
WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
# Keep pip's download/wheel cache in the BuildKit mount for faster rebuilds.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Frontend SPA build.
FROM node:22-alpine3.22 AS frontend-build
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

# Word add-in build. Vite's base path matches the bundled serving path.
FROM node:22-alpine3.22 AS addin-build
WORKDIR /src/word-addin
COPY word-addin/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY word-addin/ ./
ENV ADDIN_BASE=/addin/
RUN npm run build

# Development target used by docker-compose.dev.yml.
FROM python:${PYTHON_VERSION}-slim AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libmagic1 libgomp1 tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos "" --home /nonexistent \
       --shell /usr/sbin/nologin --no-create-home --uid 10001 appuser
COPY --from=python-deps /opt/venv /opt/venv
COPY backend/app/ /app/app/
COPY backend/alembic.ini /app/alembic.ini
COPY backend/migrations/ /app/migrations/
COPY start.sh /app/start.sh
RUN chmod 755 /app/start.sh && mkdir -p /app/data && chown appuser:appuser /app/data
EXPOSE 8000
USER appuser
CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8000"]

# Production image: nginx serves the compiled frontend and proxies API traffic;
# start.sh performs migrations, drops privileges for Uvicorn, and handles shutdown.
FROM python-base AS app
USER root
RUN apt-get update && apt-get install -y --no-install-recommends nginx gosu \
    && rm -f /etc/nginx/sites-enabled/default \
    && rm -rf /var/lib/apt/lists/*
COPY nginx.unified.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /src/frontend/dist/ /var/www/html/
COPY --from=addin-build /src/word-addin/dist/ /var/www/html/addin/
COPY word-addin/manifest.xml /app/addin-manifest.xml
EXPOSE 80
ENTRYPOINT ["/app/start.sh"]
