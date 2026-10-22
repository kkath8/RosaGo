-- DRAFT ONLY: rollback for one successfully applied 0003_trips.sql.
-- DESTRUCTIVE: removes all trips and saved memberships; review/export first.
-- Run only with separate authorization as trusted postgres. Never run at startup.
-- Unexpected dependencies must stop this transaction, not be removed implicitly.
BEGIN;

DROP FUNCTION public.rosago_trip_reorder_places(uuid, uuid[]);
DROP FUNCTION public.rosago_trip_remove_place(uuid, uuid);
DROP FUNCTION public.rosago_trip_add_place(uuid, uuid);
DROP TRIGGER rosago_trip_places_parent_lock ON public.trip_places;
DROP FUNCTION public.rosago_trip_places_lock_parent();
DROP TRIGGER rosago_trips_updated_at ON public.trips;
DROP FUNCTION public.rosago_trips_set_updated_at();
DROP POLICY trip_places_delete_own ON public.trip_places;
DROP POLICY trip_places_update_own ON public.trip_places;
DROP POLICY trip_places_insert_own_published ON public.trip_places;
DROP POLICY trip_places_select_own ON public.trip_places;
DROP POLICY trips_delete_own ON public.trips;
DROP POLICY trips_update_own ON public.trips;
DROP POLICY trips_insert_own ON public.trips;
DROP POLICY trips_select_own ON public.trips;
DROP TABLE public.trip_places;
DROP TABLE public.trips;

COMMIT;
