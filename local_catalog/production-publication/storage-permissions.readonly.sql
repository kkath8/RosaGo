-- Supplement only: no need to repeat destination/schema/object exports.
-- Confirm production Dashboard project brnkigrrqdrywahvcbvc.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_catalog.jsonb_build_object(
 'owner_selected_project_ref','brnkigrrqdrywahvcbvc',
 'transaction_read_only',pg_catalog.current_setting('transaction_read_only'),
 'tables',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('table',c.relname,
    'rls_enabled',c.relrowsecurity,'force_rls',c.relforcerowsecurity,
    'owner',pg_catalog.pg_get_userbyid(c.relowner)))
   FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='storage' AND c.relname IN ('objects','buckets')),
 'grants',(SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(g)) FROM information_schema.role_table_grants g
   WHERE g.table_schema='storage' AND g.table_name IN ('objects','buckets')),
 'api_roles',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('role',rolname,'superuser',rolsuper,'bypass_rls',rolbypassrls))
   FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','service_role'))
) AS publication_storage_permissions_json;
ROLLBACK;
