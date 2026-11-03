-- REVIEW ONLY. NOT EXECUTED. Not a migration; never run on startup.
-- Requires applied 0011. New POI publication follows each explicit plan status.
-- One-time transition: guards reject identity drift, collisions and replay.
BEGIN;
SET LOCAL standard_conforming_strings = on;
LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE tourism_before ON COMMIT DROP AS SELECT * FROM public.places;
CREATE TEMP TABLE tourism_review (
    id uuid PRIMARY KEY, slug text UNIQUE NOT NULL, expected_name text, expected_category text,
    name text NOT NULL, category text NOT NULL, description text NOT NULL, address text NOT NULL,
    tourism_type text NOT NULL, tourism_category text NOT NULL,
    tourism_opening_hours_raw text, tourism_closing_hours_raw text, tourism_hours_status text NOT NULL,
    tourism_source text NOT NULL DEFAULT 'City Tourism Office | RosaGO_Santa_Rosa_POIs.xlsx | Santa Rosa POIs',
    tourism_source_row integer UNIQUE NOT NULL, final_status text NOT NULL CHECK (final_status IN ('draft', 'published'))
) ON COMMIT DROP;
INSERT INTO tourism_review (id, slug, expected_name, expected_category, name, category, description, address,
    tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source_row, final_status) VALUES
    ('7544a303-a669-41ad-9723-21b440c8e1ff', 'enchanted-kingdom', 'Enchanted Kingdom', 'attraction', 'Enchanted Kingdom', 'attraction', 'A theme park featuring thrill rides, family attractions, themed areas, and entertainment for visitors of different ages.', 'San Lorenzo South, RSBS Boulevard, Santa Rosa, Laguna 4026', 'Local', 'Theme Park / Recreation', '11:00 AM*', '8:00 PM*', 'unverified', 2, 'published'),
    ('4751680c-faab-4043-9d5b-d55053e54415', 'nuvali', 'Nuvali', 'attraction', 'Nuvali Park', 'nature', 'A lakeside destination with green spaces and outdoor areas for walking, relaxation, photography, and leisure activities.', 'Nuvali Boulevard, Brgy. Don Jose, Santa Rosa, Laguna 4026', 'Local', 'Nature / Outdoor Recreation', '6:00 AM*', '8:00 PM*', 'unverified', 3, 'published'),
    ('772aa257-089e-426b-9669-d4da7a6492c1', 'solenad-1-2-and-3', 'Solenad 1, 2 and 3', 'shopping', 'Ayala Malls Solenad', 'shopping', 'An open-air lifestyle mall offering retail shops, restaurants, cafés, and leisure areas for shopping and dining.', 'Santa Rosa–Tagaytay Road, Brgy. Don Jose, Santa Rosa, Laguna', 'Common', 'Shopping Mall / Dining', '11:00 AM*', '9:00 PM*', 'unverified', 4, 'published'),
    ('a984ad59-ed4d-43b8-89c1-33852877cfe0', 'paseo-de-santa-rosa', 'Paseo de Santa Rosa', 'shopping', 'Paseo Outlets', 'shopping', 'An open-air shopping destination featuring outlet stores, restaurants, and spaces for casual walks and leisure activities.', 'Greenfield City, Santa Rosa–Tagaytay Road, Brgy. Don Jose, Santa Rosa, Laguna', 'Common', 'Outlet Shopping / Dining', '11:00 AM*', '8:00 PM*', 'unverified', 5, 'published'),
    ('277837ea-06bf-43ab-a509-c6d88cb44956', 'sm-city-santa-rosa', 'SM City Santa Rosa', 'shopping', 'SM City Santa Rosa', 'shopping', 'A shopping mall with retail shops, grocery stores, restaurants, services, and entertainment facilities.', 'Old National Highway, Brgy. Tagapo, Santa Rosa, Laguna', 'Common', 'Shopping Mall / Entertainment', '10:00 AM*', '9:00 PM*', 'unverified', 6, 'published'),
    ('1f04e93e-6227-42fb-be7f-e19970476efb', 'vista-mall-santa-rosa', 'Vista Mall Santa Rosa', 'shopping', 'Vista Mall Sta. Rosa', 'shopping', 'A lifestyle mall with retail shops, dining options, and services for shopping and leisure.', 'Santa Rosa–Tagaytay Road, Brgy. Don Jose, Santa Rosa, Laguna', 'Common', 'Shopping Mall / Lifestyle', '10:00 AM*', '9:00 PM*', 'unverified', 7, 'published'),
    ('428a525e-259d-4a89-90f4-1c231c6d6eae', 'robinson-s-santa-rosa', 'Robinson’s Santa Rosa', 'shopping', 'Robinsons Sta. Rosa', 'shopping', 'A shopping center offering retail outlets, groceries, dining establishments, and everyday services.', 'Manila South Road, Brgy. Tagapo, Santa Rosa, Laguna', 'Common', 'Shopping Mall / Retail', '10:00 AM*', '8:00 PM*', 'unverified', 8, 'published'),
    ('b2b0dab7-f8b1-4c1a-8828-bcff6fa5db40', 'the-city-of-santa-rosa-museum', 'The City of Santa Rosa Museum', 'heritage', 'Museo ng Santa Rosa', 'heritage', 'A local museum that preserves historical artifacts and cultural materials related to Santa Rosa''s history and heritage.', 'F. Gomez Street, Santa Rosa City proper, Laguna', 'Local', 'Museum / Cultural Heritage', '9:00 AM*', '5:00 PM*', 'unverified', 9, 'published'),
    ('2b258daf-2ede-4e12-8961-c36965d1f278', 'santa-rosa-parish-church', 'Santa Rosa Parish Church', 'heritage', 'Santa Rosa de Lima Parish Church', 'heritage', 'A Catholic parish church that serves as a place of worship and a destination for visitors interested in religious heritage and architecture.', '60 F. Gomez Street, Brgy. Kanluran, Santa Rosa, Laguna 4026', 'Local', 'Religious / Historical Landmark', '8:30 AM*', '5:30 PM*', 'unverified', 10, 'published'),
    ('5591677c-107e-4960-b36a-fbd475965e4f', 'santa-rosa-arch', 'Santa Rosa Arch', 'heritage', 'Santa Rosa Arch (Bantayang Bato)', 'heritage', 'A recognizable city landmark associated with Santa Rosa''s identity, suitable for sightseeing and photography.', 'Manila South Road corridor, Santa Rosa, Laguna', 'Local', 'Historical Landmark', 'Verify', 'Verify', 'verify_required', 11, 'published'),
    ('20fb152e-b13b-422a-a21f-4c24dc487a0e', 'cuartel-de-santo-domingo', 'Cuartel De Santo Domingo', 'heritage', 'Cuartel de Santo Domingo', 'heritage', 'A Spanish-era military fortress and barracks dating to the nineteenth century, representing part of the area''s historical heritage.', 'Brgy. Santo Domingo, Santa Rosa, Laguna', 'Local', 'Historical / Heritage Site', 'Verify', 'Verify', 'verify_required', 12, 'published'),
    ('50f6fa0f-8e79-41c1-8f15-654bde693185', 'city-of-santa-rosa-peoples-park', NULL, NULL, 'City of Santa Rosa People''s Park', 'nature', 'A public recreational space with open areas for walking, relaxation, community gatherings, and outdoor leisure.', 'Rizal Boulevard area, Santa Rosa, Laguna 4026', 'Local', 'Public Park / Recreation', '6:00 AM*', '6:00 PM*', 'unverified', 13, 'draft'),
    ('184cb1aa-fa72-42ba-a94d-07e097f33d83', 'fun-farm-sta-elena', 'Fun Farm Sta. Elena', 'attraction', 'The Fun Farm at Sta. Elena', 'attraction', 'A family-oriented outdoor attraction offering recreational activities and nature-based experiences for children and families.', 'Sta. Elena Golf and Country Estate area, Santa Rosa, Laguna', 'Local', 'Farm / Family Recreation', '9:00 AM*', '4:00 PM*', 'unverified', 14, 'published'),
    ('90e42f09-5375-4935-aabe-28ca8f02d539', 'centennial-garden', NULL, NULL, 'Centennial Garden', 'nature', 'A landscaped outdoor area suitable for walking, enjoying greenery, taking photographs, and relaxing.', 'National Highway area, Santa Rosa, Laguna; exact location to verify', 'Local', 'Garden / Outdoor Recreation', '8:00 AM*', '6:00 PM*', 'unverified', 15, 'draft'),
    ('929c8840-9203-4ceb-929a-a47b80240305', 'ipponyari-santa-rosa', NULL, NULL, 'Ipponyari Santa Rosa', 'dining', 'A casual Japanese restaurant serving Japanese-style dishes in a relaxed setting, suitable for lunch or dinner.', '2nd Floor, PIAZZA Building, Santa Rosa–Tagaytay Road, Santa Rosa, Laguna', 'Common', 'Japanese Restaurant', '11:00 AM*', '10:30 PM*', 'unverified', 16, 'published'),
    ('cc208fcc-bfff-4846-ad51-08915d0c3100', 'taste-of-joy-sta-rosa', NULL, NULL, 'Taste of Joy Sta. Rosa', 'dining', 'A casual Filipino restaurant serving familiar local dishes and shareable meals for individuals, families, and groups.', 'EMS Building, National Highway, Brgy. Balibago, Santa Rosa, Laguna', 'Common', 'Filipino Restaurant', '9:00 AM*', '9:00 PM*', 'unverified', 17, 'published'),
    ('4a436763-acde-4968-94d9-c3453e1bfc44', 'yamazaki-kitchen-laguna', NULL, NULL, 'Yamazaki Kitchen Laguna', 'dining', 'A casual dining establishment offering Japanese-style comfort food in a relaxed atmosphere.', 'Zavalla Street, Brgy. Malusak, Santa Rosa, Laguna 4026', 'Common', 'Japanese Restaurant', '5:00 PM*', '12:00 AM*', 'unverified', 18, 'published'),
    ('defa76fd-3ab9-4043-9ca7-b1c86e696722', 'kanin-club', NULL, NULL, 'Kanin Club', 'dining', 'A Filipino casual dining restaurant serving traditional comfort food, rice dishes, and meals suitable for sharing.', 'Paseo Malls 2, Greenfield City, Brgy. Don Jose, Santa Rosa, Laguna', 'Common', 'Filipino Restaurant', '10:00 AM*', '10:00 PM*', 'unverified', 19, 'published'),
    ('99cc7af3-6c4b-4b49-801d-3b901b04af3f', 'cibo-solenad', NULL, NULL, 'CIBO – Solenad', 'dining', 'An Italian restaurant serving pasta, risotto, and other Italian-inspired dishes in a contemporary dining environment.', 'Ground Floor, Solenad 3, Building B, Santa Rosa–Tagaytay Road, Santa Rosa, Laguna 4026', 'Common', 'Italian Restaurant', '11:00 AM*', '9:00 PM*', 'unverified', 20, 'published'),
    ('128cfb4c-7fca-45e8-8ad7-5ba7ba11a100', 'mama-lous-italian-kitchen', NULL, NULL, 'Mama Lou''s Italian Kitchen', 'dining', 'An Italian-style restaurant serving pizza, pasta, and other Italian-inspired comfort food for casual dining and group meals.', 'Ground Floor, SM City Santa Rosa Expansion Wing, Old National Highway, Brgy. Tagapo, Santa Rosa, Laguna 4026', 'Common', 'Italian Restaurant', '10:00 AM*', '10:00 PM*', 'unverified', 21, 'published');
DO $guard$
BEGIN
    IF (SELECT count(*) FROM tourism_review) <> 20 THEN RAISE EXCEPTION 'Expected 20 Tourism rows'; END IF;
    IF (SELECT count(*) FROM tourism_review r JOIN public.places p ON p.id = r.id
        WHERE r.expected_name IS NOT NULL AND (p.name, p.slug, p.category, p.status)
        IS NOT DISTINCT FROM (r.expected_name, r.slug, r.expected_category, 'published'::text)
        AND p.tourism_type IS NULL AND p.tourism_category IS NULL
        AND p.tourism_opening_hours_raw IS NULL AND p.tourism_closing_hours_raw IS NULL
        AND p.tourism_hours_status IS NULL AND p.tourism_source IS NULL AND p.tourism_source_row IS NULL) <> 12 THEN
        RAISE EXCEPTION 'Existing identity/metadata drift: re-review before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM tourism_review r JOIN public.places p ON p.id = r.id OR p.slug = r.slug
        WHERE r.expected_name IS NULL) THEN
        RAISE EXCEPTION 'New UUID or slug already exists: re-review before applying';
    END IF;
END;
$guard$;
-- Worksheet row 2: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 2)
WHERE id = '7544a303-a669-41ad-9723-21b440c8e1ff'::uuid;
-- Worksheet row 3: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 3)
WHERE id = '4751680c-faab-4043-9d5b-d55053e54415'::uuid;
-- Worksheet row 4: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 4)
WHERE id = '772aa257-089e-426b-9669-d4da7a6492c1'::uuid;
-- Worksheet row 5: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 5)
WHERE id = 'a984ad59-ed4d-43b8-89c1-33852877cfe0'::uuid;
-- Worksheet row 6: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 6)
WHERE id = '277837ea-06bf-43ab-a509-c6d88cb44956'::uuid;
-- Worksheet row 7: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 7)
WHERE id = '1f04e93e-6227-42fb-be7f-e19970476efb'::uuid;
-- Worksheet row 8: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 8)
WHERE id = '428a525e-259d-4a89-90f4-1c231c6d6eae'::uuid;
-- Worksheet row 9: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 9)
WHERE id = 'b2b0dab7-f8b1-4c1a-8828-bcff6fa5db40'::uuid;
-- Worksheet row 10: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 10)
WHERE id = '2b258daf-2ede-4e12-8961-c36965d1f278'::uuid;
-- Worksheet row 11: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 11)
WHERE id = '5591677c-107e-4960-b36a-fbd475965e4f'::uuid;
-- Worksheet row 12: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 12)
WHERE id = '20fb152e-b13b-422a-a21f-4c24dc487a0e'::uuid;
-- Worksheet row 13: new identity, no pin, explicit status draft.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT '50f6fa0f-8e79-41c1-8f15-654bde693185'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'draft'
FROM tourism_review WHERE tourism_source_row = 13;
-- Worksheet row 14: preserve UUID, slug, coordinates, image and status.
UPDATE public.places SET
    (name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row) =
    (SELECT name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row FROM tourism_review WHERE tourism_source_row = 14)
WHERE id = '184cb1aa-fa72-42ba-a94d-07e097f33d83'::uuid;
-- Worksheet row 15: new identity, no pin, explicit status draft.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT '90e42f09-5375-4935-aabe-28ca8f02d539'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'draft'
FROM tourism_review WHERE tourism_source_row = 15;
-- Worksheet row 16: new identity, no pin, explicit status published.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT '929c8840-9203-4ceb-929a-a47b80240305'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'published'
FROM tourism_review WHERE tourism_source_row = 16;
-- Worksheet row 17: new identity, no pin, explicit status published.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT 'cc208fcc-bfff-4846-ad51-08915d0c3100'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'published'
FROM tourism_review WHERE tourism_source_row = 17;
-- Worksheet row 18: new identity, no pin, explicit status published.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT '4a436763-acde-4968-94d9-c3453e1bfc44'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'published'
FROM tourism_review WHERE tourism_source_row = 18;
-- Worksheet row 19: new identity, no pin, explicit status published.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT 'defa76fd-3ab9-4043-9ca7-b1c86e696722'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'published'
FROM tourism_review WHERE tourism_source_row = 19;
-- Worksheet row 20: new identity, no pin, explicit status published.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT '99cc7af3-6c4b-4b49-801d-3b901b04af3f'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'published'
FROM tourism_review WHERE tourism_source_row = 20;
-- Worksheet row 21: new identity, no pin, explicit status published.
INSERT INTO public.places (id, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, latitude, longitude, image_url, status)
SELECT '128cfb4c-7fca-45e8-8ad7-5ba7ba11a100'::uuid, slug, name, category, description, address, tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source, tourism_source_row, NULL, NULL, NULL, 'published'
FROM tourism_review WHERE tourism_source_row = 21;
DO $verify$
BEGIN
    IF (SELECT count(*) FROM public.places) <> (SELECT count(*) + 8 FROM tourism_before) THEN
        RAISE EXCEPTION 'Expected exactly eight new records'; END IF;
    IF (SELECT count(*) FROM tourism_review r JOIN public.places p ON p.id = r.id
        WHERE (p.name, p.category, p.description, p.address, p.tourism_type, p.tourism_category, p.tourism_opening_hours_raw, p.tourism_closing_hours_raw, p.tourism_hours_status, p.tourism_source, p.tourism_source_row) IS NOT DISTINCT FROM (r.name, r.category, r.description, r.address, r.tourism_type, r.tourism_category, r.tourism_opening_hours_raw, r.tourism_closing_hours_raw, r.tourism_hours_status, r.tourism_source, r.tourism_source_row)
        AND p.slug = r.slug
        AND p.status = r.final_status) <> 20 THEN
        RAISE EXCEPTION 'Transition field verification failed'; END IF;
    IF EXISTS (SELECT 1 FROM tourism_before b JOIN public.places p ON p.id = b.id
        JOIN tourism_review r ON r.id = b.id
        WHERE (p.slug, p.latitude, p.longitude, p.image_url, p.status, p.created_at)
        IS DISTINCT FROM (b.slug, b.latitude, b.longitude, b.image_url, b.status, b.created_at)) THEN
        RAISE EXCEPTION 'Existing identity/location preservation failed'; END IF;
    IF EXISTS (SELECT 1 FROM tourism_before b LEFT JOIN public.places p ON p.id = b.id
        WHERE NOT EXISTS (SELECT 1 FROM tourism_review r WHERE r.id = b.id)
        AND to_jsonb(p) IS DISTINCT FROM to_jsonb(b)) THEN
        RAISE EXCEPTION 'Unmatched existing records changed'; END IF;
    IF EXISTS (SELECT 1 FROM tourism_review r JOIN public.places p ON p.id = r.id
        WHERE r.expected_name IS NULL AND (p.latitude IS NOT NULL OR p.longitude IS NOT NULL)) THEN
        RAISE EXCEPTION 'New coordinates must remain null'; END IF;
END;
$verify$;
COMMIT;
