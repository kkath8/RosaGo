-- REVIEW ONLY / NOT APPROVED FOR HOSTED APPLICATION OR MIGRATION RUNNERS.
-- Target jfaufpfzfhysqkhcdsrs. New schema approval is required separately.
-- Session-removal/not_after evidence only, not complete provider expiry policy,
-- protected recovery authority, or direct-API revocation enforcement.
BEGIN;
CREATE FUNCTION public.rosago_provider_session_current()
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    caller uuid := auth.uid();
    claims jsonb := auth.jwt();
    provider_session uuid;
BEGIN
    IF caller IS NULL
       OR claims->>'iss' IS DISTINCT FROM 'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1'
       OR claims->>'role' IS DISTINCT FROM 'authenticated'
       OR claims->>'aud' IS DISTINCT FROM 'authenticated'
       OR claims->>'sub' IS DISTINCT FROM caller::text
       OR NOT (COALESCE(claims->>'session_id','') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
       OR NOT (COALESCE(claims->>'exp','') ~ '^[0-9]{1,12}$') THEN
        RETURN false;
    END IF;
    IF (claims->>'exp')::bigint <= EXTRACT(EPOCH FROM pg_catalog.clock_timestamp()) THEN
        RETURN false;
    END IF;
    provider_session := (claims->>'session_id')::uuid;
    RETURN EXISTS (
        SELECT 1 FROM auth.sessions s
        WHERE s.id=provider_session AND s.user_id=caller
          AND (s.not_after IS NULL OR s.not_after > pg_catalog.clock_timestamp())
    );
END;
$$;
ALTER FUNCTION public.rosago_provider_session_current() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.rosago_provider_session_current()
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_provider_session_current() TO authenticated;
COMMIT;
