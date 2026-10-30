# Director-demo preparation and approval checklist

Prepared on 30 October 2026. This checklist authorizes no production action.
Repository: `Zion-123456/Memo-SWEP-Bot`; branch: `pilot/render-free-webhooks`.
Required starting commit: `968aed85f84738fe8feb9a0df9c76dcbea10d28e`.
Only Supabase target: existing `my-customers`, ref `verhllnqohsdypbyyeib`.

## Completed locally

- [x] Verify the required starting commit exists on the remote pilot branch.
- [x] Keep main unchanged; use only the pilot branch for follow-up commits.
- [x] Make webhook registration opt-in in Settings and the Render Blueprint.
- [x] Exercise the actual FastAPI lifespan and PostgreSQL dispatcher with Redis
  imports blocked and Telegram requests mocked; verify readiness and shutdown.
- [x] Add regressions for lease renewal during startup, release on failures and
  exact Supabase endpoint/project identity checks.
- [x] Align both Docker stages with Render's Python 3.12.14 configuration.

Final full-suite and Docker results are recorded in [release readiness](release-readiness.md).
Mocked integration results do not establish live Telegram or Supabase operation.

## Workspace connectivity gate

The observed workspace allows HTTPS to Telegram and Groq, plus package-manager
presets. Supabase HTTPS is present in a saved draft but not enforced in the running
environment. TCP grants are empty and VPN is not configured.

- [ ] Review and activate the existing narrow HTTPS addition:
  `verhllnqohsdypbyyeib.supabase.co`, using the inherited proxy and CA trust.
- [ ] Arrange a platform-supported PostgreSQL route. The documented TCP CONNECT
  listener is `proxy:8088`; it requires configured VPN access and an exact domain
  grant resolving to permitted private IPv4 space. It cannot directly provide
  this workspace with access to Supabase's public database endpoint merely by
  adding that hostname. A private gateway must be an actual authorized resource,
  not an invented hostname. TCP-grant changes require a replacement environment.
- [ ] Obtain operator confirmation of the route, its endpoint, TLS identity and
  access scope. Do not expose the database publicly or disable TLS verification.
- [ ] Load credentials through protected settings. `DATABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` were reported ready, which does not prove current
  authentication validity. Configure the matching non-secret `SUPABASE_URL` and
  `SUPABASE_PROJECT_REF` as listed in the deployment guide.

The public direct database target currently identifies
`db.verhllnqohsdypbyyeib.supabase.co:5432`, database `postgres`. A Render session
pooler may be appropriate for IPv4 compatibility; copy its actual connection
from this project's Connect panel securely rather than guessing its region or
hostname. An HTTPS allowlist grants neither PostgreSQL access nor database login.

## Read-only Supabase inspection gate

Run only once approved connectivity is available. Do not start the application
against production as a substitute for read-only inspection: the dispatcher writes.

- [ ] Verify the project display name/reference in the authorized Supabase UI.
- [ ] Run `poetry run python -m app.ops.inspect_database` with
  `SUPABASE_PROJECT_REF=verhllnqohsdypbyyeib`. It reads metadata and does not apply
  migrations. Never print the DSN or secret values when diagnosing failures.
- [ ] Review [the read-only inventory SQL](supabase-inspection.sql) in an approved
  database client. Record schemas, tables, columns, foreign keys, RLS status and
  Storage policy metadata. Do not publish private row contents.
- [ ] Identify actual Memo tables using their columns and ownership relationships,
  not names alone; record bounded aggregate counts, migration revision and legacy
  SWEP columns. Establish whether Memo already exists in `public` or another schema.
- [ ] List Storage buckets read-only with the existing project's dashboard or
  authenticated `GET /storage/v1/bucket`. Record bucket names, private/public flags,
  size/type limits and relevant policies. Do not download personal files or create
  signed URLs merely to inventory buckets.
- [ ] Record existing attachment-reference formats, missing-reference counts and
  legacy upload/Redis locations without copying data.

No inspection results are asserted while connectivity remains blocked.

## Migration and backup plan gate

This is a decision framework; a final production plan requires the inventory above.

- [ ] If Memo already exists, compare its actual revision and columns with
  migrations 0001–0006. Review a specific schema/permission move if necessary;
  do not create an empty parallel history or blindly stamp migrations.
- [ ] If Memo does not exist, review creating the isolated `memo` schema with a
  least-privilege role. Review migration SQL and its foreign keys before approval.
- [ ] Choose an existing suitable private bucket or propose `memo-private` only
  after inventory. Do not repurpose a public bucket containing other data.
- [ ] Define backups for database schema/data, ownership and permissions, plus
  private file objects and checksums. Confirm account backup availability and costs;
  do not assume a paid backup feature is included on a free account.
- [ ] Test restoration in an approved isolated environment before cutover; record
  row counts, ownership/FK checks and file integrity. Do not restore over production.
- [ ] Review rollback compatibility, retention and reconciliation of newer records.
  Automatic destructive downgrade is intentionally unavailable.
- [ ] Obtain explicit approval before creating anything, migrating, importing,
  copying files or changing production configuration.

## Render approval checklist

Use [render.yaml](../render.yaml) and the complete variable table in
[the deployment guide](render-free-pilot.md).

- [ ] Select the pilot branch and approved commit. Do not create the service yet.
- [ ] Confirm one **Free Web Service**, native Python, no paid worker, Redis or
  persistent disk, and automatic deployment disabled.
- [ ] Python: `3.12.14`; build:
  `pip install --upgrade pip==26.2.2 && pip install poetry==2.5.1 && poetry install --only main --no-interaction`.
- [ ] Start:
  `poetry run uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`.
- [ ] Health path: `/api/v1/ready`; independent liveness: `/live`.
- [ ] Configure protected database, Storage, Telegram and Groq credentials;
  use Render's generated webhook secret. Match the inspected private bucket.
- [ ] Keep `RUN_MIGRATIONS=false`, leave `MEMO_MIGRATION_APPROVED` unset, and keep
  `REGISTER_WEBHOOK=false` until live registration is explicitly approved.
- [ ] Verify the actual Render public URL. Render supplies `RENDER_EXTERNAL_URL`
  and `PORT`; omit `PUBLIC_BASE_URL` unless a verified custom HTTPS host is required.
- [ ] Verify existing Supabase/Groq quotas and avoid enabling paid add-ons or
  automatic spend. Free hosting does not guarantee free AI or unlimited storage.
- [ ] Obtain explicit deployment and webhook-registration approval. Only then
  set `REGISTER_WEBHOOK=true` for the approved cutover, after stopping any old poller.

## Supervised live smoke test, after approval

Record timestamp, approved commit, expected/actual result and sanitized evidence
for every step. Use an authorized account and synthetic test content.

1. Verify `/live`, `/api/v1/ready` and the expected webhook configuration. Check
   pending/error counts in `getWebhookInfo` without logging the bot credential.
2. Send `/start`, then text capture, edit, confirm, keyword search and evidence retrieval.
3. Create/rename a project; associate a memory and verify project/date filtering.
4. Start a check-in, skip a prompt, restart the service, resume and confirm once.
5. Test actual voice, photo and PDF capture; verify review, retry/cancel, original
   evidence and retrieval after redeployment. Clearly label unsupported extraction.
6. Use a second authorized account to verify ownership denial. Test replay/deduplication
   in a safe staging context rather than injecting arbitrary production updates.
7. Observe an actual Free-instance idle sleep/cold start and send a new Telegram
   message. Record delay and eventual processing; recheck duplicate saves. This
   behavior is not measured by local tests.
8. Review provider failures, queue states, private-file access and costs before GO.

Render Free can sleep while idle. Startup and Telegram retries can delay replies;
an unexpired dispatcher lease may add up to 90 seconds after an abrupt stop.
Accepted work is durable in PostgreSQL. Telegram retains unaccepted updates only
for a limited time; do not rely on an indefinite outage recovery window. Background
work alone does not establish always-on availability. Do not add artificial keepalive
traffic. Warm up manually for the supervised demo and disclose these limitations.

## Required evidence and failure criteria for sign-off

Use this table with the checkboxes above. All live rows remain **UNVERIFIED**.
The final decision and current exact test/build results are in
[the final readiness report](final-pilot-readiness-report.md). No production task
below is authorized merely because it appears in the checklist.

| Item / what to do | Verify success | Evidence to collect | Failure / stop condition |
| --- | --- | --- | --- |
| Inspect correct Supabase project | Dashboard ref exactly `verhllnqohsdypbyyeib`; read-only flag on | Ref plus sanitized metadata per inspection guide | Wrong ref, write-enabled query, inaccessible required sections |
| Check protected credentials | Matching project/bot; credentials load without logging | Presence/readiness and sanitized authentication results | Missing/mismatched credentials, values appearing in logs |
| Inventory database/buckets | Actual ownership/FKs, migration revision, private bucket identified | Aggregate counts, metadata and policy review | Unexplained schema drift, public evidence bucket, unclear data owner |
| Back up and test recovery, after approval | Restored counts/FKs/file hashes match | Protected backup manifest and isolated restore report | Missing objects, hash mismatch, failed restore |
| Review migration plan | Range matches actual revision; no parallel empty history | Approved inventory/SQL/rollback plan | Unreviewed schema move, destructive shortcut or no backup |
| Configure Free Render service | Approved commit, one Free instance, no paid add-ons; secrets protected | Sanitized settings/commit and variable matrix | Wrong branch/plan, missing environment, enabled automatic migration |
| Deploy only after explicit approval | Build/start succeed, `/live` and `/api/v1/ready` return 200 | Commit/build logs and health bodies without secrets | Startup exception, 503 readiness, unexpected writes |
| Register webhook only after explicit approval | Expected endpoint, correct secret header, no poller | Sanitized `getWebhookInfo` result/error counts | Wrong URL, repeated errors, concurrent polling |
| Personal `/start` and menu | Short onboarding and every visible action responds | Synthetic conversation transcript | Broken button or legacy required form blocking personal use |
| Text capture/edit/confirm | Full preview, original preserved, reviewed text saved once | Record ID and original/reviewed comparison privately | Silent save, lost original, duplicate record |
| Project create/rename/associate | Owner's project and linked memories searchable | Project/record IDs and query result | Duplicate defaults, orphan link, cross-owner project |
| Retrieve memory by keyword/date/project | Correct owned source, date and evidence reference | Expected vs actual IDs; no private text in report | Fabricated answer, unrelated fallback, cross-account result |
| Persistent check-in | Skip/edit/resume after restart; one confirmation | Draft/record IDs and restart checkpoint | Lost answers, overwritten edits or duplicate save |
| Real Telegram voice note | Actual OGG/Opus download → private original → Groq → review | Duration/format, timings, source checksum, outcome; no audio in report | Empty/wrong transcript labelled success, source lost, unreviewed derived text treated as verified |
| Voice failure/retry | Failure shown; same source survives; retry can succeed | Sanitized error class, unchanged checksum and saved outcome | Repeated uncontrolled retries, duplicate save or missing source |
| Photo/PDF | Retained original, honest extraction status, editable preview where derived | Format/size/checksum and outcome | Unsupported extraction claimed successful, public URL, lost file |
| Restart/redeployment | Confirmed files/records and drafts retrievable afterward | Before/after IDs and hashes | Dependence on ephemeral local files or vanished draft |
| Account isolation | Second authorized account denied read/edit/confirm/evidence access | Denial result and expected owner, without message text | Any unauthorized access |
| Failed inbox visibility/recovery | Counts/last error visible without payload dump; approved replay deduplicates save | Aggregate states and sanitized recovery record | Silent disappearance, premature acknowledgement or unapproved production requeue |
| Free cold start | New real message eventually processes after idle sleep | Measured delay/retry/outcome and no duplicate saved record | Lost work, unexplained outage, latency unsuitable for demo |
| Director-demo sign-off | All required live rows pass, blockers resolved and limitations accepted | Dated human sign-off against approved commit | Any required unverified path, unresolved ownership/backup failure |

Synthetic WAV transcription is historical provider evidence only. Real Telegram
voice download/codec handling, production private storage, actual provider quota and
timeout/retry behavior must all pass the real-note rows above. No live result is
inferred from mocks, local SQL tests or a successful Docker import.
