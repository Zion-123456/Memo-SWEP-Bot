# Read-only Supabase inspection guide

Target: **my-customers**, project **verhllnqohsdypbyyeib** only. Live inspection has
not occurred: this workspace still has no approved HTTPS/PostgreSQL route. A
service-role key does not provide PostgreSQL transport. No further blocked network
requests are needed. This Dashboard workflow avoids changing workspace network policy.

## Verify the project before executing anything

1. Open your authenticated Supabase Dashboard, choose your existing organization,
   then **my-customers**. Do not create another project.
2. Check the browser URL contains `/project/verhllnqohsdypbyyeib/`. In Project Settings,
   verify the project reference is exactly `verhllnqohsdypbyyeib`. The API URL should
   be `https://verhllnqohsdypbyyeib.supabase.co`. Do not reveal keys/passwords.
3. Open **SQL Editor → New query** in that same project. Confirm the project selector
   and URL again. Neither `current_database()` (often `postgres`) nor a literal
   project label in SQL proves project identity; Dashboard verification is required.
4. Open [supabase-inspection.sql](supabase-inspection.sql), copy its COMPLETE contents,
   review it, paste into the new query, and run. Use the existing authorized role;
   do not grant privileges merely to get results.

The script contains only SELECTs plus transaction/session controls: `BEGIN READ
ONLY`, `SET TRANSACTION READ ONLY`, local timeouts/search path, and `ROLLBACK`.
There are no data writes, schema changes, privilege changes, migrations, password
changes, bucket changes or object downloads. Local session settings are not
persistent configuration changes. PostgreSQL rejects data writes in this transaction.
The script uses PostgreSQL catalogs and built-in XML functionality supported by
Supabase PostgreSQL; it was executed successfully on local PostgreSQL 16, not on
this live project. Catalog visibility depends on the inspecting role.

## Collect each result safely

Dashboard versions may show only the last result set. To inspect an earlier section,
copy that SELECT (including any preceding comments/CTEs) into a fresh query surrounded
by this envelope, then run it in the SAME verified project:

```sql
BEGIN READ ONLY;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SET LOCAL search_path = pg_catalog;
-- Paste ONE complete reviewed SELECT from supabase-inspection.sql here.
ROLLBACK;
```

The first result must show `transaction_read_only = on`. If a timeout, missing
permission or transaction error occurs, stop that query and run `ROLLBACK;` if the
session remains open. Keep the error type/section, not credential-bearing connection
errors. Do not disable safeguards or increase privileges. A timeout gives no inventory
result; it does not mean the database is empty. Ask for review of that section.

| Section | What it establishes | Limits and evidence to retain |
| --- | --- | --- |
| Connection | Database/role, transaction read-only flag | Does not identify the Supabase project; retain Dashboard ref separately |
| Schemas/tables | Names, table kinds, owners, RLS flags and estimated counts | `-1` means unknown; stale statistics are not exact counts |
| Columns | Column names/types/nullability | Does not read column values/default expressions |
| Indexes | Names, columns, primary/unique/valid/partial/expression flags | Does not export literal-bearing index expressions |
| Constraints | Names/types, validation and ordered FK columns/targets | Includes PK/unique/check presence; check expressions deliberately omitted |
| Roles/memberships | Login, superuser, bypass-RLS and role membership flags | Uses `pg_roles`, not password-bearing `pg_authid` |
| Policies | Schema/table, role/command, permissiveness and expression presence | Review relevant actual predicates privately; presence alone proves no authorization |
| Alembic | XML containing only `version_num`, across accessible version tables | Missing results mean absent/inaccessible, not safe to stamp or migrate |
| Inbox | Aggregate counts by delivery state and maximum attempts | No payloads/account IDs; requeueing failed work is a separately approved write |
| Storage | XML of at most 200 bucket names/public/size/MIME settings | No object names, user files or signed URLs; missing rows can mean no permission |
| Optional exact counts | Generated quoted SELECT-count statements for candidate Memo tables | Nothing executes automatically; generic names do not prove Memo ownership |

To obtain exact counts, first identify actual Memo tables from their columns and FK
chains (Telegram users → events/drafts/projects → attachments). Copy only selected
`optional_exact_count_sql` results into the read-only envelope above. Counts reveal
no message content but may still time out on large tables. Do not run arbitrary
queries from untrusted output. The generated statements are only quoted `count(*)`
queries over discovered candidate tables.

For Storage, also open **Storage** in the verified Dashboard. Record bucket names,
private/public status and configured type/size limits. View relevant `storage.objects`
policies privately. Check the actual USING/WITH CHECK conditions and database grants;
a backend service-role key can bypass RLS, so backend owner checks remain essential.
Do not export predicates containing personal literals or browse/download users' files.
The inspection script omits policy expressions to avoid unnecessary disclosure.

## Share metadata, not private data

Return the confirmed project reference, schemas/table/column/FK/index names, relevant
role/RLS flags, migration versions, aggregate counts, and bucket private/public/limit
settings. Include which sections failed or were inaccessible. Redact any personal
identifiers in metadata names before sharing. Never send connection strings,
passwords, keys, tokens, message text, object paths or file contents.

`memo` and `memo-private` are proposed targets, NOT discovered resources. No part of
the script assumes they exist or creates them. If existing Memo/SWEP records live in
`public` or another schema, preserve them and request a specific reconciliation plan.
Do not create an empty parallel Memo history, stamp Alembic, migrate, import or copy
files based solely on this report. Next steps require reviewed inventory, backup/
restore evidence and separate explicit production approval.

The CLI `python -m app.ops.inspect_database` is a narrower metadata-only alternative
once an approved database route exists. It now requires the exact confirmed project
reference, checks the DSN identity before connecting and applies local read-only
transaction/time limits. It does not replace the complete Dashboard inventory.
