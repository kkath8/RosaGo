-- LOCAL ONLY, UNAPPLIED. Review before manual application; requires live 0001-0006.
-- Target PostgreSQL 17.11 (user-verified). Core pg_catalog.sha256(bytea) avoids
-- extension installation and any assumption about pgcrypto's installation schema.
-- Python remains the only plan generator. These functions validate invariants.
BEGIN;

CREATE FUNCTION public.rosago_preview_json_keys(p_value jsonb, p_keys text[])
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = ''
AS $$
BEGIN
    IF pg_catalog.jsonb_typeof(p_value) IS DISTINCT FROM 'object' THEN
        RETURN false;
    END IF;
    RETURN p_value ?& p_keys AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(p_value) AS k(key)
        WHERE NOT (k.key = ANY(p_keys)));
END;
$$;

-- Explicit escaping, not jsonb::text. UTF-8 byte order under C is Unicode scalar
-- order, matching Python sort_keys. JSONB rejects NUL and unpaired surrogates.
-- Private bounded serializer for validated manifests/catalogs (not a public API).
CREATE FUNCTION public.rosago_preview_canonical_json(p_value jsonb, p_depth integer DEFAULT 0)
RETURNS text LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
    kind text := pg_catalog.jsonb_typeof(p_value);
    result text;
    raw text;
    character text;
    code integer;
    entry record;
    separator text := '';
BEGIN
    IF p_value IS NULL OR p_depth IS NULL OR p_depth NOT BETWEEN 0 AND 16
        OR pg_catalog.octet_length(p_value::text) > 262144 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    CASE kind
    WHEN 'string' THEN
        raw := p_value #>> '{}';
        result := '"';
        FOR char_index IN 1..pg_catalog.char_length(raw) LOOP
            character := pg_catalog.substr(raw, char_index, 1);
            code := pg_catalog.ascii(character);
            result := result || CASE code
                WHEN 34 THEN pg_catalog.chr(92) || '"'
                WHEN 92 THEN pg_catalog.chr(92) || pg_catalog.chr(92)
                WHEN 8 THEN pg_catalog.chr(92) || 'b'
                WHEN 9 THEN pg_catalog.chr(92) || 't'
                WHEN 10 THEN pg_catalog.chr(92) || 'n'
                WHEN 12 THEN pg_catalog.chr(92) || 'f'
                WHEN 13 THEN pg_catalog.chr(92) || 'r'
                ELSE CASE WHEN code < 32 THEN
                    pg_catalog.chr(92) || 'u' || pg_catalog.lpad(pg_catalog.to_hex(code), 4, '0')
                    ELSE character END END;
        END LOOP;
        result := result || '"';
    WHEN 'number' THEN
        result := p_value #>> '{}';
        IF result COLLATE "C" !~ '^-?(0|[1-9][0-9]*)$'
            OR result::numeric NOT BETWEEN -9223372036854775808 AND 9223372036854775807 THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
        END IF;
    WHEN 'boolean' THEN result := p_value #>> '{}';
    WHEN 'null' THEN result := 'null';
    WHEN 'array' THEN
        result := '[';
        FOR entry IN SELECT a.value FROM pg_catalog.jsonb_array_elements(p_value)
            WITH ORDINALITY AS a(value, ordinal) ORDER BY a.ordinal LOOP
            result := result || separator || public.rosago_preview_canonical_json(entry.value, p_depth + 1);
            separator := ',';
        END LOOP;
        result := result || ']';
    WHEN 'object' THEN
        result := '{';
        FOR entry IN SELECT o.key, o.value FROM pg_catalog.jsonb_each(p_value) AS o(key, value)
            ORDER BY o.key COLLATE "C" LOOP
            result := result || separator
                || public.rosago_preview_canonical_json(pg_catalog.to_jsonb(entry.key), p_depth + 1)
                || ':' || public.rosago_preview_canonical_json(entry.value, p_depth + 1);
            separator := ',';
        END LOOP;
        result := result || '}';
    ELSE
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END CASE;
    IF pg_catalog.octet_length(result) > 262144 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    RETURN result;
END;
$$;

CREATE FUNCTION public.rosago_preview_hash(p_domain text, p_value jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path = ''
AS $$
    SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
        p_domain || public.rosago_preview_canonical_json(p_value), 'UTF8')), 'hex');
$$;

CREATE FUNCTION public.rosago_validate_itinerary_preview(
    p_preview jsonb, p_preferences jsonb, p_draft_id uuid, p_revision bigint)
RETURNS uuid[] LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
    source_doc jsonb;
    constraints_doc jsonb;
    validated_preferences jsonb;
    selected_ids uuid[] := ARRAY[]::uuid[];
    item jsonb;
    day_doc jsonb;
    stop_doc jsonb;
    field_name text;
    identity text;
    first_date date;
    day_count integer;
    destination_count integer;
    day_index integer := 0;
    stop_index integer := 0;
    expected_count integer;
    unresolved jsonb := '["visit_duration","time_feasibility","operating_hours","cost","transport_compatibility","travel_time","trip_pace"]'::jsonb;
BEGIN
    IF p_preview IS NULL OR pg_catalog.octet_length(p_preview::text) > 262144
        OR NOT public.rosago_preview_json_keys(p_preview, ARRAY[
            'preview_schema_version','builder_policy_version','planning_mode','source',
            'source_version','constraints','days','unresolved_constraints']) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    IF (p_preview -> 'preview_schema_version') IS DISTINCT FROM '1'::jsonb
        OR (p_preview -> 'builder_policy_version') IS DISTINCT FROM '"preserve-order-equal-count-v1"'::jsonb
        OR (p_preview -> 'planning_mode') IS DISTINCT FROM '"personalized"'::jsonb THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    source_doc := p_preview -> 'source';
    IF NOT public.rosago_preview_json_keys(source_doc, ARRAY['source_schema_version',
        'draft_id','draft_revision','recommendation_policy_version','selected_place_ids','catalog_fingerprint']) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    IF (source_doc -> 'source_schema_version') IS DISTINCT FROM '1'::jsonb
        OR (source_doc -> 'draft_id') IS DISTINCT FROM pg_catalog.to_jsonb(p_draft_id::text)
        OR (source_doc -> 'draft_revision') IS DISTINCT FROM pg_catalog.to_jsonb(p_revision)
        OR (source_doc -> 'recommendation_policy_version') IS DISTINCT FROM '"category-interest-v1"'::jsonb
        OR pg_catalog.jsonb_typeof(source_doc -> 'catalog_fingerprint') IS DISTINCT FROM 'string'
        OR (source_doc ->> 'catalog_fingerprint') COLLATE "C" !~ '^[0-9a-f]{64}$'
        OR pg_catalog.jsonb_typeof(source_doc -> 'selected_place_ids') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    destination_count := pg_catalog.jsonb_array_length(source_doc -> 'selected_place_ids');
    IF destination_count NOT BETWEEN 1 AND 100 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    FOR item IN SELECT a.value FROM pg_catalog.jsonb_array_elements(source_doc -> 'selected_place_ids')
        WITH ORDINALITY AS a(value, ordinal) ORDER BY a.ordinal LOOP
        identity := item #>> '{}';
        IF pg_catalog.jsonb_typeof(item) <> 'string'
            OR identity COLLATE "C" !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
        END IF;
        IF identity::uuid = ANY(selected_ids) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
        END IF;
        selected_ids := pg_catalog.array_append(selected_ids, identity::uuid);
    END LOOP;
    -- Equality to a constructed exact object also rejects unknown nested keys/types.
    IF (p_preview -> 'source_version') IS DISTINCT FROM pg_catalog.jsonb_build_object(
        'kind', 'draft', 'version', 'v1:' || public.rosago_preview_hash('rosago:source:v1:', source_doc)) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    validated_preferences := public.rosago_validate_draft_preferences(p_preferences);
    IF validated_preferences IS DISTINCT FROM p_preferences THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    constraints_doc := p_preview -> 'constraints';
    IF NOT public.rosago_preview_json_keys(constraints_doc, ARRAY['start_date','end_date',
        'daily_start_time','daily_end_time','transportation','trip_pace','timezone','budget_centavos']) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    FOREACH field_name IN ARRAY ARRAY['start_date','end_date','daily_start_time','daily_end_time',
        'transportation','trip_pace','timezone','budget_centavos'] LOOP
        IF (constraints_doc -> field_name) IS DISTINCT FROM (validated_preferences -> field_name) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
        END IF;
    END LOOP;
    first_date := (validated_preferences ->> 'start_date')::date;
    day_count := (validated_preferences ->> 'end_date')::date - first_date + 1;
    IF pg_catalog.jsonb_typeof(p_preview -> 'days') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    IF day_count NOT BETWEEN 1 AND 7 OR pg_catalog.jsonb_array_length(p_preview -> 'days') <> day_count THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    FOR day_doc IN SELECT a.value FROM pg_catalog.jsonb_array_elements(p_preview -> 'days')
        WITH ORDINALITY AS a(value, ordinal) ORDER BY a.ordinal LOOP
        IF NOT public.rosago_preview_json_keys(day_doc, ARRAY['date','stops'])
            OR (day_doc -> 'date') IS DISTINCT FROM pg_catalog.to_jsonb(pg_catalog.to_char(first_date + day_index, 'YYYY-MM-DD'))
            OR pg_catalog.jsonb_typeof(day_doc -> 'stops') IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
        END IF;
        expected_count := destination_count / day_count
            + CASE WHEN day_index < destination_count % day_count THEN 1 ELSE 0 END;
        IF pg_catalog.jsonb_array_length(day_doc -> 'stops') <> expected_count THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
        END IF;
        FOR stop_doc IN SELECT a.value FROM pg_catalog.jsonb_array_elements(day_doc -> 'stops')
            WITH ORDINALITY AS a(value, ordinal) ORDER BY a.ordinal LOOP
            stop_index := stop_index + 1;
            IF stop_doc IS DISTINCT FROM pg_catalog.jsonb_build_object(
                'place_id', selected_ids[stop_index]::text, 'order', stop_index,
                'source', 'recommended', 'keep_place', true) THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
            END IF;
        END LOOP;
        day_index := day_index + 1;
    END LOOP;
    IF stop_index <> destination_count THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    IF validated_preferences -> 'budget_centavos' <> 'null'::jsonb THEN
        unresolved := unresolved || '["budget_feasibility"]'::jsonb;
    END IF;
    IF (p_preview -> 'unresolved_constraints') IS DISTINCT FROM unresolved THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid preview document.';
    END IF;
    -- Reject fractional numeric spellings even where JSONB numeric equality would
    -- equate 1.0 with 1. The exact schema bounds this tree below 10,000 nodes.
    PERFORM public.rosago_preview_canonical_json(p_preview);
    RETURN selected_ids;
END;
$$;

CREATE FUNCTION public.rosago_itinerary_draft_store_preview(
    p_draft_id uuid, p_expected_revision bigint, p_candidate_preview jsonb)
RETURNS TABLE (draft_id uuid, state text, revision bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    owner_id uuid := auth.uid();
    locked_draft public.itinerary_drafts%ROWTYPE;
    selected_ids uuid[];
    place_row public.places%ROWTYPE;
    catalog jsonb := '[]'::jsonb;
    locked_count integer := 0;
    whitespace text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
BEGIN
    IF owner_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Authentication required.';
    END IF;
    IF p_draft_id IS NULL OR p_expected_revision IS NULL
        OR p_expected_revision NOT BETWEEN 1 AND 9223372036854775806 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    SELECT draft.* INTO locked_draft FROM public.itinerary_drafts AS draft
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    IF locked_draft.revision <> p_expected_revision OR locked_draft.schema_version <> 1
        OR locked_draft.state NOT IN ('editing', 'preview_ready')
        OR locked_draft.expires_at <= pg_catalog.clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    selected_ids := public.rosago_validate_itinerary_preview(
        p_candidate_preview, locked_draft.preferences, p_draft_id, p_expected_revision);
    IF locked_draft.state = 'preview_ready' AND
        (p_candidate_preview #> '{source,selected_place_ids}') IS DISTINCT FROM
        (locked_draft.preview #> '{source,selected_place_ids}') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    -- FOR SHARE conflicts with both ordinary non-key UPDATE and DELETE/key UPDATE.
    -- KEY SHARE would not protect name/address/category/status changes. UUID order
    -- is immutable for application users; all preview writers lock in this order.
    -- Consume the locked row versions themselves, including updates waited for.
    FOR place_row IN SELECT place.* FROM public.places AS place
        WHERE place.id = ANY(selected_ids) ORDER BY place.id FOR SHARE LOOP
        IF place_row.status <> 'published'
            OR NOT (locked_draft.preferences -> 'interests' ? place_row.category)
            OR place_row.name <> pg_catalog.btrim(place_row.name, whitespace)
            OR place_row.address <> pg_catalog.btrim(place_row.address, whitespace) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
        END IF;
        locked_count := locked_count + 1;
        catalog := catalog || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
            'id', place_row.id::text, 'category', place_row.category, 'status', 'published',
            'name', place_row.name, 'address', place_row.address,
            'is_test_record', pg_catalog.starts_with(place_row.slug, 'rosago-test-v1-')));
    END LOOP;
    IF locked_count <> pg_catalog.cardinality(selected_ids)
        OR (p_candidate_preview #>> '{source,catalog_fingerprint}') IS DISTINCT FROM
            public.rosago_preview_hash('rosago:catalog:v1:', catalog) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    -- Repeat wall-clock expiry after Place lock waits, immediately at mutation.
    -- Existing metadata trigger updates updated_at; expiry/preferences/save fields
    -- are untouched. Existing non-saved CHECK requires all save fields to be NULL.
    RETURN QUERY UPDATE public.itinerary_drafts AS draft
        SET preview = p_candidate_preview, state = 'preview_ready', revision = draft.revision + 1
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id
            AND draft.revision = p_expected_revision AND draft.schema_version = 1
            AND draft.state IN ('editing', 'preview_ready')
            AND draft.expires_at > pg_catalog.clock_timestamp()
        RETURNING draft.id, draft.state, draft.revision;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
END;
$$;

CREATE FUNCTION public.rosago_itinerary_draft_return_to_editing(p_draft_id uuid, p_expected_revision bigint)
RETURNS TABLE (draft_id uuid, state text, revision bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    owner_id uuid := auth.uid();
BEGIN
    IF owner_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Authentication required.';
    END IF;
    IF p_draft_id IS NULL OR p_expected_revision IS NULL
        OR p_expected_revision NOT BETWEEN 1 AND 9223372036854775806 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid draft request.';
    END IF;
    PERFORM draft.id FROM public.itinerary_drafts AS draft
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
    RETURN QUERY UPDATE public.itinerary_drafts AS draft
        SET preview = NULL, state = 'editing', revision = draft.revision + 1
        WHERE draft.id = p_draft_id AND draft.user_id = owner_id
            AND draft.revision = p_expected_revision AND draft.schema_version = 1
            AND draft.state = 'preview_ready'
            AND draft.expires_at > pg_catalog.clock_timestamp()
        RETURNING draft.id, draft.state, draft.revision;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.';
    END IF;
END;
$$;

ALTER FUNCTION public.rosago_preview_json_keys(jsonb, text[]) OWNER TO postgres;
ALTER FUNCTION public.rosago_preview_canonical_json(jsonb, integer) OWNER TO postgres;
ALTER FUNCTION public.rosago_preview_hash(text, jsonb) OWNER TO postgres;
ALTER FUNCTION public.rosago_validate_itinerary_preview(jsonb, jsonb, uuid, bigint) OWNER TO postgres;
ALTER FUNCTION public.rosago_itinerary_draft_store_preview(uuid, bigint, jsonb) OWNER TO postgres;
ALTER FUNCTION public.rosago_itinerary_draft_return_to_editing(uuid, bigint) OWNER TO postgres;
REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_preview_json_keys(jsonb, text[]),
    public.rosago_preview_canonical_json(jsonb, integer), public.rosago_preview_hash(text, jsonb),
    public.rosago_validate_itinerary_preview(jsonb, jsonb, uuid, bigint),
    public.rosago_itinerary_draft_store_preview(uuid, bigint, jsonb),
    public.rosago_itinerary_draft_return_to_editing(uuid, bigint)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rosago_itinerary_draft_store_preview(uuid, bigint, jsonb),
    public.rosago_itinerary_draft_return_to_editing(uuid, bigint) TO authenticated;

-- Fail closed during future manual application if the environment differs.
DO $$
DECLARE
    vector record;
BEGIN
    IF pg_catalog.current_setting('server_encoding') <> 'UTF8'
        OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to('abc', 'UTF8')), 'hex')
            <> 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' THEN
        RAISE EXCEPTION 'Preview hashing environment unsupported.';
    END IF;
    -- Frozen Phase 6D-7A vectors. These assertions run only on future authorized
    -- application, inside this transaction: a mismatch rolls back every addition.
    FOR vector IN SELECT * FROM (VALUES
        ('rosago:catalog:v1:', $vector${"ascii":"RosaGo","booleans":[true,false],"date":"2026-10-19","integer_budget":12500,"null_budget":null,"ordered":["b","a"],"time":"08:00:00","unicode":"Café — 東京","uuid":"00000000-0000-0000-0000-000000000001"}$vector$, '101a836ec89878dd20e34ad2dbcac4f47ec488f8c6468ea129764dc05c71c363'),
        ('rosago:source:v1:', $vector${"ascii":"RosaGo","booleans":[true,false],"date":"2026-10-19","integer_budget":12500,"null_budget":null,"ordered":["b","a"],"time":"08:00:00","unicode":"Café — 東京","uuid":"00000000-0000-0000-0000-000000000001"}$vector$, '301a4896815976ad4945339f7cbac330b2e33703e50a5240b98dfd9ac36825ee'),
        ('rosago:preview:v1:', $vector${"ascii":"RosaGo","booleans":[true,false],"date":"2026-10-19","integer_budget":12500,"null_budget":null,"ordered":["b","a"],"time":"08:00:00","unicode":"Café — 東京","uuid":"00000000-0000-0000-0000-000000000001"}$vector$, '6e302874fc47bf1fd27407794d6c937ee530f7072559cb848953a46add32cc16'),
        ('rosago:catalog:v1:', $vector$[{"address":"Fixture address","category":"nature","id":"00000000-0000-0000-0000-000000000001","is_test_record":false,"name":"Place 1","status":"published"}]$vector$, '4bf99dffda4cae5ed902027fec541879c9664f25f3add88db977ae30b559c68e'),
        ('rosago:source:v1:', $vector${"catalog_fingerprint":"4bf99dffda4cae5ed902027fec541879c9664f25f3add88db977ae30b559c68e","draft_id":"aaaaaaaa-0000-0000-0000-000000000001","draft_revision":2,"recommendation_policy_version":"category-interest-v1","selected_place_ids":["00000000-0000-0000-0000-000000000001"],"source_schema_version":1}$vector$, '7f63a0d428d84de5e86a0f340d85fa0a109c5683cbe631d583507ce5e09f0a17')
    ) AS frozen(domain, canonical, digest) LOOP
        IF public.rosago_preview_canonical_json(vector.canonical::jsonb) <> vector.canonical
            OR public.rosago_preview_hash(vector.domain, vector.canonical::jsonb) <> vector.digest THEN
            RAISE EXCEPTION 'Preview canonical vector mismatch.';
        END IF;
    END LOOP;
    IF public.rosago_preview_canonical_json($vector${"z":{"z":1,"a":2},"a":[2,1]}$vector$::jsonb)
        <> $vector${"a":[2,1],"z":{"a":2,"z":1}}$vector$
        OR public.rosago_preview_canonical_json($vector${"escape":"\"\\\n\t/\u001f\b\f\r"}$vector$::jsonb)
        <> $vector${"escape":"\"\\\n\t/\u001f\b\f\r"}$vector$ THEN
        RAISE EXCEPTION 'Preview canonical vector mismatch.';
    END IF;
END;
$$;
COMMIT;
