SELECT jsonb_build_object(
'role',current_user,'read_only',current_setting('transaction_read_only'),
'tables',(SELECT jsonb_agg(jsonb_build_object('name',c.relname,'owner',pg_get_userbyid(c.relowner),'rls',c.relrowsecurity,'acl',c.relacl::text) ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'),
'columns',(SELECT jsonb_agg(jsonb_build_object('table',c.relname,'name',a.attname,'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,'default',pg_get_expr(d.adbin,d.adrelid),'acl',a.attacl::text) ORDER BY c.relname,a.attnum) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped),
'constraints',(SELECT jsonb_agg(jsonb_build_object('table',c.relname,'name',k.conname,'type',k.contype,'validated',k.convalidated,'definition',pg_get_constraintdef(k.oid,true)) ORDER BY c.relname,k.conname) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),
'indexes',(SELECT jsonb_agg(jsonb_build_object('table',c.relname,'name',i.relname,'valid',x.indisvalid,'ready',x.indisready,'definition',pg_get_indexdef(i.oid)) ORDER BY c.relname,i.relname) FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),
'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.tablename,p.policyname) FROM pg_policies p WHERE schemaname='public'),
'functions',(SELECT jsonb_agg(jsonb_build_object('name',p.proname,'arguments',pg_get_function_identity_arguments(p.oid),'owner',pg_get_userbyid(p.proowner),'definer',p.prosecdef,'config',p.proconfig,'acl',p.proacl::text,'body_md5',md5(replace(p.prosrc,chr(13),'')),'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),'service_execute',has_function_privilege('service_role',p.oid,'EXECUTE')) ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'),
'triggers',(SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'definition',pg_get_triggerdef(t.oid,true)) ORDER BY t.tgname) FROM pg_trigger t WHERE NOT t.tgisinternal AND (t.tgrelid='auth.users'::regclass OR t.tgrelid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'))),
'counts',(SELECT jsonb_object_agg(relation,total) FROM (
SELECT 'profiles' AS relation,count(*) AS total FROM public.profiles
UNION ALL SELECT 'places',count(*) FROM public.places
UNION ALL SELECT 'trips',count(*) FROM public.trips
UNION ALL SELECT 'trip_places',count(*) FROM public.trip_places
UNION ALL SELECT 'itinerary_drafts',count(*) FROM public.itinerary_drafts
UNION ALL SELECT 'trip_itinerary',count(*) FROM public.trip_itinerary
UNION ALL SELECT 'trip_stop_plans',count(*) FROM public.trip_stop_plans
UNION ALL SELECT 'admin_memberships',count(*) FROM public.admin_memberships
UNION ALL SELECT 'admin_destination_audit',count(*) FROM public.admin_destination_audit
UNION ALL SELECT 'auth_users',count(*) FROM auth.users
UNION ALL SELECT 'storage_buckets',count(*) FROM storage.buckets
UNION ALL SELECT 'storage_objects',count(*) FROM storage.objects) q)
) AS postflight;
