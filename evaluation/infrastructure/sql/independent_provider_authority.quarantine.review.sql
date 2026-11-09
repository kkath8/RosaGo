-- EVALUATION EMERGENCY DENIAL CANDIDATE. Separate approval required; never run automatically.
-- Retain external revocations, Auth triggers, private configuration and new ACLs.
BEGIN;
DO $gate$ BEGIN
  RAISE EXCEPTION 'UNAPPROVED_EVALUATION_QUARANTINE'; -- LOCAL_QUALIFICATION_GATE
END $gate$;
DO $target$ BEGIN
  IF pg_catalog.strpos(pg_catalog.pg_get_functiondef('public.rosago_provider_session_present()'::regprocedure),
     'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1')=0 THEN
    RAISE EXCEPTION 'Evaluation guard identity mismatch';
  END IF;
END $target$;
CREATE OR REPLACE FUNCTION public.rosago_provider_session_current()
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=''
AS $$ SELECT false $$;
ALTER FUNCTION public.rosago_provider_session_current() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.rosago_provider_session_current() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_provider_session_current() TO authenticated;
COMMIT;
