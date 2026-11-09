# Production catalog replacement — proposed change set

> Historical status projection: the current [mapped-only policy](MAPPED_PUBLICATION_POLICY.md) supersedes the 98-Published proposal below. No hosted statuses changed.

**Review only. No hosted changes. No executable import or migration. Remote deployment NO-GO.**

This supersedes the historical name-only comparison. The supplied owner export validates as a complete all-status destination inventory. Project identity is owner-attested through the Dashboard procedure, not independently established by a successful MCP connection.

Target: **brnkigrrqdrywahvcbvc**. Exported: `2026-11-08T01:33:39.649018+00:00`.

Export file SHA-256: `390435d62c88baa6786443c43d5544dd377bc9ca1ff96e1dd18d127976846d32`.

Canonical exported rows SHA-256: `3ef42fad775d8050629d30a4c6913d09345c3a1252942cc3c7ce48e03afe19b7`.

Source CSV SHA-256: `c55ed7076b59d611bc57eb0d59b0c6c425b301e4999655b01a17a9a8ca87ed2a`.

The source files are unchanged. The exact per-record before/after values, preserved originals, UUIDs, slugs, expected update timestamps and row hashes are in [production-catalog-change-set.review.json](production-catalog-change-set.review.json). This JSON is a review artifact, not an input to the evaluation-pinned init/plan tool.

## Inventory and proposed outcome

| Status | Exported now | Proposed final, after all corrections and approvals |
| --- | ---: | ---: |
| Published | 35 | 98 |
| Draft | 2 | 2 |
| Archived | 13 | 20 |

The 50 exported rows have all 20 expected fields, valid paired coordinates or NULLs, unique canonical UUIDs, unique slugs, unique normalized names, valid timestamps, and counts that agree with the complete row list. Transaction read-only is `on`, RLS is inactive for the export role, and unexpected status count is zero. No Auth or private session records were exported.

**28 proposed updates** (18 exact normalized names and 10 explicit alias proposals), **70 proposed additions**, **7 proposed archives**, and **15 unchanged rows**. All aliases remain subject to explicit owner identity approval. No record is ready for execution while the correction and implementation gates below remain open.

## Existing destinations to update

All retain their existing UUID, slug, creation timestamp and image URL. Update timestamps are concurrency preconditions; the database must advance them normally. These updates keep publication status unchanged. Blank CSV optional fields preserve existing values. Original complex hours remain raw, with `verify_required` status; the source does not establish verified hours.

| CSV record | CSV destination | Existing destination | Identity basis | Existing UUID |
| ---: | --- | --- | --- | --- |
| 1 | Enchanted Kingdom | Enchanted Kingdom | Exact normalized name | 7544a303-a669-41ad-9723-21b440c8e1ff |
| 2 | Nuvali Lakeside / Park | Nuvali Park | **Alias: approve identity** | 4751680c-faab-4043-9d5b-d55053e54415 |
| 3 | Ayala Malls Solenad (Ayala Malls Nuvali) | Ayala Malls Solenad | **Alias: approve identity** | 772aa257-089e-426b-9669-d4da7a6492c1 |
| 4 | Paseo Outlets | Paseo Outlets | Exact normalized name | a984ad59-ed4d-43b8-89c1-33852877cfe0 |
| 5 | SM City Santa Rosa | SM City Santa Rosa | Exact normalized name | 277837ea-06bf-43ab-a509-c6d88cb44956 |
| 6 | Robinsons Sta. Rosa | Robinsons Sta. Rosa | Exact normalized name | 428a525e-259d-4a89-90f4-1c231c6d6eae |
| 7 | Vista Mall Sta. Rosa | Vista Mall Sta. Rosa | Exact normalized name | 1f04e93e-6227-42fb-be7f-e19970476efb |
| 10 | WalterMart Santa Rosa | Waltermart Santa Rosa | Exact normalized name | 0a98d162-51ba-410f-b917-4b95720f105b |
| 12 | Fort Santo Domingo / Cuartel de Santo Domingo | Cuartel de Santo Domingo | **Alias: approve identity** | 20fb152e-b13b-422a-a21f-4c24dc487a0e |
| 13 | Santa Rosa de Lima Parish Church | Santa Rosa de Lima Parish Church | Exact normalized name | 2b258daf-2ede-4e12-8961-c36965d1f278 |
| 21 | Chowking Sta. Rosa Balibago | Chowking Sta. Rosa Balibago | Exact normalized name | 9c745f18-aebc-43f3-96da-fdd1a9dd787d |
| 26 | Ipponyari Santa Rosa | Ipponyari Santa Rosa | Exact normalized name | 929c8840-9203-4ceb-929a-a47b80240305 |
| 28 | Taste of Joy Sta. Rosa | Taste of Joy Sta. Rosa | Exact normalized name | cc208fcc-bfff-4846-ad51-08915d0c3100 |
| 42 | Santa Rosa Arch | Santa Rosa Arch (Bantayang Bato) | **Alias: approve identity** | 5591677c-107e-4960-b36a-fbd475965e4f |
| 43 | The City of Santa Rosa Museum (Museo de Santa Rosa) | Museo ng Santa Rosa | **Alias: approve identity** | b2b0dab7-f8b1-4c1a-8828-bcff6fa5db40 |
| 44 | Arambulo Ancestral House | Arambulo Ancestral House | Exact normalized name | 639dc783-b54c-4deb-9ab5-7d7781030fe5 |
| 45 | Zavalla Ancestral House | Zavalla Ancestral House | Exact normalized name | 2ba8d0cb-5b67-4aeb-82b2-7fc702cd90ec |
| 46 | Gonzales Ancestral House | Gonzales Ancestral House | Exact normalized name | 5e8083a4-e365-4ffa-8f65-504d081e62a6 |
| 47 | Toyota Santa Rosa (Toyota Motor Philippines) | Toyota Santa Rosa | **Alias: approve identity** | c4927777-5067-40bc-92af-0cc143deac11 |
| 48 | Coca-Cola Santa Rosa (Coca-Cola Beverages Philippines) | Coca-Cola Santa Rosa | **Alias: approve identity** | 22c498a5-2540-421b-b355-afbf5017c463 |
| 49 | Monde Nissin Santa Rosa Plant | Monde Nissin Santa Rosa | **Alias: approve identity** | 8253f1f0-acc7-4a7a-aad5-a3fe4c4ccdd0 |
| 50 | Mitsubishi Motors Philippines Corporation | Mitsubishi Motors Santa Rosa | **Alias: approve identity** | fe47d1c8-2078-4615-8ee9-9fb07393b658 |
| 51 | Fun Farm at Sta. Elena | The Fun Farm at Sta. Elena | **Alias: approve identity** | 184cb1aa-fa72-42ba-a94d-07e097f33d83 |
| 52 | Santa Rosa City Auditorium | Santa Rosa City Auditorium | Exact normalized name | 2f344787-301d-426c-b5a1-83939848ce01 |
| 53 | City of Santa Rosa Multi-Purpose Complex | City of Santa Rosa Multi-Purpose Complex | Exact normalized name | 1a850644-f471-4cef-ab13-4d434cfe834c |
| 54 | Laguna Central | Laguna Central | Exact normalized name | 1205e2c0-1280-4503-9ce4-483a9be33a75 |
| 55 | Yamazaki Kitchen Laguna | Yamazaki Kitchen Laguna | Exact normalized name | 4a436763-acde-4968-94d9-c3453e1bfc44 |
| 90 | Target Mall | Target Mall | Exact normalized name | 7ae6a3e8-2768-440b-a7f8-f97620cfbe22 |

## New destination candidates

These have no assigned UUID. Create as Draft only after approval and validation; publish separately through the guarded Admin flow. Proposed slugs must be rechecked against a fresh inventory at creation time. New photos stay NULL until separately reviewed; CSV listing/share links are not silently imported as image URLs.

| CSV record | Destination | Proposed slug | Outstanding source issue |
| ---: | --- | --- | --- |
| 8 | S&R Membership Shopping Nuvali | s-and-r-membership-shopping-nuvali | Global review gates below |
| 9 | Landers Superstore Nuvali | landers-superstore-nuvali | Global review gates below |
| 11 | Balibago Complex | balibago-complex | Global review gates below |
| 14 | Timezone Solenad 3 | timezone-solenad-3 | Global review gates below |
| 15 | SM Game Park - Santa Rosa | sm-game-park-santa-rosa | Global review gates below |
| 16 | McDonald's Nuvali Santa Rosa | mcdonalds-nuvali-santa-rosa | Global review gates below |
| 17 | Jollibee Balibago Crossing | jollibee-balibago-crossing | Global review gates below |
| 18 | Jollibee Balibago Complex | jollibee-balibago-complex | Global review gates below |
| 19 | Jollibee Sta. Rosa Bayan | jollibee-sta-rosa-bayan | Global review gates below |
| 20 | Jollibee Golden City | jollibee-golden-city | Global review gates below |
| 22 | Chowking Sta. Rosa Bayan | chowking-sta-rosa-bayan | No coordinates |
| 23 | Burger King - SM Sta. Rosa | burger-king-sm-sta-rosa | Global review gates below |
| 24 | Pizza Hut - SM City Santa Rosa | pizza-hut-sm-city-santa-rosa | Global review gates below |
| 25 | Nono's - SM Santa Rosa | nonos-sm-santa-rosa | Global review gates below |
| 27 | Pho Saigon Vietnamese Restaurant - Sta. Rosa | pho-saigon-vietnamese-restaurant-sta-rosa | Global review gates below |
| 29 | Three Monkeys Brews & Bites | three-monkeys-brews-and-bites | Global review gates below |
| 30 | Bad H Coffee Bar - Specialty Coffee | bad-h-coffee-bar-specialty-coffee | Global review gates below |
| 31 | UCC Clockwork Nuvali | ucc-clockwork-nuvali | Global review gates below |
| 32 | Amare La Cucina Nuvali | amare-la-cucina-nuvali | Global review gates below |
| 33 | Ebi 10 | ebi-10 | Global review gates below |
| 34 | The Café Mediterranean | the-cafe-mediterranean | Global review gates below |
| 35 | Manam Comfort Filipino - Nuvali | manam-comfort-filipino-nuvali | Global review gates below |
| 36 | The Morning After | the-morning-after | Global review gates below |
| 37 | Nonna's Pasta and Pizzeria | nonnas-pasta-and-pizzeria | Global review gates below |
| 38 | Bistro Charlemagne | bistro-charlemagne | Global review gates below |
| 39 | Gerry's Grill - Ayala Malls Solenad | gerrys-grill-ayala-malls-solenad | Global review gates below |
| 40 | TGI Fridays Nuvali | tgi-fridays-nuvali | Global review gates below |
| 41 | Bites & Barrels Gastropub | bites-and-barrels-gastropub | Global review gates below |
| 56 | Nuvali Sand Courts | nuvali-sand-courts | missing_required:Description |
| 57 | ACES Badminton and Pickleball Center - Santa Rosa, Laguna | aces-badminton-and-pickleball-center-santa-rosa-laguna | Global review gates below |
| 58 | Winner Badminton Court | winner-badminton-court | missing_required:Description |
| 59 | Court Zero Pickleball Court | court-zero-pickleball-court | missing_required:Description |
| 60 | Infinite Badminton & Sports Center | infinite-badminton-and-sports-center | missing_required:Description |
| 61 | Pickle G Society | pickle-g-society | Global review gates below |
| 62 | TCC - The Common Court | tcc-the-common-court | Global review gates below |
| 63 | Pickle Patio | pickle-patio | Global review gates below |
| 64 | Tagapo Basketball Court | tagapo-basketball-court | Global review gates below |
| 65 | Mabuhay Homes Basketball Court | mabuhay-homes-basketball-court | Global review gates below |
| 66 | Golden City Clubhouse Basketball Court | golden-city-clubhouse-basketball-court | Global review gates below |
| 67 | Balibago Court | balibago-court | Global review gates below |
| 68 | Seda Nuvali | seda-nuvali | Global review gates below |
| 69 | Technopark Hotel | technopark-hotel | Global review gates below |
| 70 | Terrazas de Teodora Pavilion and Resort | terrazas-de-teodora-pavilion-and-resort | Category key collision |
| 71 | Garden Villas 1 Clubhouse (Pool) | garden-villas-1-clubhouse-pool | Global review gates below |
| 72 | Summer's Place Resort | summers-place-resort | Category key collision |
| 73 | Popong Resort | popong-resort | Category key collision |
| 74 | Paseo Premiere Hotel | paseo-premiere-hotel | Global review gates below |
| 75 | Hotel Sogo Santa rosa | hotel-sogo-santa-rosa | Global review gates below |
| 76 | El Cielito Hotel - Sta. Rosa | el-cielito-hotel-sta-rosa | Global review gates below |
| 77 | My Hotel Sta. Rosa | my-hotel-sta-rosa | Global review gates below |
| 78 | Sans Hotel | sans-hotel | Global review gates below |
| 79 | Mariposa Budget Hotel Sta. Rosa | mariposa-budget-hotel-sta-rosa | Global review gates below |
| 80 | Candy Inn Motel | candy-inn-motel | Global review gates below |
| 81 | E.M. Drive Inn | e-m-drive-inn | Global review gates below |
| 82 | Golden Gate Inn | golden-gate-inn | Global review gates below |
| 83 | Madie's Place | madies-place | Global review gates below |
| 84 | Amethyst Econotel | amethyst-econotel | Global review gates below |
| 85 | Asiatel Econo Hotel | asiatel-econo-hotel | Global review gates below |
| 86 | Calypso Resort Hotel | calypso-resort-hotel | Global review gates below |
| 87 | Lolo Uweng Chapel | lolo-uweng-chapel | No coordinates; Tourism type not recorded |
| 88 | KFC Paseo de Sta. Rosa | kfc-paseo-de-sta-rosa | No coordinates |
| 89 | Victory Central Mall | victory-central-mall | No coordinates |
| 91 | Cafe Maestro | cafe-maestro | No coordinates |
| 92 | Cafe Royal | cafe-royal | No coordinates |
| 93 | Cafe de Rosa | cafe-de-rosa | No coordinates |
| 94 | Cafe Amelia | cafe-amelia | No coordinates |
| 95 | Kafé Lando | kafe-lando | No coordinates |
| 96 | Island Foodpark | island-foodpark | No coordinates |
| 97 | Grill Yard | grill-yard | No coordinates |
| 98 | Mary Grace | mary-grace | No coordinates |

## Previously published records proposed for archiving

These are proposals for explicit approval, not automatic omission handling. Archive changes status only; retain the record, image, relationships and audit trail. Existing saved trips may reference these IDs and must not be deleted or rewritten. Review their behavior after archiving during offline acceptance.

| Destination | UUID | Review note |
| --- | --- | --- |
| Mama Lou's Italian Kitchen | 128cfb4c-7fca-45e8-8ad7-5ba7ba11a100 | Not represented in CSV by the proposed mapping. |
| Lakeside Activities (Nuvali) | 2880335f-88b4-4886-9553-bffd933801d0 | Scope overlap with CSV #2: proposed reuse of Nuvali Park UUID and archival of this separate activity record requires explicit confirmation; no merge or relationship transfer. |
| CIBO – Solenad | 99cc7af3-6c4b-4b49-801d-3b901b04af3f | Not represented in CSV by the proposed mapping. |
| Perlas Ancestral House | bbb40cb4-1abe-4faf-8a60-04c24b24b160 | Not represented in CSV by the proposed mapping. |
| Tiongco Ancestral House | d03ad79f-743e-442a-a73a-26d3fded879d | Not represented in CSV by the proposed mapping. |
| Kanin Club | defa76fd-3ab9-4043-9ca7-b1c86e696722 | Not represented in CSV by the proposed mapping. |
| Waltermart Bel-Air | ea79b08e-3461-4540-b71f-fc7c2fed8fbb | Not represented in CSV by the proposed mapping. |

Leave the two existing Drafts (Centennial Garden and City of Santa Rosa People's Park) and all 13 already-Archived records unchanged. Do not delete or revive archived synthetic records.

## Corrections and identity decisions

| CSV record | Required correction |
| ---: | --- |
| 2 | Nuvali Lakeside / Park: latitude incorrectly contains an East value outside latitude range. Supply a verified latitude and review both coordinates; do not swap or infer automatically. |
| 10 | WalterMart Santa Rosa: longitude uses an N hemisphere suffix. Supply a verified longitude; do not silently change the suffix. |
| 56 | Nuvali Sand Courts: supply description. |
| 58 | Winner Badminton Court: supply description. |
| 59 | Court Zero Pickleball Court: supply description. |
| 60 | Infinite Badminton & Sports Center: supply description. |

The proposed values retain existing coordinate pairs for #2 and #10, but their source errors still block execution. They are not marked corrected. Any source correction requires regenerating and reapproving the package under the new CSV hash.

- Approve the ten alias mappings above and resolve the Nuvali Park / Lakeside Activities scope decision before finalizing the seven-archive list.
- Treat Chowking Bayan (#22) separately from Chowking Balibago (#21). Restaurants inside malls remain distinct from the mall itself: Pizza Hut (#24), Gerry's Grill (#39), KFC (#88) and Nono's (#25) do not reuse mall IDs. McDonald's (#16) does not match Monde Nissin. The JSON preserves other heuristic candidates for review; no fuzzy match assigns an ID.
- Exact CSV names and proposed new slugs have no duplicates or existing-slug collisions. This does not prove physical-place identity, address accuracy or branch scope. Shared coordinates do not prove duplicate destinations.
- Exact coordinate groups: CSV #5/#24, #32/#36, #33/#34 and #35/#38. Arambulo (#44) and Gonzales (#46) also have nearly identical coordinates; confirm locations without merging the distinct records.
- Thirteen CSV rows have no coordinates. Existing Target Mall (#90) keeps its stored coordinates; twelve new rows (#22, #87–89, #91–98) would have NULL pairs. They can remain unlocated records under current semantics, but full map/routing coverage is not established. Do not fabricate points.
- Lolo Uweng Chapel (#87) lacks tourism type. Supply Local/Common or explicitly accept Not recorded; no type has been invented. Sixty-three rows lack days and 24 have complex hours strings; preserve unknown/raw schedule semantics.
- There are 73 category labels. `Resort / Swimming Pool` and `Resort Swimming Pool` normalize to the same proposed key. Decide whether to merge the labels or give them distinct stable keys; #70/#72/#73 remain blocked. All category parent/legacy-interest relationships require review, not an invented taxonomy.
- All three existing image URLs are preserved (Enchanted Kingdom, Chowking Balibago, Santa Rosa City Auditorium). Eighty-four CSV external photo references remain unverified; they will not replace images or trigger downloads/uploads. Blank/N/A photos never clear existing images. The unnamed checkmark column is ignored, not treated as approval.

## Required application/schema preparation

The current schema/RPC/runtime still enforce seven category keys. This package proposes extensible registry keys and an `operating_days_raw` field; these are not currently accepted mutation payloads. No migration is bundled or approved by this report. Before data application, implement and qualify the reviewed registry, legacy-interest relationships, Admin inputs/filters/insights, User browse/map/preferences and itinerary validators/recommendations together. Extend guarded metadata/provenance/operating-day RPC allowlists and audit details; preserve provider guards, RLS and grants. Read current target schema/functions/security definitions before preparing exact target-specific migration SQL for separate approval.

Weather identity metadata must be reconciled for changed category/name identities without weakening its verified-identity checks. Existing metadata is unchanged. Recommendation eligibility is category-based with Local/NULL/Common ranking; publication does not imply every destination is selected for every itinerary.

## Controlled publication sequence — conditional, not executable yet

1. Confirm identities, Nuvali scope, all seven archives, category keys/relationships and field corrections. Regenerate this per-record package against the corrected CSV. Approve exact values and separately review any schema/application changes. Obtain separate approval for authenticated operator testing when the security gates permit it.
2. Immediately before authorized writes, independently verify target, source/export hashes, complete current inventory and every affected row version/hash. Stop on drift and prepare a new diff. The old export cannot authorize changes to newer rows.
3. Use the existing guarded, audited Admin mutation/status behavior. Stage 70 new Drafts with server-assigned UUIDs; verify them before any publication. Apply the 28 approved updates preserving IDs/slugs/images. Updating Published rows is immediately visible, so approve that timing explicitly. Do not use direct owner INSERT/UPDATE, forged request claims or service keys to bypass authorization and logging.
4. The final 98 published records fit the current 100-candidate recommendation bound. Publishing all 70 additions first would temporarily reach 105 and must be avoided. Either review an authenticated audited transactional cutover, or explicitly approve a bounded staged cutover: after all corrections and Draft verification, archive the seven approved old records (35 to 28 Published), then publish the 70 new Drafts (28 to 98). The latter has temporary partial availability and requires separate timing/failure-handling approval; do not silently choose it or blindly retry after errors.
5. Verify final counts (98 Published, 2 Draft, 20 Archived), exact approved IDs/values, no duplicates, three original image references, and complete mutation audit records. Verify User browse/detail/map pagination, published-only RLS, hidden Draft/Archived records, expanded-category recommendations, preserved saved-trip relationships and Admin edit/filter/status behavior. Geographic tests must retain explicit unknown coordinates rather than inventing feasibility.

No account, permission, Auth, Storage, secret or hosted database change is performed by this review. The next approval is for the record/identity/archive decisions and the necessary local preparation; hosted application requires a refreshed, corrected and separately approved package. Remote deployment remains **NO-GO**.

## Focused verification

35 offline tests passed across `test_current_catalog_review.py`, `test_publication_review.py` and `test_local_destination_catalog.py`, with network connections blocked. Tests cover export scope/counts/role/read-only evidence, wrappers, duplicate identities, timestamps, alias proposals, blank/image/identity preservation, explicit archive proposals, draft-first creation, category collisions and shared coordinates. They do not qualify the unimplemented dynamic-category runtime or hosted writes. No live sign-in was performed.
