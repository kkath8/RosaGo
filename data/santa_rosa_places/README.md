# Santa Rosa Explore catalog

In Supabase, open the project configured by this app, open **SQL Editor**, paste
the complete contents of `publish.sql`, and click **Run**. Deploy the accompanying
application changes first. Do not rerun the original table migrations.

The script has been prepared locally; it has not been executed against Supabase.
Its final query should return all 28 requested places with `published` status.
Refresh Explore after running it. The ordinary published catalog now supplies
the cards, details, filters and Add to Trip actions; there is no separate directory.

The script runs in one transaction and can be rerun. Existing records with the
same slug retain their IDs, descriptions, addresses, coordinates, images and
creation dates; their names, categories and publication statuses are updated.
Synthetic `rosago-test-v1-` records are archived, preserving saved trip references.
Other existing places are left unchanged. No rows are deleted.

The 28 names and four groups come from the project owner's supplied list:
9 heritage, 4 industrial tourism, 6 entertainment/sports (`attraction`), and
9 shopping/dining (`shopping`). `places.json` is the accompanying review copy.
Industrial Tourism is supported throughout the catalog and itinerary UI. The
existing itinerary interest validator is extended if present, retaining its six
selection limit and privileges.

New records use the city-level address `Santa Rosa, Laguna, Philippines` and
general category descriptions. These are not verified street addresses, opening
hours, historical designations, admission details or promises of public access.
Confirm access to private homes and industrial facilities before visiting.

Exact map coordinates and images are intentionally NULL. The script removes
only the requirement for published records to have map coordinates; coordinate
pair/range checks, other validation, grants and RLS remain in place. The app
accepts a missing coordinate pair and omits those records from map pins while
keeping them available in Explore and trips. Populate both verified coordinates
later to make each destination appear on the map.
