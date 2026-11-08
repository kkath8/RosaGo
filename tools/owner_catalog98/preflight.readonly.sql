-- Owner-operated production preflight ONLY. No schema or data writes.
-- Operator must independently confirm Dashboard project brnkigrrqdrywahvcbvc.
BEGIN READ ONLY;
SELECT jsonb_build_object('expected_project_ref','brnkigrrqdrywahvcbvc',
 'identity_basis','Operator-confirmed Dashboard selection; expected ref is not server attestation',
 'session_user',SESSION_USER,'current_user',CURRENT_USER,'transaction_read_only',current_setting('transaction_read_only'),
 'counts',(SELECT jsonb_build_object('total',count(*),'published',count(*) FILTER(WHERE status='published'),
  'draft',count(*) FILTER(WHERE status='draft'),'archived',count(*) FILTER(WHERE status='archived')) FROM public.places),
 'prior_owner_batch_schema',to_regnamespace('rosago_owner_catalog98') IS NOT NULL,
 'auth_users',(SELECT count(*) FROM auth.users),'profiles',(SELECT count(*) FROM public.profiles),
 'admin_memberships',(SELECT count(*) FROM public.admin_memberships)) AS owner98_preflight_json;
COMMIT;
