-- REVIEW ONLY. Evaluation jfaufpfzfhysqkhcdsrs only. Not a hosted migration.
-- Adds restrictive RLS and entry guards; preserves existing authorization.
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

CREATE POLICY rosago_current_provider_session ON public.admin_destination_audit
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.admin_memberships
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.itinerary_drafts
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.places
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.profiles
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.trip_itinerary
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.trip_places
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.trip_stop_plans
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

CREATE POLICY rosago_current_provider_session ON public.trips
    AS RESTRICTIVE FOR ALL TO authenticated
    USING ((SELECT public.rosago_provider_session_current()))
    WITH CHECK ((SELECT public.rosago_provider_session_current()));

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_admin_mutate_destination(text,text,timestamp with time zone,jsonb)'::regprocedure AND md5(p.prosrc)='4cab3fdc6baf75133fd19b8f1dde6345'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_admin_mutate_destination(p_action text, p_slug text, p_expected_updated_at timestamp with time zone, p_values jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    result jsonb;
    target_id uuid;
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
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
$function$
$review_definition$;
END;
$review_guard$;

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_admin_operational_overview(text,integer)'::regprocedure AND md5(p.prosrc)='1f4d6573ce99452bdb52b0488c6e9d8b'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_admin_operational_overview(p_query text, p_offset integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    result jsonb;
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
    PERFORM m.user_id FROM public.admin_memberships m
        WHERE m.user_id = (SELECT auth.uid()) FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Admin access required.';
    END IF;
    IF p_query IS NULL OR pg_catalog.char_length(p_query)>150 OR p_offset IS NULL
        OR p_offset<0 OR p_offset>2499975 THEN
        RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid directory page.';
    END IF;
    WITH directory AS (
        SELECT u.id::text AS identifier, u.email::text AS email,
            NULLIF(pg_catalog.btrim(pg_catalog.concat_ws(' ',p.first_name,p.last_name)),'') AS name,
            u.created_at FROM auth.users u LEFT JOIN public.profiles p ON p.id=u.id
    ), matching AS (
        SELECT * FROM directory WHERE p_query='' OR
            pg_catalog.strpos(pg_catalog.lower(COALESCE(email,'')),pg_catalog.lower(p_query))>0 OR
            pg_catalog.strpos(pg_catalog.lower(COALESCE(name,'')),pg_catalog.lower(p_query))>0
    ), users_page AS (SELECT * FROM matching ORDER BY created_at DESC,identifier LIMIT 25 OFFSET p_offset),
    popularity AS (
        SELECT p.name,p.slug,pg_catalog.count(DISTINCT tp.trip_id) AS trips
        FROM public.trip_places tp JOIN public.places p ON p.id=tp.place_id
        GROUP BY p.id,p.name,p.slug ORDER BY trips DESC,p.slug LIMIT 10
    ), category_usage AS (
        SELECT p.category,pg_catalog.count(DISTINCT tp.trip_id) AS trips
        FROM public.trip_places tp JOIN public.places p ON p.id=tp.place_id
        GROUP BY p.category ORDER BY p.category
    ) SELECT pg_catalog.jsonb_build_object(
        'users_total',(SELECT pg_catalog.count(*) FROM directory),
        'users_matching',(SELECT pg_catalog.count(*) FROM matching),
        'users',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(up) ORDER BY up.created_at DESC,up.identifier) FROM users_page up),'[]'::jsonb),
        'trips_total',(SELECT pg_catalog.count(*) FROM public.trips),
        'upcoming_trips',(SELECT pg_catalog.count(*) FROM public.trips WHERE visit_date >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila')::date),
        'destinations_in_trips',(SELECT pg_catalog.count(DISTINCT place_id) FROM public.trip_places),
        'popular',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(pop) ORDER BY pop.trips DESC,pop.slug) FROM popularity pop),'[]'::jsonb),
        'categories',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(c) ORDER BY c.category) FROM category_usage c),'[]'::jsonb)
    ) INTO result;
    RETURN result;
END;
$function$
$review_definition$;
END;
$review_guard$;

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_itinerary_draft_adjust_preview(uuid,bigint,jsonb,jsonb)'::regprocedure AND md5(p.prosrc)='48289089d3380eb9805de3c178fca84a'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_itinerary_draft_adjust_preview(p_draft_id uuid, p_expected_revision bigint, p_preferences jsonb, p_candidate_preview jsonb)
 RETURNS TABLE(draft_id uuid, state text, revision bigint)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    owner_id uuid := auth.uid();
    locked_draft public.itinerary_drafts%ROWTYPE;
    validated_preferences jsonb;
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
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
$function$
$review_definition$;
END;
$review_guard$;

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_itinerary_draft_create()'::regprocedure AND md5(p.prosrc)='5a98abe0ca0962adb15ad34c3da7c74e'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_itinerary_draft_create()
 RETURNS TABLE(draft_id uuid, state text, revision bigint)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    owner_id uuid := auth.uid();
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
    IF owner_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Authentication required.';
    END IF;
    RETURN QUERY INSERT INTO public.itinerary_drafts AS draft
        (user_id, state, schema_version, revision)
        VALUES (owner_id, 'editing', 1, 1)
        RETURNING draft.id, draft.state, draft.revision;
END;
$function$
$review_definition$;
END;
$review_guard$;

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_itinerary_draft_return_to_editing(uuid,bigint)'::regprocedure AND md5(p.prosrc)='d11eec9e49c00e25ee2ad8b790d0e979'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_itinerary_draft_return_to_editing(p_draft_id uuid, p_expected_revision bigint)
 RETURNS TABLE(draft_id uuid, state text, revision bigint)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    owner_id uuid := auth.uid();
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
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
$function$
$review_definition$;
END;
$review_guard$;

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_itinerary_draft_store_preview(uuid,bigint,jsonb)'::regprocedure AND md5(p.prosrc)='d59daed134d2bc215985d1100b2749c0'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_itinerary_draft_store_preview(p_draft_id uuid, p_expected_revision bigint, p_candidate_preview jsonb)
 RETURNS TABLE(draft_id uuid, state text, revision bigint)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    owner_id uuid := auth.uid();
    locked_draft public.itinerary_drafts%ROWTYPE;
    selected_ids uuid[];
    place_row public.places%ROWTYPE;
    catalog jsonb := '[]'::jsonb;
    locked_count integer := 0;
    whitespace text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
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
$function$
$review_definition$;
END;
$review_guard$;

DO $review_guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
        WHERE p.oid='rosago_itinerary_draft_update_preferences(uuid,bigint,jsonb)'::regprocedure AND md5(p.prosrc)='9194014e756ced5d5b466d2dab0eb02a'
          AND p.prosecdef AND l.lanname='plpgsql' AND p.proconfig=ARRAY['search_path=""']
          AND pg_get_userbyid(p.proowner)='postgres') THEN
        RAISE EXCEPTION 'STOP: Reviewed RPC baseline differs';
    END IF;
    EXECUTE $review_definition$CREATE OR REPLACE FUNCTION public.rosago_itinerary_draft_update_preferences(p_draft_id uuid, p_expected_revision bigint, p_preferences jsonb)
 RETURNS TABLE(draft_id uuid, state text, revision bigint)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    owner_id uuid := auth.uid();
    validated_preferences jsonb;
BEGIN
    IF NOT public.rosago_provider_session_current() THEN
        RAISE EXCEPTION 'Current provider session required' USING ERRCODE='42501';
    END IF;
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
$function$
$review_definition$;
END;
$review_guard$;

COMMIT;
