-- Run SELECTs separately through the unchanged evaluation MCP after approval
-- and owner execution. UUIDs/booleans only; no email/password/token extraction.
SELECT current_user AS inspection_role,
       current_setting('transaction_read_only') AS transaction_read_only;

SELECT u.id AS auth_uuid,
       u.email_confirmed_at IS NOT NULL AS individually_confirmed,
       p.id IS NOT NULL AS profile_exists,
       m.user_id IS NOT NULL AS admin_member
FROM auth.users u
LEFT JOIN public.profiles p ON p.id=u.id
LEFT JOIN public.admin_memberships m ON m.user_id=u.id
ORDER BY u.id;

SELECT 'auth_users' AS relation,count(*) AS total FROM auth.users
UNION ALL SELECT 'profiles',count(*) FROM public.profiles
UNION ALL SELECT 'admin_memberships',count(*) FROM public.admin_memberships
UNION ALL SELECT 'provider_sessions',count(*) FROM auth.sessions
UNION ALL SELECT 'places',count(*) FROM public.places
UNION ALL SELECT 'trips',count(*) FROM public.trips
UNION ALL SELECT 'trip_places',count(*) FROM public.trip_places
UNION ALL SELECT 'itinerary_drafts',count(*) FROM public.itinerary_drafts
UNION ALL SELECT 'trip_itinerary',count(*) FROM public.trip_itinerary
UNION ALL SELECT 'trip_stop_plans',count(*) FROM public.trip_stop_plans
UNION ALL SELECT 'admin_destination_audit',count(*) FROM public.admin_destination_audit
UNION ALL SELECT 'storage_buckets',count(*) FROM storage.buckets
UNION ALL SELECT 'storage_objects',count(*) FROM storage.objects;

SELECT id,slug,status FROM public.places ORDER BY id;
SELECT schemaname,tablename,policyname,roles,cmd,qual,with_check
FROM pg_policies WHERE schemaname='public'
AND tablename IN ('profiles','admin_memberships','places')
ORDER BY tablename,policyname;
-- Verify all 15 schema migration versions/names using list_migrations as well.
