-- Read-only check of actual anon RLS, after separately approved cutover only.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL ROLE anon;
SELECT count(*) AS visible_published_count,
       bool_and(status='published' AND latitude IS NOT NULL AND longitude IS NOT NULL) AS all_visible_rows_published_and_mapped
FROM public.places;
ROLLBACK;
