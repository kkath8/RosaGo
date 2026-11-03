-- REVIEW ONLY / UNAPPLIED. Trusted operator approval and target-schema review required.
-- Requires existing profiles/places/trips, 0008/0009 and Tourism columns from 0011.
-- Do NOT rerun historical migrations or Tourism transition scripts.
-- No new catalog, columns, bulk changes, direct table write grants or Auth admin key.
BEGIN;

CREATE FUNCTION public.rosago_admin_mutate_destination(
    p_action text, p_slug text, p_expected_updated_at timestamptz, p_values jsonb)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    destination public.places%ROWTYPE;
    new_slug text;
    field_name text;
    field_value text;
    target_status text;
    tourism_fields boolean;
BEGIN
    -- Lock membership until commit, including audit insertion if installed.
    PERFORM m.user_id FROM public.admin_memberships m
        WHERE m.user_id = (SELECT auth.uid()) FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Admin access required.';
    END IF;
    IF p_action IS NULL OR p_action NOT IN ('create','edit','publish','draft','archive','restore')
        OR p_values IS NULL OR pg_catalog.jsonb_typeof(p_values) <> 'object' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid destination action.';
    END IF;
    IF p_action = 'create' THEN
        IF p_slug IS NOT NULL OR p_expected_updated_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid creation identity.';
        END IF;
    ELSE
        SELECT * INTO destination FROM public.places WHERE slug = p_slug FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Destination unavailable.';
        END IF;
        IF p_expected_updated_at IS NULL OR destination.updated_at <> p_expected_updated_at THEN
            RAISE EXCEPTION USING ERRCODE = '40001', MESSAGE = 'Destination changed. Reload before saving.';
        END IF;
    END IF;
    IF p_action IN ('create','edit') THEN
        IF NOT (p_values ?& ARRAY['name','category','description','address','latitude','longitude'])
            OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_object_keys(p_values) k
                WHERE k NOT IN ('name','category','description','address','latitude','longitude',
                  'tourism_type','tourism_category','tourism_opening_hours_raw',
                  'tourism_closing_hours_raw','tourism_hours_status')) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid destination fields.';
        END IF;
        FOREACH field_name IN ARRAY ARRAY['name','description','address'] LOOP
            field_value := p_values ->> field_name;
            IF pg_catalog.jsonb_typeof(p_values -> field_name) <> 'string' OR field_value IS NULL
                OR pg_catalog.char_length(pg_catalog.btrim(field_value)) NOT BETWEEN 1 AND
                    (CASE field_name WHEN 'name' THEN 150 WHEN 'address' THEN 500 ELSE 3000 END) THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid required destination text.';
            END IF;
        END LOOP;
        IF (p_values ->> 'category') IS NULL OR (p_values ->> 'category') NOT IN
            ('attraction','dining','shopping','accommodation','nature','heritage','industrial') THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid RosaGo category.';
        END IF;
        IF pg_catalog.jsonb_typeof(p_values -> 'latitude') NOT IN ('number','null')
            OR pg_catalog.jsonb_typeof(p_values -> 'longitude') NOT IN ('number','null')
            OR ((p_values ->> 'latitude') IS NULL) <> ((p_values ->> 'longitude') IS NULL)
            OR (p_values ->> 'latitude')::double precision NOT BETWEEN -90 AND 90
            OR (p_values ->> 'longitude')::double precision NOT BETWEEN -180 AND 180 THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid coordinate pair.';
        END IF;
        tourism_fields := p_values ?| ARRAY['tourism_type','tourism_category',
            'tourism_opening_hours_raw','tourism_closing_hours_raw','tourism_hours_status'];
        IF tourism_fields THEN
            IF NOT (p_values ?& ARRAY['tourism_type','tourism_category',
                'tourism_opening_hours_raw','tourism_closing_hours_raw','tourism_hours_status']) THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Incomplete Tourism fields.';
            END IF;
            FOREACH field_name IN ARRAY ARRAY['tourism_type','tourism_category',
                'tourism_opening_hours_raw','tourism_closing_hours_raw','tourism_hours_status'] LOOP
                IF pg_catalog.jsonb_typeof(p_values -> field_name) NOT IN ('string','null') THEN
                    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid Tourism field.';
                END IF;
                field_value := p_values ->> field_name;
                IF field_value IS NOT NULL AND (pg_catalog.char_length(field_value) NOT BETWEEN 1 AND 250
                    OR pg_catalog.btrim(field_value) = '') THEN
                    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid Tourism text.';
                END IF;
            END LOOP;
            IF (p_values ->> 'tourism_type') NOT IN ('Local','Common')
                OR (p_values ->> 'tourism_hours_status') NOT IN ('unverified','verify_required','not_supplied') THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid Tourism classification.';
            END IF;
        END IF;
        IF p_action = 'create' THEN
            -- Immutable, collision-resistant identity; no name transliteration or guessed metadata.
            new_slug := 'destination-' || pg_catalog.replace(pg_catalog.gen_random_uuid()::text, '-', '');
            INSERT INTO public.places(name,slug,category,description,address,latitude,longitude,status)
            VALUES (pg_catalog.btrim(p_values->>'name'),new_slug,p_values->>'category',
                pg_catalog.btrim(p_values->>'description'),pg_catalog.btrim(p_values->>'address'),
                (p_values->>'latitude')::double precision,(p_values->>'longitude')::double precision,'draft')
            RETURNING * INTO destination;
        ELSE
            UPDATE public.places SET name=pg_catalog.btrim(p_values->>'name'),category=p_values->>'category',
                description=pg_catalog.btrim(p_values->>'description'),address=pg_catalog.btrim(p_values->>'address'),
                latitude=(p_values->>'latitude')::double precision,longitude=(p_values->>'longitude')::double precision
            WHERE id=destination.id RETURNING * INTO destination;
        END IF;
        IF tourism_fields THEN
            UPDATE public.places SET tourism_type=p_values->>'tourism_type',
                tourism_category=p_values->>'tourism_category',
                tourism_opening_hours_raw=p_values->>'tourism_opening_hours_raw',
                tourism_closing_hours_raw=p_values->>'tourism_closing_hours_raw',
                tourism_hours_status=p_values->>'tourism_hours_status'
            WHERE id=destination.id RETURNING * INTO destination;
        END IF;
    ELSE
        IF p_values <> '{}'::jsonb OR NOT (
            (p_action='publish' AND destination.status='draft') OR
            (p_action='draft' AND destination.status='published') OR
            (p_action='archive' AND destination.status IN ('draft','published')) OR
            (p_action='restore' AND destination.status='archived')) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid publication transition.';
        END IF;
        target_status := CASE p_action WHEN 'publish' THEN 'published' WHEN 'archive' THEN 'archived' ELSE 'draft' END;
        UPDATE public.places SET status=target_status WHERE id=destination.id RETURNING * INTO destination;
    END IF;
    RETURN pg_catalog.jsonb_build_object('slug',destination.slug,'status',destination.status);
END;
$$;

-- Aggregate/private-boundary projection only: no additional RLS policies on users/trips.
CREATE FUNCTION public.rosago_admin_operational_overview(p_query text, p_offset integer)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    result jsonb;
BEGIN
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
$$;

REVOKE ALL ON FUNCTION public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb),
    public.rosago_admin_operational_overview(text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb),
    public.rosago_admin_operational_overview(text,integer) TO authenticated;
COMMIT;
