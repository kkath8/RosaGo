# Historical destination archive — reference only

These files are preserved byte-for-byte; `manifest.json` records their original
and archived paths and SHA-256 hashes:

- `places.json`: original 28-place publication review copy.
- `publish.sql`: historical publication/upsert and schema-adjustment script.
- `tourism_transition_plan.json`: historical Tourism transition proposal and baseline.
- `tourism_transition_review.sql`: one-time guarded transition SQL.
- `README.original.md`: original instructions, retained as historical evidence.

The old instructions do not authorize executing SQL now. This archive is not an
active data source, a current backup or an import/synchronization directory.
Nothing here should run automatically. No rows or SQL files were deleted.

Offline tests still inspect these artifacts as text. Current weather metadata
stays at `../weather_metadata.json`; the runtime loader and build files are unchanged.
Future catalog work belongs in [local_catalog](../../../local_catalog/README.md).
