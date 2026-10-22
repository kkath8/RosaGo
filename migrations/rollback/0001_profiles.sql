-- DRAFT ONLY: development rollback for a successfully applied 0001_profiles.sql.
-- DESTRUCTIVE: removes all profile data. Review/export data before future use.
-- Run as the trusted postgres migration role, never as an application user.
-- No CASCADE: unexpected dependent objects must stop rollback for review.
BEGIN;

DROP TRIGGER rosago_auth_user_profile_created ON auth.users;
DROP FUNCTION public.rosago_create_user_profile();
DROP POLICY profiles_update_own ON public.profiles;
DROP POLICY profiles_select_own ON public.profiles;
DROP TABLE public.profiles;

COMMIT;
