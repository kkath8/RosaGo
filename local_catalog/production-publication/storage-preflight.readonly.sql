-- OWNER READ-ONLY ONLY. Confirm Dashboard project brnkigrrqdrywahvcbvc.
-- No credential, Auth session, password, or object-body export.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_catalog.jsonb_build_object(
 'export_format','rosago_publication_storage_preflight_v1',
 'owner_selected_project_ref','brnkigrrqdrywahvcbvc',
 'project_identity_requires_dashboard_confirmation',true,
 'exported_at',pg_catalog.clock_timestamp(),'database_role',current_user,
 'transaction_read_only',pg_catalog.current_setting('transaction_read_only'),
 'bucket',(SELECT pg_catalog.jsonb_build_object('id',b.id,'public',b.public,
   'file_size_limit',b.file_size_limit,'allowed_mime_types',b.allowed_mime_types)
   FROM storage.buckets b WHERE b.id='destination-images'),
 'objects',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
   'name',o.name,'size',o.metadata->'size','mimetype',o.metadata->'mimetype') ORDER BY o.name)
   FROM storage.objects o WHERE o.bucket_id='destination-images'),'[]'::jsonb),
 'policies',(SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(p)) FROM pg_catalog.pg_policies p
   WHERE schemaname='storage' AND tablename IN ('objects','buckets')),
 'identity_counts',pg_catalog.jsonb_build_object(
   'auth_users',(SELECT count(*) FROM auth.users),'profiles',(SELECT count(*) FROM public.profiles),
   'admin_memberships',(SELECT count(*) FROM public.admin_memberships)),
 'membership_identity_digest',(SELECT pg_catalog.md5(COALESCE(pg_catalog.string_agg(user_id::text,',' ORDER BY user_id),'')) FROM public.admin_memberships)
) AS publication_storage_preflight_json;
ROLLBACK;
