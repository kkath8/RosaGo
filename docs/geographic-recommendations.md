# Location-aware recommendation selection

RosaGo considers available destination locations to recommend places that can be
visited more practically together.

Category eligibility is unchanged. Automatic selection still covers each available
interest once per round, and Local → unclassified → Common priority precedes
geography. The anchor is the first eligible candidate in the highest available
tourism tier, with canonical UUID as the stable tie-break.

Each next selection uses the least represented available categories and then the
best available tourism tier. Among those comparable candidates, it favors the
smallest mean Haversine distance to the located stops already selected. Using the
whole developing group reduces drift toward a succession of increasingly distant
stops. No business names are interpreted and no routing API is called.

Candidates with missing coordinate pairs retain their deterministic turns. Only
located candidates compete on distance, and only when the baseline candidate has
a location and at least two comparable located choices exist. With fewer than two
distinct locations in the eligible pool, the previous selection policy applies
exactly. This deliberately conservative policy can retain an unknown-location
candidate even when located alternatives exist.

After selection, nearest-next ordering starts at the first located selected stop.
Unknown-location stops retain their positions from deterministic ranking. The
recommendation page, automatic generation, checkbox preview creation, and AI
adjustment use these locations. Existing stored previews retain their stored order.
These are practical heuristics, not road travel estimates or route guarantees.

## Live catalog comparison

The read-only audit in `geographic-recommendation-live-audit.json` records the
published catalog, coordinates, Local/Common classifications, selected sequences,
and straight-line distances for both policies against the same data snapshot.
Run `tools/audit_geographic_recommendations.py` to repeat the comparison. It does
not write drafts or modify catalog data.

Original preferences were not supplied, so the audit uses Shopping + Dining with
seven stops as a comparable request, plus Shopping with three stops to verify
that geography changes the destination set itself.

| Destination from the supplied example | Latitude | Longitude |
| --- | ---: | ---: |
| Waltermart Santa Rosa | 14.288030 | 121.094370 |
| Laguna Central | 14.250240 | 121.064960 |
| Target Mall | 14.294430 | 121.103460 |
| Waltermart Bel-Air | 14.267560 | 121.077740 |
| Mama Lou's Italian Kitchen | NULL | NULL |
| Vista Mall Sta. Rosa | 14.243830 | 121.058120 |
| Yamazaki Kitchen Laguna | NULL | NULL |

Shopping, three stops:

- Before: Waltermart Santa Rosa → Laguna Central → Target Mall; 11.694 km.
- After: Waltermart Santa Rosa → Target Mall → Waltermart Bel-Air; 5.286 km.

This replaces a farther comparable shopping destination, rather than merely
reordering the old set. Both Waltermart branches remain legitimate selections.

Shopping + Dining, seven stops:

- Before: Waltermart Santa Rosa → Laguna Central → Target Mall → Waltermart
  Bel-Air → Mama Lou's → Yamazaki → Ipponyari.
- After: Waltermart Santa Rosa → Target Mall → Waltermart Bel-Air → Laguna
  Central → Mama Lou's → Yamazaki → Ipponyari.

The current category policy selects four Shopping and three Dining destinations;
it does not reproduce the supplied five-Shopping/two-Dining example exactly.
The set stays unchanged because category coverage and tourism tiers take priority.
The located subsequence measures 15.770 km before and 7.654 km after. Those values
exclude unknown-location stops and are not total itinerary travel distances.
The supplied example's first three legs measure 5.263, 6.431, and 4.075 km;
the remaining adjacent legs cannot be calculated with available coordinates.

No coordinates were changed or inferred. The catalog provides no independent
coordinate verification flag; the implementation uses only the existing numeric
catalog pairs accepted by the public catalog validation, never names or addresses.
