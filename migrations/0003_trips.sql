-- DRAFT ONLY: prepared and checked offline; not executed against any database.
-- Apply manually once as trusted postgres after verified 0001 and 0002.
-- Unexpected existing objects require review; never run at application startup.
BEGIN;

CREATE TABLE public.trips (
    id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid()
        REFERENCES auth.users(id) ON DELETE CASCADE,
    name text NOT NULL,
    visit_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT trips_name_check CHECK (
        char_length(name) BETWEEN 1 AND 100
        AND name = regexp_replace(name, '^[[:space:]]+|[[:space:]]+$', '', 'g')),
    CONSTRAINT trips_visit_date_check CHECK (
        visit_date IS NULL OR visit_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31')
);

CREATE INDEX trips_owner_listing_idx ON public.trips (user_id, created_at, id);

CREATE TABLE public.trip_places (
    trip_id uuid NOT NULL REFERENCES public.trips(id) ON DELETE CASCADE,
    place_id uuid NOT NULL REFERENCES public.places(id) ON DELETE RESTRICT,
    position integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT trip_places_pkey PRIMARY KEY (trip_id, place_id),
    CONSTRAINT trip_places_position_check CHECK (position >= 1),
    CONSTRAINT trip_places_trip_position_unique UNIQUE (trip_id, position)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX trip_places_place_id_idx ON public.trip_places (place_id);

ALTER TABLE public.trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trip_places ENABLE ROW LEVEL SECURITY;

-- Generated identity/ownership/timestamps and membership keys are not updatable.
REVOKE ALL PRIVILEGES ON TABLE public.trips, public.trip_places
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, DELETE ON TABLE public.trips TO authenticated;
GRANT INSERT (name, visit_date) ON TABLE public.trips TO authenticated;
GRANT UPDATE (name, visit_date) ON TABLE public.trips TO authenticated;
GRANT SELECT, DELETE ON TABLE public.trip_places TO authenticated;
GRANT INSERT (trip_id, place_id, position) ON TABLE public.trip_places TO authenticated;
GRANT UPDATE (position) ON TABLE public.trip_places TO authenticated;

CREATE POLICY trips_select_own ON public.trips
    FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));
CREATE POLICY trips_insert_own ON public.trips
    FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY trips_update_own ON public.trips
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY trips_delete_own ON public.trips
    FOR DELETE TO authenticated USING (user_id = (SELECT auth.uid()));

CREATE POLICY trip_places_select_own ON public.trip_places
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.trips AS trip
        WHERE trip.id = trip_places.trip_id AND trip.user_id = (SELECT auth.uid())
    ));
CREATE POLICY trip_places_insert_own_published ON public.trip_places
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.trips AS trip
            WHERE trip.id = trip_places.trip_id AND trip.user_id = (SELECT auth.uid())
        ) AND EXISTS (
            SELECT 1 FROM public.places AS place
            WHERE place.id = trip_places.place_id AND place.status = 'published'
        )
    );
CREATE POLICY trip_places_update_own ON public.trip_places
    FOR UPDATE TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.trips AS trip
        WHERE trip.id = trip_places.trip_id AND trip.user_id = (SELECT auth.uid())
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.trips AS trip
        WHERE trip.id = trip_places.trip_id AND trip.user_id = (SELECT auth.uid())
    ));
CREATE POLICY trip_places_delete_own ON public.trip_places
    FOR DELETE TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.trips AS trip
        WHERE trip.id = trip_places.trip_id AND trip.user_id = (SELECT auth.uid())
    ));

CREATE FUNCTION public.rosago_trips_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at := pg_catalog.now();
    RETURN NEW;
END;
$$;

REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_trips_set_updated_at()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER rosago_trips_updated_at
    BEFORE UPDATE ON public.trips
    FOR EACH ROW EXECUTE FUNCTION public.rosago_trips_set_updated_at();

-- Direct writes also lock the parent before changing each membership row.
-- RLS supplies ownership; no publication check here: archived rows remain editable.
-- Row-target acquisition can precede this trigger, so direct multi-row writes
-- can deadlock with parent-first RPCs. PostgreSQL must abort, not partially save.
-- Callers must not treat earlier reads/position calculations as a transaction.
CREATE FUNCTION public.rosago_trip_places_lock_parent()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    target_trip_id uuid;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.trip_id IS DISTINCT FROM OLD.trip_id
            OR NEW.place_id IS DISTINCT FROM OLD.place_id THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Membership identity cannot change.';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        target_trip_id := OLD.trip_id;
    ELSE
        target_trip_id := NEW.trip_id;
    END IF;

    PERFORM trip.id FROM public.trips AS trip
        WHERE trip.id = target_trip_id FOR UPDATE;
    IF NOT FOUND AND TG_OP <> 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Trip not found.';
    END IF;
    -- ON DELETE CASCADE runs after the parent is deleted in this transaction.
    -- Its parent lock is already held. Ordinary DELETE still requires own-row RLS.
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_trip_places_lock_parent()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER rosago_trip_places_parent_lock
    BEFORE INSERT OR UPDATE OR DELETE ON public.trip_places
    FOR EACH ROW EXECUTE FUNCTION public.rosago_trip_places_lock_parent();

-- One RPC call is one transaction. Ownership is auth.uid(), never an argument.
-- Each RPC locks the parent before reading membership; trigger reacquisition is safe.
-- READ COMMITTED gives fresh membership visibility after waiting on that lock.
-- Reject fixed-snapshot transactions rather than validate an obsolete permutation.
CREATE FUNCTION public.rosago_trip_add_place(p_trip_id uuid, p_place_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    last_position integer;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Unsupported transaction isolation.';
    END IF;
    PERFORM trip.id FROM public.trips AS trip
        WHERE trip.id = p_trip_id AND trip.user_id = (SELECT auth.uid()) FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Trip not found.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.places AS place
        WHERE place.id = p_place_id AND place.status = 'published'
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Place unavailable.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.trip_places AS membership
        WHERE membership.trip_id = p_trip_id AND membership.place_id = p_place_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Place already in trip.';
    END IF;
    SELECT COALESCE(pg_catalog.max(membership.position), 0) INTO last_position
        FROM public.trip_places AS membership WHERE membership.trip_id = p_trip_id;
    IF last_position = 2147483647 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Trip ordering limit reached.';
    END IF;
    INSERT INTO public.trip_places (trip_id, place_id, position)
        VALUES (p_trip_id, p_place_id, last_position + 1);
END;
$$;

CREATE FUNCTION public.rosago_trip_remove_place(p_trip_id uuid, p_place_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Unsupported transaction isolation.';
    END IF;
    PERFORM trip.id FROM public.trips AS trip
        WHERE trip.id = p_trip_id AND trip.user_id = (SELECT auth.uid()) FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Trip not found.';
    END IF;
    IF p_place_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid place identifier.';
    END IF;
    -- Removing an already-absent membership is a no-op; gaps are valid.
    DELETE FROM public.trip_places AS membership
        WHERE membership.trip_id = p_trip_id AND membership.place_id = p_place_id;
END;
$$;

CREATE FUNCTION public.rosago_trip_reorder_places(p_trip_id uuid, p_place_ids uuid[])
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Unsupported transaction isolation.';
    END IF;
    PERFORM trip.id FROM public.trips AS trip
        WHERE trip.id = p_trip_id AND trip.user_id = (SELECT auth.uid()) FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'Trip not found.';
    END IF;
    -- Empty arrays are valid only for empty trips. NULL/multidimensional arrays,
    -- NULL elements, duplicates, omissions and foreign IDs are rejected.
    IF p_place_ids IS NULL
        OR COALESCE(pg_catalog.array_ndims(p_place_ids), 1) <> 1
        OR pg_catalog.cardinality(p_place_ids) <> (
            SELECT pg_catalog.count(DISTINCT item.place_id)
            FROM pg_catalog.unnest(p_place_ids) AS item(place_id)
        )
        OR pg_catalog.cardinality(p_place_ids) <> (
            SELECT pg_catalog.count(*) FROM public.trip_places AS membership
            WHERE membership.trip_id = p_trip_id
        )
        OR EXISTS (
            SELECT 1 FROM pg_catalog.unnest(p_place_ids) AS item(place_id)
            WHERE NOT EXISTS (
                SELECT 1 FROM public.trip_places AS membership
                WHERE membership.trip_id = p_trip_id AND membership.place_id = item.place_id
            )
        ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Invalid trip order.';
    END IF;

    SET CONSTRAINTS public.trip_places_trip_position_unique DEFERRED;
    UPDATE public.trip_places AS membership SET position = item.ordinality::integer
        FROM pg_catalog.unnest(p_place_ids) WITH ORDINALITY AS item(place_id, ordinality)
        WHERE membership.trip_id = p_trip_id AND membership.place_id = item.place_id;
    SET CONSTRAINTS public.trip_places_trip_position_unique IMMEDIATE;
END;
$$;

REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_trip_add_place(uuid, uuid),
    public.rosago_trip_remove_place(uuid, uuid), public.rosago_trip_reorder_places(uuid, uuid[])
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rosago_trip_add_place(uuid, uuid),
    public.rosago_trip_remove_place(uuid, uuid), public.rosago_trip_reorder_places(uuid, uuid[])
    TO authenticated;

COMMIT;
