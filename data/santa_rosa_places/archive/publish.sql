-- Run in the Supabase SQL Editor for the RosaGo project used by this app.
-- Apply the accompanying application changes first (nullable map coordinates
-- and the industrial category). No credentials or permission grants are changed.
-- Names and grouping: project-owner supplied list. Precise addresses, map pins,
-- visitor access and historical designations have NOT been independently verified.
-- NULL coordinates are intentional; these places appear in Explore and trips,
-- but do not receive a map pin until both verified coordinates are supplied.
BEGIN;

LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.places DROP CONSTRAINT IF EXISTS places_published_coordinates_check;
ALTER TABLE public.places DROP CONSTRAINT places_category_check;
ALTER TABLE public.places ADD CONSTRAINT places_category_check CHECK (
    category IN ('attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage', 'industrial'));
-- Keep all other validation, coordinate-pair checks, grants and RLS in place.

-- Keep existing itinerary validation compatible with the new interest category.
-- Retain its six-interest limit, security mode and existing function permissions.
DO $migration$
BEGIN
    IF pg_catalog.to_regprocedure('public.rosago_itinerary_interests_valid(text[])') IS NOT NULL THEN
        EXECUTE $definition$
CREATE OR REPLACE FUNCTION public.rosago_itinerary_interests_valid(values_to_check text[])
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
            'attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage', 'industrial']::text[]
        AND pg_catalog.cardinality(values_to_check) = (
            SELECT pg_catalog.count(DISTINCT item.value)
            FROM pg_catalog.unnest(values_to_check) AS item(value)
        ), false);
$$;

        $definition$;
    END IF;
END;
$migration$;

CREATE TEMP TABLE rosago_requested_places (LIKE public.places INCLUDING DEFAULTS) ON COMMIT DROP;
INSERT INTO rosago_requested_places (name, slug, description, category, address, latitude, longitude, image_url, status) VALUES
    ('Santa Rosa Arch', 'santa-rosa-arch', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('The City of Santa Rosa Museum', 'the-city-of-santa-rosa-museum', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Santa Rosa Parish Church', 'santa-rosa-parish-church', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Cuartel De Santo Domingo', 'cuartel-de-santo-domingo', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Arambulo Ancestral House', 'arambulo-ancestral-house', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Zavalla Ancestral House', 'zavalla-ancestral-house', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Gonzales Ancestral House', 'gonzales-ancestral-house', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Tiongco Ancestral House', 'tiongco-ancestral-house', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Perlas Ancestral House', 'perlas-ancestral-house', 'Heritage destination in Santa Rosa, Laguna. Confirm visitor access before visiting; ancestral houses may be private residences.', 'heritage', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Toyota Santa Rosa', 'toyota-santa-rosa', 'Industrial tourism listing in Santa Rosa, Laguna. Contact the company before visiting to confirm whether tours or visitor access are available.', 'industrial', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Coca-Cola Santa Rosa', 'coca-cola-santa-rosa', 'Industrial tourism listing in Santa Rosa, Laguna. Contact the company before visiting to confirm whether tours or visitor access are available.', 'industrial', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Monde Nissin Santa Rosa', 'monde-nissin-santa-rosa', 'Industrial tourism listing in Santa Rosa, Laguna. Contact the company before visiting to confirm whether tours or visitor access are available.', 'industrial', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Mitsubishi Motors Santa Rosa', 'mitsubishi-motors-santa-rosa', 'Industrial tourism listing in Santa Rosa, Laguna. Contact the company before visiting to confirm whether tours or visitor access are available.', 'industrial', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Enchanted Kingdom', 'enchanted-kingdom', 'Entertainment, recreation or sports destination in Santa Rosa, Laguna. Confirm available activities, opening hours and entry requirements with the venue.', 'attraction', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Nuvali', 'nuvali', 'Entertainment, recreation or sports destination in Santa Rosa, Laguna. Confirm available activities, opening hours and entry requirements with the venue.', 'attraction', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Lakeside Activities (Nuvali)', 'lakeside-activities-nuvali', 'Entertainment, recreation or sports destination in Santa Rosa, Laguna. Confirm available activities, opening hours and entry requirements with the venue.', 'attraction', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Fun Farm Sta. Elena', 'fun-farm-sta-elena', 'Entertainment, recreation or sports destination in Santa Rosa, Laguna. Confirm available activities, opening hours and entry requirements with the venue.', 'attraction', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('City Auditorium', 'city-auditorium', 'Entertainment, recreation or sports destination in Santa Rosa, Laguna. Confirm available activities, opening hours and entry requirements with the venue.', 'attraction', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('City of Santa Rosa Multi-Purpose Complex', 'city-of-santa-rosa-multi-purpose-complex', 'Entertainment, recreation or sports destination in Santa Rosa, Laguna. Confirm available activities, opening hours and entry requirements with the venue.', 'attraction', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('SM City Santa Rosa', 'sm-city-santa-rosa', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Robinson’s Santa Rosa', 'robinson-s-santa-rosa', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Target Mall', 'target-mall', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Waltermart Santa Rosa', 'waltermart-santa-rosa', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Waltermart Bel-Air', 'waltermart-bel-air', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Vista Mall Santa Rosa', 'vista-mall-santa-rosa', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Paseo de Santa Rosa', 'paseo-de-santa-rosa', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Laguna Central', 'laguna-central', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published'),
    ('Solenad 1, 2 and 3', 'solenad-1-2-and-3', 'Shopping and dining destination in Santa Rosa, Laguna. Confirm store hours and available establishments before visiting.', 'shopping', 'Santa Rosa, Laguna, Philippines', NULL, NULL, NULL, 'published');

-- Reuse existing slug identities, preserving trip references, verified coordinates,
-- images, descriptions, addresses and creation timestamps on existing records.
INSERT INTO public.places (name, slug, description, category, address, latitude, longitude, image_url, status)
SELECT name, slug, description, category, address, latitude, longitude, image_url, status FROM rosago_requested_places WHERE true
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    category = EXCLUDED.category,
    status = EXCLUDED.status;

-- Retire only the synthetic dataset from the earlier development demonstration.
-- Archive rather than delete so saved trip references remain valid.
UPDATE public.places SET status = 'archived'
WHERE slug LIKE 'rosago-test-v1-%' AND status <> 'archived';

DO $$
BEGIN
    IF (SELECT count(*) FROM public.places p
        JOIN rosago_requested_places r USING (slug)
        WHERE p.status = 'published') <> 28 THEN
        RAISE EXCEPTION 'Expected all 28 requested places to be published.';
    END IF;
END;
$$;

COMMIT;

-- Expected: 28 rows, all published; coordinates may be NULL.
SELECT name, slug, category, status, latitude, longitude
FROM public.places
WHERE slug IN (
    'santa-rosa-arch',
    'the-city-of-santa-rosa-museum',
    'santa-rosa-parish-church',
    'cuartel-de-santo-domingo',
    'arambulo-ancestral-house',
    'zavalla-ancestral-house',
    'gonzales-ancestral-house',
    'tiongco-ancestral-house',
    'perlas-ancestral-house',
    'toyota-santa-rosa',
    'coca-cola-santa-rosa',
    'monde-nissin-santa-rosa',
    'mitsubishi-motors-santa-rosa',
    'enchanted-kingdom',
    'nuvali',
    'lakeside-activities-nuvali',
    'fun-farm-sta-elena',
    'city-auditorium',
    'city-of-santa-rosa-multi-purpose-complex',
    'sm-city-santa-rosa',
    'robinson-s-santa-rosa',
    'target-mall',
    'waltermart-santa-rosa',
    'waltermart-bel-air',
    'vista-mall-santa-rosa',
    'paseo-de-santa-rosa',
    'laguna-central',
    'solenad-1-2-and-3')
ORDER BY category, name;
