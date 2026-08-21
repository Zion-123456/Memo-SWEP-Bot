#!/bin/sh
# =============================================================================
# Memo Application Entrypoint
#
# Runs database migrations before starting the application server.
# This ensures the schema is always up to date when the container starts.
# =============================================================================
set -e

# If the first argument is pytest or alembic, skip migration unless explicitly requested
if [ "$1" = "pytest" ] || [ "$1" = "alembic" ] || [ "$1" = "black" ] || [ "$1" = "ruff" ] || [ "$1" = "mypy" ]; then
    exec "$@"
fi

if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
else
    echo "Skipping database migrations (RUN_MIGRATIONS is not 'true')..."
fi


if [ $# -gt 0 ]; then
    echo "Executing command: $@"
    exec "$@"
else
    echo "Starting application server..."
    exec uvicorn main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --no-access-log
fi
