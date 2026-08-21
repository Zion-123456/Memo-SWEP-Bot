# =============================================================================
# Stage 1: Builder
# Installs Poetry and all production dependencies into an isolated virtualenv.
# =============================================================================
FROM python:3.12-slim AS builder

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.4 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /build

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="$POETRY_HOME/bin:$PATH"

# Copy only dependency manifests first for layer caching
COPY pyproject.toml ./

# Install production dependencies (generates lock file if absent)
RUN poetry lock --no-update && \
    poetry install --only=main --no-root

# =============================================================================
# Stage 2: Final runtime image
# Minimal image containing only the application and its dependencies.
# =============================================================================
FROM python:3.12-slim AS final

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app

# Install only runtime system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini alembic.ini
COPY main.py main.py
COPY docker/entrypoint.sh entrypoint.sh

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
