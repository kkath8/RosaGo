-- READ-ONLY backup/export. Run the whole script in a fresh SQL connection.
-- Export BOTH result rows, including the complete definition and ACL fields,
-- as JSON or CSV. Save with the pre-deployment verification export.
-- Expect two PASS_REVIEWED_BASELINE rows before deploying the photo contract.
-- Any other status requires review before deployment. No target function runs.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH expected(identity,baseline_md5) AS (
    VALUES
      ('public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)',
       'd9d66eb24db349ccefabc2ea323be6c8'),
      ('public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)',
       '4cab3fdc6baf75133fd19b8f1dde6345')
), targets AS (
    SELECT e.*,pg_catalog.to_regprocedure(e.identity)::pg_catalog.oid AS function_oid
    FROM expected e
)
SELECT
    CASE WHEN p.oid IS NULL THEN 'FAIL_FUNCTION_MISSING'
         WHEN pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))=t.baseline_md5
              THEN 'PASS_REVIEWED_BASELINE' ELSE 'REVIEW_SOURCE_DIFFERS' END AS status,
    pg_catalog.statement_timestamp() AS exported_at,
    pg_catalog.current_database() AS database_name,
    pg_catalog.current_setting('server_version') AS server_version,
    t.identity AS expected_identity,p.oid AS function_oid,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS identity_arguments,
    pg_catalog.pg_get_function_result(p.oid) AS return_type,
    p.proargnames AS argument_names,p.proowner AS owner_oid,owner_role.rolname AS owner_name,
    p.prosecdef AS security_definer,p.proconfig AS function_configuration,
    p.provolatile AS volatility,p.proisstrict AS strict,p.proparallel AS parallel,
    p.proleakproof AS leakproof,
    p.proacl IS NULL AS acl_uses_default,p.proacl::text AS raw_acl,
    COALESCE((
        SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'grantor_oid',acl.grantor,'grantor',grantor.rolname,
            'grantee_oid',acl.grantee,
            'grantee',CASE WHEN acl.grantee=0 THEN 'PUBLIC' ELSE grantee.rolname::text END,
            'privilege',acl.privilege_type,'grant_option',acl.is_grantable)
            ORDER BY acl.grantee,acl.grantor,acl.privilege_type)
        FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) AS acl
        LEFT JOIN pg_catalog.pg_roles grantor ON grantor.oid=acl.grantor
        LEFT JOIN pg_catalog.pg_roles grantee ON grantee.oid=acl.grantee
        WHERE p.oid IS NOT NULL
    ),'[]'::pg_catalog.jsonb) AS grants,
    pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),'')) AS source_md5,
    t.baseline_md5 AS expected_baseline_md5,
    pg_catalog.pg_get_functiondef(p.oid) AS function_definition
FROM targets t
LEFT JOIN pg_catalog.pg_proc p ON p.oid=t.function_oid
LEFT JOIN pg_catalog.pg_roles owner_role ON owner_role.oid=p.proowner
ORDER BY t.identity;

COMMIT;
