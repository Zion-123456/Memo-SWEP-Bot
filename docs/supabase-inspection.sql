-- Review and execute only through an approved connection to the confirmed project.
-- Metadata only. No schema creation, migrations, row contents or object downloads.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';

SELECT current_database() AS database_name, current_user AS inspection_role;

SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema'
ORDER BY schema_name;

SELECT n.nspname AS schema_name, c.relname AS table_name,
       c.relkind, c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced,
       c.reltuples::bigint AS estimated_rows
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r', 'p', 'v', 'm')
ORDER BY n.nspname, c.relname;
-- estimated_rows comes from PostgreSQL statistics; -1 means unknown, not zero.

SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema NOT LIKE 'pg_%' AND table_schema <> 'information_schema'
ORDER BY table_schema, table_name, ordinal_position;

SELECT n.nspname AS schema_name, t.relname AS table_name,
       c.conname AS constraint_name,
       pg_catalog.pg_get_constraintdef(c.oid) AS foreign_key_definition
FROM pg_catalog.pg_constraint c
JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
WHERE c.contype = 'f'
  AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
ORDER BY n.nspname, t.relname, c.conname;

SELECT schemaname, tablename, policyname, permissive, roles, cmd,
       qual IS NOT NULL AS has_using_expression,
       with_check IS NOT NULL AS has_check_expression
FROM pg_catalog.pg_policies
WHERE schemaname IN ('public', 'memo', 'storage')
ORDER BY schemaname, tablename, policyname;
-- Presence flags alone do not prove authorization is correct. Review the actual
-- relevant policy predicates privately after identifying Memo's tables/buckets.

ROLLBACK;
