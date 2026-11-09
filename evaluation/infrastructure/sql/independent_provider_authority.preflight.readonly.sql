-- READ ONLY. Confirm jfaufpfzfhysqkhcdsrs in the dashboard before running.
-- Expected-project labels do not independently attest the connected project.
BEGIN READ ONLY;
SELECT pg_catalog.jsonb_build_object(
  'expected_project_ref','jfaufpfzfhysqkhcdsrs',
  'evaluation_helper_issuer_present',pg_catalog.strpos(
    pg_catalog.pg_get_functiondef('public.rosago_provider_session_current()'::regprocedure),
    'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1')>0,
  'http',(SELECT jsonb_build_object('available_version',a.default_version,'installed_version',a.installed_version,
     'installed_schema',(SELECT n.nspname FROM pg_catalog.pg_extension e
       JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='http'))
     FROM pg_catalog.pg_available_extensions a WHERE a.name='http'),
  'vault',(SELECT jsonb_build_object('available_version',a.default_version,'installed_version',a.installed_version)
     FROM pg_catalog.pg_available_extensions a WHERE a.name='supabase_vault'),
  'postgres_attributes',(SELECT jsonb_build_object('superuser',rolsuper,'bypassrls',rolbypassrls)
     FROM pg_catalog.pg_roles WHERE rolname='postgres'),
  'auth_sessions',(SELECT jsonb_build_object('owner',pg_catalog.pg_get_userbyid(c.relowner),
     'postgres_trigger_privilege',pg_catalog.has_table_privilege('postgres',c.oid,'TRIGGER'),
     'postgres_inherits_owner',pg_catalog.pg_has_role((SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres'),c.relowner,'USAGE'))
     FROM pg_catalog.pg_class c WHERE c.oid='auth.sessions'::regclass),
  'http_execution',(SELECT jsonb_agg(jsonb_build_object('signature',p.oid::regprocedure::text,
     'owner',pg_catalog.pg_get_userbyid(p.proowner),
     'postgres_execute',pg_catalog.has_function_privilege('postgres',p.oid,'EXECUTE')) ORDER BY p.oid::regprocedure::text)
     FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname='extensions' AND p.proname IN ('http','http_reset_curlopt','http_set_curlopt')),
  'existing_auth_session_triggers',(SELECT jsonb_agg(jsonb_build_object('name',tgname,'enabled',tgenabled)
     ORDER BY tgname) FROM pg_catalog.pg_trigger WHERE tgrelid='auth.sessions'::regclass AND NOT tgisinternal),
  'read_only',true
) AS independent_provider_authority_preflight_json;
COMMIT;
