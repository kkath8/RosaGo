-- LOCAL ONLY, UNAPPLIED. Requires live 0001-0005. Never rerun those migrations.
-- Replace only the private JSONB validator; no table, policy or public RPC changes.
BEGIN;

CREATE OR REPLACE FUNCTION public.rosago_validate_draft_preferences(p_preferences jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    field_name text;
    selected_interests text[];
    free_text text;
    text_limit integer;
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
            'end_date', 'daily_start_time', 'daily_end_time', 'transportation',
            'trip_pace', 'activity_preferences', 'environment_preference'])
        OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_object_keys(p_preferences) AS k(key)
            WHERE k.key NOT IN ('interests', 'companion_type', 'budget_centavos',
                'start_date', 'end_date', 'daily_start_time', 'daily_end_time',
                'transportation', 'timezone', 'trip_pace', 'activity_preferences',
                'environment_preference', 'other_interests', 'additional_preferences')) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    FOREACH field_name IN ARRAY ARRAY['companion_type', 'start_date', 'end_date',
            'daily_start_time', 'daily_end_time', 'transportation', 'trip_pace',
            'environment_preference'] LOOP
        IF pg_catalog.jsonb_typeof(p_preferences -> field_name) IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
    END LOOP;
    IF p_preferences ->> 'companion_type' NOT IN ('solo', 'couple', 'family', 'friends', 'group')
        OR p_preferences ->> 'transportation' NOT IN ('walking', 'bicycle', 'motorcycle',
            'private_car', 'public_transport', 'ride_hailing', 'mixed_transport')
        OR p_preferences ->> 'trip_pace' NOT IN ('relaxed', 'balanced', 'packed')
        OR p_preferences ->> 'environment_preference' NOT IN ('indoor', 'outdoor', 'mixed')
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
    IF pg_catalog.jsonb_typeof(p_preferences -> 'activity_preferences') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    IF pg_catalog.jsonb_array_length(p_preferences -> 'activity_preferences') NOT BETWEEN 1 AND 6
        OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(p_preferences -> 'activity_preferences') AS i(value)
            WHERE pg_catalog.jsonb_typeof(i.value) <> 'string'
                OR i.value #>> '{}' NOT IN ('sightseeing', 'food_trip', 'shopping',
                    'outdoor_activities', 'culture_heritage', 'relaxation'))
        OR pg_catalog.jsonb_array_length(p_preferences -> 'activity_preferences') <> (
            SELECT pg_catalog.count(DISTINCT i.value)
            FROM pg_catalog.jsonb_array_elements(p_preferences -> 'activity_preferences') AS i(value)) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    -- Untrusted literal text, never interpreted as SQL, JSON, HTML or instructions.
    FOREACH field_name IN ARRAY ARRAY['other_interests', 'additional_preferences'] LOOP
        IF p_preferences ? field_name AND p_preferences -> field_name <> 'null'::jsonb
            AND pg_catalog.jsonb_typeof(p_preferences -> field_name) IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
        -- Explicit Unicode whitespace set matches Python str.strip(), independent of locale.
        free_text := pg_catalog.btrim(p_preferences ->> field_name, U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000');
        text_limit := CASE WHEN field_name = 'other_interests' THEN 200 ELSE 500 END;
        IF pg_catalog.char_length(free_text) > text_limit THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
        END IF;
        p_preferences := p_preferences || pg_catalog.jsonb_build_object(field_name, NULLIF(free_text, ''));
    END LOOP;
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
        OR last_date NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
        OR last_date NOT BETWEEN first_date AND first_date + 6
        OR last_time <= first_time THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.';
    END IF;
    -- Only documented defaults are added; malformed inputs are never repaired.
    RETURN p_preferences || pg_catalog.jsonb_build_object(
        'timezone', 'Asia/Manila', 'budget_centavos', COALESCE(p_preferences -> 'budget_centavos', 'null'::jsonb));
END;
$$;

ALTER FUNCTION public.rosago_validate_draft_preferences(jsonb) OWNER TO postgres;
REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_validate_draft_preferences(jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
COMMIT;
