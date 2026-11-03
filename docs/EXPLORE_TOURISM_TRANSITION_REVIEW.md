# Tourism catalog transition review (Phase 3)

REVIEW ONLY: the SQL has not been executed. Migration 0011 was manually applied
and verified by the project owner before this phase; its file is unchanged.
Read-only public queries confirmed 28 published records and all seven Tourism
metadata fields NULL. No runtime flag, UI, weather or recommendation change is included.

## Artifacts and publication decision

- tourism_transition_plan.json: exact source values, reviewed identities, baseline
  public records, and untouched-record snapshots; UUIDs are fixed in this artifact.
- tourism_transition_review.sql: one-time transaction text only, outside migrations.
- tourism_catalog_transition.py: offline source reader, exact category mapping,
  hours classification, plan validation and SQL rendering. No SQL execution path.

The 12 reused records keep their published status, UUIDs, slugs, existing pins or
missing pins, images and creation timestamps. Phase 3A revises only the proposed
publication statuses: People's Park and Centennial Garden remain drafts because
their locations require confirmation; the six new restaurants are published.
All eight retain their fixed new UUIDs and null coordinate pairs. Missing pins
do not prevent the restaurants from appearing in Explore or destination details;
they remain unavailable for map markers/routing. Their starred hours remain
unverified. Publication does not verify operating hours.

The existing per-row `status` in the JSON plan is the explicit final status.
The generator carries it into the temporary SQL `final_status` column and checks
`p.status = r.final_status` for each POI, without inferring status from newness.

| New POI | Final status |
|---|---|
| City of Santa Rosa People's Park | draft |
| Centennial Garden | draft |
| Ipponyari Santa Rosa | published |
| Taste of Joy Sta. Rosa | published |
| Yamazaki Kitchen Laguna | published |
| Kanin Club | published |
| CIBO – Solenad | published |
| Mama Lou's Italian Kitchen | published |

The catalog involved would contain 36 records: the existing 28 published records
plus six published restaurants and two drafts (34 published, two drafts), not only
20. This count excludes any pre-existing records
hidden from the public read. All 16 unmatched published records remain unchanged
with unresolved/null Tourism Type. Retain them now; any later archive proposal
must separately review saved-trip references and publication visibility.

## Complete crosswalk

| Worksheet row | Tourism name | Type | Original category | Application category | Action | UUID | Final slug | Coordinates | Hours status |
|---|---|---|---|---|---|---|---|---|
| 2 | Enchanted Kingdom | Local | Theme Park / Recreation | attraction | UPDATE EXISTING | 7544a303-a669-41ad-9723-21b440c8e1ff | enchanted-kingdom | Preserve (14.281947, 121.095394) | unverified |
| 3 | Nuvali Park | Local | Nature / Outdoor Recreation | nature | UPDATE EXISTING | 4751680c-faab-4043-9d5b-d55053e54415 | nuvali | Preserve (14.239906, 121.059477) | unverified |
| 4 | Ayala Malls Solenad | Common | Shopping Mall / Dining | shopping | UPDATE EXISTING | 772aa257-089e-426b-9669-d4da7a6492c1 | solenad-1-2-and-3 | Preserve NULL pair | unverified |
| 5 | Paseo Outlets | Common | Outlet Shopping / Dining | shopping | UPDATE EXISTING | a984ad59-ed4d-43b8-89c1-33852877cfe0 | paseo-de-santa-rosa | Preserve NULL pair | unverified |
| 6 | SM City Santa Rosa | Common | Shopping Mall / Entertainment | shopping | UPDATE EXISTING | 277837ea-06bf-43ab-a509-c6d88cb44956 | sm-city-santa-rosa | Preserve (14.31334, 121.09778) | unverified |
| 7 | Vista Mall Sta. Rosa | Common | Shopping Mall / Lifestyle | shopping | UPDATE EXISTING | 1f04e93e-6227-42fb-be7f-e19970476efb | vista-mall-santa-rosa | Preserve (14.24383, 121.05812) | unverified |
| 8 | Robinsons Sta. Rosa | Common | Shopping Mall / Retail | shopping | UPDATE EXISTING | 428a525e-259d-4a89-90f4-1c231c6d6eae | robinson-s-santa-rosa | Preserve NULL pair | unverified |
| 9 | Museo ng Santa Rosa | Local | Museum / Cultural Heritage | heritage | UPDATE EXISTING | b2b0dab7-f8b1-4c1a-8828-bcff6fa5db40 | the-city-of-santa-rosa-museum | Preserve (14.31361, 121.11196) | unverified |
| 10 | Santa Rosa de Lima Parish Church | Local | Religious / Historical Landmark | heritage | UPDATE EXISTING | 2b258daf-2ede-4e12-8961-c36965d1f278 | santa-rosa-parish-church | Preserve (14.31403, 121.11135) | unverified |
| 11 | Santa Rosa Arch (Bantayang Bato) | Local | Historical Landmark | heritage | UPDATE EXISTING | 5591677c-107e-4960-b36a-fbd475965e4f | santa-rosa-arch | Preserve (14.315167, 121.111472) | verify_required |
| 12 | Cuartel de Santo Domingo | Local | Historical / Heritage Site | heritage | UPDATE EXISTING | 20fb152e-b13b-422a-a21f-4c24dc487a0e | cuartel-de-santo-domingo | Preserve (14.23081, 121.04986) | verify_required |
| 13 | City of Santa Rosa People's Park | Local | Public Park / Recreation | nature | INSERT NEW | 50f6fa0f-8e79-41c1-8f15-654bde693185 | city-of-santa-rosa-peoples-park | New NULL pair | unverified |
| 14 | The Fun Farm at Sta. Elena | Local | Farm / Family Recreation | attraction | UPDATE EXISTING | 184cb1aa-fa72-42ba-a94d-07e097f33d83 | fun-farm-sta-elena | Preserve (14.26701, 121.11078) | unverified |
| 15 | Centennial Garden | Local | Garden / Outdoor Recreation | nature | INSERT NEW | 90e42f09-5375-4935-aabe-28ca8f02d539 | centennial-garden | New NULL pair | unverified |
| 16 | Ipponyari Santa Rosa | Common | Japanese Restaurant | dining | INSERT NEW | 929c8840-9203-4ceb-929a-a47b80240305 | ipponyari-santa-rosa | New NULL pair | unverified |
| 17 | Taste of Joy Sta. Rosa | Common | Filipino Restaurant | dining | INSERT NEW | cc208fcc-bfff-4846-ad51-08915d0c3100 | taste-of-joy-sta-rosa | New NULL pair | unverified |
| 18 | Yamazaki Kitchen Laguna | Common | Japanese Restaurant | dining | INSERT NEW | 4a436763-acde-4968-94d9-c3453e1bfc44 | yamazaki-kitchen-laguna | New NULL pair | unverified |
| 19 | Kanin Club | Common | Filipino Restaurant | dining | INSERT NEW | defa76fd-3ab9-4043-9ca7-b1c86e696722 | kanin-club | New NULL pair | unverified |
| 20 | CIBO – Solenad | Common | Italian Restaurant | dining | INSERT NEW | 99cc7af3-6c4b-4b49-801d-3b901b04af3f | cibo-solenad | New NULL pair | unverified |
| 21 | Mama Lou's Italian Kitchen | Common | Italian Restaurant | dining | INSERT NEW | 128cfb4c-7fca-45e8-8ad7-5ba7ba11a100 | mama-lous-italian-kitchen | New NULL pair | unverified |

The prior ambiguous mappings are proposed exactly as requested: Nuvali Park
reuses Nuvali; Ayala Malls Solenad reuses Solenad 1, 2 and 3; Paseo Outlets
reuses Paseo de Santa Rosa. Lakeside Activities (Nuvali) is untouched.

## Untouched current destinations

- Arambulo Ancestral House (`639dc783-b54c-4deb-9ab5-7d7781030fe5`)
- City Auditorium (`2f344787-301d-426c-b5a1-83939848ce01`)
- City of Santa Rosa Multi-Purpose Complex (`1a850644-f471-4cef-ab13-4d434cfe834c`)
- Coca-Cola Santa Rosa (`22c498a5-2540-421b-b355-afbf5017c463`)
- Gonzales Ancestral House (`5e8083a4-e365-4ffa-8f65-504d081e62a6`)
- Laguna Central (`1205e2c0-1280-4503-9ce4-483a9be33a75`)
- Lakeside Activities (Nuvali) (`2880335f-88b4-4886-9553-bffd933801d0`)
- Mitsubishi Motors Santa Rosa (`fe47d1c8-2078-4615-8ee9-9fb07393b658`)
- Monde Nissin Santa Rosa (`8253f1f0-acc7-4a7a-aad5-a3fe4c4ccdd0`)
- Perlas Ancestral House (`bbb40cb4-1abe-4faf-8a60-04c24b24b160`)
- Target Mall (`7ae6a3e8-2768-440b-a7f8-f97620cfbe22`)
- Tiongco Ancestral House (`d03ad79f-743e-442a-a73a-26d3fded879d`)
- Toyota Santa Rosa (`c4927777-5067-40bc-92af-0cc143deac11`)
- Waltermart Bel-Air (`ea79b08e-3461-4540-b71f-fc7c2fed8fbb`)
- Waltermart Santa Rosa (`0a98d162-51ba-410f-b917-4b95720f105b`)
- Zavalla Ancestral House (`2ba8d0cb-5b67-4aeb-82b2-7fc702cd90ec`)

## Weather identity reconciliation, plan only

All twelve addresses change from `Santa Rosa, Laguna, Philippines` to the exact
Tourism address in the SQL/JSON. Ten names change; Nuvali alone changes application
category, from attraction to nature. Slugs remain unchanged. Current sidecar
lookup requires exact slug/name/category/address equality, so all twelve entries
would fall back to unknown until separately reconciled.

| Slug | Binding fields changed | Existing exposure |
|---|---|---|
| enchanted-kingdom | address | mixed |
| nuvali | name, category, address | unknown |
| solenad-1-2-and-3 | name, address | unknown |
| paseo-de-santa-rosa | name, address | unknown |
| sm-city-santa-rosa | address | indoor |
| vista-mall-santa-rosa | name, address | unknown |
| robinson-s-santa-rosa | name, address | indoor |
| the-city-of-santa-rosa-museum | name, address | unknown |
| santa-rosa-parish-church | name, address | unknown |
| santa-rosa-arch | name, address | unknown |
| cuartel-de-santo-domingo | name, address | unknown |
| fun-farm-sta-elena | name, address | unknown |

Enchanted Kingdom (mixed), SM City Santa Rosa (indoor) and Robinson?s Santa Rosa
(indoor) have curated non-unknown classifications, verified_on 2026-10-26.
For each, first confirm the retained identity/site scope. Then prepare a separate
review of sidecar name/address/category bindings, keeping applicable exposure,
source URL, source note and verification date; reverify when scope/evidence no
longer fits. Do not silently promote workbook descriptions to verified exposure.
For the nine unknown entries, reconcile identity fields only after approved
transition; keep exposure unknown and provenance null. New POIs default to
unknown. All sixteen unmatched sidecar entries stay unchanged. Regenerate
affected previews/weather proposals rather than bypassing fingerprint checks.

## SQL guards and application limits

The script locks places against concurrent writes, snapshots it in temporary
tables, validates the twelve expected UUID/name/slug/category/published identities
and null metadata, and rejects new UUID/slug collisions. It does not use an
upsert, so a repeat application or drift fails for re-review. The twelve UPDATE
statements each target one literal UUID. Eight INSERT statements use literal new
UUIDs. Postconditions check all twenty final records, eight added rows, preserved
identity/location fields, new null pins, and complete equality of untouched rows.
All assertions raise an exception within the transaction on failure. Temporary
tables disappear on commit; no persistent schema object or policy is created.

The guards are simple PL/pgSQL DO blocks, not deployed application functions.
This SQL was not executed even in tests: tests inspect/tokenize it and compare
it to the source and renderer. PostgreSQL parser/execution validation remains an
operator review step. Use the intended project and a separately authorized trusted
operator. The table lock can block writes. Inspect triggers/policies/schema before
future execution; this phase only verified public read visibility of 0011 columns.

Source rows are actual worksheet rows 2?21, not the No. values. All seven source
fields retain exact text. There are 36 starred hour cells; two POIs have Verify
in both cells. Status is unverified for 18 and verify_required for two. No verified
state exists. Centennial Garden retains exact location to verify; Yamazaki retains
12:00 AM*. These hours are not scheduling guarantees. Stable provenance is
`City Tourism Office | RosaGO_Santa_Rosa_POIs.xlsx | Santa Rosa POIs`.

No Local/Common priority is active. Mapping is an offline helper only. Applying
the proposed data later would change Nuvali category eligibility, as explicitly
requested, without changing the ranking algorithm. A subsequent ranking phase
must preserve category eligibility first, Local before Common second, with Common
and unresolved/null Type still eligible; Gemini must not classify Type.

Before publication of the two park drafts, resolve their location questions.
Keep restaurant hours unverified and coordinate weather reconciliation with
preview/proposal invalidation. Enable
the existing Tourism reader only through the separately reviewed deployment
setting after schema visibility is confirmed. No environment setting was changed.
