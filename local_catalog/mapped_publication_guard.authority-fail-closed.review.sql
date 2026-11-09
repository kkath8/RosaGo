-- REVIEW REVISION: NULL/unknown authority is denied; original qualified draft preserved.
-- LOCAL REVIEW DRAFT ONLY. NO HOSTED EXECUTION APPROVAL.
-- Apply only after qualified catalog_extension, current target preflight,
-- explicit policy/visibility-impact approval and authenticated RPC qualification.
-- No coordinate evidence is backfilled; valid-looking numbers are not verified.
BEGIN;
DO $gate$
BEGIN
    RAISE EXCEPTION 'UNQUALIFIED_HOSTED_PREFLIGHT: do not apply this review draft.';
END;
$gate$;

CREATE SCHEMA rosago_catalog_private;
REVOKE ALL ON SCHEMA rosago_catalog_private FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE rosago_catalog_private.location_verifications (
    destination_id uuid PRIMARY KEY REFERENCES public.places(id) ON DELETE RESTRICT,
    confirmed_name text NOT NULL,
    confirmed_address text NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90
        AND latitude NOT IN ('NaN'::double precision,'Infinity'::double precision,'-Infinity'::double precision)),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180
        AND longitude NOT IN ('NaN'::double precision,'Infinity'::double precision,'-Infinity'::double precision)),
    evidence_ref text NOT NULL CHECK (pg_catalog.char_length(evidence_ref) BETWEEN 1 AND 1000
        AND evidence_ref=pg_catalog.btrim(evidence_ref)),
    verified_by uuid NOT NULL,
    verified_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);
ALTER TABLE rosago_catalog_private.location_verifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON rosago_catalog_private.location_verifications FROM PUBLIC,anon,authenticated,service_role;
-- There are deliberately no ordinary-role policies or private schema USAGE.
CREATE FUNCTION rosago_catalog_private.location_verified(
    p_id uuid,p_name text,p_address text,p_latitude double precision,p_longitude double precision)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $verified$
    SELECT EXISTS (SELECT 1 FROM rosago_catalog_private.location_verifications v
        WHERE v.destination_id=p_id AND v.confirmed_name=p_name AND v.confirmed_address=p_address
          AND v.latitude=p_latitude AND v.longitude=p_longitude);
$verified$;
REVOKE ALL ON FUNCTION rosago_catalog_private.location_verified(uuid,text,text,double precision,double precision)
    FROM PUBLIC,anon,authenticated,service_role;
-- Stored CHECK/policy expressions resolve this function by OID. Schema USAGE
-- stays denied, so clients cannot call this private predicate by name/RPC.
GRANT EXECUTE ON FUNCTION rosago_catalog_private.location_verified(uuid,text,text,double precision,double precision)
    TO anon,authenticated;

ALTER TABLE public.places ADD CONSTRAINT places_verified_location_before_publication CHECK (
    status<>'published' OR rosago_catalog_private.location_verified(id,name,address,latitude,longitude)
) NOT VALID;
-- NOT VALID avoids modifying existing records. New/changed Published rows must
-- satisfy evidence immediately. Validate after the approved catalog cutover.
CREATE POLICY places_verified_location_anon_visibility ON public.places AS RESTRICTIVE
    FOR SELECT TO anon USING (status='published'
        AND rosago_catalog_private.location_verified(id,name,address,latitude,longitude));
CREATE POLICY places_verified_location_user_visibility ON public.places AS RESTRICTIVE
    FOR SELECT TO authenticated USING (public.rosago_is_admin()
        OR (status='published' AND rosago_catalog_private.location_verified(id,name,address,latitude,longitude)));
-- The existing published-only and provider-session policies still apply.
-- This hides legacy unverified Published records from ordinary readers at
-- installation: that impact needs separate explicit cutover approval.

CREATE FUNCTION public.rosago_admin_verify_destination_location(
    p_slug text,p_expected_updated_at timestamptz,p_values jsonb,p_evidence_ref text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $approval$
DECLARE
    result jsonb;
    destination public.places%ROWTYPE;
BEGIN
    -- The production preflight currently lacks this caller-bound authority.
    -- Refuse verification rather than assuming the older Admin wrapper has it.
    IF pg_catalog.to_regprocedure('public.rosago_provider_session_current()') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Provider-session authority unavailable.';
    END IF;
    IF public.rosago_provider_session_current() IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Current provider session required.';
    END IF;
    -- After the caller-bound provider check, delegate to the CURRENT audited
    -- mutation wrapper for its existing Admin and row-version checks.
    -- Do not copy a stale authorization preamble into this new RPC.
    result := public.rosago_admin_mutate_destination('edit',p_slug,p_expected_updated_at,p_values);
    IF result->>'status' IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Verify a Draft destination before publication.';
    END IF;
    IF p_values IS NULL OR pg_catalog.jsonb_typeof(p_values)<>'object'
       OR NOT (p_values ?& ARRAY['name','category','description','address','latitude','longitude'])
       OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_object_keys(p_values) k
           WHERE k NOT IN ('name','category','description','address','latitude','longitude'))
       OR p_evidence_ref IS NULL OR pg_catalog.char_length(p_evidence_ref) NOT BETWEEN 1 AND 1000
       OR p_evidence_ref<>pg_catalog.btrim(p_evidence_ref) THEN
        RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid coordinate confirmation.';
    END IF;
    SELECT * INTO STRICT destination FROM public.places WHERE slug=result->>'slug' FOR UPDATE;
    IF destination.latitude IS NULL OR destination.longitude IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Confirm both coordinates before verification.';
    END IF;
    INSERT INTO rosago_catalog_private.location_verifications(
        destination_id,confirmed_name,confirmed_address,latitude,longitude,evidence_ref,verified_by)
    VALUES (destination.id,destination.name,destination.address,destination.latitude,destination.longitude,
        p_evidence_ref,(SELECT auth.uid()))
    ON CONFLICT (destination_id) DO UPDATE SET confirmed_name=EXCLUDED.confirmed_name,
        confirmed_address=EXCLUDED.confirmed_address,latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,
        evidence_ref=EXCLUDED.evidence_ref,verified_by=EXCLUDED.verified_by,
        verified_at=pg_catalog.clock_timestamp();
    INSERT INTO public.admin_destination_audit(actor_id,action,destination_id,summary)
    VALUES ((SELECT auth.uid()),'edit',destination.id,pg_catalog.jsonb_build_object(
        'submitted_fields',ARRAY['coordinate_verification'],'resulting_status','draft'));
    RETURN result;
    -- Any validation/evidence/audit failure rolls back the delegated edit too.
END;
$approval$;
REVOKE ALL ON FUNCTION public.rosago_admin_verify_destination_location(text,timestamptz,jsonb,text)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_admin_verify_destination_location(text,timestamptz,jsonb,text)
    TO authenticated;
COMMIT;
-- No new authentication flow, no owner evidence insertion, no auto-verification.
-- Coordinate/identity edits invalidate the predicate by tuple mismatch; edit a
-- Draft and explicitly reverify rather than moving an already Published point.
