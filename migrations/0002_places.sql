-- DRAFT ONLY: prepared offline; not executed against Supabase.
-- Requires separate execution authorization and target-schema review.
-- One-time migration, run by trusted postgres; never on application startup.
BEGIN;

CREATE TABLE public.places (
    id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL,
    description text NOT NULL,
    category text NOT NULL,
    address text NOT NULL,
    latitude double precision,
    longitude double precision,
    image_url text,
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT places_slug_unique UNIQUE (slug),
    CONSTRAINT places_name_check CHECK (
        char_length(name) BETWEEN 1 AND 150
        AND name = regexp_replace(name, '^[[:space:]]+|[[:space:]]+$', '', 'g')),
    CONSTRAINT places_slug_check CHECK (
        char_length(slug) BETWEEN 1 AND 120
        AND slug COLLATE "C" ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT places_description_check CHECK (
        char_length(description) BETWEEN 1 AND 3000
        AND description = regexp_replace(description, '^[[:space:]]+|[[:space:]]+$', '', 'g')),
    CONSTRAINT places_address_check CHECK (
        char_length(address) BETWEEN 1 AND 500
        AND address = regexp_replace(address, '^[[:space:]]+|[[:space:]]+$', '', 'g')),
    CONSTRAINT places_category_check CHECK (
        category IN ('attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage')),
    CONSTRAINT places_latitude_check CHECK (
        latitude IS NULL OR (latitude BETWEEN -90 AND 90
        AND latitude NOT IN ('NaN'::double precision, 'Infinity'::double precision, '-Infinity'::double precision))),
    CONSTRAINT places_longitude_check CHECK (
        longitude IS NULL OR (longitude BETWEEN -180 AND 180
        AND longitude NOT IN ('NaN'::double precision, 'Infinity'::double precision, '-Infinity'::double precision))),
    CONSTRAINT places_coordinate_pair_check CHECK (
        (latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT places_published_coordinates_check CHECK (
        status <> 'published' OR (latitude IS NOT NULL AND longitude IS NOT NULL)),
    -- This is a URL baseline only, not complete URL/host/rights validation.
    CONSTRAINT places_image_url_check CHECK (
        image_url IS NULL OR (char_length(image_url) BETWEEN 9 AND 2048
        AND image_url = regexp_replace(image_url, '^[[:space:]]+|[[:space:]]+$', '', 'g')
        AND image_url LIKE 'https://%')),
    CONSTRAINT places_status_check CHECK (
        status IN ('draft', 'published', 'archived'))
);

ALTER TABLE public.places ENABLE ROW LEVEL SECURITY;

-- Override default grants. No service-role application access is introduced.
REVOKE ALL PRIVILEGES ON TABLE public.places
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.places TO anon, authenticated;

CREATE POLICY places_select_published ON public.places
    FOR SELECT TO anon, authenticated
    USING (status = 'published');

CREATE FUNCTION public.rosago_places_set_updated_at()
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

-- No direct application function privileges; this function is trigger-only.
REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_places_set_updated_at()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER rosago_places_updated_at
    BEFORE UPDATE ON public.places
    FOR EACH ROW EXECUTE FUNCTION public.rosago_places_set_updated_at();

COMMIT;
