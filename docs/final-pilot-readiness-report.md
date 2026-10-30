# Memo final pilot readiness report

30 October 2026 (Africa/Lagos). Decision: **NOT READY — SPECIFIC BLOCKERS REMAIN.**
Prepared engineering can be reviewed; this is not deployment, migration or webhook
approval. No live production interaction is inferred from local/mocked tests.

## A. Repository state

- Repository: `Zion-123456/Memo-SWEP-Bot`; branch: `pilot/render-free-webhooks`.
- Latest verified implementation SHA: `6fa42c89909def5237b5b1019767af12e91ac225`.
- Required starting commit `ff42a8d82fce0e1223c1effe8a540a4f14babc8f` was verified
  locally and on the remote branch before changes. The checkout was clean.
- Remote main was verified as `1dec7701b8a9de73896b7babbe1e1e07b7cda1ea` and is
  not merged into, rewritten or pushed by this work.
- This report and review documents are finalized in a subsequent documentation
  commit; the final chat gives the exact pushed branch-tip SHA. The application
  SHA above identifies the tested implementation, not a self-referential report hash.
- [Complete changed-file manifest against main](validation/changed-files.txt).
  This review changes AI/provider/evidence handling, the inspection CLI, nine manual
  probe scripts, dependency manifests/lockfile, Docker/Render configuration, related
  tests and the inspection/migration/deployment documentation.

## B. Supabase inspection

Only authorized target: existing **my-customers**, ref **verhllnqohsdypbyyeib**.
The display name is user-provided; it has not been independently checked live.

Complete reviewed SQL: [docs/supabase-inspection.sql](supabase-inspection.sql),
SHA-256 `e2e70b0a8b958469bfeb8378f42d261ff0c7831740ee76e5f0dc7685de84a9d9`.
It is read-only: SELECT queries, a READ ONLY transaction, local timeouts/search path
and ROLLBACK. There are no data/DDL/privilege mutations. SELECT-only dynamic XML
queries are generated from quoted catalog identifiers and restricted projections;
no arbitrary user SQL or private message contents are executed/exported.

Coverage: schemas, tables/owners/RLS flags/statistical row estimates, columns,
indexes, constraints/FK columns, role capabilities/memberships, policy presence,
accessible Alembic versions, aggregate inbox states and up to 200 bucket metadata
rows. Exact count statements are generated for candidate tables but require manual
identification and execution in a separate read-only transaction. Actual policy
predicates must be reviewed privately; the script avoids literal-bearing expressions.
No rows from storage.objects, personal messages, password hashes or keys are selected.

The expanded SQL ran on local PostgreSQL 16, including synthetic migration/bucket/
inbox metadata, and rolled back. **Live database and Storage inspection did not run.**
Actual tables, counts, versions, bucket existence and policies remain unknown.
`memo` and `memo-private` are proposals/code assumptions, not discovered resources.

Observed enforced HTTPS rules still omit the confirmed Supabase domain. TCP grants
are empty; VPN is unconfigured. No approved private gateway is supplied. The documented
CONNECT route at proxy:8088 requires VPN/private IPv4 and appropriate grants; adding
the public database hostname is insufficient. No more blocked service requests were
attempted during this review. No bypass, guessed connection or alternate project was used.

Follow [the Dashboard SQL Editor guide](supabase-inspection-guide.md). Verify the
Dashboard URL and Project Settings ref before execution; a SQL project label or
`current_database() = postgres` does not prove project identity. Collect metadata
and aggregates only, and report missing privileges separately.

## C. Code quality and verification

| Check | Actual result | Scope/limit |
| --- | --- | --- |
| Full pytest suite | **332 passed, 0 failed, 0 skipped, 0 errors**, 9.46 s | Database tests enabled against isolated local PostgreSQL; Telegram/Groq/Storage network calls mocked |
| Integration coverage | Passed within full suite | Authenticated webhook→durable receipt→real PTB dispatcher→SQL; deduplication, per-chat ordering, retries, leases, restart/resume, ownership, PDF and provider failures |
| Docker | Build passed, Python 3.12.14 | Image `sha256:e209d4a88777eaa529df49e99bb4404430938027090e4f1df4156ed6fdeb5b7d`; local build only |
| Container startup/shutdown | Passed | Actual FastAPI lifespan/PostgreSQL dispatcher and liveness/readiness; mocked Telegram, local temporary storage, no Redis installed, registration disabled |
| Targeted Ruff syntax checks | Passed | E9,F63,F7,F82 on app/tests/migrations/manual probes |
| Full repository Ruff | **273 findings; not clean** | Predominantly style/import rules, plus other outstanding lint debt; no blanket lint-pass claim |
| Mypy | **279 errors in 39 files; not clean** | 102 files checked with `--explicit-package-bases`; default invocation separately hits duplicate-module discovery |
| Poetry / pip consistency | Passed | Poetry metadata deprecation warnings remain; root-package metadata refreshed after dependency upgrades |
| Dependency advisories | **0 across 109 local packages; 0 across 42 runtime-image packages** | pip-audit using approved PyPI service; Python advisory matching only, not OS/image vulnerability scanning |
| Inspection SQL | Passed locally, production untested | Optional metadata branches exercised with synthetic fixtures |
| Offline migration generation | Passed | Fresh→0006 and 0004→0006 generated; neither executed |

Machine-readable evidence: [final-validation.json](validation/final-validation.json).
No Render latency/throughput/cold-start performance or production capacity was measured.

Defects fixed in this review:

1. Groq HTTP server/transient statuses were incorrectly non-retryable. They now
   expose retryable flags to the existing bounded service retry policy; authentication
   errors remain non-retryable. The SDK's automatic retries remain disabled.
2. Late voice/PDF extraction populated the original-text field. Newly processed
   transcripts/extraction now live separately in payload metadata with an unverified
   label; original wording/files remain intact. Cached derived text avoids repeated
   extraction. Empty voice transcripts fail honestly without invoking analysis.
   Existing historical data is not rewritten.
3. The inspection CLI retained an optional/substring project guard. It now requires
   the exact confirmed ref, validates the direct/pooler identity before connecting,
   and applies read-only transaction/statement/lock limits.
4. The advisory scan initially returned 32 records (17 distinct package/advisory
   pairs) across Starlette, Black, pytest and pip. Updated FastAPI to 0.162.0,
   explicitly constrained Starlette to 1.10.0, updated compatible test/formatter
   tools and pinned pip 26.2.2 in Docker/Render build setup. Lockfile, full tests
   and image were rebuilt and audited after remediation.
5. Nine pre-existing manual probe scripts contained token-shaped hard-coded literals,
   present already in main. Replaced them with `os.environ["TELEGRAM_BOT_TOKEN"]`;
   scripts were syntax-checked, never executed. The literals did not match current
   injected credentials. They remain in existing Git history: validity/revocation
   is unverified, no history was rewritten, and no credential was rotated.

Outstanding engineering limits: repository-wide strict lint/type debt; no malware
scanner or full content-signature validation; no OCR; no real Telegram OGG/Opus
voice/private-storage end-to-end verification. Private documents are retained as
originals and extraction is only claimed when successful. Do not describe arbitrary
files as scanned/safe or AI-derived records as verified facts. Code review and local
coverage do not prove production ownership enforcement without the live smoke tests.

## D. Deployment configuration

One native Python **Render Free Web Service**, one instance, no paid worker/Redis/
persistent disk, automatic deployment disabled; Python **3.12.14**.

Build (updated to include the security-patched installer):

```sh
pip install --upgrade pip==26.2.2 && pip install poetry==2.5.1 && poetry install --only main --no-interaction
```

Start:

```sh
poetry run uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log
```

Health check: `/api/v1/ready`; independent liveness: `/live`.
`REGISTER_WEBHOOK=false` in Settings/Blueprint and `RUN_MIGRATIONS=false` remain.
Native Uvicorn startup never runs Alembic. A dispatcher still writes accepted work,
so do not start the real application against production merely to inspect it.

The production code currently requires an isolated `memo` schema and private Supabase
storage. Actual existing schema/bucket must be inventoried and reconciled before
approval; setting the proposed names is not provisioning or verification. Backend
ownership checks remain essential because a service-role credential bypasses RLS.

The complete source/default/format/testing matrix follows; it is maintained in
[render-environment-matrix.md](render-environment-matrix.md).
### Verified Render environment-variable matrix

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

## E. Production safety

| Area | Status |
| --- | --- |
| Production backups/restoration | Not performed; account backup availability unverified |
| Production migrations/schema/buckets/imports | Not performed; no production objects or files changed |
| Migration review | Offline artifacts generated; conditional plan awaits real inventory |
| Credentials | Protected bindings reported ready; live validity not checked; no rotation/change |
| Historical credential literals | Removed from pilot tree, retained in historical commits; owner security review required |
| Telegram webhook | Not registered or changed; registration remains opt-in and disabled |
| Deployment | Not performed; no Render resource or paid infrastructure created |
| Main branch | Unchanged |

Use [the conditional migration and backup plan](production-migration-plan.md).
The migration artifacts contain state-changing SQL and MUST NOT be confused with
the read-only inspection file. Actual inventory, approved backups/restoration and
explicit production approval are still required before any execution.

## F. Pilot experience

| Approved feature | Evidence now | Remaining real test |
| --- | --- | --- |
| Personal Telegram/dashboard | Real PTB dispatcher, local SQL, mocked responses | Live webhook `/start` and every visible action |
| Text/voice/photo/document capture | Preview/edit/confirm/cancel/retry, source preservation, failure recovery and PDF tests | Real Telegram text/voice/photo/PDF through private Supabase Storage |
| Persistent check-ins | SQL skip/edit/resume, restart and confirm-once tests | Actual Render restart/resume |
| Projects/life areas | Owner-scoped defaults/create/rename/archive/association/search | Live project flows and isolation |
| Memory retrieval | Keyword/date/project filters, evidence IDs, empty matches, unverified suggestions | Actual saved production pilot records under two authorized accounts |
| Evidence/provenance | Originals separate from reviewed/derived text, checksums, owner-only evidence | Production private-file retrieval after redeployment and late-extraction verification labels |

Real Telegram voice status: **UNVERIFIED**. Historical synthetic WAV provider success
is not Telegram OGG/Opus download/codec validation. Verify actual getFile/download,
file MIME/size, private upload/read, transcription, empty/timeout/quota errors,
source-preserving retry, editable transcript, confirmation and post-redeployment
retrieval. No automatic model substitution is claimed; models remain configurable.

Historical polling `/start` and synthetic Groq checks were reported earlier, not
rerun here and not proof of the current webhook stack. No mentorship/sharing,
gamification, reminders, exports or unrelated features were introduced.

Render Free may sleep when idle; startup and Telegram retries delay responses.
Accepted inbox work persists, but unaccepted Telegram deliveries have a finite
retention window. Abrupt termination can leave a dispatcher lease for up to 90 s.
No keepalive traffic was added. Use a supervised demo window and measure an actual
cold start before sign-off; no always-on or 1,000-user claim is made.

## G. Final decision and exact next actions

**NOT READY — SPECIFIC BLOCKERS REMAIN.**

1. In Supabase Dashboard, verify only `my-customers` / `verhllnqohsdypbyyeib` and
   run the complete read-only inventory using the guide. Return sanitized metadata,
   selected aggregate counts, actual version and private-bucket/policy findings.
   No connection strings, keys, messages or files are needed in chat.
2. Review the historical credential exposure with the credential owner. Do not treat
   removal from the latest tree as removal from history. Determine the appropriate
   authorized credential response separately; this assignment makes no credential
   change and does not test whether those old literals still authenticate.
3. Arrange approved workspace PostgreSQL/HTTPS connectivity or an authorized operator
   environment for subsequent inspection and approved operations. Do not invent a
   gateway, expose the database or bypass the proxy. Supply credentials only through
   protected settings and confirm their intended target privately.
4. Reconcile the actual inventory with the proposed schema/bucket and review the
   exact migration/backup/restore/rollback plan. Obtain separate approval before
   provisioning, backing up/copying private data, migrating or importing.
5. Review the updated Free Blueprint, security results and remaining static-quality
   debt. Configure protected Render values only when the target plan is approved.
6. Separately approve deployment and live webhook registration. Then perform every
   required live row in [director-demo-checklist.md](director-demo-checklist.md),
   including actual voice, account isolation, failures and restart/retrieval.
7. Collect human director-demo sign-off against the approved commit only after the
   required live journeys and recovery checks pass. Until then, no deployment or
   launch readiness is claimed.
