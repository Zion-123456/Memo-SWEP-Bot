-- Target: my-customers / verhllnqohsdypbyyeib. Verify Dashboard project BEFORE Run.
-- This label cannot prove the identity of the connected PostgreSQL server.
-- Metadata/aggregates only. No personal messages, object paths or credentials.
BEGIN READ ONLY;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SET LOCAL search_path = pg_catalog;

SELECT current_database() AS database_name, current_user AS inspection_role,
       current_setting('transaction_read_only') AS transaction_read_only;

SELECT schema_name
FROM information_schema.schemata
WHERE schema_name !~ '^pg_' AND schema_name <> 'information_schema'
ORDER BY schema_name;

SELECT n.nspname AS schema_name, c.relname AS table_name, c.relkind,
       pg_get_userbyid(c.relowner) AS owner_role,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced,
       c.reltuples::bigint AS estimated_rows
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r', 'p', 'v', 'm')
ORDER BY n.nspname, c.relname;
-- Statistics estimates are NOT exact counts. -1 means unknown, not empty.

SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema !~ '^pg_' AND table_schema <> 'information_schema'
ORDER BY table_schema, table_name, ordinal_position;

SELECT n.nspname AS schema_name, t.relname AS table_name,
       i.relname AS index_name, x.indisprimary AS primary_index,
       x.indisunique AS unique_index, x.indisvalid AS valid_index,
       x.indpred IS NOT NULL AS partial_index,
       x.indexprs IS NOT NULL AS expression_index,
       ARRAY(SELECT a.attname FROM unnest(x.indkey) WITH ORDINALITY k(num, pos)
             JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.num
             ORDER BY k.pos) AS indexed_columns
FROM pg_index x JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
ORDER BY n.nspname, t.relname, i.relname;

SELECT n.nspname AS schema_name, t.relname AS table_name,
       c.conname AS constraint_name, c.contype AS constraint_type,
       c.convalidated AS validated,
       ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num, pos)
             JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.num
             ORDER BY k.pos) AS columns,
       rn.nspname AS referenced_schema, rt.relname AS referenced_table,
       ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num, pos)
             JOIN pg_attribute a ON a.attrelid = rt.oid AND a.attnum = k.num
             ORDER BY k.pos) AS referenced_columns
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_class rt ON rt.oid = c.confrelid
LEFT JOIN pg_namespace rn ON rn.oid = rt.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
ORDER BY n.nspname, t.relname, c.conname;
-- Constraint type: p=primary, u=unique, f=foreign, c=check, x=exclusion.
-- Literal-bearing expressions are omitted deliberately.

SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
       rolcanlogin, rolbypassrls
FROM pg_roles ORDER BY rolname;
-- pg_roles hides password hashes; never substitute pg_authid here.
SELECT granted.rolname AS granted_role, member.rolname AS member_role,
       m.admin_option
FROM pg_auth_members m
JOIN pg_roles granted ON granted.oid = m.roleid
JOIN pg_roles member ON member.oid = m.member
ORDER BY granted.rolname, member.rolname;

SELECT schemaname, tablename, policyname, permissive, roles, cmd,
       qual IS NOT NULL AS has_using_expression,
       with_check IS NOT NULL AS has_check_expression
FROM pg_policies
WHERE schemaname !~ '^pg_' AND schemaname <> 'information_schema'
ORDER BY schemaname, tablename, policyname;
-- Flags do not prove authorization. Review relevant actual predicates privately
-- in Dashboard; expressions can contain personal literals and are not exported.

SELECT n.nspname AS migration_schema,
       query_to_xml(format('SELECT version_num FROM %I.%I ORDER BY version_num LIMIT 20',
                           n.nspname, c.relname), false, false, '') AS migration_versions
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relname = 'alembic_version' AND c.relkind IN ('r', 'p')
  AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  AND has_table_privilege(c.oid, 'SELECT')
  AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
              AND a.attname = 'version_num' AND NOT a.attisdropped);
-- XML contains ONLY migration versions, not application records.

SELECT n.nspname AS inbox_schema,
       query_to_xml(format(
         'SELECT state, count(*) AS update_count, max(attempts) AS max_attempts FROM %I.%I GROUP BY state ORDER BY state',
         n.nspname, c.relname), false, false, '') AS delivery_counts
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relname = 'memo_telegram_inbox' AND c.relkind IN ('r', 'p')
  AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  AND has_table_privilege(c.oid, 'SELECT')
  AND (SELECT count(*) FROM pg_attribute a WHERE a.attrelid = c.oid
       AND a.attname IN ('state', 'attempts') AND NOT a.attisdropped) = 2;
-- Aggregate inbox health only. No Telegram payloads or individual account IDs.

SELECT query_to_xml(
  'SELECT jsonb_build_object(''name'', to_jsonb(b)->''name'',
     ''public'', to_jsonb(b)->''public'',
     ''file_size_limit'', to_jsonb(b)->''file_size_limit'',
     ''allowed_mime_types'', to_jsonb(b)->''allowed_mime_types'') AS bucket
   FROM storage.buckets b LIMIT 200', false, false, '') AS bucket_metadata
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'storage' AND c.relname = 'buckets'
  AND c.relkind IN ('r', 'p') AND has_table_privilege(c.oid, 'SELECT');
-- No rows means absent/inaccessible table, NOT proof that there are no buckets.
-- At most 200 bucket metadata rows; no storage.objects rows are read.

SELECT n.nspname AS candidate_schema, c.relname AS candidate_table,
       format('SELECT count(*) AS row_count FROM %I.%I;', n.nspname, c.relname)
         AS optional_exact_count_sql
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname !~ '^pg_'
  AND n.nspname NOT IN ('information_schema', 'auth', 'storage')
  AND (c.relname ~ '^memo_' OR c.relname IN
       ('users', 'events', 'attachments', 'conversations'))
  AND has_table_privilege(c.oid, 'SELECT')
ORDER BY n.nspname, c.relname;
-- Generated count statements are NOT executed. After identifying actual Memo
-- tables, run only selected statements in a separate READ ONLY transaction with
-- the same timeouts. Generic names alone do not identify Memo/SWEP data.
ROLLBACK;
