-- DEVELOPMENT ONLY / NEVER PRODUCTION. Data script, NOT a migration.
-- Production means real production users/data, not the Supabase branch label.
-- A main/PRODUCTION label grants no authorization. Verify and designate the
-- entire project as RosaGO capstone development/testing only; see README.md.
-- Prepared offline; NOT executed. Verify the development project manually.
-- In an editor copy only, replace the empty acknowledgement below.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $rosago$
DECLARE
    operator_acknowledgement constant text := '';
    expected constant jsonb := $manifest$
[
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000001",
    "name": "RosaGO Test Attraction 01",
    "slug": "rosago-test-v1-attraction-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "attraction",
    "address": "Synthetic map point 01 - UI testing only; not a real visitor address.",
    "latitude": 14.278,
    "longitude": 121.087,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000002",
    "name": "RosaGO Test Attraction 02",
    "slug": "rosago-test-v1-attraction-02",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "attraction",
    "address": "Synthetic map point 02 - UI testing only; not a real visitor address.",
    "latitude": 14.278,
    "longitude": 121.089,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000003",
    "name": "RosaGO Test Dining Spot 01",
    "slug": "rosago-test-v1-dining-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "dining",
    "address": "Synthetic map point 03 - UI testing only; not a real visitor address.",
    "latitude": 14.278,
    "longitude": 121.091,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000004",
    "name": "RosaGO Test Dining Spot 02",
    "slug": "rosago-test-v1-dining-02",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "dining",
    "address": "Synthetic map point 04 - UI testing only; not a real visitor address.",
    "latitude": 14.278,
    "longitude": 121.093,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000005",
    "name": "RosaGO Test Shopping Spot 01",
    "slug": "rosago-test-v1-shopping-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "shopping",
    "address": "Synthetic map point 05 - UI testing only; not a real visitor address.",
    "latitude": 14.28,
    "longitude": 121.087,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000006",
    "name": "RosaGO Test Accommodation 01",
    "slug": "rosago-test-v1-accommodation-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "accommodation",
    "address": "Synthetic map point 06 - UI testing only; not a real visitor address.",
    "latitude": 14.28,
    "longitude": 121.089,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000007",
    "name": "RosaGO Test Nature Spot 01",
    "slug": "rosago-test-v1-nature-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "nature",
    "address": "Synthetic map point 07 - UI testing only; not a real visitor address.",
    "latitude": 14.28,
    "longitude": 121.091,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000008",
    "name": "RosaGO Test Nature Spot 02",
    "slug": "rosago-test-v1-nature-02",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "nature",
    "address": "Synthetic map point 08 - UI testing only; not a real visitor address.",
    "latitude": 14.28,
    "longitude": 121.093,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000009",
    "name": "RosaGO Test Heritage Site 01",
    "slug": "rosago-test-v1-heritage-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "heritage",
    "address": "Synthetic map point 09 - UI testing only; not a real visitor address.",
    "latitude": 14.282,
    "longitude": 121.087,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000010",
    "name": "RosaGO Test Heritage Site 02",
    "slug": "rosago-test-v1-heritage-02",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "heritage",
    "address": "Synthetic map point 10 - UI testing only; not a real visitor address.",
    "latitude": 14.282,
    "longitude": 121.089,
    "image_url": null,
    "status": "published"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000011",
    "name": "RosaGO Test Draft Attraction 01",
    "slug": "rosago-test-v1-draft-attraction-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "attraction",
    "address": "Synthetic map point 11 - UI testing only; not a real visitor address.",
    "latitude": 14.282,
    "longitude": 121.091,
    "image_url": null,
    "status": "draft"
  },
  {
    "id": "9f56c6a0-5c4d-4e82-9b31-000000000012",
    "name": "RosaGO Test Archived Heritage Site 01",
    "slug": "rosago-test-v1-archived-heritage-01",
    "description": "DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. Not verified or endorsed by the Santa Rosa City Tourism Office. This fictional entry supports catalog cards, category filtering, and detail-page testing.",
    "category": "heritage",
    "address": "Synthetic map point 12 - UI testing only; not a real visitor address.",
    "latitude": 14.282,
    "longitude": 121.093,
    "image_url": null,
    "status": "archived"
  }
]
$manifest$::jsonb;
BEGIN
    IF operator_acknowledgement IS DISTINCT FROM 'I verified the connected Supabase project. I designated this entire project for RosaGO capstone development/testing only; it is not serving real production users/data. I understand these are synthetic test records and the Supabase main/PRODUCTION branch label does not make this safe automatically. I intentionally authorize this development-only operation.' THEN
    RAISE EXCEPTION 'Development project acknowledgement required.';
    END IF;
    -- This acknowledgement is not proof of the connected project.
    -- Fail rather than read a stale snapshot after waiting for the table lock.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED isolation required.';
    END IF;
    -- Serialize place writes while checking identities and applying this dataset.
    LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;
    -- Strict identity/content check: even changed test rows need manual review.
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(expected) AS manifest(item)
        JOIN public.places AS place ON place.id = (manifest.item->>'id')::uuid
        WHERE (to_jsonb(place) - 'created_at' - 'updated_at')
              IS DISTINCT FROM manifest.item
    ) THEN
        RAISE EXCEPTION 'Test UUID has unexpected identity or content; cleanup refused.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.trip_places AS membership
        JOIN jsonb_array_elements(expected) AS manifest(item)
          ON membership.place_id = (manifest.item->>'id')::uuid
    ) THEN
        RAISE EXCEPTION 'Test places are referenced by trips; cleanup refused.';
    END IF;

    -- The existing restrictive FK remains the final concurrent-reference guard.
    -- Never delete trips or memberships here.
    DELETE FROM public.places AS place
    USING jsonb_array_elements(expected) AS manifest(item)
    WHERE place.id = (manifest.item->>'id')::uuid;
END;
$rosago$;
COMMIT;
