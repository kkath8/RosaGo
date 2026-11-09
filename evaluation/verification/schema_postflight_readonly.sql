-- Read-only inventory after schema-only application to jfaufpfzfhysqkhcdsrs.
-- First verify the project URL independently through supabase-evaluation.
-- No account, seed, role impersonation, RPC mutation or configuration changes.
SELECT current_user AS inspection_role,
       current_setting('transaction_read_only') AS transaction_read_only;

SELECT c.relname AS table_name, pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS force_rls,
       c.relacl::text AS table_acl
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1;

SELECT table_name,column_name,data_type,is_nullable,column_default
FROM information_schema.columns WHERE table_schema='public'
ORDER BY table_name,ordinal_position;

SELECT c.relname AS table_name,k.conname,k.contype,k.convalidated,
       pg_get_constraintdef(k.oid,true) AS definition
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' ORDER BY 1,2;

SELECT c.relname AS table_name,i.relname AS index_name,
       x.indisvalid,x.indisready,pg_get_indexdef(i.oid) AS definition
FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid
JOIN pg_class i ON i.oid=x.indexrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' ORDER BY 1,2;

SELECT grantee,table_name,privilege_type,is_grantable
FROM information_schema.table_privileges WHERE table_schema='public'
ORDER BY table_name,grantee,privilege_type;
SELECT grantee,table_name,column_name,privilege_type
FROM information_schema.column_privileges WHERE table_schema='public'
ORDER BY table_name,column_name,grantee,privilege_type;

SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check
FROM pg_policies WHERE schemaname IN ('public','auth','storage')
ORDER BY schemaname,tablename,policyname;

SELECT p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,
       pg_get_userbyid(p.proowner) AS owner,p.prosecdef,p.proconfig,
       p.proacl::text AS acl,md5(replace(p.prosrc,chr(13),'')) AS body_md5,
       has_function_privilege('anon',p.oid,'EXECUTE') AS anon_execute,
       has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_execute,
       has_function_privilege('service_role',p.oid,'EXECUTE') AS service_role_execute
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' ORDER BY 1,2;

SELECT t.tgname,pg_get_triggerdef(t.oid,true) AS definition
FROM pg_trigger t WHERE NOT t.tgisinternal
AND (t.tgrelid='auth.users'::regclass OR t.tgrelid IN
    (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public')) ORDER BY 1;

-- Every count must remain zero after schema-only setup.
SELECT 'profiles' AS relation,count(*) FROM public.profiles
UNION ALL SELECT 'places',count(*) FROM public.places
UNION ALL SELECT 'trips',count(*) FROM public.trips
UNION ALL SELECT 'trip_places',count(*) FROM public.trip_places
UNION ALL SELECT 'itinerary_drafts',count(*) FROM public.itinerary_drafts
UNION ALL SELECT 'trip_itinerary',count(*) FROM public.trip_itinerary
UNION ALL SELECT 'trip_stop_plans',count(*) FROM public.trip_stop_plans
UNION ALL SELECT 'admin_memberships',count(*) FROM public.admin_memberships
UNION ALL SELECT 'admin_destination_audit',count(*) FROM public.admin_destination_audit
UNION ALL SELECT 'auth.users',count(*) FROM auth.users
UNION ALL SELECT 'storage.buckets',count(*) FROM storage.buckets
UNION ALL SELECT 'storage.objects',count(*) FROM storage.objects;

-- Use supabase-evaluation.list_migrations separately. This SELECT also locates
-- the history table without assuming that the migration runner has created it.
SELECT to_regclass('supabase_migrations.schema_migrations') AS migration_history;
