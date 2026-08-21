# Architecture

Memo is built with a rigorous separation of concerns to ensure the codebase remains maintainable as complex AI features are introduced in future sprints.

## The Clean Architecture Stack

The application enforces a unidirectional dependency flow:

```
[ HTTP Requests ]   [ Telegram Updates ]
        |                    |
        v                    v
[ FastAPI Router ]  [ PTB Handlers ]     <-- Transport Layer (No business logic)
        |                    |
        +---------+----------+
                  |
                  v
       [ Service Layer ]                 <-- Domain Layer (Business logic only)
                  |
                  v
      [ Repository Layer ]               <-- Data Access Layer (SQLAlchemy only)
                  |
                  v
         [ ORM Models ]                  <-- Data Layer
                  |
                  v
            [ Database ]
```

### 1. Transport Layer (API & Telegram)
- **Responsibility**: Accept inputs, parse them, pass them to a Service, and format the output.
- **Rule**: Handlers must never contain business rules. They only route data. If an HTTP endpoint and a Telegram handler trigger the same action, they both call the same method on a Service.

### 2. Service Layer
- **Responsibility**: Orchestrate use-cases. This is where domain invariants (e.g. "end date must be after start date") are enforced.
- **Rule**: Services must never execute SQL queries directly. They communicate with the database exclusively through Repositories.

### 3. Repository Layer
- **Responsibility**: Abstract away the database. Provides typed CRUD methods.
- **Rule**: Repositories must never throw Domain exceptions or contain business logic. They translate between the application's needs and the underlying persistence mechanics.

### 4. Data Layer (Models & Schemas)
- **Models**: SQLAlchemy ORM classes reflecting the database tables.
- **Schemas**: Pydantic models for API validation. Decoupling Schemas from Models allows the API surface to evolve independently of the database.

## Dependency Injection

Dependencies (Database Sessions, Redis Clients, Repositories, Services) flow downward. 
- In FastAPI, this is handled via `Depends()`.
- In Telegram, dependencies are bound to `context.bot_data` at application startup and accessed by handlers during updates.

## Infrastructure

- **Single Process**: For Sprint 1, FastAPI and the Telegram bot (via long polling) run in the same asyncio event loop. This drastically simplifies deployment without sacrificing concurrency.
- **Migrations**: Database schema updates are managed by Alembic. In development, migrations run automatically on startup via `entrypoint.sh` when `RUN_MIGRATIONS=true`. In production, auto-migrations are disabled (`RUN_MIGRATIONS=false`) and are triggered as a distinct, single-concurrency pre-deployment step (e.g. `alembic upgrade head`) to avoid migration races.

