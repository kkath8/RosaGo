# Mapping and correction decisions ? approval pending

> Current [mapped-only policy](MAPPED_PUBLICATION_POLICY.md): NULL or unverified coordinates require Draft, superseding any unlocated-publication option below.

No CSV, snapshot or hosted record has been corrected or approved by this document. The existing review package remains unchanged.

## Ten proposed alias mappings

| Existing destination | CSV destination | Recommended decision |
| --- | --- | --- |
| Nuvali Park | #2 Nuvali Lakeside / Park | Reuse existing ID and slug; update displayed name after approval. Confirm park/lakeside scope and the separate activity record before archiving. |
| Ayala Malls Solenad | #3 Ayala Malls Solenad (Ayala Malls Nuvali) | Reuse existing ID and slug; update displayed name after approval. |
| Cuartel de Santo Domingo | #12 Fort Santo Domingo / Cuartel de Santo Domingo | Reuse existing ID and slug; update displayed name after approval. |
| Santa Rosa Arch (Bantayang Bato) | #42 Santa Rosa Arch | Reuse existing ID and slug; update displayed name after approval. |
| Museo ng Santa Rosa | #43 The City of Santa Rosa Museum (Museo de Santa Rosa) | Reuse existing ID and slug; update displayed name after approval. |
| Toyota Santa Rosa | #47 Toyota Santa Rosa (Toyota Motor Philippines) | Reuse existing ID and slug; update displayed name after approval. |
| Coca-Cola Santa Rosa | #48 Coca-Cola Santa Rosa (Coca-Cola Beverages Philippines) | Reuse existing ID and slug; update displayed name after approval. |
| Monde Nissin Santa Rosa | #49 Monde Nissin Santa Rosa Plant | Reuse existing ID and slug; update displayed name after approval. |
| Mitsubishi Motors Santa Rosa | #50 Mitsubishi Motors Philippines Corporation | Reuse existing ID and slug; update displayed name after approval. |
| The Fun Farm at Sta. Elena | #51 Fun Farm at Sta. Elena | Reuse existing ID and slug; update displayed name after approval. |

## Seven proposed archives

| Existing published destination | Reason | Possible overlap requiring review |
| --- | --- | --- |
| Mama Lou's Italian Kitchen | Omitted from the CSV under the proposed identity mapping. | CSV contains other Italian restaurants; no evidence that these are Mama Lou's. |
| Lakeside Activities (Nuvali) | Omitted from the CSV under the proposed identity mapping. | CSV #2 Nuvali Lakeside / Park. Recommend preserving Nuvali Park ID; archive activity record only after scope approval. No automatic merge or relationship transfer. |
| CIBO – Solenad | Omitted from the CSV under the proposed identity mapping. | CSV #3 is the mall, not this restaurant; other Solenad restaurants are separate. |
| Perlas Ancestral House | Omitted from the CSV under the proposed identity mapping. | CSV #44?46 name Arambulo, Zavalla and Gonzales houses; do not merge distinct houses. |
| Tiongco Ancestral House | Omitted from the CSV under the proposed identity mapping. | CSV #44?46 name Arambulo, Zavalla and Gonzales houses; do not merge distinct houses. |
| Kanin Club | Omitted from the CSV under the proposed identity mapping. | No same-name CSV destination; other places in the same category are distinct. |
| Waltermart Bel-Air | Omitted from the CSV under the proposed identity mapping. | CSV #10 WalterMart Santa Rosa. Recommend treating Bel-Air as a separate branch; confirm the two physical outlets before archiving. |

## Incorrect coordinates and stored-data reuse candidates

Stored values below are verified against the supplied export, not independently geocoded or surveyed. Approval of the alias is required before reusing a stored pair. Preserve complete pairs rather than mixing sources.

| CSV record | CSV latitude | CSV longitude | Proposed reuse from exported matching record |
| --- | --- | --- | --- |
| #2 Nuvali Lakeside / Park | 121.0599106° E | 121.0579° E | `14.239906, 121.059477` from Nuvali Park. Conditional proposal; source correction still needs approval. |
| #10 WalterMart Santa Rosa | 14.2881921° N | 14.2881921° N | `14.28803, 121.09437` from Waltermart Santa Rosa. Conditional proposal; source correction still needs approval. |
| #90 Target Mall | (blank) | (blank) | `14.29443, 121.10346` from Target Mall. Missing pair, not an invalid supplied pair. |

## Missing descriptions

| CSV record | Destination | Existing matching description available? |
| ---: | --- | --- |
| 56 | Nuvali Sand Courts | No matching existing record. Owner/source description required; no generated replacement. |
| 58 | Winner Badminton Court | No matching existing record. Owner/source description required; no generated replacement. |
| 59 | Court Zero Pickleball Court | No matching existing record. Owner/source description required; no generated replacement. |
| 60 | Infinite Badminton & Sports Center | No matching existing record. Owner/source description required; no generated replacement. |

## Missing tourism type

| CSV record | Destination | Safe recommendation |
| ---: | --- | --- |
| 87 | Lolo Uweng Chapel | No matching stored classification. Supply Local/Common from the owner/source, or explicitly approve NULL / Not recorded. Do not infer from being a chapel. |

## All 13 CSV records with missing coordinates

| CSV record | Destination | Recommendation |
| ---: | --- | --- |
| 22 | Chowking Sta. Rosa Bayan | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 87 | Lolo Uweng Chapel | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 88 | KFC Paseo de Sta. Rosa | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 89 | Victory Central Mall | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 90 | Target Mall | Reuse stored pair shown above after approval. |
| 91 | Cafe Maestro | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 92 | Cafe Royal | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 93 | Cafe de Rosa | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 94 | Cafe Amelia | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 95 | Kafé Lando | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 96 | Island Foodpark | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 97 | Grill Yard | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |
| 98 | Mary Grace | No matching stored point. Obtain verified coordinates or explicitly accept NULL and incomplete map/routing coverage. |

## Additional unresolved source decisions

- Resort category labels collide at the same normalized key: #70 Terrazas de Teodora Pavilion and Resort, #72 Summer's Place Resort and #73 Popong Resort. Merge the two labels or approve distinct keys; do not silently choose.
- Review parent relationships to the seven preserved legacy interests. They have not been inferred or approved.
- 63 entries lack operating days; preserve unknowns. Opening/closing hours remain source text, with no verified-feasibility claim. No hours have been invented.
- Shared coordinates do not justify merging malls with tenants or distinct restaurants. Review the coordinate groups in the main change set; Arambulo and Gonzales points are also nearly identical.
- Photos remain a separate review. Preserve all existing images; do not promote CSV share/listing links to image URLs.

## Approval sequence

1. Approve or correct the ten alias mappings and each of the seven archives, especially Nuvali and the WalterMart branches.
2. Approve or reject reuse of the three stored coordinate pairs above. Supply the four descriptions and the chapel tourism type (or explicitly accept Not recorded). Decide how to handle the twelve new destinations without coordinates.
3. Resolve category keys and legacy-interest parents. Complete the current-schema read-only preflight and qualify the local rollout/migration package.
4. After these decisions, regenerate the corrected source/overlay and full field-level publication package with new hashes for final hosted-write approval. Do not treat this document or the earlier candidate package as that approval.

Remote deployment remains **NO-GO**.
