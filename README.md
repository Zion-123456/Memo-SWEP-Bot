# Memo

> AI Memory Operating System for SWEP students.

This repository contains the backend for Memo. It provides a FastAPI REST API and an asynchronous Telegram Bot connected to a PostgreSQL database, all orchestrated via Docker Compose.

---

## Prerequisites

- **Docker** and **Docker Compose**
- **Poetry** (if running locally outside Docker for development)
- A **Telegram Bot Token** (obtain from [@BotFather](https://t.me/botfather))

---

## Quickstart

### Local Development Workflow
By default, the docker-compose setup is configured to run database migrations automatically before startup (`RUN_MIGRATIONS: "true"`).

1. **Clone and Configure**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and insert your `TELEGRAM_BOT_TOKEN`.

2. **Run the Stack**
   ```bash
   docker compose up --build
   ```
   This will start PostgreSQL, Redis, and the Memo application container. The database migrations will run automatically.

---

### Production Deployment Workflow
In multi-instance production environments, running migrations automatically on container start leads to race conditions. Instead:

1. **Disable Auto-Migrations**: Ensure your production environment variable is set to `RUN_MIGRATIONS=false`.
2. **Execute migrations as a pre-deployment step** (run in a single container context):
   ```bash
   docker compose run --rm app alembic upgrade head
   ```
3. **Deploy application containers**: Startup instances concurrently.


3. **Verify Health**
   ```bash
   curl http://localhost:8000/api/v1/health
   ```
   You should receive a `200 OK` response with a JSON payload indicating both the database and Redis are healthy.

4. **Interact with the Bot**
   Find your bot on Telegram and send `/start` to begin the SWEP onboarding flow.

---

## Development

The project uses Poetry for dependency management.

### Setup

```bash
poetry install
poetry shell
```

### Formatting, Linting, and Types

```bash
# Auto-format code
black .

# Run linter
ruff check .

# Run type checker
mypy .
```

### Testing

```bash
pytest
```

---

## Architecture Overview

The codebase strictly adheres to **Clean Architecture** principles.

- **`app/models/`**: SQLAlchemy ORM entities (Data Layer).
- **`app/repositories/`**: Typed data access objects (Data Access Layer). No business logic here.
- **`app/services/`**: Business logic and use-case orchestration (Domain Layer).
- **`app/schemas/`**: Pydantic models for API request/response validation (Presentation Layer).
- **`app/api/`**: FastAPI endpoints mapping HTTP to the service layer.
- **`app/telegram/`**: PTB handlers mapping Telegram updates to the service layer.

For a detailed breakdown, see [docs/architecture.md](docs/architecture.md).
