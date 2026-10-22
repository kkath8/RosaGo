-- LOCAL DRAFT ONLY. Not applied; no startup runner. Review with 0004 design notes.
-- Requires applied 0001, 0002, 0003; do not edit or rerun those migrations.
-- Intentionally no application writes or Save RPC until preview contracts exist.
BEGIN;

CREATE FUNCTION public.rosago_itinerary_interests_valid(values_to_check text[])
RETURNS boolean
LANGUAGE sql
IMMUTABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT COALESCE(
        pg_catalog.array_ndims(values_to_check) = 1
        AND pg_catalog.array_lower(values_to_check, 1) = 1
        AND pg_catalog.cardinality(values_to_check) BETWEEN 1 AND 6
        AND values_to_check <@ ARRAY[
            'attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage']::text[]
        AND pg_catalog.cardinality(values_to_check) = (
            SELECT pg_catalog.count(DISTINCT item.value)
            FROM pg_catalog.unnest(values_to_check) AS item(value)
        ), false);
$$;

REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_itinerary_interests_valid(text[])
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE public.itinerary_drafts (
    id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid()
        REFERENCES auth.users(id) ON DELETE CASCADE,
    state text NOT NULL DEFAULT 'editing',
    schema_version smallint NOT NULL DEFAULT 1,
    revision bigint NOT NULL DEFAULT 1,
    preferences jsonb,
    preview jsonb,
    saved_trip_id uuid REFERENCES public.trips(id) ON DELETE SET NULL,
    saved_at timestamptz,
    accepted_preview_digest text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + INTERVAL '24 hours'),

    CONSTRAINT itinerary_drafts_state_check CHECK (
        state IN ('editing', 'generating', 'preview_ready', 'failed', 'saved', 'expired')),
    CONSTRAINT itinerary_drafts_version_check CHECK (schema_version = 1 AND revision > 0),
    -- Envelope bounds only: future trusted writers must validate the versioned
    -- document's fields and semantics. JSON never proves ownership/publication.
    CONSTRAINT itinerary_drafts_preferences_check CHECK (
        preferences IS NULL OR (jsonb_typeof(preferences) = 'object'
        AND octet_length(preferences::text) <= 16384)),
    CONSTRAINT itinerary_drafts_preview_check CHECK (
        preview IS NULL OR (jsonb_typeof(preview) = 'object'
        AND octet_length(preview::text) <= 262144)),
    CONSTRAINT itinerary_drafts_document_state_check CHECK (
        (state NOT IN ('generating', 'preview_ready', 'saved') OR preferences IS NOT NULL)
        AND (state <> 'preview_ready' OR preview IS NOT NULL)),
    -- Draft UUID is the save idempotency identity. Retain the saved marker/digest
    -- after trip deletion; NULL saved_trip_id then means deleted, never resavable.
    CONSTRAINT itinerary_drafts_save_check CHECK (
        (state = 'saved' AND saved_at IS NOT NULL AND accepted_preview_digest IS NOT NULL)
        OR (state <> 'saved' AND saved_trip_id IS NULL AND saved_at IS NULL
            AND accepted_preview_digest IS NULL)),
    CONSTRAINT itinerary_drafts_digest_check CHECK (
        accepted_preview_digest IS NULL
        OR accepted_preview_digest COLLATE "C" ~ '^[0-9a-f]{64}$'),
    -- Save eligibility/expiry enforcement belongs to the future validated Save RPC.
    CONSTRAINT itinerary_drafts_saved_time_check CHECK (
        saved_at IS NULL OR (isfinite(saved_at) AND saved_at >= created_at)),
    CONSTRAINT itinerary_drafts_time_check CHECK (
        isfinite(created_at) AND isfinite(updated_at) AND isfinite(expires_at)
        AND updated_at >= created_at AND expires_at > created_at
        AND expires_at <= created_at + INTERVAL '24 hours')
);

CREATE INDEX itinerary_drafts_owner_listing_idx
    ON public.itinerary_drafts (user_id, created_at, id);
CREATE INDEX itinerary_drafts_expiry_idx ON public.itinerary_drafts (expires_at);
CREATE UNIQUE INDEX itinerary_drafts_saved_trip_idx
    ON public.itinerary_drafts (saved_trip_id) WHERE saved_trip_id IS NOT NULL;

CREATE TABLE public.trip_itinerary (
    trip_id uuid NOT NULL PRIMARY KEY REFERENCES public.trips(id) ON DELETE CASCADE,
    interests text[] NOT NULL,
    companion_type text NOT NULL,
    budget_centavos bigint,
    start_date date NOT NULL,
    end_date date NOT NULL,
    daily_start_time time without time zone NOT NULL,
    daily_end_time time without time zone NOT NULL,
    transportation text NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Manila',
    schedule_revision bigint NOT NULL DEFAULT 1,
    fingerprint_version smallint NOT NULL DEFAULT 1,
    schedule_fingerprint text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT trip_itinerary_interests_check CHECK (
        public.rosago_itinerary_interests_valid(interests)),
    CONSTRAINT trip_itinerary_companion_check CHECK (
        companion_type IN ('solo', 'couple', 'family', 'friends', 'group')),
    -- Fixed unit/scope: PHP centavos per person for the WHOLE itinerary.
    -- NULL is unknown/not supplied, never zero. Initial ceiling: PHP 100,000.
    CONSTRAINT trip_itinerary_budget_check CHECK (
        budget_centavos IS NULL OR budget_centavos BETWEEN 0 AND 10000000),
    CONSTRAINT trip_itinerary_dates_check CHECK (
        start_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
        AND end_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
        AND end_date BETWEEN start_date AND start_date + 6),
    CONSTRAINT trip_itinerary_window_check CHECK (
        daily_end_time > daily_start_time),
    CONSTRAINT trip_itinerary_transportation_check CHECK (
        transportation IN ('walking', 'private_car', 'public_transport')),
    CONSTRAINT trip_itinerary_timezone_check CHECK (timezone = 'Asia/Manila'),
    -- Baseline for comparison, NOT evidence of freshness by itself. No changes
    -- to existing membership triggers/RPCs. NULL means unvalidated/needs review.
    CONSTRAINT trip_itinerary_revision_check CHECK (
        schedule_revision > 0 AND fingerprint_version = 1),
    CONSTRAINT trip_itinerary_fingerprint_check CHECK (
        schedule_fingerprint IS NULL
        OR schedule_fingerprint COLLATE "C" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT trip_itinerary_time_check CHECK (
        isfinite(created_at) AND isfinite(updated_at) AND updated_at >= created_at)
);

CREATE TABLE public.trip_stop_plans (
    trip_id uuid NOT NULL,
    place_id uuid NOT NULL,
    scheduled_date date,
    planned_start_time time without time zone,
    planned_end_time time without time zone,
    source text NOT NULL DEFAULT 'manual',
    keep_place boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT trip_stop_plans_pkey PRIMARY KEY (trip_id, place_id),
    CONSTRAINT trip_stop_plans_membership_fk FOREIGN KEY (trip_id, place_id)
        REFERENCES public.trip_places(trip_id, place_id) ON DELETE CASCADE,
    CONSTRAINT trip_stop_plans_source_check CHECK (source IN ('manual', 'recommended')),
    CONSTRAINT trip_stop_plans_date_check CHECK (
        scheduled_date IS NULL OR scheduled_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'),
    CONSTRAINT trip_stop_plans_time_pair_check CHECK (
        (planned_start_time IS NULL) = (planned_end_time IS NULL)),
    CONSTRAINT trip_stop_plans_window_check CHECK (
        planned_start_time IS NULL OR (scheduled_date IS NOT NULL
        AND planned_end_time > planned_start_time)),
    CONSTRAINT trip_stop_plans_timestamp_check CHECK (
        isfinite(created_at) AND isfinite(updated_at) AND updated_at >= created_at)
);

ALTER TABLE public.itinerary_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trip_itinerary ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trip_stop_plans ENABLE ROW LEVEL SECURITY;

-- Deny all direct writes, including lifecycle/owner/fingerprint manipulation.
-- No elevated function or runtime service-role dependency is introduced.
REVOKE ALL PRIVILEGES ON TABLE public.itinerary_drafts, public.trip_itinerary,
    public.trip_stop_plans FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.itinerary_drafts, public.trip_itinerary,
    public.trip_stop_plans TO authenticated;

CREATE POLICY itinerary_drafts_select_own ON public.itinerary_drafts
    FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));
CREATE POLICY trip_itinerary_select_own ON public.trip_itinerary
    FOR SELECT TO authenticated USING (EXISTS (
        SELECT 1 FROM public.trips AS trip
        WHERE trip.id = trip_itinerary.trip_id AND trip.user_id = (SELECT auth.uid())
    ));
CREATE POLICY trip_stop_plans_select_own ON public.trip_stop_plans
    FOR SELECT TO authenticated USING (EXISTS (
        SELECT 1 FROM public.trips AS trip
        WHERE trip.id = trip_stop_plans.trip_id AND trip.user_id = (SELECT auth.uid())
    ));

-- This only touches new rows/tables. It preserves identity and updates metadata;
-- lifecycle transitions and revision increments belong to future validated RPCs.
CREATE FUNCTION public.rosago_itinerary_guard_metadata()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Creation time cannot change.';
        END IF;
        IF TG_TABLE_NAME = 'itinerary_drafts' THEN
            IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Draft identity cannot change.';
            END IF;
        ELSE
            IF NEW.trip_id IS DISTINCT FROM OLD.trip_id THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Trip identity cannot change.';
            END IF;
            IF TG_TABLE_NAME = 'trip_stop_plans' THEN
                IF NEW.place_id IS DISTINCT FROM OLD.place_id THEN
                    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Membership identity cannot change.';
                END IF;
            END IF;
        END IF;
        NEW.updated_at := pg_catalog.now();
    END IF;
    IF TG_TABLE_NAME = 'itinerary_drafts' THEN
        -- A plain trip FK alone would allow a saved link to another owner.
        -- Existing trips ownership is immutable for application users (0003).
        IF NEW.saved_trip_id IS NOT NULL THEN
            PERFORM trip.id FROM public.trips AS trip
                WHERE trip.id = NEW.saved_trip_id AND trip.user_id = NEW.user_id
                FOR KEY SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Saved trip unavailable.';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_itinerary_guard_metadata()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER itinerary_drafts_metadata
    BEFORE INSERT OR UPDATE ON public.itinerary_drafts
    FOR EACH ROW EXECUTE FUNCTION public.rosago_itinerary_guard_metadata();
CREATE TRIGGER trip_itinerary_metadata
    BEFORE INSERT OR UPDATE ON public.trip_itinerary
    FOR EACH ROW EXECUTE FUNCTION public.rosago_itinerary_guard_metadata();
CREATE TRIGGER trip_stop_plans_metadata
    BEFORE INSERT OR UPDATE ON public.trip_stop_plans
    FOR EACH ROW EXECUTE FUNCTION public.rosago_itinerary_guard_metadata();

COMMIT;
