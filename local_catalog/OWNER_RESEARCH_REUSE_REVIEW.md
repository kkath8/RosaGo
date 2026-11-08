# Reuse original research; review exceptions only

This is the current research assessment. It supersedes the earlier inference
that empty approval worksheet cells mean all 98 places need new geographic
research. No new research spreadsheet or individual re-entry is required for
otherwise sound researched CSV pairs. No hosted operation is authorized.

## Owner-confirmed research

The owner explicitly confirmed:

> The 98 destinations in our CSV were already researched and verified when we originally created the list.

That confirmation is now recorded as **owner-confirmed original research**,
bound to the unchanged 98-row CSV SHA-256
`c55ed7076b59d611bc57eb0d59b0c6c425b301e4999655b01a17a9a8ca87ed2a`.
It is legitimate provenance, not merely a numeric check and not an independent
survey performed by Codex. The original research date/method and individual
external source snapshots are not invented. The JSON recording timestamp is
when this confirmation was recorded locally, not when original research occurred.

## Evidence reused and its scope

| Evidence class | What is available | Treatment |
| --- | --- | --- |
| Owner-confirmed prior research | Current explicit statement covers the original 98-destination dataset | Retain research provenance for all 98; reuse the sound coordinate data without blanket re-verification |
| Previously documented project support | Existing CSV field report, production owner export, matched UUIDs/values and historical Tourism metadata | Reuse existing matching, provenance and numeric findings; no rematching or source revalidation |
| Independently documented geographic verification | No reviewed per-record survey/geocoding evidence establishes this distinct claim | Do not label owner research as an independent survey; this absence alone does not reject owner-confirmed research |
| Known exceptions | Malformed/missing pairs, targeted near-identical house pins and other identified record decisions | Review only these exceptions; retain Draft for unresolved location problems |

The earlier CSV report already records **83 valid numeric pairs**, two malformed
pairs and 13 absent pairs. No new CSV inspection was run. The existing owner
export supports stored-pair proposals for #2, #10 and #90, but confirmation of
the researched dataset does not automatically repair incorrect or missing cells.

Historical documentation identifies a separate City Tourism Office workbook
and its metadata transition. This supports historical source provenance for
matched records, not a claim that all 98 updated CSV coordinates were independently
verified by that office. The original archived 28-place publication file explicitly
used NULL coordinates for new rows, so it cannot supply missing points now.
The unnamed CSV checkmarks are still not treated as verification or publication.

**83 CSV pairs retain owner-confirmed research evidence. Of those, 81 need no
additional location question. Two retain that research provenance but have a
specific pre-existing house-pin question. Fifteen other records need a coordinate
correction or must stay Draft.** This is location-evidence classification, not
hosted publication approval or an independent-verification count.

## Short list: additional information or decisions

| Issue | Destinations | Required action |
| --- | --- | --- |
| Malformed coordinates | #2 Nuvali Lakeside / Park; #10 WalterMart Santa Rosa | Confirm the matching venue/branch, then approve the complete stored-pair correction or supply the researched correction. Do not invent/swap values. |
| Missing pair with stored proposal | #90 Target Mall | Approve the existing exported pair if it is the researched location; otherwise provide correction or retain Draft. |
| Missing pair, no stored substitute | #22 Chowking Sta. Rosa Bayan; #87 Lolo Uweng Chapel; #88 KFC Paseo de Sta. Rosa; #89 Victory Central Mall; #91 Cafe Maestro; #92 Cafe Royal; #93 Cafe de Rosa; #94 Cafe Amelia; #95 Kafé Lando; #96 Island Foodpark; #97 Grill Yard; #98 Mary Grace | Supply missing researched coordinates only if available; otherwise keep these 12 Draft. No fresh venue research is requested merely to keep a Draft. |
| Specific house-pin ambiguity | #44 Arambulo Ancestral House; #46 Gonzales Ancestral House | Confirm whether the near-identical researched points intentionally identify separate adjacent houses or require a correction; existing addresses only specify Poblacion. Preserve both identities. |
| Missing descriptions | #56 Nuvali Sand Courts; #58 Winner Badminton Court; #59 Court Zero Pickleball Court; #60 Infinite Badminton & Sports Center | Supply original/source-backed descriptions; no generated substitute. |
| Missing tourism type | #87 Lolo Uweng Chapel | Supply researched Local/Common, or explicitly accept NULL/Not recorded. |
| Category key/parent conflict | #70 Terrazas de Teodora Pavilion and Resort; #72 Summer's Place Resort; #73 Popong Resort | Decide merge versus distinct resort keys and lodging/recreation parent; preserve source labels until approved. |
| Existing-record identity aliases | #2, #3, #12, #42, #43, #47, #48, #49, #50, #51 | Approve/correct the 10 prepared UUID mappings, as a batch if appropriate. This is matching approval, not repeat geographic research. |
| Proposed archives | Mama Lou's Italian Kitchen; Lakeside Activities (Nuvali); CIBO – Solenad; Perlas Ancestral House; Tiongco Ancestral House; Kanin Club; Waltermart Bel-Air | Approve/reject seven individual status changes, especially Nuvali scope and WalterMart branches. Missing from CSV alone does not authorize archiving. |

These groups overlap: **33 CSV destinations have a remaining record-specific
decision**, not 98 re-verification tasks. Archives concern separate existing
records. There is also one batch registry/legacy-interest-parent approval for
the 73 prepared categories; this is an application compatibility decision,
not a request to research all category labels again. Existing per-record security,
content and publication checks still apply.

Existing shared-coordinate groups #5/#24, #32/#36, #33/#34 and #35/#38 have
source addresses within the same named mall/Solenad complex. Shared coordinates
do not establish a duplicate or, by themselves, a location error. Retain the
owner's researched points and separate venue identities; do not infer exact
entrance/indoor routing precision or require fresh pins for every tenant.

## Editable outputs

- [Remaining destination decisions only](remaining-destination-decisions.csv):
  33 rows with the existing unresolved issues and editable owner response/evidence.
- [Research-aware 98-record reference](destinations-98.research-aware.csv):
  correct evidence labels, existing matches, coordinate candidates, source
  completeness and image disposition. The other 65 have no new record-specific
  question; batch category, security and final change-set approvals still apply.
- [Source-bound research assessment](owner-research-reuse.review.json):
  machine-readable owner confirmation, existing evidence support and exceptions.

The earlier `owner-review/` tables and JSON plans are preserved for traceability;
their blank geographic approval cells are not the current research assessment.
Do not complete all 98 evidence rows merely to satisfy that older worksheet.
Continue using its alias/archive/category tables for actual outstanding decisions.
No editable worksheet is automatically imported.

## Preserved gates and next step

No coordinates, descriptions, classifications, aliases or archive decisions
were silently corrected or approved. The original CSV, stored-row export,
location ledger review and v4 publication package are unchanged. This new
assessment supersedes their blanket research-absence interpretation; it does
not falsely set audited verification records or remove the SQL guard.

The next publication package must consume this source-bound owner research
assessment and resolved exceptions, rather than count old empty worksheet fields
as evidence against the research. Actual location verification records must
still be established through the approved authenticated, audited workflow at
cutover. The owner research statement can be cited as its provenance; no new
independent-survey claim or owner DML bypass is introduced.

Image mapping stays **79 proposed attachments / 3 hosted covers / 16 placeholders**.
Nuvali Sand Courts remains unassigned. No image scanning/integration was repeated.
Provider authority/Auth restore-replay and production migration/cutover remain
unqualified; remote deployment remains **NO-GO**. These are separate from whether
the source was originally researched. No hosted changes, SQL execution, uploads,
publication, deployment, commits, pushes or live sign-ins occurred.

**21 focused offline tests passed**, including six new research-reuse tests and
15 existing evidence/decision-gate tests, with socket connections blocked. They
verify evidence classification, retention of bad/missing-coordinate exceptions,
target/source binding, unchanged inputs/images and no execution authorization.
