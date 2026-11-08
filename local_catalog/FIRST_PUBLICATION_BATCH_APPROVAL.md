# First publication batch: content decisions for approval

**81 previously researched locations are accepted for local planning. No new
manual geographic review is requested for those 81.** Owner-confirmed research
is retained as provenance, not represented as a new independent survey.
No hosted changes or publication have occurred. Remote deployment is **NO-GO**.

## First batch

[first-publication-batch.csv](first-publication-batch.csv) lists the exact
**65 content candidates: 14 existing-record updates and 51 additions**.
They have accepted researched locations, source descriptions, non-colliding
category keys and no pending alias mapping. The complete before/after and
held-record review is
[production-first-publication-batch-v2.review.json](production-first-publication-batch-v2.review.json).

Batch CSV numbers: **1, 4–9, 11, 13–21, 23–41, 45, 52–55, 57, 61–69, 71,
74–86**. All 65 still depend on approval of the common category registry/parent
mapping, qualified security/migration/cutover and the exact final field/status
changes. “Candidate” does not mean approved for execution. New records stage as
Draft; verification and publication remain distinct authenticated/audited steps.

**16 other accepted-location records remain held only for decisions below:**
aliases #3/#12/#42/#43/#47–51; descriptions #56/#58–60; resort categories
#70/#72/#73. Approving all those content proposals could expand the CSV batch
to 81 without any new location review. Missing photos do not block publication.

**17 unresolved-location records remain Draft in the proposal:**
#2, #10, #22, #44, #46, #87–98. No stored pair is adopted automatically.

## Stored coordinate corrections

| CSV destination | Existing identity to preserve | Proposed complete stored pair | Approval needed |
| --- | --- | --- | --- |
| #2 Nuvali Lakeside / Park | Nuvali Park; `4751680c-faab-4043-9d5b-d55053e54415`; slug `nuvali` | `14.239906, 121.059477` | Confirm same park/lakeside scope and approve pair reuse; do not merge the separate activities record |
| #10 WalterMart Santa Rosa | Waltermart Santa Rosa; `0a98d162-51ba-410f-b917-4b95720f105b`; slug `waltermart-santa-rosa` | `14.28803, 121.09437` | Confirm this outlet, distinct from Waltermart Bel-Air, and approve pair reuse |

#90 Target Mall also has the existing stored-pair proposal
`14.29443, 121.10346`; it stays Draft until separately accepted. The 12 without
any usable pair (#22, #87–89, #91–98) can simply stay Draft. #44 Arambulo and
#46 Gonzales remain held for the specific near-identical-pin clarification.
No other locations need a new approval worksheet.

## Four supported description proposals

These short drafts restate only the CSV's recorded venue name, category,
environment and address. They add no hours, pricing, access promises, court
counts, amenities or promotional claims. Supporting source fields are retained
in the batch JSON. The original CSV and proposed database values remain
unchanged until approval.

| # | Destination | Description proposed for approval |
| --- | --- | --- |
| 56 | Nuvali Sand Courts | An outdoor beach volleyball court on Nuvali Boulevard in Santa Rosa, Laguna. |
| 58 | Winner Badminton Court | An indoor badminton venue in the San Lorenzo South area of Santa Rosa, Laguna. |
| 59 | Court Zero Pickleball Court | An indoor pickleball venue at Building 26, Daystar Santa Rosa Industrial Park, Santa Rosa, Laguna. |
| 60 | Infinite Badminton & Sports Center | An indoor badminton venue at One Sta. Rosa Prime on the National Highway in Santa Rosa, Laguna. |

## Three category conflicts: recommended single resolution

| Destination | Recorded category | Recommended application key / legacy parent |
| --- | --- | --- |
| #70 Terrazas de Teodora Pavilion and Resort | Resort / Swimming Pool | `resort-swimming-pool` / `attraction` |
| #72 Summer's Place Resort | Resort Swimming Pool | `resort-swimming-pool` / `attraction` |
| #73 Popong Resort | Resort Swimming Pool | `resort-swimming-pool` / `attraction` |

Merge the two equivalent source labels into one display category **Resort /
Swimming Pool**, retaining each original `tourism_category` text. The CSV
descriptions emphasize swimming/events/recreation; they do not establish
overnight accommodation. Therefore `attraction` is the supported parent
recommendation, not a claim about whether lodging exists.

[category-registry.merged-resort.review.json](category-registry.merged-resort.review.json)
contains the proposed 79-key registry: seven unchanged legacy keys, the 71
previous specific-key/parent proposals and one merged resort key. It is
**approved=false**, unusable as active runtime configuration. The other parent
proposals can be approved as a batch rather than researched again. Database/file
parity and authorization remain required before enabling flexible categories.

## Ten alias decisions

“Approve” means keep the existing UUID/slug and use the CSV display name.
It is not permission to write data or silently repair a coordinate.

| Existing name | CSV destination | Recommended decision |
| --- | --- | --- |
| Nuvali Park | #2 Nuvali Lakeside / Park | Approve if park/lakeside scope matches; coordinate correction and activities archive remain explicit decisions |
| Ayala Malls Solenad | #3 Ayala Malls Solenad (Ayala Malls Nuvali) | Approve same identity |
| Cuartel de Santo Domingo | #12 Fort Santo Domingo / Cuartel de Santo Domingo | Approve same identity |
| Santa Rosa Arch (Bantayang Bato) | #42 Santa Rosa Arch | Approve same identity |
| Museo ng Santa Rosa | #43 The City of Santa Rosa Museum (Museo de Santa Rosa) | Approve same identity |
| Toyota Santa Rosa | #47 Toyota Santa Rosa (Toyota Motor Philippines) | Approve same site identity |
| Coca-Cola Santa Rosa | #48 Coca-Cola Santa Rosa (Coca-Cola Beverages Philippines) | Approve same site identity |
| Monde Nissin Santa Rosa | #49 Monde Nissin Santa Rosa Plant | Approve same identity |
| Mitsubishi Motors Santa Rosa | #50 Mitsubishi Motors Philippines Corporation | Approve same site identity |
| The Fun Farm at Sta. Elena | #51 Fun Farm at Sta. Elena | Approve same identity |

The nine aliases excluding #2 can join the accepted-location batch once the
identity decisions are approved. No new geographic review is needed for them.

## Seven archive decisions

| Existing destination | Recommended decision | Reason / condition |
| --- | --- | --- |
| Mama Lou's Italian Kitchen | Approve archive | Omitted from replacement CSV; other Italian restaurants are distinct |
| Lakeside Activities (Nuvali) | Hold until scope confirmed, then approve archive if covered by #2 | Avoid confusing activities with park identity; no merge or relationship transfer |
| CIBO – Solenad | Approve archive | Omitted restaurant; #3 is its mall, not the restaurant |
| Perlas Ancestral House | Approve archive | Omitted; not Arambulo, Zavalla or Gonzales |
| Tiongco Ancestral House | Approve archive | Omitted; not Arambulo, Zavalla or Gonzales |
| Kanin Club | Approve archive | Omitted; no same-name replacement |
| Waltermart Bel-Air | Hold until separate branch confirmed, then approve archive | Distinguish from #10 WalterMart Santa Rosa |

All seven remain unapproved proposals. Archive preserves the record, UUID,
images, saved-trip relationships and audit history. Never delete omitted records.
Editable decisions remain in `owner-review/aliases.csv` and
`owner-review/proposed-archives.csv`, or can be supplied together in a reply.

## Cutover totals must be explicit

The first 65 are CSV batch members, not automatically the whole hosted Published
set. Of the original 35 Published records, 14 match the first batch. Another
14 CSV matches are held, and seven existing records are archive proposals.
Without those separate status approvals, adding the first 51 new Published
records would leave **86 total Published** (65 selected CSV records + 21 existing
outside the batch), not a complete replacement. No such interim state is
approved here. The v2 package lists the 14 held existing rows and their required
status-change approvals. Final totals/cutover must be regenerated after decisions.

## Security progress and remaining gates

A separate revision,
`mapped_publication_guard.authority-fail-closed.review.sql`, changes only the
proposed provider check from `IF NOT ...` to `... IS NOT TRUE`. This rejects a
NULL/unknown future authority result. The current evaluation helper's EXISTS
result is normally non-NULL; this is hardening for authority integration, not
a claim that installed SQL currently returns NULL. Original reviewed SQL and
its prior qualification evidence remain unchanged.

**Five new native PostgreSQL entry-gate checks passed** in a disposable cached
PostgreSQL 17 container, network disabled and no exposed ports. Missing, false
and NULL helper outcomes denied access before delegation; the old NULL fallthrough
was reproduced; true reached the delegation boundary. The owned container was
removed. Results: [catalog-authority-gate-local-results.json](catalog-authority-gate-local-results.json).

This tests the extracted entry gate only, not full RPC/Admin authorization or
the real provider. The new SQL still contains its unconditional unqualified
preflight exception: **do not run it**. Full clone/RPC qualification of the exact
revision remains required. The earlier 25 clone checks are preserved, not claimed
as rerun on the new revision.

Auth restore/replay and direct hosted API bypass remain unresolved. Production
lacks the evaluation helper in its supplied snapshot. Durable independent
authority, enforced direct-path protection, authenticated audited mutation/
verification acceptance and a target-qualified migration/cutover are still
required. No weaker fallback or owner/service-role DML bypass was added.

**Six focused first-batch tests passed** for the newly generated package,
covering accepted/held records, unsupported automatic promotions, preserved
images/inputs, coordinate proposals and merged-registry compatibility. No image
processing or full CSV research/validation was repeated.

Image dispositions remain **79 proposed attachments / 3 existing covers /
16 placeholders**. Nuvali Sand Courts and the held Winner photo remain unassigned.
Image attachment approval is separate; the batch can use placeholders safely.

Next content approval: the four description drafts, shared resort resolution
and batch registry, nine straightforward aliases plus the conditional Nuvali
mapping, and each archive decision. #2/#10/#90 pair reuse and house-pin decisions
can be provided separately; unresolved records stay Draft. After content and
security gates pass, present the regenerated exact SQL/field/status package for
explicit hosted approval. No uploads, SQL application, live sign-ins, deployment,
commits or pushes occurred.
