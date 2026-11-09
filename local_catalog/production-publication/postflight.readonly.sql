-- AFTER a separately approved cutover only; do not run before preparation.
-- Confirm Dashboard project brnkigrrqdrywahvcbvc. No hosted writes.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_catalog.jsonb_build_object(
 'owner_selected_project_ref','brnkigrrqdrywahvcbvc','exported_at',pg_catalog.clock_timestamp(),
 'transaction_read_only',pg_catalog.current_setting('transaction_read_only'),
 'counts',(SELECT pg_catalog.jsonb_build_object('total',count(*),'published',count(*) FILTER(WHERE status='published'),
   'draft',count(*) FILTER(WHERE status='draft'),'archived',count(*) FILTER(WHERE status='archived')) FROM public.places),
 'rows',(SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(p) ORDER BY p.id) FROM public.places p),
 'categories',(SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(c) ORDER BY c.key) FROM public.destination_categories c),
 'receipts',(SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(b)) FROM rosago_catalog_private.publication_batches b),
 'place_policies',(SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(p)) FROM pg_catalog.pg_policies p WHERE schemaname='public' AND tablename='places'),
 'place_constraints',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',conname,'validated',convalidated,
   'definition',pg_catalog.pg_get_constraintdef(oid))) FROM pg_catalog.pg_constraint WHERE conrelid='public.places'::regclass),
 'functions',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',p.proname,'owner',pg_catalog.pg_get_userbyid(p.proowner),
   'security_definer',p.prosecdef,'config',p.proconfig,'acl',p.proacl::text,'body_md5',pg_catalog.md5(p.prosrc)))
   FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'rosago_%'),
 'audit_count',(SELECT count(*) FROM public.admin_destination_audit),
 'identity_counts',pg_catalog.jsonb_build_object('auth_users',(SELECT count(*) FROM auth.users),
   'profiles',(SELECT count(*) FROM public.profiles),'admin_memberships',(SELECT count(*) FROM public.admin_memberships)),
 'membership_identity_digest',(SELECT pg_catalog.md5(COALESCE(pg_catalog.string_agg(user_id::text,',' ORDER BY user_id),'')) FROM public.admin_memberships)
) AS publication_postflight_json;
ROLLBACK;
