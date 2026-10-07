-- DRAFT ONLY: not applied. Review migrations/README.md before execution.
-- Intended executor/owner: the trusted Supabase postgres migration role.
-- One-time migration: an existing profiles table is an error requiring review.
BEGIN;

CREATE TABLE public.profiles (
    id uuid NOT NULL PRIMARY KEY
        REFERENCES auth.users(id) ON DELETE CASCADE,
    first_name text,
    last_name text,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Override any Supabase default table grants. No service-role application
-- integration is introduced by this migration.
REVOKE ALL PRIVILEGES ON TABLE public.profiles
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.profiles TO authenticated;
GRANT UPDATE (first_name, last_name) ON TABLE public.profiles TO authenticated;

CREATE POLICY profiles_select_own ON public.profiles
    FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = id);

CREATE POLICY profiles_update_own ON public.profiles
    FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = id)
    WITH CHECK ((SELECT auth.uid()) = id);

-- Auth insertion is privileged; ordinary clients cannot insert profiles.
-- No dynamic SQL, role metadata, or caller-supplied ownership is used.
CREATE FUNCTION public.rosago_create_user_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.profiles (id, first_name, last_name)
    VALUES (
        NEW.id,
        NULLIF(pg_catalog.regexp_replace(
            NEW.raw_user_meta_data ->> 'first_name',
            '^[[:space:]]+|[[:space:]]+$', '', 'g'), ''),
        NULLIF(pg_catalog.regexp_replace(
            NEW.raw_user_meta_data ->> 'last_name',
            '^[[:space:]]+|[[:space:]]+$', '', 'g'), '')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

ALTER FUNCTION public.rosago_create_user_profile() OWNER TO postgres;
-- PostgreSQL functions otherwise grant EXECUTE to PUBLIC by default.
REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_create_user_profile()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER rosago_auth_user_profile_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.rosago_create_user_profile();

-- Existing accounts, including unconfirmed accounts, receive missing profiles.
-- This statement alone is repeatable; it never overwrites an existing profile.
-- created_at records profile creation time, not the original Auth signup time.
INSERT INTO public.profiles (id, first_name, last_name)
SELECT
    users.id,
    NULLIF(pg_catalog.regexp_replace(
        users.raw_user_meta_data ->> 'first_name',
        '^[[:space:]]+|[[:space:]]+$', '', 'g'), ''),
    NULLIF(pg_catalog.regexp_replace(
        users.raw_user_meta_data ->> 'last_name',
        '^[[:space:]]+|[[:space:]]+$', '', 'g'), '')
FROM auth.users AS users
ON CONFLICT (id) DO NOTHING;

COMMIT;
