-- EVALUATION ONLY: operator confirms SQL Editor project jfaufpfzfhysqkhcdsrs.
-- Read-only postflight; definitions contain secret REFERENCES, never secret values.
BEGIN READ ONLY;
SELECT pg_catalog.jsonb_build_object(
  'expected_project_ref','jfaufpfzfhysqkhcdsrs',
  'project_identity_attestation','Operator must independently confirm project in dashboard',
  'http_extension',(SELECT jsonb_build_object('version',e.extversion,'schema',n.nspname)
    FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='http'),
  'vault_present',pg_catalog.to_regclass('vault.decrypted_secrets') IS NOT NULL,
  'private_schema_present',pg_catalog.to_regnamespace('rosago_provider_authority') IS NOT NULL,
  'private_config',(SELECT jsonb_build_object('rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,
    'owner',pg_catalog.pg_get_userbyid(c.relowner)) FROM pg_catalog.pg_class c
    WHERE c.oid=pg_catalog.to_regclass('rosago_provider_authority.config')),
  'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.tablename,p.policyname)
    FROM pg_catalog.pg_policies p WHERE (p.schemaname='public' AND p.policyname='rosago_current_provider_session')
      OR p.schemaname='rosago_provider_authority'),
  'functions',(SELECT jsonb_agg(jsonb_build_object('signature',p.oid::regprocedure::text,
    'owner',pg_catalog.pg_get_userbyid(p.proowner),'definer',p.prosecdef,'settings',p.proconfig,
    'body_md5',md5(p.prosrc),'definition',pg_catalog.pg_get_functiondef(p.oid),
    'anon_execute',pg_catalog.has_function_privilege('anon',p.oid,'EXECUTE'),
    'authenticated_execute',pg_catalog.has_function_privilege('authenticated',p.oid,'EXECUTE'),
    'service_execute',pg_catalog.has_function_privilege('service_role',p.oid,'EXECUTE')) ORDER BY p.oid::regprocedure::text)
    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='rosago_provider_authority' OR (n.nspname='public' AND p.proname IN
      ('rosago_provider_session_current','rosago_provider_session_present',
       'rosago_itinerary_draft_create','rosago_itinerary_draft_store_preview','rosago_itinerary_draft_adjust_preview',
       'rosago_itinerary_draft_return_to_editing','rosago_itinerary_draft_update_preferences',
       'rosago_admin_mutate_destination','rosago_admin_operational_overview'))),
  'auth_session_triggers',(SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'enabled',t.tgenabled,
    'definition',pg_catalog.pg_get_triggerdef(t.oid)) ORDER BY t.tgname)
    FROM pg_catalog.pg_trigger t WHERE t.tgrelid='auth.sessions'::regclass AND NOT t.tgisinternal),
  'existing_record_counts',jsonb_build_object('auth_users',(SELECT count(*) FROM auth.users),
    'profiles',(SELECT count(*) FROM public.profiles),'memberships',(SELECT count(*) FROM public.admin_memberships),
    'destinations',(SELECT count(*) FROM public.places)),
  'migration_history_relation_present',pg_catalog.to_regclass('supabase_migrations.schema_migrations') IS NOT NULL,
  'migration_history',CASE WHEN pg_catalog.to_regclass('supabase_migrations.schema_migrations') IS NULL THEN NULL
    ELSE pg_catalog.query_to_xml('SELECT version,name FROM supabase_migrations.schema_migrations ORDER BY version',
      true,true,'')::text END,
  'read_only',true
) AS independent_provider_authority_postflight_json;
COMMIT;
