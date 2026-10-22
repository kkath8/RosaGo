-- Review only; do not apply automatically. Requires live migrations 0001–0008.
BEGIN;

-- Existing authenticated SELECT grant is sufficient. Permissive SELECT policies
-- combine with OR: published rows for everyone, all rows for current Admins.
CREATE POLICY places_select_admin ON public.places
    AS PERMISSIVE FOR SELECT TO authenticated
    USING ((SELECT public.rosago_is_admin()));

COMMIT;
