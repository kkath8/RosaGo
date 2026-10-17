-- LOCAL ONLY, UNAPPLIED. Requires applied 0001-0004; never rerun/edit them.
-- Trusted postgres owns these fixed, narrow entry points (as in 0001).
-- SECURITY DEFINER is necessary: authenticated retains SELECT-only table ACLs.
-- No table grants/policies, dynamic SQL, provider calls, or final Save operation.
BEGIN;

-- Private validator: no application EXECUTE grant. Version 1 complete snapshot.
CREATE FUNCTION public.rosago_validate_draft_preferences(p_preferences jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    field_name text;
    selected_interests text[];
    first_date date;
    last_date date;
    first_time time;
    last_time time;
BEGIN
    IF p_preferences IS NULL OR pg_catalog.jsonb_typeof(p_preferences) <> 'object'
        OR pg_catalog.octet_length(p_preferences::text) > 16384 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    IF NOT (p_preferences ?& ARRAY['interests', 'companion_type', 'start_date',
            'end_date', 'daily_start_time', 'daily_end_time', 'transportation'])
        OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_object_keys(p_preferences) AS k(key)
            WHERE k.key NOT IN ('interests', 'companion_type', 'budget_centavos',
                'start_date', 'end_date', 'daily_start_time', 'daily_end_time',
                'transportation', 'timezone')) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    FOREACH field_name IN ARRAY ARRAY['companion_type', 'start_date', 'end_date',
            'daily_start_time', 'daily_end_time', 'transportation'] LOOP
        IF pg_catalog.jsonb_typeof(p_preferences -> field_name) IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
    END LOOP;
    IF p_preferences ->> 'companion_type' NOT IN ('solo', 'couple', 'family', 'friends', 'group')
        OR p_preferences ->> 'transportation' NOT IN ('walking', 'private_car', 'public_transport')
        OR (p_preferences ? 'timezone' AND
            (p_preferences -> 'timezone') IS DISTINCT FROM '"Asia/Manila"'::jsonb) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    IF pg_catalog.jsonb_typeof(p_preferences -> 'interests') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    IF pg_catalog.jsonb_array_length(p_preferences -> 'interests') NOT BETWEEN 1 AND 6
        OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(p_preferences -> 'interests') AS i(value)
            WHERE pg_catalog.jsonb_typeof(i.value) <> 'string') THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    SELECT pg_catalog.array_agg(i.value ORDER BY i.ordinality) INTO selected_interests
        FROM pg_catalog.jsonb_array_elements_text(p_preferences -> 'interests')
        WITH ORDINALITY AS i(value, ordinality);
    IF NOT public.rosago_itinerary_interests_valid(selected_interests) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    IF p_preferences ? 'budget_centavos' AND p_preferences -> 'budget_centavos' <> 'null'::jsonb THEN
        IF pg_catalog.jsonb_typeof(p_preferences -> 'budget_centavos') <> 'number'
            OR (p_preferences ->> 'budget_centavos') COLLATE "C" !~ '^(0|[1-9][0-9]{0,7})$' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
        IF (p_preferences ->> 'budget_centavos')::bigint > 10000000 THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
    END IF;
    -- Strict ISO spelling before casts: do not accept SQL's permissive date/time input.
    FOREACH field_name IN ARRAY ARRAY['start_date', 'end_date'] LOOP
        IF (p_preferences ->> field_name) COLLATE "C" !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
    END LOOP;
    FOREACH field_name IN ARRAY ARRAY['daily_start_time', 'daily_end_time'] LOOP
        IF (p_preferences ->> field_name) COLLATE "C" !~ '^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
    END LOOP;
    BEGIN
        first_date := (p_preferences ->> 'start_date')::date;
        last_date := (p_preferences ->> 'end_date')::date;
        first_time := (p_preferences ->> 'daily_start_time')::time;
        last_time := (p_preferences ->> 'daily_end_time')::time;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END;
    IF first_date NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
        OR last_date NOT BETWEEN first_date AND first_date + 6
        OR last_time <= first_time THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    -- Only documented defaults are added; malformed inputs are never repaired.
    RETURN p_preferences || pg_catalog.jsonb_build_object(
        'timezone', 'Asia/Manila', 'budget_centavos', COALESCE(p_preferences -> 'budget_centavos', 'null'::jsonb));
END;
$$;

CREATE FUNCTION public.rosago_itinerary_draft_create()
RETURNS TABLE (draft_id uuid, state text, revision bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    owner_id uuid := auth.uid();
BEGIN
    IF owner_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Authentication required.';
    END IF;
    RETURN QUERY INSERT INTO public.itinerary_drafts AS draft
        (user_id, state, schema_version, revision)
        VALUES (owner_id, 'editing', 1, 1)
        RETURNING draft.id, draft.state, draft.revision;
END;
$$;

CREATE FUNCTION public.rosago_itinerary_draft_update_preferences(
    p_draft_id uuid, p_expected_revision bigint, p_preferences jsonb)
RETURNS TABLE (draft_id uuid, state text, revision bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    owner_id uuid := auth.uid();
    validated_preferences jsonb;
BEGIN
    IF owner_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Authentication required.';
    END IF;
    IF p_draft_id IS NULL OR p_expected_revision IS NULL
        OR p_expected_revision NOT BETWEEN 1 AND 9223372036854775806 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    validated_preferences := public.rosago_validate_draft_preferences(p_preferences);
    -- Explicit ownership is mandatory because the function owner bypasses RLS.
    -- Lock first, then check wall-clock expiry AFTER any lock wait.
    PERFORM draft.id FROM public.itinerary_drafts AS draft
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    RETURN QUERY UPDATE public.itinerary_drafts AS draft
        SET preferences = validated_preferences, revision = draft.revision + 1
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id
            AND draft.state = 'editing' AND draft.schema_version = 1
            AND draft.expires_at > pg_catalog.clock_timestamp()
            AND draft.revision = p_expected_revision
        RETURNING draft.id, draft.state, draft.revision;
    IF NOT FOUND THEN
        -- Missing/foreign/stale/expired/non-editing are intentionally indistinguishable.
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
END;
$$;

ALTER FUNCTION public.rosago_validate_draft_preferences(jsonb) OWNER TO postgres;
ALTER FUNCTION public.rosago_itinerary_draft_create() OWNER TO postgres;
ALTER FUNCTION public.rosago_itinerary_draft_update_preferences(uuid, bigint, jsonb) OWNER TO postgres;
REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_validate_draft_preferences(jsonb),
    public.rosago_itinerary_draft_create(),
    public.rosago_itinerary_draft_update_preferences(uuid, bigint, jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rosago_itinerary_draft_create(),
    public.rosago_itinerary_draft_update_preferences(uuid, bigint, jsonb) TO authenticated;
COMMIT;
