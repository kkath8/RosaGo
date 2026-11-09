-- REVIEW ONLY / NOT APPROVED. Bound to owner schema export; no hosted execution.
-- REVIEW DRAFT ONLY. NOT APPROVED, NOT QUALIFIED, DO NOT APPLY.
-- Target: brnkigrrqdrywahvcbvc. No destination import/backfill/publication.
-- Missing current function/constraint preflight deliberately prevents execution.
-- Finalization must review the exact live definitions, fill the two body hashes,
-- verify the category constraint, regenerate and request separate SQL approval.
-- Keep ROSAGO_FLEXIBLE_CATALOG_ENABLED disabled until postflight and registry parity.
BEGIN;
DO $preflight_snapshot$
BEGIN
    IF pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination_unlogged(text,text,timestamp with time zone,jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination_unlogged(text,text,timestamp with time zone,jsonb)')),pg_catalog.chr(13),''))<>'899a8cc09470279f88a6bec2b113e30d' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination(text,text,timestamp with time zone,jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination(text,text,timestamp with time zone,jsonb)')),pg_catalog.chr(13),''))<>'b7c9aa07d915578ece20fb4d72e4ca18' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_admin_operational_overview(text,integer)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_admin_operational_overview(text,integer)')),pg_catalog.chr(13),''))<>'a9c9337f3c6959b1ab91a71e3ccf4bdf' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_create_user_profile()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_create_user_profile()')),pg_catalog.chr(13),''))<>'d984e01c13cb8ac42471ede8e4f4b4c9' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_is_admin()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_is_admin()')),pg_catalog.chr(13),''))<>'eccad91f2793e88718fe4d734fdaae8a' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_draft_adjust_preview(uuid,bigint,jsonb,jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_draft_adjust_preview(uuid,bigint,jsonb,jsonb)')),pg_catalog.chr(13),''))<>'5714ff81ca28a9a588dfc813c1c87ecb' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_draft_create()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_draft_create()')),pg_catalog.chr(13),''))<>'a66425a090f3824ed7681301c12aae29' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_draft_return_to_editing(uuid,bigint)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_draft_return_to_editing(uuid,bigint)')),pg_catalog.chr(13),''))<>'351d90b451fe404122c72302f5565748' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_draft_store_preview(uuid,bigint,jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_draft_store_preview(uuid,bigint,jsonb)')),pg_catalog.chr(13),''))<>'ae246cd734f23b5f41c48955d7b7b599' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_draft_update_preferences(uuid,bigint,jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_draft_update_preferences(uuid,bigint,jsonb)')),pg_catalog.chr(13),''))<>'4a0b213fa2bc3cb02693f24ba3aefb92' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_guard_metadata()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_guard_metadata()')),pg_catalog.chr(13),''))<>'1aef032b484e03c0860cd84925c04714' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_interests_valid(text[])') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_itinerary_interests_valid(text[])')),pg_catalog.chr(13),''))<>'f1384f9fb8d60d97de56e3921823c805' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_places_set_updated_at()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_places_set_updated_at()')),pg_catalog.chr(13),''))<>'fdc024ed9b6b76a91474fdd006c4fd51' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_preview_canonical_json(jsonb,integer)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_preview_canonical_json(jsonb,integer)')),pg_catalog.chr(13),''))<>'76510db2fd1fbd1483da5a8045a1b18b' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_preview_hash(text,jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_preview_hash(text,jsonb)')),pg_catalog.chr(13),''))<>'a56c18d4915b55c4efc1ef9fb271b23c' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_preview_json_keys(jsonb,text[])') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_preview_json_keys(jsonb,text[])')),pg_catalog.chr(13),''))<>'82ddb5c4f4d38c29ec9c1568dea617cf' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_trip_add_place(uuid,uuid)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_trip_add_place(uuid,uuid)')),pg_catalog.chr(13),''))<>'02bdb7ec0c41a48725e938bd4efc16ff' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_trip_places_lock_parent()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_trip_places_lock_parent()')),pg_catalog.chr(13),''))<>'514f13d9f3e8fb6a9d48193ebf1ad91c' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_trip_remove_place(uuid,uuid)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_trip_remove_place(uuid,uuid)')),pg_catalog.chr(13),''))<>'684641e1a0cbd3052127ce03cdda7180' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_trip_reorder_places(uuid,uuid[])') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_trip_reorder_places(uuid,uuid[])')),pg_catalog.chr(13),''))<>'c6ccc4af791fef44462a36d69c961d1d' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_trips_set_updated_at()') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_trips_set_updated_at()')),pg_catalog.chr(13),''))<>'d6d9a6da3de3938db3153683dc5aa8ef' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_validate_draft_preferences(jsonb)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_validate_draft_preferences(jsonb)')),pg_catalog.chr(13),''))<>'70ce23ad83b208c2f0a315fc797418dd' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
    IF pg_catalog.to_regprocedure('public.rosago_validate_itinerary_preview(jsonb,jsonb,uuid,bigint)') IS NULL OR
       pg_catalog.md5(pg_catalog.replace(pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure('public.rosago_validate_itinerary_preview(jsonb,jsonb,uuid,bigint)')),pg_catalog.chr(13),''))<>'ba9af32cd885d52985ce61b3c9588072' THEN
        RAISE EXCEPTION 'Exported function definition/authority changed; stop and re-review';
    END IF;
END;
$preflight_snapshot$;
DO $review$
DECLARE
    expected_mutation_body_md5 constant text := '399faf695b6a607f33bf1fb7c2dd9386';
    expected_interests_body_md5 constant text := '23e804b7aaad0adeff4ecd1db8e1a645';
    expected_category_check_md5 constant text := '62c540028374c0ecfa1d5fa3877b519f';
    mutation_oid oid := pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)');
    interests_oid oid := pg_catalog.to_regprocedure('public.rosago_itinerary_interests_valid(text[])');
    wrapper_oid oid := pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)');
BEGIN
    IF expected_mutation_body_md5 !~ '^[0-9a-f]{32}$' OR expected_interests_body_md5 !~ '^[0-9a-f]{32}$'
       OR expected_category_check_md5 !~ '^[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'UNQUALIFIED: current production schema/function preflight and separate approval required.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c
        WHERE c.conrelid='public.places'::pg_catalog.regclass AND c.conname='places_category_check'
        AND pg_catalog.md5(pg_catalog.pg_get_constraintdef(c.oid))=expected_category_check_md5) THEN
        RAISE EXCEPTION 'Category constraint baseline mismatch.';
    END IF;
    IF mutation_oid IS NULL OR interests_oid IS NULL OR wrapper_oid IS NULL THEN
        RAISE EXCEPTION 'Required audited mutation/itinerary functions missing.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=mutation_oid AND p.prosecdef
        AND pg_catalog.pg_get_userbyid(p.proowner)='postgres'
        AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))=expected_mutation_body_md5
        AND p.proconfig && ARRAY['search_path=','search_path=""'])
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=interests_oid
        AND NOT p.prosecdef AND pg_catalog.pg_get_userbyid(p.proowner)='postgres'
        AND pg_catalog.md5(pg_catalog.replace(p.prosrc,pg_catalog.chr(13),''))=expected_interests_body_md5) THEN
        RAISE EXCEPTION 'Function baseline mismatch; stop, do not retry.';
    END IF;
    IF pg_catalog.has_function_privilege('anon',mutation_oid,'EXECUTE')
       OR pg_catalog.has_function_privilege('authenticated',mutation_oid,'EXECUTE')
       OR pg_catalog.has_function_privilege('anon',wrapper_oid,'EXECUTE')
       OR NOT pg_catalog.has_function_privilege('authenticated',wrapper_oid,'EXECUTE') THEN
        RAISE EXCEPTION 'Unexpected mutation execution privileges.';
    END IF;
    IF pg_catalog.to_regclass('public.destination_categories') IS NOT NULL
       OR EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
           AND table_name='places' AND column_name='operating_days_raw') THEN
        RAISE EXCEPTION 'Extension already or partially installed; review state, never rerun blindly.';
    END IF;
END;
$review$;

CREATE TABLE public.destination_categories (
    key text PRIMARY KEY CHECK (pg_catalog.char_length(key) BETWEEN 1 AND 120 AND key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    label text NOT NULL CHECK (pg_catalog.char_length(label) BETWEEN 1 AND 250 AND label=pg_catalog.btrim(label)),
    parent_key text REFERENCES public.destination_categories(key) ON DELETE RESTRICT,
    CHECK (parent_key IS NULL OR parent_key<>key)
);
ALTER TABLE public.destination_categories ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.destination_categories FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.destination_categories TO anon,authenticated;
-- Taxonomy labels only; no destination, user or session data. No client DML.
CREATE POLICY destination_categories_read ON public.destination_categories FOR SELECT TO anon,authenticated USING (true);
INSERT INTO public.destination_categories(key,label) VALUES
    ('attraction','Attractions'),('dining','Dining'),('shopping','Shopping'),
    ('accommodation','Accommodation'),('nature','Nature'),('heritage','Heritage'),('industrial','Industrial Tourism');
CREATE FUNCTION public.rosago_category_parent_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
AS $parents$
BEGIN
    IF pg_catalog.current_setting('transaction_isolation')<>'serializable' THEN
        RAISE EXCEPTION 'Registry changes require a SERIALIZABLE owner transaction.';
    END IF;
    IF EXISTS (
        WITH RECURSIVE ancestors(key,seen) AS (
            SELECT NEW.parent_key,ARRAY[NEW.key]::text[]
            UNION ALL
            SELECT c.parent_key,a.seen||a.key FROM ancestors a
                JOIN public.destination_categories c ON c.key=a.key
                WHERE a.key IS NOT NULL AND NOT a.key=ANY(a.seen)
        ) SELECT 1 FROM ancestors WHERE key=ANY(seen)
    ) THEN RAISE EXCEPTION 'Category parent cycle is not allowed.'; END IF;
    RETURN NEW;
END;
$parents$;
REVOKE ALL ON FUNCTION public.rosago_category_parent_guard() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER destination_category_parent_guard AFTER INSERT OR UPDATE ON public.destination_categories
    FOR EACH ROW EXECUTE FUNCTION public.rosago_category_parent_guard();
-- Additional labels and legacy relationships need a separately approved registry
-- package. This script does not guess a parent for any of the 73 CSV labels.

ALTER TABLE public.places ADD COLUMN operating_days_raw text
    CHECK (operating_days_raw IS NULL OR (pg_catalog.char_length(operating_days_raw) BETWEEN 1 AND 2000
           AND pg_catalog.btrim(operating_days_raw)<>''));
COMMENT ON COLUMN public.places.operating_days_raw IS 'Original source operating-day text; not verified opening-time feasibility.';
ALTER TABLE public.places ADD CONSTRAINT places_category_registry_fk FOREIGN KEY (category)
    REFERENCES public.destination_categories(key) ON DELETE RESTRICT;
-- The exact existing check definition must be verified in preflight before this
-- draft may be finalized. Add the validated FK before removing the fixed enum.
ALTER TABLE public.places DROP CONSTRAINT places_category_check;

-- An additional database collision guard for the reviewed catalog. The offline
-- full Unicode casefold/identity/alias review remains mandatory: SQL lower() and
-- Python casefold() are not equivalent for every Unicode character.
CREATE FUNCTION public.rosago_catalog_name_key(p_name text)
RETURNS text LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path=''
AS $key$
    SELECT pg_catalog.btrim(pg_catalog.regexp_replace(
        pg_catalog.replace(pg_catalog.replace(pg_catalog.replace(
            pg_catalog.lower(pg_catalog.regexp_replace(pg_catalog.normalize(p_name,'NFKD'),U&'[\0300-\036f]','','g')),
            '&',' and '),'''',''),U&'\2019',''),
        '[^[:alnum:]]+',' ','g'));
$key$;
REVOKE ALL ON FUNCTION public.rosago_catalog_name_key(text) FROM PUBLIC,anon,authenticated,service_role;
CREATE UNIQUE INDEX places_catalog_name_identity_unique ON public.places(public.rosago_catalog_name_key(name));

DO $patch$
DECLARE
    mutation_oid oid := pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)');
    interests_oid oid := pg_catalog.to_regprocedure('public.rosago_itinerary_interests_valid(text[])');
    wrapper_oid oid := pg_catalog.to_regprocedure('public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)');
    wrapper_before text := pg_catalog.pg_get_functiondef(wrapper_oid);
    definition text; body text; original text; old_fragment text; new_fragment text;
    old_acl aclitem[]; old_owner oid; old_config text[];
BEGIN
    SELECT pg_catalog.pg_get_functiondef(p.oid), p.prosrc, p.proacl,p.proowner,p.proconfig
        INTO definition, original,old_acl,old_owner,old_config FROM pg_catalog.pg_proc p WHERE p.oid=mutation_oid;
    body := pg_catalog.replace(original,pg_catalog.chr(13),'');
    old_fragment := $old$IF (p_values ->> 'category') IS NULL OR (p_values ->> 'category') NOT IN
            ('attraction','dining','shopping','accommodation','nature','heritage','industrial') THEN$old$;
    new_fragment := $new$IF pg_catalog.jsonb_typeof(p_values->'category') IS DISTINCT FROM 'string'
            OR NOT EXISTS (SELECT 1 FROM public.destination_categories c WHERE c.key=p_values->>'category') THEN$new$;
    old_fragment := pg_catalog.replace(old_fragment,pg_catalog.chr(13),'');
    new_fragment := pg_catalog.replace(new_fragment,pg_catalog.chr(13),'');
    IF (pg_catalog.length(body)-pg_catalog.length(pg_catalog.replace(body,old_fragment,'')))/pg_catalog.length(old_fragment)<>1 THEN
        RAISE EXCEPTION 'Category validator differs from reviewed structure.';
    END IF;
    body := pg_catalog.replace(body,old_fragment,new_fragment);
    old_fragment := $old$'image_url','environment',$old$;
    IF (pg_catalog.length(body)-pg_catalog.length(pg_catalog.replace(body,old_fragment,'')))/pg_catalog.length(old_fragment)<>1 THEN
        RAISE EXCEPTION 'Mutation allowlist differs from reviewed structure.';
    END IF;
    body := pg_catalog.replace(body,old_fragment,$new$'image_url','environment','operating_days_raw','tourism_source','tourism_source_row',$new$);
    old_fragment := $old$tourism_fields := p_values$old$;
    new_fragment := $new$IF p_values ? 'operating_days_raw' AND NOT (
            pg_catalog.jsonb_typeof(p_values->'operating_days_raw')='null' OR
            (pg_catalog.jsonb_typeof(p_values->'operating_days_raw')='string'
             AND pg_catalog.char_length(p_values->>'operating_days_raw') BETWEEN 1 AND 2000
             AND pg_catalog.btrim(p_values->>'operating_days_raw')<>'')) THEN
            RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid operating-day text.';
        END IF;
        IF p_values ?| ARRAY['tourism_source','tourism_source_row'] THEN
            IF NOT p_values ?& ARRAY['tourism_source','tourism_source_row'] OR NOT (
                (pg_catalog.jsonb_typeof(p_values->'tourism_source')='null'
                 AND pg_catalog.jsonb_typeof(p_values->'tourism_source_row')='null') OR
                (pg_catalog.jsonb_typeof(p_values->'tourism_source')='string'
                 AND pg_catalog.char_length(p_values->>'tourism_source') BETWEEN 1 AND 500
                 AND pg_catalog.btrim(p_values->>'tourism_source')<>''
                 AND pg_catalog.jsonb_typeof(p_values->'tourism_source_row')='number'
                 AND (p_values->>'tourism_source_row') ~ '^[0-9]{1,7}$'
                 AND (p_values->>'tourism_source_row')::numeric BETWEEN 2 AND 1048576)) THEN
                RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid source provenance.';
            END IF;
        END IF;
        tourism_fields := p_values$new$;
    IF (pg_catalog.length(body)-pg_catalog.length(pg_catalog.replace(body,old_fragment,'')))/pg_catalog.length(old_fragment)<>1 THEN
        RAISE EXCEPTION 'Tourism validation insertion point differs.';
    END IF;
    body := pg_catalog.replace(body,old_fragment,new_fragment);
    old_fragment := $old$IF p_values ? 'environment' THEN$old$;
    new_fragment := $new$IF p_values ? 'operating_days_raw' THEN
            UPDATE public.places SET operating_days_raw=p_values->>'operating_days_raw'
            WHERE id=destination.id RETURNING * INTO destination;
        END IF;
        IF p_values ? 'tourism_source' THEN
            UPDATE public.places SET tourism_source=p_values->>'tourism_source',
                tourism_source_row=(p_values->>'tourism_source_row')::integer
            WHERE id=destination.id RETURNING * INTO destination;
        END IF;
        IF p_values ? 'environment' THEN$new$;
    IF (pg_catalog.length(body)-pg_catalog.length(pg_catalog.replace(body,old_fragment,'')))/pg_catalog.length(old_fragment)<>1 THEN
        RAISE EXCEPTION 'Optional-field update insertion point differs.';
    END IF;
    body := pg_catalog.replace(body,old_fragment,new_fragment);
    -- All caller/provider checks, locks, photo rules and transitions in the live
    -- body stay intact; do not replace it with an old migration's full body.
    EXECUTE pg_catalog.replace(definition,original,body);
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=mutation_oid
        AND p.proacl IS NOT DISTINCT FROM old_acl AND p.proowner=old_owner
        AND p.proconfig IS NOT DISTINCT FROM old_config AND p.prosecdef) THEN
        RAISE EXCEPTION 'Mutation authority attributes changed.';
    END IF;

    SELECT pg_catalog.pg_get_functiondef(p.oid),p.prosrc,p.proacl,p.proowner,p.proconfig
        INTO definition,original,old_acl,old_owner,old_config
        FROM pg_catalog.pg_proc p WHERE p.oid=interests_oid;
    body := pg_catalog.regexp_replace(original,
        'values_to_check <@ ARRAY\[[^]]+\]::text\[\]',
        'NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(values_to_check) item(value) WHERE item.value IS NULL OR NOT EXISTS (SELECT 1 FROM public.destination_categories c WHERE c.key=item.value))');
    IF body=original THEN RAISE EXCEPTION 'Interests validator differs from reviewed structure.'; END IF;
    definition := pg_catalog.replace(definition,original,body);
    -- A lookup of table contents is STABLE, never IMMUTABLE. Existing limits,
    -- NULL rejection, uniqueness and every caller guard remain unchanged.
    definition := pg_catalog.replace(definition,'IMMUTABLE','STABLE');
    EXECUTE definition;
    ALTER FUNCTION public.rosago_itinerary_interests_valid(text[]) STABLE;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=interests_oid
        AND p.proacl IS NOT DISTINCT FROM old_acl AND p.proowner=old_owner
        AND p.proconfig IS NOT DISTINCT FROM old_config AND NOT p.prosecdef AND p.provolatile='s') THEN
        RAISE EXCEPTION 'Interests validator authority attributes changed.';
    END IF;
    IF pg_catalog.pg_get_functiondef(wrapper_oid) IS DISTINCT FROM wrapper_before THEN
        RAISE EXCEPTION 'Audit wrapper changed; roll back.';
    END IF;
END;
$patch$;
COMMIT;
-- NOT A FINAL APPLY PACKAGE: registry rows/relationships, current live provenance
-- rules, DB/app registry parity and target-specific preflight remain mandatory.
-- No destination values, statuses, IDs/images, existing policies or ACLs change.
