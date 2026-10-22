-- REVIEW ONLY: not applied. Run once through a trusted migration operator.
-- Authorization foundation only; no provisioning or destination write grants.
BEGIN;

CREATE TABLE public.admin_memberships (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    granted_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.admin_memberships ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.admin_memberships
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.admin_memberships TO authenticated;

CREATE POLICY admin_memberships_select_own ON public.admin_memberships
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

-- Invoker rights suffice: the caller can read only their own membership.
-- Never call this predicate from the membership policy itself (recursion).
CREATE FUNCTION public.rosago_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.admin_memberships AS membership
        WHERE membership.user_id = (SELECT auth.uid())
    );
$$;

REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_is_admin()
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rosago_is_admin() TO authenticated;

COMMIT;
