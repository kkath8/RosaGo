-- LOCAL, UNAPPLIED. Requires 0006 and 0007. Apply once after review.
-- No table/RLS changes. A failed nested store rolls back every intermediate write.
BEGIN;
CREATE FUNCTION public.rosago_itinerary_draft_adjust_preview(
    p_draft_id uuid, p_expected_revision bigint, p_preferences jsonb, p_candidate_preview jsonb)
RETURNS TABLE (draft_id uuid, state text, revision bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    owner_id uuid := auth.uid();
    locked_draft public.itinerary_drafts%ROWTYPE;
    validated_preferences jsonb;
BEGIN
    IF owner_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Authentication required.';
    END IF;
    IF p_draft_id IS NULL OR p_expected_revision IS NULL
        OR p_expected_revision NOT BETWEEN 1 AND 9223372036854775806
        OR pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    SELECT draft.* INTO locked_draft FROM public.itinerary_drafts AS draft
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    IF locked_draft.state <> 'preview_ready' OR locked_draft.schema_version <> 1
        OR locked_draft.revision <> p_expected_revision
        OR locked_draft.expires_at <= pg_catalog.clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    validated_preferences := public.rosago_validate_draft_preferences(p_preferences);
    IF validated_preferences IS DISTINCT FROM p_preferences
        OR (validated_preferences - ARRAY['interests', 'trip_pace']) IS DISTINCT FROM
           (locked_draft.preferences - ARRAY['interests', 'trip_pace']) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    -- Private, transaction-local transition permits a changed selection using the
    -- unchanged 0007 writer. It revalidates the contract, locks published Places,
    -- verifies category eligibility/fingerprint, rechecks expiry after lock waits,
    -- and increments revision exactly once. Exceptions propagate and roll back.
    UPDATE public.itinerary_drafts AS draft
        SET preferences = validated_preferences, preview = NULL, state = 'editing'
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id;
    RETURN QUERY SELECT stored.draft_id, stored.state, stored.revision
        FROM public.rosago_itinerary_draft_store_preview(
            p_draft_id, p_expected_revision, p_candidate_preview) AS stored;
END;
$$;
ALTER FUNCTION public.rosago_itinerary_draft_adjust_preview(uuid, bigint, jsonb, jsonb) OWNER TO postgres;
REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_itinerary_draft_adjust_preview(uuid, bigint, jsonb, jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rosago_itinerary_draft_adjust_preview(uuid, bigint, jsonb, jsonb) TO authenticated;
COMMIT;
