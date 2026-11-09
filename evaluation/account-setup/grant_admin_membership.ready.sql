-- REVIEW ONLY: requires separate Admin membership approval before hosted use.
-- Target jfaufpfzfhysqkhcdsrs; verify dashboard project URL independently.
-- Replace only these two placeholders with the dashboard-verified synthetic IDs.
-- No credentials, emails, role metadata or Auth row writes belong in this file.
BEGIN;
LOCK TABLE public.admin_memberships IN EXCLUSIVE MODE;
DO $$
DECLARE
    synthetic_user uuid := '3c572202-c1da-4e5a-aa20-d89be25b2d9f';
    synthetic_admin uuid := '4bc67593-c979-4441-b42a-99b6d3da2885';
BEGIN
    IF synthetic_user = synthetic_admin THEN
        RAISE EXCEPTION 'Synthetic User and Admin must be different accounts.';
    END IF;
    IF (SELECT count(*) FROM auth.users) <> 2
       OR (SELECT count(*) FROM public.profiles) <> 2
       OR EXISTS (SELECT 1 FROM public.admin_memberships) THEN
        RAISE EXCEPTION 'Expected exactly two accounts/profiles and zero memberships. Stop.';
    END IF;
    IF (SELECT count(*) FROM auth.users
        WHERE id IN (synthetic_user,synthetic_admin)
          AND email_confirmed_at IS NOT NULL) <> 2 THEN
        RAISE EXCEPTION 'Both supplied account UUIDs must exist and be individually confirmed.';
    END IF;
    IF (SELECT count(*) FROM public.profiles
        WHERE id IN (synthetic_user,synthetic_admin)) <> 2 THEN
        RAISE EXCEPTION 'Expected trigger-created profiles for both synthetic UUIDs.';
    END IF;
    -- This is the entire privilege elevation: one membership row, no SQL GRANT.
    INSERT INTO public.admin_memberships(user_id) VALUES (synthetic_admin);
END;
$$;
COMMIT;
