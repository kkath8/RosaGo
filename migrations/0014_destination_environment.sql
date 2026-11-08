-- PHASE 1A: REVIEW ONLY / UNAPPLIED. Never run on application startup.
-- Atomic nullable-column migration plus exact-baseline inner-function update.
-- Requires the reviewed photo contract to be deployed already. Not rerunnable.
-- No backfill/import, external fetch, Storage writes, auth changes, grants,
-- owner changes, RLS changes, or replacement of the audit wrapper.
-- Keep ROSAGO_DESTINATION_ENVIRONMENT_ENABLED disabled until this transaction
-- has been manually reviewed, applied, and verified. Then enable it and restart.
-- Existing rows gain NULL; IDs, photos, states and audit history are untouched.
BEGIN;
DO $$
DECLARE
    inner_oid pg_catalog.oid := pg_catalog.to_regprocedure(
        'public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)')::pg_catalog.oid;
    wrapper_oid pg_catalog.oid := pg_catalog.to_regprocedure(
        'public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)')::pg_catalog.oid;
BEGIN
    IF inner_oid IS NULL OR wrapper_oid IS NULL THEN
        RAISE EXCEPTION 'Reviewed audited photo mutation functions are required.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid=inner_oid AND p.prokind='f' AND p.prosecdef
          AND p.prorettype='pg_catalog.jsonb'::pg_catalog.regtype
          AND p.proargnames=ARRAY['p_action','p_slug','p_expected_updated_at','p_values']
          AND pg_catalog.pg_get_userbyid(p.proowner)='postgres'
          AND EXISTS (SELECT 1 FROM pg_catalog.unnest(p.proconfig) AS c(value)
                      WHERE c.value IN ('search_path=','search_path=""'))
          AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))='aa4441116ded963faa4e1ee8e3024e4b') THEN
        RAISE EXCEPTION 'Inner function differs from the reviewed photo baseline. Stop and review.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid=wrapper_oid AND p.prokind='f' AND p.prosecdef
          AND p.prorettype='pg_catalog.jsonb'::pg_catalog.regtype
          AND p.proargnames=ARRAY['p_action','p_slug','p_expected_updated_at','p_values']
          AND pg_catalog.pg_get_userbyid(p.proowner)='postgres'
          AND EXISTS (SELECT 1 FROM pg_catalog.unnest(p.proconfig) AS c(value)
                      WHERE c.value IN ('search_path=','search_path=""'))
          AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))='4cab3fdc6baf75133fd19b8f1dde6345') THEN
        RAISE EXCEPTION 'Audit wrapper differs from the reviewed baseline. Stop and review.';
    END IF;
    IF pg_catalog.has_function_privilege('anon',inner_oid,'EXECUTE')
       OR pg_catalog.has_function_privilege('authenticated',inner_oid,'EXECUTE')
       OR pg_catalog.has_function_privilege('anon',wrapper_oid,'EXECUTE')
       OR NOT pg_catalog.has_function_privilege('authenticated',wrapper_oid,'EXECUTE') THEN
        RAISE EXCEPTION 'Unexpected ordinary-role mutation privileges. Stop and review; no grants are changed.';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc p,
        LATERAL pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
        WHERE p.oid IN (inner_oid,wrapper_oid) AND a.grantee=0 AND a.privilege_type='EXECUTE') THEN
        RAISE EXCEPTION 'PUBLIC mutation execution must not be granted.';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_attribute
        WHERE attrelid='public.places'::pg_catalog.regclass AND attname='environment' AND NOT attisdropped)
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid='public.places'::pg_catalog.regclass AND conname='places_environment_check') THEN
        RAISE EXCEPTION 'Environment column or constraint already exists. Stop; do not rerun.';
    END IF;
END;
$$;
ALTER TABLE public.places
    ADD COLUMN environment text,
    ADD CONSTRAINT places_environment_check CHECK (
        environment IN ('Indoor','Outdoor','Mix of Both'));
COMMENT ON COLUMN public.places.environment IS
    'Destination setting: Indoor, Outdoor or Mix of Both; NULL means not recorded. Separate from verified weather exposure.';
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
                WHERE k NOT IN ('name','category','description','address','latitude','longitude','image_url','environment',
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
             AND (p_values->>'image_url') ~ '^https://brnkigrrqdrywahvcbvc[.]supabase[.]co/storage/v1/object/public/destination-images/destinations/[0-9a-f]{32}[.](jpg|png|webp)$')
        ) THEN
            RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid destination photo.';
        END IF;
        -- Optional Environment is separate from curated weather exposure.
        IF p_values ? 'environment' AND NOT (
            pg_catalog.jsonb_typeof(p_values->'environment') = 'null' OR
            (pg_catalog.jsonb_typeof(p_values->'environment') = 'string'
             AND (p_values->>'environment') IN ('Indoor','Outdoor','Mix of Both'))
        ) THEN
            RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid destination environment.';
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
        IF p_values ? 'environment' THEN
            UPDATE public.places SET environment=p_values->>'environment'
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

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid=pg_catalog.to_regprocedure(
            'public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)')::pg_catalog.oid
          AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))='399faf695b6a607f33bf1fb7c2dd9386')
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid=pg_catalog.to_regprocedure(
            'public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)')::pg_catalog.oid
          AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))='4cab3fdc6baf75133fd19b8f1dde6345') THEN
        RAISE EXCEPTION 'Postflight function checks failed; roll back the entire transaction.';
    END IF;
END;
$$;
COMMIT;
-- Success: nullable environment column/check plus reviewed inner body; wrapper
-- checksum unchanged. Any exception requires ROLLBACK; leave the flag disabled.
-- Before live edits, verify column nullability/no default, three check values,
-- function hashes/owner/search_path/ACL and publication RLS using read-only checks.
-- No test destination writes or uploads are part of this script.
