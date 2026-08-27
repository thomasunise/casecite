# Multi-stage Dockerfile for Coolify deployment
# Stage 1: Build frontend with Vite
# Stage 2: Serve both backend API and frontend from one container

# ---- Stage 1: Frontend Build ----
# Floating patch tag: picks up OS security fixes on rebuild (Trivy gates the
# image in CI, so a stale pin means a permanently red build job).
FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* frontend/.npmrc* ./
RUN npm ci
COPY frontend/ .
RUN npm run build && \
    test -f dist/index.html && \
    echo "✓ Vite build successful" || \
    (echo "✗ FATAL: Vite build failed - dist/index.html not found" && exit 1)

# ---- Stage 2: Python Runtime ----
# Floating patch tag (see note above on the frontend stage).
FROM python:3.11-slim AS python-base
ENV PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Install nginx (pinned), system dependencies, and security updates
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    nginx \
    curl \
    gosu \
    libmagic1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running the application
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Bake the git sha into the runtime env so /health can report which build is
# serving. Coolify (and most CI) pass SOURCE_COMMIT as a build arg.
ARG SOURCE_COMMIT=unknown
ENV SOURCE_COMMIT=$SOURCE_COMMIT

# Set working directory
WORKDIR /app

# Copy backend requirements and install (prefer lock file for reproducible builds)
COPY backend/requirements.txt backend/requirements.lock* ./

# Base-image tooling is not in the lock file but ships in the image, so Trivy
# scans it. Pin it to current releases (pip/setuptools/wheel/jaraco.context
# CVEs in 2026) instead of whatever python:3.11-slim happens to bundle.
RUN pip install --no-cache-dir --upgrade "pip==26.2.1" "setuptools==84.0.0" "wheel==0.48.0" "jaraco.context==6.1.2"

# Install Python dependencies (prefer lock file for reproducible builds)
RUN if [ -f requirements.lock ]; then \
      pip install --no-cache-dir -r requirements.lock; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

# pip and wheel are build-time tools: strip them from the runtime filesystem.
# Nothing installs packages at runtime, and pip's vendored copies of its own
# dependencies (pip/_vendor/vendor.txt) otherwise surface in image scans with
# no fix available short of a new pip release. setuptools stays: greenlet, pillow
# and uvloop declare it as a runtime requirement.
RUN python -m pip uninstall -y pip wheel

# Copy backend code
COPY --chown=appuser:appuser backend/app ./app

# Copy Alembic config + migrations so `alembic upgrade head` can run at startup.
# Without these, schema changes never apply in production (create_all only adds
# whole tables, never columns).
COPY --chown=appuser:appuser backend/alembic.ini ./alembic.ini
COPY --chown=appuser:appuser backend/migrations ./migrations

# Copy built frontend from stage 1
COPY --chown=appuser:appuser --from=frontend-build /frontend/dist /var/www/html

# Verify the built index.html references assets (not /src/main.jsx)
RUN grep -q '/assets/' /var/www/html/index.html && \
    echo "✓ Frontend dist verified" || \
    (echo "✗ FATAL: /var/www/html/index.html missing asset references" && cat /var/www/html/index.html && exit 1)

# Copy logo asset for favicon/branding
COPY --chown=appuser:appuser frontend/logo.webp /var/www/html/logo.webp

# Copy nginx config
COPY --chown=appuser:appuser nginx.unified.conf /etc/nginx/sites-enabled/default

# Create data directories with broad permissions (Coolify may run as non-root)
RUN mkdir -p /app/data/chroma /app/data/uploads /app/data/audit_logs /app/data/user_settings \
    && chmod -R 755 /app/data

# Allow nginx to run as non-root (bind to port 80)
RUN chown -R appuser:appuser /var/log/nginx /var/lib/nginx /run \
    && sed -i 's/user www-data;/user appuser;/' /etc/nginx/nginx.conf 2>/dev/null || true

# Declare data volume
VOLUME ["/app/data"]

# Expose port 80 (Coolify expects this)
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start script - runs both nginx and uvicorn
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Run as root so we can fix volume permissions at startup,
# then start.sh drops to appuser via gosu/su-exec
CMD ["/start.sh"]
