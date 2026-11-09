-- LOCAL PREPARATION ONLY. Target project: jfaufpfzfhysqkhcdsrs
-- LOCAL, UNAPPLIED. Additive metadata foundation only; apply once after review.
-- No import, backfill, category mapping, coordinate changes or policy changes.
BEGIN;

ALTER TABLE public.places
    ADD COLUMN tourism_type text,
    ADD COLUMN tourism_category text,
    ADD COLUMN tourism_opening_hours_raw text,
    ADD COLUMN tourism_closing_hours_raw text,
    ADD COLUMN tourism_hours_status text,
    ADD COLUMN tourism_source text,
    ADD COLUMN tourism_source_row integer,
    ADD CONSTRAINT places_tourism_type_check CHECK (
        tourism_type IS NULL OR tourism_type IN ('Local', 'Common')),
    ADD CONSTRAINT places_tourism_category_check CHECK (
        tourism_category IS NULL OR char_length(tourism_category) BETWEEN 1 AND 250),
    ADD CONSTRAINT places_tourism_opening_hours_raw_check CHECK (
        tourism_opening_hours_raw IS NULL OR char_length(tourism_opening_hours_raw) BETWEEN 1 AND 250),
    ADD CONSTRAINT places_tourism_closing_hours_raw_check CHECK (
        tourism_closing_hours_raw IS NULL OR char_length(tourism_closing_hours_raw) BETWEEN 1 AND 250),
    ADD CONSTRAINT places_tourism_hours_status_check CHECK (
        tourism_hours_status IS NULL OR tourism_hours_status IN (
            'unverified', 'verify_required', 'not_supplied')),
    ADD CONSTRAINT places_tourism_source_check CHECK (
        tourism_source IS NULL OR char_length(tourism_source) BETWEEN 1 AND 500),
    ADD CONSTRAINT places_tourism_source_row_check CHECK (
        tourism_source_row IS NULL OR tourism_source_row BETWEEN 2 AND 1048576);

COMMENT ON COLUMN public.places.tourism_type IS
    'City Tourism classification, exactly Local or Common; NULL means unresolved.';
COMMENT ON COLUMN public.places.tourism_category IS
    'Original Tourism category text; independent of the application category.';
COMMENT ON COLUMN public.places.tourism_opening_hours_raw IS
    'Unmodified source text, including asterisks and Verify; not a verified schedule.';
COMMENT ON COLUMN public.places.tourism_closing_hours_raw IS
    'Unmodified source text, including asterisks and Verify; not a verified schedule.';
COMMENT ON COLUMN public.places.tourism_hours_status IS
    'NULL: unresolved; not_supplied: neither hour supplied; verify_required: source says Verify; otherwise unverified. No verified state.';
COMMENT ON COLUMN public.places.tourism_source IS
    'Stable source label including supplier, workbook and sheet; never a local filesystem path.';
COMMENT ON COLUMN public.places.tourism_source_row IS
    'One-based worksheet row (header is row 1), not the workbook No. value.';

COMMIT;
