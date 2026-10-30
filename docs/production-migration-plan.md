# Production migration and backup plan — review only

Target: existing `my-customers` / `verhllnqohsdypbyyeib`. **Not approved to execute.**
Actual production inventory is unavailable. This is a conditional plan, not a claim
that the target is empty, backed up or compatible. No online migrations ran during
this review. Preserve all existing rows and originals, including SWEP records.

1. **Inventory:** use [the read-only guide](supabase-inspection-guide.md). Record
   schemas, column types, constraints/indexes, owners/grants/RLS, version tables,
   candidate table counts, bucket settings/policies and legacy attachment locations.
   Identify inaccessible sections explicitly. Inspect only the confirmed project.
2. **Identify Memo/SWEP:** validate Telegram identity columns and user→event→attachment,
   project/draft ownership chains. Generic `users`/`events` names may belong to other
   applications. Record the real Alembic revision and any schema drift. Never stamp
   a database merely to bypass errors. The production guard currently requires
   `DATABASE_SCHEMA=memo`; that requirement does not prove such a schema exists.
3. **Preservation:** compare all legacy SWEP columns; migrations 0005/0006 keep rows
   and make optional legacy fields nullable. Retain attachment references, original
   files, voice recordings, checksums, drafts, conversation state and verification
   flags. Do not rewrite historic provenance based on guesswork. Stop writers only
   during an explicitly approved maintenance/cutover window.
4. **Backup:** after separate approval, use the project's authorized PostgreSQL export
   or `pg_dump --format=custom` through a protected libpq service profile (no DSN or
   passwords in commands/logs). Include discovered Memo tables/types/version table,
   related dependencies and permissions. Protect unrelated customer data if a full
   project backup is needed. Record server/client versions, timestamp, SHA-256 and
   inventory counts. PostgreSQL dumps do not contain Supabase Storage object bytes:
   separately export authorized private objects plus a protected reference/checksum
   manifest. Preserve legacy local files and Redis archives. Keep backups outside
   Git, with directory mode 0700 and file mode 0600 or equivalent access control.
   Confirm which backup features are actually available on the existing account;
   do not purchase add-ons or assume PITR is included.
5. **Verify recovery:** inspect the archive with `pg_restore --list`; then restore into
   a separately approved isolated database/storage location. No production overwrite.
   Compare aggregate counts, PK/FK ownership, SWEP values, draft states, checksums and
   original-file retrieval. Record elapsed time, failures and recovery steps. Local
   historical restore tests do not establish this production backup's recoverability.
6. **Choose migration order based on evidence:**
   - Existing compatible 0004 Memo: review the incremental 0004→0005→0006 artifact.
   - Existing earlier revision: select only missing ordered migrations after checking
     actual columns/types against history; do not replay completed changes.
   - Existing Memo in `public`/another schema: review a specific dependency-aware
     schema move or compatibility change first. Do not initialize an empty parallel
     Memo database. No schema move SQL is authorized by this plan.
   - No existing Memo: after confirming that fact, review the fresh 0001→0006 artifact,
     isolated schema/role grants and private bucket proposal.
7. **Resolve conflicts before execution:** check shared enum/table/index/constraint
   names, existing version tables, shared customer tables, cross-schema FKs, RLS and
   backend-role grants. Keep Memo's schema out of public PostgREST exposure. Migration
   0002 renames/adds enum values; 0005 relaxes nullability/adds ownership FKs; 0006 adds
   durable delivery/state/lease tables. These operations can take locks; determine a
   maintenance window and bounded lock strategy based on the real table sizes.
8. **Rollback:** keep an approved compatible application revision available. Prefer
   retaining additive schema/data and rolling back application code. Historic
   downgrades 0001–0004 contain destructive DDL; never run them as a shortcut.
   0005/0006 deliberately refuse automatic destructive downgrade. A data rollback
   requires a separate restore/reconciliation plan preserving records written since
   backup. Any live webhook cutover requires explicit approval; no parallel poller.
9. **Post-migration verification, after approval:** compare before/after counts,
   ownership joins, orphan/reference counts, SWEP samples privately, version 0006,
   required indexes and actual role access. Verify private bucket settings and original
   file hashes. Run readiness and authorized account-isolation tests. Stop on any
   unexplained count loss or changed evidence; retain backups and original files.

## Offline review artifacts

- [empty-to-0006.sql](migration-review/empty-to-0006.sql): proposed fresh schema path.
- [0004-to-0006.sql](migration-review/0004-to-0006.sql): only for a verified compatible 0004 baseline.

Generated with Alembic **offline** using a synthetic local connection configuration
and `DATABASE_SCHEMA=memo`. No database connection or migration execution occurred.
Both artifacts contain state-changing DDL/version writes by design and are **not**
the read-only inspection script. They assume a previously reviewed existing `memo`
schema and appropriate grants; neither provisions that schema nor reconciles data.
Do not paste these migration artifacts into Dashboard SQL Editor now.

A future authorized operator must first obtain the inventory, demonstrate backup
recovery, review the exact target/range/permissions and obtain explicit migration
approval. `MEMO_MIGRATION_APPROVED=true` is an additional software guard, not approval.
Build/start keep migrations disabled. Bucket provisioning/imports require separate
approval; neither is part of these SQL artifacts.
