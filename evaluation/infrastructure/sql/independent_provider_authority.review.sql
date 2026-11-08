-- EVALUATION CANDIDATE ONLY: jfaufpfzfhysqkhcdsrs. NOT APPROVED FOR APPLICATION.
-- Keep the two installed security scripts unchanged. No account/application DML.
BEGIN;
DO $gate$ BEGIN
  -- Removed only by the disposable local qualification harness, never in place.
  RAISE EXCEPTION 'UNQUALIFIED_INDEPENDENT_PROVIDER_AUTHORITY'; -- LOCAL_QUALIFICATION_GATE
END $gate$;
DO $baseline$ BEGIN
  IF pg_catalog.strpos(pg_catalog.pg_get_functiondef('public.rosago_provider_session_current()'::regprocedure),
      'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1')=0
     OR (SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='public'
         AND policyname='rosago_current_provider_session' AND permissive='RESTRICTIVE')<>9
     OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n
         ON n.oid=e.extnamespace WHERE e.extname='http' AND n.nspname='extensions')
     OR pg_catalog.to_regclass('vault.decrypted_secrets') IS NULL THEN
    RAISE EXCEPTION 'STOP: evaluation guard/http/Vault baseline mismatch';
  END IF;
END $baseline$;

CREATE SCHEMA rosago_provider_authority AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA rosago_provider_authority FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE rosago_provider_authority.config (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  origin text NOT NULL CHECK(origin ~ '^https://[a-z0-9]([a-z0-9.-]*[a-z0-9])?$'),
  authority_id text NOT NULL CHECK(authority_id ~ '^[A-Za-z0-9_-]{16,128}$'),
  incarnation text NOT NULL CHECK(incarnation ~ '^[A-Za-z0-9_-]{16,128}$'),
  namespace text NOT NULL CHECK(namespace ~ '^[A-Za-z0-9_-]{1,64}$'),
  check_secret_id uuid NOT NULL,
  revoke_secret_id uuid NOT NULL CHECK(revoke_secret_id<>check_secret_id)
);
ALTER TABLE rosago_provider_authority.config ENABLE ROW LEVEL SECURITY;
ALTER TABLE rosago_provider_authority.config FORCE ROW LEVEL SECURITY;
CREATE POLICY operator_only ON rosago_provider_authority.config TO postgres USING(true) WITH CHECK(true);
REVOKE ALL ON rosago_provider_authority.config FROM PUBLIC,anon,authenticated,service_role;
-- Intentionally NO config or secrets inserted. Empty configuration denies all.
-- The enrollment credential must NEVER be placed in PostgreSQL or Vault.

CREATE FUNCTION rosago_provider_authority.exchange(operation text, caller uuid, sid uuid, deadline double precision DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $function$
DECLARE
  c rosago_provider_authority.config%ROWTYPE;
  credential text;
  request jsonb;
  response extensions.http_response;
  result jsonb;
  nonce text := pg_catalog.replace(pg_catalog.gen_random_uuid()::text,'-','');
BEGIN
  IF operation NOT IN ('check','revoke','inspect','constrain') OR caller IS NULL OR sid IS NULL THEN RETURN NULL; END IF;
  SELECT * INTO STRICT c FROM rosago_provider_authority.config WHERE singleton;
  SELECT decrypted_secret INTO STRICT credential FROM vault.decrypted_secrets
    WHERE id=CASE WHEN operation IN ('revoke','constrain') THEN c.revoke_secret_id ELSE c.check_secret_id END;
  IF credential IS NULL OR length(credential)<32 OR length(credential)>256
      OR credential ~ '[[:space:]]' THEN RETURN NULL; END IF;
  request:=pg_catalog.jsonb_build_object('version',1,'nonce',nonce,
    'authority_id',c.authority_id,'incarnation',c.incarnation,'namespace',c.namespace,
    'issuer','https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1',
    'uid',caller::text,'sid',sid::text,'now',extract(epoch FROM pg_catalog.clock_timestamp()));
  IF operation='constrain' THEN request:=request||pg_catalog.jsonb_build_object('deadline',deadline); END IF;
  -- Clear pooled connection options, including caller-set proxies/CA/TLS flags.
  -- pgsql-http POST follows redirects; HEAD has no redirect branch and no body.
  PERFORM extensions.http_reset_curlopt();
  IF extensions.http_set_curlopt('CURLOPT_PROXY','') IS NOT TRUE
     OR extensions.http_set_curlopt('CURLOPT_CONNECTTIMEOUT_MS','300') IS NOT TRUE
     OR extensions.http_set_curlopt('CURLOPT_TIMEOUT_MS','1000') IS NOT TRUE THEN RETURN NULL; END IF;
  -- reset restores libcurl's verified-peer/hostname defaults and system CA.
  -- Do not require superuser-only TLS setters on hosted Supabase's postgres role.
  response:=extensions.http(ROW('HEAD',c.origin||'/v1/provider/'||operation,
    ARRAY[ROW('Authorization','Bearer '||credential)::extensions.http_header,
          ROW('X-RosaGo-Request',request::text)::extensions.http_header,
          ROW('Cache-Control','no-store')::extensions.http_header],NULL,NULL)::extensions.http_request);
  PERFORM extensions.http_reset_curlopt();
  IF response.status<>200 OR (SELECT count(*) FROM pg_catalog.unnest(response.headers) h
      WHERE lower(h.field)='x-rosago-result')<>1 THEN RETURN NULL; END IF;
  SELECT h.value::jsonb INTO STRICT result FROM pg_catalog.unnest(response.headers) h
    WHERE lower(h.field)='x-rosago-result' AND length(h.value)<=4096;
  IF result->>'version' IS DISTINCT FROM '1' OR result->>'nonce' IS DISTINCT FROM nonce
     OR result->>'authority_id' IS DISTINCT FROM c.authority_id
     OR result->>'incarnation' IS DISTINCT FROM c.incarnation
     OR result->>'namespace' IS DISTINCT FROM c.namespace
     OR result->>'issuer' IS DISTINCT FROM request->>'issuer'
     OR result->>'uid' IS DISTINCT FROM caller::text OR result->>'sid' IS DISTINCT FROM sid::text
     OR pg_catalog.jsonb_typeof(result->'now') IS DISTINCT FROM 'number'
     OR abs((result->>'now')::numeric-extract(epoch FROM pg_catalog.clock_timestamp()))>5
     OR pg_catalog.jsonb_typeof(result->'active') IS DISTINCT FROM 'boolean'
     OR pg_catalog.jsonb_typeof(result->'revoked') IS DISTINCT FROM 'boolean'
     OR pg_catalog.jsonb_typeof(result->'known') IS DISTINCT FROM 'boolean'
     OR pg_catalog.jsonb_typeof(result->'expired') IS DISTINCT FROM 'boolean'
     OR (result->>'active'='true' AND (result->>'revoked'='true' OR result->>'known'='false' OR result->>'expired'='true'))
     THEN RETURN NULL; END IF;
  RETURN result;
EXCEPTION WHEN OTHERS THEN
  PERFORM extensions.http_reset_curlopt();
  RETURN NULL; -- No credentials, raw transport errors, or optimistic fallback.
END $function$;

-- Diagnostic for logout confirmation only. It cannot authorize data access.
CREATE FUNCTION public.rosago_provider_session_present()
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $function$
DECLARE caller uuid:=auth.uid(); claims jsonb:=auth.jwt(); sid uuid;
BEGIN
  IF caller IS NULL OR claims->>'iss' IS DISTINCT FROM 'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1'
     OR claims->>'role' IS DISTINCT FROM 'authenticated' OR claims->>'aud' IS DISTINCT FROM 'authenticated'
     OR claims->>'sub' IS DISTINCT FROM caller::text
     OR NOT(coalesce(claims->>'session_id','') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
     OR NOT(coalesce(claims->>'exp','') ~ '^[0-9]{1,12}$') THEN RETURN NULL; END IF;
  IF (claims->>'exp')::bigint<=extract(epoch FROM pg_catalog.clock_timestamp()) THEN RETURN NULL; END IF;
  sid:=(claims->>'session_id')::uuid;
  RETURN EXISTS(SELECT 1 FROM auth.sessions s WHERE s.id=sid AND s.user_id=caller);
EXCEPTION WHEN OTHERS THEN RETURN NULL;
END $function$;

CREATE OR REPLACE FUNCTION public.rosago_provider_session_current()
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $function$
DECLARE result jsonb;
BEGIN
  IF public.rosago_provider_session_present() IS NOT TRUE THEN RETURN false; END IF;
  IF NOT EXISTS(SELECT 1 FROM auth.sessions s WHERE s.id=(auth.jwt()->>'session_id')::uuid
      AND s.user_id=auth.uid() AND (s.not_after IS NULL OR s.not_after>pg_catalog.clock_timestamp())) THEN
    RETURN false;
  END IF;
  result:=rosago_provider_authority.exchange('check',auth.uid(),(auth.jwt()->>'session_id')::uuid);
  RETURN coalesce(result->'active'='true'::jsonb,false);
EXCEPTION WHEN OTHERS THEN RETURN false;
END $function$;

-- Synchronous external tombstone BEFORE provider deletion. A failed SQL commit
-- never rolls back the external denial. Outage blocks deletion, never grants.
CREATE FUNCTION rosago_provider_authority.auth_session_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $function$
DECLARE result jsonb;
BEGIN
  IF TG_OP='DELETE' THEN
    result:=rosago_provider_authority.exchange('revoke',OLD.user_id,OLD.id);
    IF result->'revoked' IS DISTINCT FROM 'true'::jsonb THEN
      RAISE EXCEPTION 'Independent provider revocation unavailable' USING ERRCODE='42501';
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP='UPDATE' AND (NEW.id<>OLD.id OR NEW.user_id<>OLD.user_id) THEN
    RAISE EXCEPTION 'Provider session identity is immutable' USING ERRCODE='42501';
  END IF;
  IF NEW.not_after IS NOT NULL AND NEW.not_after<=pg_catalog.clock_timestamp() THEN
    result:=rosago_provider_authority.exchange('revoke',NEW.user_id,NEW.id);
    IF result->'revoked' IS DISTINCT FROM 'true'::jsonb THEN
      RAISE EXCEPTION 'Independent provider revocation unavailable' USING ERRCODE='42501';
    END IF;
  ELSE
    IF NEW.not_after IS NOT NULL THEN
      result:=rosago_provider_authority.exchange('constrain',NEW.user_id,NEW.id,
        extract(epoch FROM NEW.not_after)::double precision);
      IF result IS NULL THEN
        RAISE EXCEPTION 'Independent provider expiry unavailable' USING ERRCODE='42501';
      END IF;
    END IF;
    result:=rosago_provider_authority.exchange('inspect',NEW.user_id,NEW.id);
    IF result IS NULL OR result->'revoked'='true'::jsonb
       OR result->'expired'='true'::jsonb THEN
      RAISE EXCEPTION 'Provider session restoration denied' USING ERRCODE='42501';
    END IF;
  END IF;
  RETURN NEW;
END $function$;
CREATE TRIGGER rosago_independent_provider_session BEFORE INSERT OR UPDATE OR DELETE ON auth.sessions
  FOR EACH ROW EXECUTE FUNCTION rosago_provider_authority.auth_session_change();
ALTER TABLE auth.sessions ENABLE ALWAYS TRIGGER rosago_independent_provider_session;

CREATE FUNCTION rosago_provider_authority.deny_truncate()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $function$ BEGIN
  RAISE EXCEPTION 'Provider sessions require per-row independent revocation; TRUNCATE denied' USING ERRCODE='42501';
END $function$;
CREATE TRIGGER rosago_independent_provider_truncate BEFORE TRUNCATE ON auth.sessions
  FOR EACH STATEMENT EXECUTE FUNCTION rosago_provider_authority.deny_truncate();
ALTER TABLE auth.sessions ENABLE ALWAYS TRIGGER rosago_independent_provider_truncate;

ALTER FUNCTION rosago_provider_authority.exchange(text,uuid,uuid,double precision) OWNER TO postgres;
ALTER FUNCTION rosago_provider_authority.auth_session_change() OWNER TO postgres;
ALTER FUNCTION rosago_provider_authority.deny_truncate() OWNER TO postgres;
ALTER FUNCTION public.rosago_provider_session_present() OWNER TO postgres;
ALTER FUNCTION public.rosago_provider_session_current() OWNER TO postgres;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA rosago_provider_authority FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.rosago_provider_session_present() FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.rosago_provider_session_current() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_provider_session_present() TO authenticated;
GRANT EXECUTE ON FUNCTION public.rosago_provider_session_current() TO authenticated;
COMMIT;
