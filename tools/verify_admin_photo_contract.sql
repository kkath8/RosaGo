-- READ-ONLY production inspection. Run the entire script in a fresh connection.
-- No destination/auth/Storage data is read. Neither mutation function is invoked.
-- One result set: section, status, subject, details. FAIL requires correction;
-- REVIEW requires operator assessment; PASS is a catalog check, not deployment
-- approval. Owners must be trusted database operators, not application roles.
-- Definitions/hashes are exact-source comparisons with CR line endings removed.
-- Formatting-only edits therefore require review too. A photo hash indicates
-- deployment already happened; the baseline-guarded deployment is not rerunnable.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH
expected(function_role, expected_identity, baseline_md5, photo_md5) AS (
    VALUES
        ('inner', 'public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)',
         'd9d66eb24db349ccefabc2ea323be6c8', 'aa4441116ded963faa4e1ee8e3024e4b'),
        ('audit_wrapper', 'public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)',
         '4cab3fdc6baf75133fd19b8f1dde6345', NULL)
),
targets AS (
    SELECT e.*, pg_catalog.to_regprocedure(e.expected_identity)::pg_catalog.oid AS function_oid
    FROM expected e
),
functions AS (
    SELECT t.*, p.proowner, p.pronamespace, p.proacl, p.prosecdef, p.proconfig,
        p.prokind, p.prorettype, p.proretset, p.proargnames, p.pronargdefaults,
        p.provolatile, p.proisstrict, p.proparallel, p.proleakproof,
        owner_role.rolname AS owner_name, owner_role.rolsuper AS owner_superuser,
        owner_role.rolbypassrls AS owner_bypasses_rls, lang.lanname AS language,
        pg_catalog.pg_get_function_identity_arguments(p.oid) AS identity_arguments,
        pg_catalog.pg_get_function_result(p.oid) AS return_type,
        pg_catalog.pg_get_functiondef(p.oid) AS definition,
        pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),'')) AS source_md5,
        EXISTS (SELECT 1 FROM pg_catalog.unnest(p.proconfig) AS config(value)
                WHERE config.value IN ('search_path=', 'search_path=""')) AS empty_search_path,
        (p.prokind='f' AND p.prorettype='pg_catalog.jsonb'::pg_catalog.regtype
         AND NOT p.proretset AND p.pronargdefaults=0
         AND p.proargnames=ARRAY['p_action','p_slug','p_expected_updated_at','p_values']) AS signature_ok,
        (p.provolatile='v' AND NOT p.proisstrict AND p.proparallel='u' AND NOT p.proleakproof) AS call_properties_ok
    FROM targets t
    LEFT JOIN pg_catalog.pg_proc p ON p.oid=t.function_oid
    LEFT JOIN pg_catalog.pg_roles owner_role ON owner_role.oid=p.proowner
    LEFT JOIN pg_catalog.pg_language lang ON lang.oid=p.prolang
),
-- A NULL proacl means default privileges, including PUBLIC EXECUTE. Do not
-- mistake it for an empty ACL. PUBLIC is the ACL pseudo-role with OID zero.
execute_acl AS (
    SELECT f.function_role, f.function_oid, acl.grantee, acl.grantor,
        acl.is_grantable,
        CASE WHEN acl.grantee=0 THEN 'PUBLIC' ELSE grantee.rolname::text END AS grantee_name,
        grantor.rolname AS grantor_name
    FROM functions f
    CROSS JOIN LATERAL pg_catalog.aclexplode(
        COALESCE(f.proacl,pg_catalog.acldefault('f',f.proowner))) AS acl
    LEFT JOIN pg_catalog.pg_roles grantee ON grantee.oid=acl.grantee
    LEFT JOIN pg_catalog.pg_roles grantor ON grantor.oid=acl.grantor
    WHERE f.function_oid IS NOT NULL AND acl.privilege_type='EXECUTE'
),
role_access AS (
    -- Include all database roles so custom application roles cannot be missed.
    SELECT f.function_role, f.function_oid, r.oid AS role_oid, r.rolname,
        r.rolsuper, r.rolinherit, r.rolcanlogin, r.rolbypassrls,
        (r.oid=f.proowner) AS is_function_owner,
        (r.oid=(SELECT proowner FROM functions WHERE function_role='audit_wrapper')) AS is_wrapper_owner,
        EXISTS (SELECT 1 FROM execute_acl a
                WHERE a.function_oid=f.function_oid AND a.grantee=r.oid) AS direct_execute,
        EXISTS (SELECT 1 FROM execute_acl a
                WHERE a.function_oid=f.function_oid AND a.grantee=0) AS public_execute,
        ARRAY(SELECT DISTINCT a.grantee_name FROM execute_acl a
              WHERE a.function_oid=f.function_oid
                AND CASE WHEN a.grantee<>0 AND a.grantee<>r.oid
                         THEN pg_catalog.pg_has_role(r.oid,a.grantee,'USAGE') ELSE false END
              ORDER BY a.grantee_name) AS inherited_execute_via,
        CASE WHEN f.function_oid IS NOT NULL
             THEN pg_catalog.has_function_privilege(r.oid,f.function_oid,'EXECUTE') END AS effective_execute,
        CASE WHEN f.function_oid IS NOT NULL
             THEN pg_catalog.has_schema_privilege(r.oid,f.pronamespace,'USAGE') END AS schema_usage,
        -- SET ROLE capability is distinct from immediately inherited access.
        -- PostgreSQL 16+ honors the membership SET option. On older versions,
        -- MEMBER is the corresponding membership test. No SET ROLE is executed.
        ARRAY(SELECT switch_role.rolname::text FROM pg_catalog.pg_roles switch_role
              WHERE f.function_oid IS NOT NULL AND NOT r.rolsuper AND switch_role.oid<>r.oid
                AND CASE WHEN pg_catalog.current_setting('server_version_num')::integer>=160000
                         THEN pg_catalog.pg_has_role(r.oid,switch_role.oid,'SET')
                         ELSE pg_catalog.pg_has_role(r.oid,switch_role.oid,'MEMBER') END
                AND pg_catalog.has_function_privilege(switch_role.oid,f.function_oid,'EXECUTE')
                AND pg_catalog.has_schema_privilege(switch_role.oid,f.pronamespace,'USAGE')
              ORDER BY switch_role.rolname) AS set_role_execute_via
    FROM functions f CROSS JOIN pg_catalog.pg_roles r
),
role_report AS (
    SELECT a.*,
        CASE
            WHEN function_oid IS NULL THEN 'FAIL_FUNCTION_MISSING'
            WHEN rolsuper OR is_function_owner THEN 'INFO_PRIVILEGED_DATABASE_ROLE'
            WHEN function_role='inner' AND is_wrapper_owner
                THEN CASE WHEN effective_execute AND schema_usage THEN 'PASS_WRAPPER_CAN_CALL_INNER'
                          ELSE 'FAIL_WRAPPER_CANNOT_CALL_INNER' END
            WHEN function_role='inner' AND (effective_execute OR pg_catalog.cardinality(set_role_execute_via)>0)
                THEN CASE WHEN rolname IN ('anon','authenticated','service_role','authenticator')
                          THEN 'FAIL_APPLICATION_CAN_REACH_INNER' ELSE 'REVIEW_EXTRA_INNER_ACCESS' END
            WHEN function_role='audit_wrapper' AND rolname='authenticated'
                THEN CASE WHEN effective_execute AND schema_usage THEN 'PASS_EXPECTED_WRAPPER_ACCESS'
                          ELSE 'FAIL_AUTHENTICATED_WRAPPER_ACCESS_MISSING' END
            WHEN function_role='audit_wrapper' AND rolname IN ('anon','service_role','authenticator')
                 AND (effective_execute OR pg_catalog.cardinality(set_role_execute_via)>0)
                THEN 'REVIEW_UNEXPECTED_WRAPPER_ACCESS'
            WHEN function_role='audit_wrapper' AND effective_execute THEN 'REVIEW_EXTRA_WRAPPER_ACCESS'
            ELSE 'PASS_NO_UNEXPECTED_EXECUTE'
        END AS status
    FROM role_access a
),
report AS (
    SELECT '00_context'::text AS section, 'INFO'::text AS status,
        pg_catalog.current_database()::text AS subject,
        pg_catalog.jsonb_build_object(
            'observed_at',pg_catalog.statement_timestamp(),
            'server_version',pg_catalog.current_setting('server_version'),
            'current_user',current_user,'session_user',session_user,
            'transaction_read_only',pg_catalog.current_setting('transaction_read_only'),
            'note','Catalog inspection only. No target functions called. PASS does not establish that a database owner is trusted.') AS details
    UNION ALL
    SELECT '01_function',
        CASE WHEN f.function_oid IS NULL THEN 'FAIL_FUNCTION_MISSING'
             WHEN f.signature_ok IS NOT TRUE OR NOT f.prosecdef OR NOT f.empty_search_path OR f.language<>'plpgsql'
                  THEN 'FAIL_FUNCTION_CONTRACT_OR_SECURITY'
             WHEN f.owner_name IN ('anon','authenticated','service_role','authenticator')
                  THEN 'FAIL_APPLICATION_ROLE_OWNS_FUNCTION'
             WHEN NOT f.call_properties_ok THEN 'REVIEW_CHANGED_CALL_PROPERTIES'
             WHEN f.source_md5=f.photo_md5 THEN 'PASS_PHOTO_CONTRACT_ALREADY_APPLIED'
             WHEN f.source_md5=f.baseline_md5 THEN 'PASS_REVIEWED_BASELINE'
             ELSE 'REVIEW_SOURCE_HASH_DIFFERS' END,
        f.expected_identity,
        pg_catalog.jsonb_build_object(
            'oid',f.function_oid,'identity_arguments',f.identity_arguments,'return_type',f.return_type,
            'argument_names',f.proargnames,'owner',f.owner_name,'owner_superuser',f.owner_superuser,
            'owner_bypasses_rls',f.owner_bypasses_rls,'security_definer',f.prosecdef,
            'configuration',f.proconfig,'explicit_empty_search_path',f.empty_search_path,
            'language',f.language,'volatility',f.provolatile,'strict',f.proisstrict,
            'parallel',f.proparallel,'leakproof',f.proleakproof,
            'source_md5',f.source_md5,'expected_baseline_source_md5',f.baseline_md5,
            'expected_photo_source_md5',f.photo_md5,'definition',f.definition)
    FROM functions f
    UNION ALL
    SELECT '02_execute_acl',
        CASE WHEN a.grantee=0 THEN 'FAIL_PUBLIC_EXECUTE'
             WHEN a.function_role='inner' AND a.grantee_name IN ('anon','authenticated','service_role','authenticator')
                  THEN 'FAIL_DIRECT_APPLICATION_INNER_EXECUTE' ELSE 'INFO_EXPLICIT_OR_DEFAULT_GRANT' END,
        a.function_role || ' -> ' || COALESCE(a.grantee_name,'unknown role'),
        pg_catalog.jsonb_build_object('function_oid',a.function_oid,'grantee_oid',a.grantee,
            'grantor',a.grantor_name,'execute',true,'grant_option',a.is_grantable)
    FROM execute_acl a
    UNION ALL
    SELECT '02_public_execute',
        CASE WHEN f.function_oid IS NULL THEN 'FAIL_FUNCTION_MISSING'
             WHEN EXISTS (SELECT 1 FROM execute_acl a WHERE a.function_oid=f.function_oid AND a.grantee=0)
                  THEN 'FAIL_PUBLIC_EXECUTE' ELSE 'PASS_PUBLIC_EXECUTE_NOT_GRANTED' END,
        f.function_role || ' -> PUBLIC',
        pg_catalog.jsonb_build_object('function_oid',f.function_oid,
            'public_execute',EXISTS (SELECT 1 FROM execute_acl a WHERE a.function_oid=f.function_oid AND a.grantee=0))
    FROM functions f
    UNION ALL
    SELECT '03_role_effective_access',r.status,r.function_role || ' -> ' || r.rolname,
        pg_catalog.jsonb_build_object('role_oid',r.role_oid,'role_superuser',r.rolsuper,
            'role_inherit',r.rolinherit,'role_can_login',r.rolcanlogin,'role_bypasses_rls',r.rolbypassrls,
            'function_owner',r.is_function_owner,'audit_wrapper_owner',r.is_wrapper_owner,
            'direct_execute',r.direct_execute,'public_execute',r.public_execute,
            'inherited_execute_via',r.inherited_execute_via,
            'effective_execute_now',r.effective_execute,'schema_usage',r.schema_usage,
            'callable_now',r.effective_execute AND r.schema_usage,
            'potential_execute_after_set_role',r.set_role_execute_via)
    FROM role_report r
    UNION ALL
    SELECT '04_authenticated_inner_verdict',
        CASE WHEN r.function_oid IS NULL THEN 'FAIL_FUNCTION_MISSING'
             WHEN r.rolsuper OR r.is_function_owner OR r.is_wrapper_owner THEN 'FAIL_AUTHENTICATED_IS_PRIVILEGED_OWNER'
             WHEN r.effective_execute THEN 'FAIL_AUTHENTICATED_HAS_DIRECT_OR_INHERITED_INNER_EXECUTE'
             WHEN pg_catalog.cardinality(r.set_role_execute_via)>0 THEN 'FAIL_AUTHENTICATED_CAN_ASSUME_INNER_EXECUTOR'
             ELSE 'PASS_AUTHENTICATED_CANNOT_CALL_INNER' END,
        'authenticated -> inner',
        pg_catalog.jsonb_build_object('function_oid',r.function_oid,
            'effective_execute_now',r.effective_execute,'callable_now',r.effective_execute AND r.schema_usage,
            'inherited_execute_via',r.inherited_execute_via,'set_role_execute_via',r.set_role_execute_via,
            'note','The wrapper is intentionally executable by authenticated; its body must still verify auth.uid() Admin membership.')
    FROM role_report r WHERE r.function_role='inner' AND r.rolname='authenticated'
    UNION ALL
    SELECT '05_required_roles','FAIL_REQUIRED_ROLE_MISSING',required.name,
        pg_catalog.jsonb_build_object('note','Expected Supabase application role was not found.')
    FROM (VALUES ('anon'),('authenticated'),('service_role'),('authenticator')) AS required(name)
    WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname=required.name)
    UNION ALL
    SELECT '06_owner_compatibility',
        CASE WHEN i.function_oid IS NULL OR w.function_oid IS NULL THEN 'FAIL_FUNCTION_MISSING'
             WHEN pg_catalog.has_function_privilege(w.proowner,i.function_oid,'EXECUTE')
                  AND pg_catalog.has_schema_privilege(w.proowner,i.pronamespace,'USAGE')
                  THEN 'PASS_WRAPPER_OWNER_CAN_CALL_INNER' ELSE 'FAIL_WRAPPER_OWNER_CANNOT_CALL_INNER' END,
        'audit wrapper owner -> inner',
        pg_catalog.jsonb_build_object('wrapper_owner',w.owner_name,'inner_owner',i.owner_name,
            'same_owner',w.proowner=i.proowner,
            'note','Owner trust and inherited role memberships require manual review; no grants are changed.')
    FROM functions i CROSS JOIN functions w WHERE i.function_role='inner' AND w.function_role='audit_wrapper'
    UNION ALL
    SELECT '07_owner_trust',
        CASE WHEN f.function_oid IS NULL THEN 'FAIL_FUNCTION_MISSING' ELSE 'REVIEW_OWNER_TRUST_REQUIRED' END,
        f.expected_identity,
        pg_catalog.jsonb_build_object('owner',f.owner_name,'owner_superuser',f.owner_superuser,
            'owner_bypasses_rls',f.owner_bypasses_rls,
            'note','Confirm this is the approved trusted database owner. Source hashes do not certify owner identity or trust.')
    FROM functions f
)
SELECT section,status,subject,details FROM report ORDER BY section,subject;

COMMIT;
