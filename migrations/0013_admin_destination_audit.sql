-- REVIEW ONLY / UNAPPLIED. Audit logging requires migration approval.
-- Apply after reviewed 0012, using trusted postgres. No historical backfill.
BEGIN;
CREATE TABLE public.admin_destination_audit (
    id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    actor_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('create','edit','publish','draft','archive','restore')),
    destination_id uuid NOT NULL REFERENCES public.places(id) ON DELETE RESTRICT,
    occurred_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    summary jsonb NOT NULL
);
ALTER TABLE public.admin_destination_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.admin_destination_audit FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON TABLE public.admin_destination_audit TO authenticated;
CREATE POLICY admin_destination_audit_select ON public.admin_destination_audit
    FOR SELECT TO authenticated USING ((SELECT public.rosago_is_admin()));
CREATE INDEX admin_destination_audit_time_idx ON public.admin_destination_audit(occurred_at DESC,id);

ALTER FUNCTION public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)
    RENAME TO rosago_admin_mutate_destination_unlogged;
REVOKE ALL ON FUNCTION public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)
    FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION public.rosago_admin_mutate_destination(
    p_action text,p_slug text,p_expected_updated_at timestamptz,p_values jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE
    result jsonb;
    target_id uuid;
BEGIN
    -- Inner function performs authorization, validation, row and membership locks.
    result := public.rosago_admin_mutate_destination_unlogged(p_action,p_slug,p_expected_updated_at,p_values);
    SELECT id INTO STRICT target_id FROM public.places WHERE slug=result->>'slug';
    INSERT INTO public.admin_destination_audit(actor_id,action,destination_id,summary)
    VALUES ((SELECT auth.uid()),p_action,target_id,pg_catalog.jsonb_build_object(
        'submitted_fields',ARRAY(SELECT pg_catalog.jsonb_object_keys(p_values)),
        'resulting_status',result->>'status'));
    -- One transaction: logging failure rolls back the destination mutation.
    RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb) TO authenticated;
COMMIT;
