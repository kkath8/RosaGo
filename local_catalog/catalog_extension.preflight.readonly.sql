-- OWNER REVIEW ONLY. Confirm Dashboard target brnkigrrqdrywahvcbvc first.
-- The project reference below is an owner attestation, not server identity proof.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_catalog.jsonb_pretty(pg_catalog.jsonb_build_object(
    'export_format', 'rosago_catalog_schema_preflight_v1',
    'owner_selected_project_ref', 'brnkigrrqdrywahvcbvc',
    'project_identity_requires_dashboard_confirmation', true,
    'exported_at', pg_catalog.statement_timestamp(),
    'database_role', CURRENT_USER,
    'transaction_read_only', pg_catalog.current_setting('transaction_read_only'),
    'functions', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'identity', p.oid::pg_catalog.regprocedure::text,
        'definition', pg_catalog.pg_get_functiondef(p.oid),
        'body_md5', pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),'')),
        'owner', pg_catalog.pg_get_userbyid(p.proowner),
        'security_definer', p.prosecdef, 'config', p.proconfig, 'acl', p.proacl::text
    ) ORDER BY p.oid::pg_catalog.regprocedure::text)
    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public' AND p.prokind='f' AND p.proname LIKE 'rosago_%'),
    'indexes', (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(i)) FROM pg_catalog.pg_indexes i
        WHERE i.schemaname='public' AND i.tablename IN ('places','itinerary_drafts','admin_destination_audit')),
    'table_security', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'table',c.relname,'rls_enabled',c.relrowsecurity,'force_rls',c.relforcerowsecurity,
        'owner',pg_catalog.pg_get_userbyid(c.relowner)))
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname IN ('places','itinerary_drafts','admin_destination_audit')),
    'migration_history_relation_present', pg_catalog.to_regclass('supabase_migrations.schema_migrations') IS NOT NULL,
    'constraints', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'name', c.conname, 'definition', pg_catalog.pg_get_constraintdef(c.oid)))
        FROM pg_catalog.pg_constraint c WHERE c.conrelid='public.places'::pg_catalog.regclass),
    'columns', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'name', column_name, 'type', data_type, 'nullable', is_nullable, 'default', column_default))
        FROM information_schema.columns WHERE table_schema='public' AND table_name='places'),
    'policies', (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(p)) FROM pg_catalog.pg_policies p
        WHERE p.schemaname='public' AND p.tablename IN ('places','itinerary_drafts','admin_destination_audit')),
    'table_grants', (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(g)) FROM information_schema.role_table_grants g
        WHERE g.table_schema='public' AND g.table_name IN ('places','itinerary_drafts','admin_destination_audit'))
)) AS catalog_schema_preflight_json;
ROLLBACK;
