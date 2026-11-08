-- OWNER-OPERATED READ-ONLY EXPORT ONLY.
-- Before running, confirm the Dashboard project reference is exactly
-- brnkigrrqdrywahvcbvc. The literal below records owner selection; it is not
-- independent database identity proof. Do not run in the evaluation project.
-- Use the SQL Editor's existing postgres role. Do not change any role grants.
-- Run the entire file once. It contains no writes and ends with ROLLBACK.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH destination_rows AS (
    SELECT id, slug, name, description, category, address, latitude, longitude,
           image_url, status, created_at, updated_at, tourism_type,
           tourism_category, tourism_opening_hours_raw,
           tourism_closing_hours_raw, tourism_hours_status, tourism_source,
           tourism_source_row, environment
    FROM public.places
), inventory AS (
    SELECT count(*) AS row_count,
           count(*) FILTER (WHERE status = 'published') AS published,
           count(*) FILTER (WHERE status = 'draft') AS draft,
           count(*) FILTER (WHERE status = 'archived') AS archived,
           count(*) FILTER (
               WHERE status IS NULL OR status NOT IN ('published', 'draft', 'archived')
           ) AS unexpected_status_count,
           coalesce(jsonb_agg(to_jsonb(destination_rows) ORDER BY id), '[]'::jsonb) AS rows
    FROM destination_rows
)
SELECT jsonb_pretty(jsonb_build_object(
    'export_format', 'rosago_owner_destination_inventory_v1',
    'owner_selected_project_ref', 'brnkigrrqdrywahvcbvc',
    'project_identity_requires_dashboard_confirmation', true,
    'table', 'public.places',
    'scope', 'all_publication_statuses',
    'exported_at', statement_timestamp(),
    'database_role', current_user,
    'transaction_read_only', current_setting('transaction_read_only'),
    'row_security_active_for_export_role', row_security_active('public.places'::regclass),
    'row_count', row_count,
    'status_counts', jsonb_build_object(
        'published', published, 'draft', draft, 'archived', archived
    ),
    'unexpected_status_count', unexpected_status_count,
    'rows', rows
)) AS destination_inventory_json
FROM inventory;

ROLLBACK;
