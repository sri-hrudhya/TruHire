FROM python:3.13-slim

# System dependencies for native extensions, OCR (RapidOCR/OpenCV), OpenMP, and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install uv for high-performance dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Configure Python and uv runtime environments
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Copy package definitions first for optimal layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies into virtual environment
RUN uv sync --frozen --no-dev

# Copy backend source code
COPY backend/ ./backend/

# Create runtime directories for uploads and logs
RUN mkdir -p /app/uploads/resumes /app/uploads/job_descriptions /app/logs

EXPOSE 8999

# Backend health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8999/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8999"]

