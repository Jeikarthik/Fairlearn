# ── Stage 1: Build dependencies ──────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for building (gcc for C extensions, libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install -e ".[prod]" 2>/dev/null || \
    pip install --no-cache-dir --prefix=/install -e "."


# ── Stage 2: Production image ───────────────────────
FROM python:3.12-slim AS production

# Runtime deps only (no gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd --gid 1000 fairlens && \
    useradd --uid 1000 --gid fairlens --create-home fairlens

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code ONLY (no tests, no dev files)
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY pyproject.toml ./

# Create directories with correct ownership
RUN mkdir -p /app/uploads /app/reports && \
    chown -R fairlens:fairlens /app

# Switch to non-root
USER fairlens

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ready || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
