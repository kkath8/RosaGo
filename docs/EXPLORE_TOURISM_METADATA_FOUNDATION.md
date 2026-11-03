# City Tourism metadata foundation (Phase 2)

Migration `0011_places_tourism_metadata.sql` is a local review draft, NOT applied.
No destination import, backfill, mapping, ranking, weather or coordinate changes
are included. The 20-row source is `RosaGO_Santa_Rosa_POIs.xlsx`, sheet
`Santa Rosa POIs`, supplied by the City Tourism Office. Its local path is not
permanent provenance.

## Existing schema contract and uncertainty

The repository defines `public.places` in 0002: UUID primary key with generated
default; required name, unique slug, description, application category, address,
status, created_at and updated_at; optional latitude, longitude and image_url.
Status is draft/published/archived. Timestamps default to now; the before-update
trigger maintains updated_at. The primary key and slug uniqueness create indexes.
0003 adds the trip_places place_id index and an ON DELETE RESTRICT foreign key to
places; itinerary stops reference trip memberships through a composite FK (0004).

0002 enables RLS, grants anon/authenticated table SELECT, and permits published
rows. 0009 adds authenticated Admin SELECT access through rosago_is_admin. No
destination write permission is added by this foundation. Provenance fields are
not rendered in public HTML, but the existing table SELECT grants mean they are
not confidential database columns. Store source identification only, never
credentials, private operator notes or local filesystem paths.

0002 checks coordinate pairs, finite ranges, and originally required coordinates
for publication. The separate catalog publish.sql drops that publication-only
requirement and adds industrial to the category check and interest validator.
The preceding read-only comparison observed 28 live published destinations,
including nine without coordinates and four with industrial category. Thus the
original 0002 definition alone cannot describe live constraints. Neither the
current exact constraint definitions, index/policy inventory, nor actual migration
application history is proven by repository files. No schema RPC or migration
runner is introduced here. Review the actual live schema before applying 0011;
do not execute publish.sql or replay earlier migrations to resolve uncertainty.

Migration sequence inspected: 0001 profiles; 0002 places; 0003 trips/memberships;
0004 itinerary foundation; 0005 draft lifecycle; 0006 extended preference
validation; 0007 preview lifecycle/fingerprints; 0008 Admin authorization;
0009 Admin catalog reads; 0010 preview adjustment. Local comments saying
unapplied are not authoritative evidence of the current remote deployment.

## Seven nullable fields

| Field | Meaning |
|---|---|
| tourism_type | Exactly Local or Common; NULL means unresolved, never default Common. |
| tourism_category | Original source label, up to 250 characters; application category stays separate. |
| tourism_opening_hours_raw | Exact source text, up to 250 characters. |
| tourism_closing_hours_raw | Exact source text, up to 250 characters. |
| tourism_hours_status | NULL/unresolved, unverified, verify_required or not_supplied. |
| tourism_source | Stable supplier/workbook/sheet label, up to 500 characters. |
| tourism_source_row | Actual one-based worksheet row, 2 through Excel's 1048576; not the No. cell. |

Future importer status rule: when either raw value says `Verify`, use
verify_required; when neither is supplied, use not_supplied; otherwise use
unverified. Starred and even unstarred supplied times are never verified by this
foundation. The parser validates stored status vocabulary; it does not infer,
rewrite or cross-populate source fields. NULL remains allowed for legacy data.
No import/status assignment has been implemented. Source text is never trimmed
or parsed as a guaranteed schedule. Asterisks, Verify, source spelling and any
unresolved address notes must survive a future reviewed import.

Example future source label:
`City Tourism Office | RosaGO_Santa_Rosa_POIs.xlsx | Santa Rosa POIs`.
All metadata columns have no defaults and permit NULL. Existing values, UUIDs,
foreign keys, coordinates, categories, timestamps, triggers, RLS and grants are
untouched. There is no backfill, new index or destination data statement. This
is a one-time migration: unexpected existing columns/constraints should fail
for review rather than be silently reused.

## Read rollout and presentation

The public service retains its original projection by default. After an operator
has separately reviewed/applied 0011 and confirmed PostgREST schema visibility,
`ROSAGO_TOURISM_METADATA_ENABLED=true` enables the extended SELECT projection on
application restart. This setting is NOT enabled or added to .env in this phase.
Enabling it before 0011 will cause catalog queries to fail, so deploy the code
with the default first. No error-driven schema fallback or automatic migration
occurs. Direct PlacesService callers can pass tourism_metadata_enabled=True.

The pure parser accepts old projections, missing/null Tourism fields, and null
coordinate pairs. Invalid non-null metadata uses the existing sanitized
PlacesConsistencyError convention. New Place fields have trailing defaults so
existing constructors remain compatible. Trip hydration retains its existing
projection; Tourism metadata is not required for membership reads.

Explore cards and filters remain unchanged. Details can show Type and original
Tourism category, plus escaped raw hours under an unconditional verification
notice whenever raw hours exist. No source label/row or internal status is shown.
All values remain untrusted text subject to Jinja autoescaping. Until separately
enabled and populated, the display stays the same for current destinations.

Recommendation ranking/automatic selection, policy versions, AI context,
operating-hour feasibility, preview fingerprints and weather metadata are
unchanged. No category mapping helper is introduced: the next phase must resolve
Public Park and destination identity/scope before applying source mappings.

## Review before application

Confirm target project/table ownership, live column/constraint/policy definitions,
and that the seven new names do not already exist. ALTER TABLE takes a strong
table lock and CHECK constraints may scan existing rows; schedule accordingly.
This draft was not executed against PostgreSQL, so static/offline tests do not
establish live DDL compatibility. Applying it adds NULL fields to existing rows
without changing existing values or firing the row UPDATE trigger. Enable the
reader only after a separate authorized migration and schema-cache check.
