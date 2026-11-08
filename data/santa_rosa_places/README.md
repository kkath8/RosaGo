# Santa Rosa runtime metadata and historical archive

`weather_metadata.json` remains the active, curated weather-exposure sidecar.
Its location and contents have not changed. `destination_weather_metadata.py`
and the evaluation Docker allowlist continue to use this exact path.

Historical catalog publication files now live in [archive/](archive/README.md).
They are preserved reference artifacts, not the live destination catalog or a
sync source. Do not execute their SQL or regenerate a live catalog from them.

Admin and User destinations remain in Supabase's `public.places` table in the
application's configured project. Admin changes do not rewrite local JSON files.

Use [local_catalog](../../local_catalog/README.md) for future offline catalog
review. It requires a separately authorized, current snapshot covering all
publication statuses. No hosted export or import has been performed.
