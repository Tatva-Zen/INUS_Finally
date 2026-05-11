# Stage 1: Build Next.js frontend static export
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps first (cached layer)
COPY backend/pyproject.toml backend/uv.lock* backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy backend app code
COPY backend/ /app/backend/

# Copy frontend static build output
COPY --from=frontend-builder /app/frontend/out /app/static

# Runtime db directory
RUN mkdir -p /app/db

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
