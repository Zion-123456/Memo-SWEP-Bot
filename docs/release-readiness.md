# Memo Free Webhook Pilot — validation record

Target: one $0 Render Web Service, Telegram webhooks and the existing `my-customers`
Supabase project `verhllnqohsdypbyyeib`. See [the operator guide](render-free-pilot.md)
and [render.yaml](../render.yaml). The branch is `pilot/render-free-webhooks`.

Release decision: **NO-GO for live deployment yet**. The repository implementation
is prepared, but workspace Supabase access is network-blocked. Existing database
schemas and buckets therefore have not been inspected. No production migration,
bucket creation, Render deployment or webhook registration has been performed.

## Evidence and current feature matrix

The GitHub baseline was `1dec7701b8a9de73896b7babbe1e1e07b7cda1ea` with **236 passing
tests** after resolving the undeclared aiofiles dependency and test settings.
Before the Free-plan adaptation the suite reached 280 passing tests. Final local
validation: **320 passed, 0 failed, 0 skipped, 0 errors**, in 8.43 seconds, with
the database tests enabled against an isolated local PostgreSQL database. Telegram
API delivery and Supabase Storage HTTP responses were mocked in automated tests.
The final Docker image built successfully on Python 3.12.14 without Redis installed.
An additional image smoke test exercised the actual FastAPI lifespan, PostgreSQL
dispatcher, readiness, liveness and graceful shutdown against the isolated local
database. It used mocked Telegram requests and local temporary storage; it does
not verify the production Supabase configuration. Webhook registration was disabled.
Targeted Ruff syntax checks, `git diff --check`, and dependency consistency checks
passed. Poetry reported existing package-metadata deprecation warnings; no full
static-type-check claim is made.

## Follow-up review of the required pilot commit

Remote starting commit `968aed85f84738fe8feb9a0df9c76dcbea10d28e` was verified
on 30 October 2026; its baseline suite passed all 310 tests. Follow-up fixes:

- Settings previously defaulted webhook registration to enabled. Code and Blueprint
  now default to disabled, with a regression that forbids registration API calls.
- Supabase identity validation previously accepted substring matches. Direct
  endpoints and session-pooler project suffixes must now match exactly; private
  database roles remain supported. API ports are restricted to standard HTTPS.
- Dispatcher renewal previously began after initialization, and some construction
  or shutdown errors could skip lease release. Renewal covers asynchronous startup
  and cleanup now releases the lease even on those failures.
- Docker's floating Python tag had drifted to 3.12.16 while Render specified
  3.12.14. Both Docker stages are pinned to the configured Render patch release.

Ten additional passing tests cover these regressions and actual application startup
without Redis. The read-only inventory SQL also completed against the isolated local
database and rolled back. See [the director-demo checklist](director-demo-checklist.md)
for connectivity, inspection, backup, approval and live smoke-test gates.

| Approved feature | Implementation | Verification and limit |
| --- | --- | --- |
| Personal Telegram experience | Short `/start`, menu, optional legacy SWEP setup | Actual PTB dispatcher exercised through authenticated HTTP and SQL, with Telegram API mocked |
| Text/voice/photo/doc capture | Persistent previews, edit/confirm/cancel/retry, retained originals | Automated handler, provider, PDF and storage checks; real Groq extraction and synthetic speech transcription passed earlier; no live Telegram voice test |
| Check-ins/drafts | SQL drafts, skip/done/resume/edit, deduplicated answers and confirmation | Real PostgreSQL and dispatcher restart/resume tests |
| Projects/life areas | Seven defaults, create/rename/archive, assign, project/date search | SQL ownership, search and dispatcher journey tests |
| Trustworthy retrieval | Reviewed text plus original sources, empty-match handling, evidence-ID validation | SQL search and provider-fallback tests; no production search dataset accessed |
| Evidence/provenance | Original wording/files, reviewed text, verification metadata, checksum and private retrieval | Source-preservation, cross-owner denial, private-storage and file-migration tests; live Supabase bucket unverified |

The production REST data API is deliberately unavailable pending authentication.
Telegram users remain owner-scoped and are limited to private chats. AI suggestions
are labelled unverified and do not overwrite original user input.

## Integrations and safety

- Telegram previously confirmed `@use_memo_bot` through `getMe`. The user sent
  `/start`; the temporary polling log recorded `onboarding.started` after the
  handler awaited its reply. The user also reported interacting with it. This
  verifies the preceding polling interaction, not the new webhook deployment.
- Groq accepted the configured credential and listed both configured models.
  A synthetic memory extraction and synthetic speech transcription passed.
- A local PostgreSQL backup was restored to an isolated database. Migration 0005
  preserved the compared existing local user, event, attachment and conversation
  values. Migrations 0001–0006 ran in a fresh isolated schema while leaving the
  public table list unchanged. Nothing establishes production migration safety
  until the actual project is inspected.
- PostgreSQL conversation/profile persistence, inbox deduplication, retry recovery,
  per-chat ordering, dispatcher ownership and private-storage behavior are tested.
- Local legacy Redis state and local files have non-destructive, dry-run-first copy
  tools. The private-storage adapter is tested against a simulated Storage API;
  no live bucket creation or retrieval is claimed. The local database is at
  migration 0006; a fresh Redis dry-run found one eligible legacy state row and
  left the source unchanged. A pre-webhook local database backup was retained.
- The temporary polling process was stopped. No replacement public webhook
  deployment is running, so live bot availability is not claimed.
- The earlier bounded local SQL workload used 1,000 synthetic registered users,
  10 concurrent interactions and 1,000 capture/confirm/search interactions with
  zero failures. [Raw results](load-test-results.json) exclude Telegram, AI, real
  Supabase, Render and attachments. They do **not** demonstrate Render Free
  capacity or change the current small-pilot goal.
- No paid infrastructure, extra Supabase project, mentorship/AATC features,
  reminders, leaderboards or journey exports were introduced.

## Remaining operator actions

1. Activate the newly saved environment network settings for the confirmed
   Supabase HTTPS domain and arrange supported database TCP access. No network
   bypass has been attempted. The earlier project reference is not a valid target.
2. Inspect schemas/tables and buckets read-only using the protected bindings.
   Determine whether existing Memo records need a reviewed schema move.
3. Review and approve a private bucket, backups, safe migrations and any legacy
   state/file copies. The proposed bucket name is `memo-private`; its existence
   has not been verified.
4. Review the separate branch and Free Blueprint, configure protected Render
   variables, then explicitly approve deployment and webhook registration.
5. Perform the guide's live Telegram and redeployment-retrieval smoke tests.

Render Free sleeping/cold starts, provider quotas, private storage quotas and the
lack of a live webhook/Supabase test remain pilot limitations. Nothing here claims
permanent unattended agent execution, an always-on deployment or production scale.
