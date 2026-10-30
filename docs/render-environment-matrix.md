# Verified Render environment-variable matrix

Source review: `app/config/settings.py`, `app/factory.py`, `app/database/session.py`,
`app/storage/local.py`, `app/intent/classifier.py`, `docker/entrypoint.sh`,
`migrations/env.py`, `app/ops/` and `render.yaml`. No secret values are included.

Required means required for this proposed AI/voice-enabled Render pilot, not that
Settings always requires an explicit environment value. Tests validate parsing and
local/mocked behavior; they do not verify these values in a live Render account.

| Variable | Required? | Purpose | Secret? | Verified source/default, format and testing |
| --- | --- | --- | --- | --- |
| `PYTHON_VERSION` | Native build | Render runtime selection | No | Blueprint `3.12.14`; exact Docker runtime tested; Render installation unverified |
| `POETRY_VIRTUALENVS_IN_PROJECT` | Build convention | Poetry environment placement | No | Blueprint `true`; Poetry/Docker build checked |
| `PORT` | Render-provided | Uvicorn listener | No | Decimal port supplied by Render; start command consumes it; Docker fallback `8000` |
| `RENDER_EXTERNAL_URL` | Render-provided at registration | Public service base URL fallback | No | Settings default factory reads it; validated HTTPS URL required when registering; actual host unverified |
| `PUBLIC_BASE_URL` | Optional override | Custom public HTTPS base URL | No | Defaults to `RENDER_EXTERNAL_URL` or empty; omit override for normal Render host; webhook URL validation tested |
| `APP_ENV` | Yes | Production guards | No | Code default `development`; Blueprint `production`; accepted `development/test/production`; guard tests |
| `APP_NAME` | Optional | App metadata | No | Settings default `Memo`; factory consumes string |
| `APP_VERSION` | Optional | App/health metadata | No | Settings default `0.1.0`; health serialization tested |
| `LOG_LEVEL` | Optional | Application log level | No | Default `INFO`; use standard logging level; redaction tests |
| `DATABASE_URL` | Yes | PostgreSQL connection | **Yes** | Explicit protected binding required in production; local default is unsuitable; PostgreSQL DSN with TLS; normalization/pooling tested locally; live authentication unverified |
| `DATABASE_SCHEMA` | Yes for production guard | Search path/version table | No | Code default `public`; production currently requires `memo`; lowercase identifier regex tested; `memo` is a code requirement/proposal, not a verified existing schema |
| `MEMO_DB_POOL_SIZE` | Optional, set for pilot | Baseline database connections | No | Raw env in session factory; default `5`, Blueprint `2`; integer; local connection tests |
| `MEMO_DB_MAX_OVERFLOW` | Optional, set for pilot | Extra database connections | No | Raw env default `5`, Blueprint `2`; integer; max proposed pool total 4 per engine/process |
| `STORAGE_PROVIDER` | Yes | Durable production storage | No | Default `local`; production requires `supabase`; fail-closed tests |
| `SUPABASE_PROJECT_REF` | Yes | Project identity guard | No | Default empty; use only `verhllnqohsdypbyyeib`; exact direct/pooler validation tested |
| `SUPABASE_URL` | Yes | Storage API origin | No | Default empty; `https://verhllnqohsdypbyyeib.supabase.co`; standard HTTPS port; local/mocked origin tests |
| `SUPABASE_STORAGE_BUCKET` | Yes, verify target | Private bucket | No | Code/Blueprint proposed default `memo-private`; actual existence unknown; private-only API behavior mocked |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Server-side private Storage API | **Yes** | No credential default; `SecretStr`; private bucket checks mocked; live key/privileges unverified |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot API authentication | **Yes** | Placeholder rejected; validated BotFather token shape; use protected binding for `@use_memo_bot`; no live calls this review |
| `TELEGRAM_WEBHOOK_SECRET` | Yes even with registration off | Incoming secret header | **Yes** | No default; Blueprint generates; 32–256 letters/digits/underscore/hyphen; authentication tests |
| `REGISTER_WEBHOOK` | Optional, explicit opt-in | Mutating Telegram registration gate | No | **Default/Blueprint `false`**; only set `true` with explicit approval; no registration call when off tested |
| `AI_ENABLED` | Yes for AI/voice demo | Provider initialization | No | Default `false`, Blueprint `true`; boolean; enabled configuration requires key; parsing/provider tests |
| `GROQ_API_KEY` | With AI enabled | Groq authentication | **Yes** | No default; `SecretStr`; provider tests mocked; no fresh live provider call claimed |
| `GROQ_MODEL` | Optional | Interpretation/query model | No | Default/Blueprint `openai/gpt-oss-120b`; model identifier; mocked configuration tests; no silent model switching |
| `GROQ_TRANSCRIPTION_MODEL` | Optional | Voice/audio transcription model | No | Default/Blueprint `whisper-large-v3`; mocked OGG requests; real Telegram voice unverified |
| `INTENT_MODEL` | Optional | Intent-classification model override | No | Settings default empty, falls back to provider model; classifier tests |
| `DOC_MAX_EXTRACT_CHARS` | Optional | Background document extraction cap | No | Integer default `100000`; personal capture preview separately capped at 20000; PDF tests |
| `RUN_MIGRATIONS` | Keep disabled | Docker startup migration gate | No | Shell runs Alembic only for exact `true`; Blueprint `false`; native Uvicorn never invokes migrations |

The following are tooling/development variables, NOT required Render service settings:

| Variable | Required? | Purpose | Secret? | Verified source/default |
| --- | --- | --- | --- | --- |
| `MEMO_MIGRATION_APPROVED` | Approved production tools only | Additional migration/copy guard | No | Must be exact `true` for guarded production tooling; leave unset; not authorization by itself |
| `REDIS_URL` | Legacy importer/tests only | Source Redis state | **Yes if authenticated** | Settings legacy default localhost; importer requires explicit source; runtime creates no Redis client; no production dependency |
| `LEGACY_UPLOAD_DIR` | Legacy file importer only | Location of preserved originals | No | Explicit source path, no default; do not configure in Render ephemeral filesystem |
| `UPLOAD_DIR` | Local development only | Local storage root | No | Local provider default `./data/uploads`; production local storage rejected |
| `MEMO_TEST_DATABASE_URL` | Database tests/load harness only | Disposable PostgreSQL target | **Yes if authenticated** | No default; tests otherwise skip; enabled in reported full suite; never set to production |

No paid Redis, background worker or persistent Render disk is required. The proposed
`memo` schema and private bucket must be reconciled with the actual existing inventory
before approving deployment. `MEMO_MIGRATION_APPROVED` is not set and no migrations
are part of the build/start commands.
