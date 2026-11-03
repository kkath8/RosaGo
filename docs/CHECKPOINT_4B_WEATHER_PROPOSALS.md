# Checkpoint 4B: curated weather exposure and explicit proposals

## Review status

Weather proposal infrastructure is ready, but curated destination verification is
required before enabling replacement.

All **28 current destinations remain unknown**. No real venue received a claimed
verified classification, and no curated data update SQL was generated. Local
catalog descriptions are generic category text, not exposure evidence. A limited
primary-source review of [Nuvali's activity article](https://www.nuvali.ph/your-ultimate-checklist-for-a-merrier-holiday-season/)
describes estate activities but does not establish current, complete venue-wide
coverage for the catalog records. It was not used to classify a destination.
Names, categories, Gemini and general knowledge were not used as substitutes.

The user confirmed migration **0010 has already been manually applied**. Do not
rerun it or migrations 0001–0009, and do not rerun `publish.sql`. This checkpoint
creates **no migration** and changes no live database rows or historical SQL.

## Smallest metadata model without a schema change

The database Place contract and public/admin projections stay unchanged. Admin
destination management is currently read-only. The server reads the versioned
`data/santa_rosa_places/weather_metadata.json` curation sidecar, keyed by stable
catalog slug and bound to exact name, category and address. Metadata never creates
or publishes a Place: every proposal resolves against the real published catalog.
If the identity no longer matches, exposure falls back to unknown.

Exposure is `indoor`, `covered`, `mixed`, `outdoor` or `unknown`. An unknown row
has null provenance. Every non-unknown row requires an HTTPS factual source URL
(maximum 2048 characters, no embedded credentials), a concise source/evidence note
(maximum 500 characters), and an ISO verification date. Verification is a curated
human claim backed by its source, not something URL validation alone proves.

Use indoor only where evidence supports an enclosed primary visitor experience;
covered only where evidence supports roofed visitor areas without full enclosure;
mixed where meaningful visitor areas include both exposed and sheltered spaces;
outdoor where the documented visitor experience is exposed. A covered entrance or
an indoor shop within a large park does not establish the whole venue as covered
or indoor. Unknown remains the default whenever scope or evidence is insufficient.

The loader validates exact keys, enums, scalar types, provenance, identity bounds,
unique slugs, schema version, duplicate JSON keys, and a 64 KB file limit. Missing,
invalid or oversized metadata fails closed to unknown without hiding itineraries.
There is no browser input or Admin save operation for this file. It must be reviewed
and deployed as project data. The checked-in file explicitly covers all 28 catalog
records; other published destinations default to unknown. Public detail and Admin
detail show exposure and bounded provenance as escaped text.

Metadata is reread per request. Its complete content hash participates in proposal
approval, so source-note/provenance changes invalidate prior approvals as well.
This avoids changing the established database Preview fingerprint or requiring a
migration of existing stored contracts. If database-managed curation becomes
necessary later, design that migration separately; do not pretend a schema change
is already applied.

## Proposal algorithm

The Checkpoint 4 city forecast policy, request-driven checks, requested-start
cutoff, cache and Settings behavior are preserved. No concern means no proposal.
Any stronger/severe concern means review-only: this policy does not propose
alternatives for severe weather or promise that indoor venues are safe.

For ordinary rain, start from the latest validated stored Preview and its existing
day/stop order. Only selected stops on affected dates with verified outdoor or
mixed exposure can be replaced. Unknown stops remain without inferring exposure;
indoor/covered stops and unaffected dates remain unchanged.

Use the existing deterministic category-interest ranker on the complete bounded
published catalog. Eligible replacements have verified indoor/covered exposure,
belong to current interests and are not already selected. Prefer the same category,
then another current interest, with the ranker's canonical ID ordering as tie-break.
Reserve every current destination so retained stops cannot be duplicated. Fill
only original positions, retaining total count and unaffected stops. If no verified
alternative exists, retain the original and disclose that limitation. Never use
unknown/mixed metadata as a less-exposed alternative, expand interests, invent a
destination, or claim cost/opening-hour/route feasibility.

The UI keeps Current itinerary and Suggested adjustment separate, lists the
complete suggested order with retained/new labels, and shows each proposed removal
and replacement with its exposure and reason. The alert link says Review Suggested
Adjustment only when a real changed proposal exists; otherwise Review Itinerary
continues. Saved-trip Alerts remain review-only because those manual trip lists
are not linked to temporary Planner drafts or the draft adjustment lifecycle.

## Approval, concurrency and privacy

`POST /user/itinerary/<draft_id>/preview/weather` accepts exactly CSRF token,
expected revision, proposal token and `decision` (`keep` or `accept`). Body is capped
at 4096 bytes. No destination IDs, structured constraints or proposed list are
accepted from the browser. The endpoint requires authentication, ownership,
preview_ready state, unexpired draft, same Origin, valid CSRF and expected revision.

A server-signed token expires after 600 seconds. It contains only a proposal
digest and an HMAC owner binding, not names, account identifiers, auth credentials,
destination lists or forecast payloads. Its digest covers draft identity/revision,
the current Preview digest, complete published-catalog fingerprint and slugs,
curation fingerprint, relevant concern codes/probabilities/dates/coverage, and the
ordered proposed IDs. It is not an authoritative browser-submitted plan.

Acceptance rereads current published destinations, rechecks the original catalog
fingerprint, reloads curation and weather, recomputes the deterministic proposal,
and compares the signed binding. Changed revision, metadata, provenance, catalog,
forecast, start cutoff or Settings can invalidate it. An unavailable forecast
cannot authorize a replacement. Rejected tokens can display a newly computed
proposal, which requires another explicit review/action.

Only explicit acceptance builds and writes the recomputed proposal through the
existing applied 0010 atomic adjustment RPC. Preferences remain identical. The
RPC independently checks owner/revision/expiry and selected published catalog
fingerprints under locks and increments revision once. There are no retries or
split preference/Preview writes. An ambiguous RPC timeout uses the existing
unconfirmed-write error, never an assertion of rollback. The route rereads the
committed draft and clears transient AI explanations. Explain with AI and
conversational adjustment remain available afterward.

Keep Current performs no itinerary write and hides the suggestion only for its
response. Refresh may offer it again. Stale acceptance after a conversational
revision change is rejected even if the browser edits expected_revision. Merely
loading Preview or Alerts never writes. There are no proposal database rows,
background jobs or notifications beyond the existing in-app request-driven UI.
Gemini is never called to classify, propose or accept weather adjustments.

## Manual curation steps before enabling real suggestions

1. Review each destination's exact live slug, name, category and address. The
   original `places.json` may differ from preserved live address/name values;
   identity mismatches deliberately stay unknown.
2. Obtain current primary venue/LGU documentation or a documented direct venue
   confirmation that covers the actual visitor areas. Record the evidence URL,
   verification date and a short note explaining classification scope. Do not
   classify an entire complex from a photograph of one covered section.
3. Review and edit only the corresponding sidecar entries. Keep uncertain places
   unknown with null provenance. Do not rerun publish.sql or any migration.
4. Validate the document directly before deploying (so validation errors are
   visible rather than invoking the runtime's fail-closed fallback):

   ```powershell
   .\.venv\Scripts\python.exe -c "import json; from destination_weather_metadata import METADATA_PATH, validate_weather_catalog; c=validate_weather_catalog(json.loads(METADATA_PATH.read_text(encoding='utf-8'))); print('Valid records:', len(c.records))"
   ```

5. Meaningful ordinary-rain proposals need at least one verified outdoor/mixed
   selected stop on an affected date and an unselected verified indoor/covered
   published alternative within current interests. If that evidence does not
   exist, keep the review-only behavior; do not add guessed test classifications.
6. Deploy the reviewed data file consistently to serving processes. A changed
   file intentionally invalidates previous signed approvals. No SQL is necessary.

## Manual browser review

With the current all-unknown file, generate a rainy future Preview. Verify Review
Itinerary, honest unknown-exposure notices, and absence of acceptance controls.
Verify public/Admin detail show Unknown. This is the expected live result now.

After factual curation supplies the combination described above:

1. Generate a Preview before its requested start and within the three-day forecast
   range. An ordinary-rain concern should show Review Suggested Adjustment, current
   cards, proposed order, retained/new labels and replacement reasons. Merely
   refreshing must not change selection or revision.
2. Choose Keep Current. Verify unchanged destinations/revision and dismissal for
   that response. Refreshing may offer the proposal again.
3. Explain with AI, review a proposal, then choose Use Suggested Itinerary. Verify
   only the reviewed changes, one revision increment, unchanged preferences/count,
   cleared explanations and usable destination links. Request new explanations.
4. In Tab A review a proposal; in Tab B conversationally adjust. Accept in Tab A:
   expect rejection and preservation of Tab B's newer revision. Repeat after
   changing curation/provenance or publication: old approval must fail.
5. Test invalid CSRF, foreign Origin, another user's draft, expired draft/token,
   and added browser destination-ID fields. Each must fail without a mutation.
6. Verify severe weather, unknown metadata, no eligible alternative, weather
   failure and out-of-range dates remain review-only. No indoor safety guarantee,
   forecast fabrication or automatic replacement should appear.
7. After accepting, submit a normal conversational adjustment and Explain with AI.
   Repeat with JavaScript disabled. Verify session alert preferences still work.

Offline tests use explicitly synthetic metadata and mocked provider/database
transports. They do not classify the real catalog or prove live PostgreSQL locks.
