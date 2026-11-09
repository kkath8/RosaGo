-- Owner-only read-only postflight. Contains destination/operator data, no credentials.
BEGIN READ ONLY;
SELECT jsonb_build_object('expected_project_ref','brnkigrrqdrywahvcbvc',
 'counts',(SELECT jsonb_build_object('total',count(*),'published',count(*) FILTER(WHERE status='published'),
  'draft',count(*) FILTER(WHERE status='draft'),'archived',count(*) FILTER(WHERE status='archived')) FROM public.places),
 'csv_status_counts',(SELECT jsonb_build_object('total',count(*),'published',count(*) FILTER(WHERE p.status='published'),
  'draft',count(*) FILTER(WHERE p.status='draft')) FROM rosago_owner_catalog98.events e JOIN public.places p ON p.id=e.destination_id
  WHERE e.csv_record IS NOT NULL AND e.action IN ('owner_create','owner_update')),
 'batches',(SELECT jsonb_agg(jsonb_build_object('batch_id',batch_id,'plan_sha256',plan_sha256,'operator',operator_name,
  'status',status,'applied_at',applied_at)) FROM rosago_owner_catalog98.batches),
 'owner_events',(SELECT count(*) FROM rosago_owner_catalog98.events),
 'function_access',(SELECT jsonb_agg(jsonb_build_object('signature',p.oid::regprocedure::text,'definer',p.prosecdef,'config',p.proconfig,
  'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
  'service_execute',has_function_privilege('service_role',p.oid,'EXECUTE'))) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='rosago_owner_catalog98'),
 'auth_users',(SELECT count(*) FROM auth.users),'profiles',(SELECT count(*) FROM public.profiles),
 'admin_memberships',(SELECT count(*) FROM public.admin_memberships),
 'read_only',true) AS owner98_postflight_json;
COMMIT;
