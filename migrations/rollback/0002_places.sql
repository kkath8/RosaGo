-- DRAFT ONLY: rollback for one successfully applied 0002_places.sql.
-- DESTRUCTIVE: removes all places data; review/export before authorized use.
-- Run as trusted postgres. Unexpected dependencies must stop rollback.
BEGIN;

DROP TRIGGER rosago_places_updated_at ON public.places;
DROP FUNCTION public.rosago_places_set_updated_at();
DROP POLICY places_select_published ON public.places;
DROP TABLE public.places;

COMMIT;
