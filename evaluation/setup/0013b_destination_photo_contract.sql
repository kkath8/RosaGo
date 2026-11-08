-- LOCAL PREPARATION ONLY. Target project: jfaufpfzfhysqkhcdsrs
-- REVIEW / APPLY SEPARATELY. No automatic deployment or backfill.
-- Existing project: jfaufpfzfhysqkhcdsrs; existing bucket: destination-images.
-- Updates only the existing protected inner mutator. No columns, buckets,
-- Storage policies, direct write grants, audit rows or catalog data are changed.
-- Apply with trusted database-owner authority after reviewing this function.
BEGIN;
DO $$
DECLARE
    inner_oid pg_catalog.oid := pg_catalog.to_regprocedure(
        'public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)')::pg_catalog.oid;
    wrapper_oid pg_catalog.oid := pg_catalog.to_regprocedure(
        'public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)')::pg_catalog.oid;
BEGIN
    IF inner_oid IS NULL OR wrapper_oid IS NULL
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
           WHERE p.oid=wrapper_oid
             AND p.prokind='f' AND p.prorettype='pg_catalog.jsonb'::pg_catalog.regtype
             AND p.prosrc LIKE '%rosago_admin_mutate_destination_unlogged%'
             AND p.prosrc LIKE '%INSERT INTO public.admin_destination_audit%') THEN
        RAISE EXCEPTION 'Existing audited destination mutation wrapper is required.';
    END IF;
    -- Refuse to replace an inner function that has diverged from the reviewed
    -- 0012 implementation. This prevents silently reverting other live changes.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid=inner_oid
          AND p.prokind='f' AND p.prorettype='pg_catalog.jsonb'::pg_catalog.regtype
          AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))='d9d66eb24db349ccefabc2ea323be6c8') THEN
        RAISE EXCEPTION 'Destination mutator differs from the reviewed baseline. Review before applying photo changes.';
    END IF;
END;
$$;
CREATE OR REPLACE FUNCTION public.rosago_admin_mutate_destination_unlogged(
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
                WHERE k NOT IN ('name','category','description','address','latitude','longitude','image_url',
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
        -- Only the optional image field changes the stored cover. Omission
        -- preserves it; JSON null removes it. No remote URL fetch is performed.
        IF p_values ? 'image_url' AND NOT (
            pg_catalog.jsonb_typeof(p_values->'image_url') = 'null' OR
            (pg_catalog.jsonb_typeof(p_values->'image_url') = 'string'
             AND pg_catalog.char_length(p_values->>'image_url') BETWEEN 9 AND 2048
             AND (p_values->>'image_url') ~ '^https://jfaufpfzfhysqkhcdsrs[.]supabase[.]co/storage/v1/object/public/destination-images/destinations/[0-9a-f]{32}[.](jpg|png|webp)$')
        ) THEN
            RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid destination photo.';
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
        IF p_values ? 'image_url' THEN
            UPDATE public.places SET image_url=p_values->>'image_url'
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

-- Keep this internal function inaccessible to application roles. All writes
-- still go through the existing wrapper and its authenticated auth.uid() audit.
REVOKE ALL ON FUNCTION public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)
FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
