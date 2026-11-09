# Editable destination decisions

> Superseding research assessment: [OWNER_RESEARCH_REUSE_REVIEW.md](../OWNER_RESEARCH_REUSE_REVIEW.md). Do not re-enter independent verification for all 98 rows. The owner's original research is recognized; use the new exception-only CSV for remaining information, and retain these alias/archive/category tables for pending decisions. Original worksheets are preserved unchanged.

Start with **[destinations-98.csv](destinations-98.csv)**. It contains one row
for each of the 98 CSV destinations, in original CSV-number order. These are
local review worksheets, not an import package or active application data.
Target context: production `brnkigrrqdrywahvcbvc`, from the existing owner export.
No hosted access or changes occurred when preparing them.

## Files to edit

| Worksheet | Rows | Purpose |
| --- | ---: | --- |
| [destinations-98.csv](destinations-98.csv) | 98 | Main destination review, coordinate evidence and corrections |
| [aliases.csv](aliases.csv) | 10 | Confirm or reject proposed existing-record identities |
| [proposed-archives.csv](proposed-archives.csv) | 7 | Decide each omitted Published record individually |
| [category-conflicts.csv](category-conflicts.csv) | 2 | Resolve colliding resort labels and ambiguous parents; affects #70, #72, #73 |
| [category-parents.csv](category-parents.csv) | 73 | Review all proposed legacy-interest parents, including the two conflicts |

Open these files in VS Code or a local spreadsheet application. CSV files are
UTF-8 with BOM so names and accented characters display correctly. A spreadsheet
table view is easier for the wide main worksheet. Keep the header names, CSV
numbers, names and UUIDs intact. Save back as UTF-8 CSV and preserve decimal
coordinate precision. Fields containing commas, quotes or line breaks must
remain properly CSV-quoted; spreadsheet applications handle this when saving.
Potential formula-like text is prefixed with an apostrophe for spreadsheet
safety; this is review text, not a value to import automatically.

## Reading the main table

| Columns | Meaning |
| --- | --- |
| `csv_number`, `destination_name` | Stable link back to the source CSV |
| `existing_match`, `existing_id`, `proposed_action` | Proposed identity; 28 Update and 70 Add; alias matches remain unapproved |
| `current_stored_status` | Status in the owner export, not a fresh hosted read |
| `proposed_publication_status` | Current plan: Draft for all 98; existing hosted statuses have not changed |
| `address` | Proposed source address, useful for identifying the exact branch/venue |
| `candidate_latitude`, `candidate_longitude` | Candidate complete pair, not automatically verified or approved |
| `coordinate_basis` | CSV numeric pair, conditional stored-pair reuse, or no usable pair |
| `geographic_verification`, `recorded_verification_evidence` | Existing approved evidence state; currently NOT independently verified / blank |
| `category`, `proposed_category_key`, `tourism_type` | Source classification/proposed key; no new classification was invented |
| `description_completeness`, `description` | Present source text versus missing; present does not mean independently fact-checked |
| `image_assignment_status`, `proposed_image_file` | Completed image disposition and staged candidate reference only; no uploads or assignments |
| `issues_requiring_approval` | Record-specific identity/location/category/content/photo and status-change gates |
| `owner_*` | Editable decision, evidence and correction fields described below |

## How to record your decisions

1. Put **Approve proposed content**, **Correct**, or **Hold Draft** in
   `owner_decision`, with any conditions in `owner_notes`. A content approval is
   not coordinate verification, migration approval or permission to write data.
2. To confirm a physical location, fill **both** `owner_confirmed_latitude` and
   `owner_confirmed_longitude`, plus `owner_location_evidence`,
   `owner_location_reviewer` and `owner_location_reviewed_at`. Use a source URL
   or identifiable document/reference, venue/branch details and the actual
   review time (ISO 8601 with timezone, e.g. `2026-11-08T15:00:00+08:00`).
   Leave these blank if you have not independently checked the location.
   Do not overwrite the candidate/evidence baseline columns to imply approval.
3. Existing-pair reuse for **#2 Nuvali**, **#10 WalterMart Santa Rosa** and
   **#90 Target Mall** still requires confirmed identity and location evidence.
   Valid numeric ranges, an old Published record and an image filename are not
   proof of geography. Twelve rows currently have no usable pair at all.
4. Supply source-backed text in `owner_description_correction` for missing
   descriptions **#56, #58, #59 and #60**; cite its source in `owner_notes`.
   Leave unknown descriptions unresolved rather than inventing them.
5. Use `owner_tourism_type_decision` for **#87 Lolo Uweng Chapel**: source-backed
   Local/Common with the source in notes, or explicitly accept NULL/Not recorded.
   Its missing location still requires Draft.
6. In **aliases.csv**, use `owner_decision` = **Approve same destination**,
   **Reject match**, or **Hold**, adding evidence/notes. Approval preserves
   existing UUID/slug. Rejected identities require a reviewed revised match;
   they must not silently become new records.
7. In **proposed-archives.csv**, choose **Approve archive**, **Keep**, or **Hold**.
   Review Nuvali scope and WalterMart branch overlaps in particular. No record
   is deleted, merged or archived by editing these cells.
8. In **category-parents.csv**, choose **Approve proposal**, **Correct**, or
   **Hold**. For corrections, fill `owner_approved_key`/`owner_approved_parent`
   and notes. In **category-conflicts.csv**, explicitly choose a shared merged
   label/key with affected-record mapping OR distinct keys, and decide the
   lodging/recreation parent. Mirror the decision in the corresponding parent
   rows. Contradictory decisions must be reconciled, never guessed.

Keep current stored status separate from your desired outcome. Existing
Published-to-Draft transitions need explicit approval too; changing a worksheet
does not authorize those transitions. Destinations without verified coordinates
remain Draft. Even a verified point does not bypass missing descriptions,
category decisions, authorization or the other publication gates.

## Preserved work and next step

Image dispositions remain **79 proposed attachments, 3 preserved hosted covers
and 16 placeholders**. Nuvali Sand Courts stays unassigned; Winner Badminton
Court remains held. These sheets do not alter the completed image mapping.
Do not put a placeholder path into a database image URL. Image ownership/venue
and upload/assignment approval remain separate from the location review.

When you have edited the worksheets, tell Codex they are ready for review.
There is deliberately **no automatic importer**. Edits will first be checked
for identity/source binding, evidence completeness, conflicting decisions and
unintended changes, then translated into a new review package for your approval.
The original CSV, exports, JSON reviews, images and security components stay
unchanged. The exporter refuses to overwrite this folder, protecting your edits.

`manifest.json` records the input hashes and initial worksheet hashes; edited
worksheet hashes are expected to differ. It is traceability, not an approval.
The current blocker/cutover checklist remains
[FINAL_PUBLICATION_DECISION_CHECKLIST.md](../FINAL_PUBLICATION_DECISION_CHECKLIST.md).
The Auth restore/replay blocker remains unresolved. No SQL, hosted writes,
uploads, publication, deployment, commits or pushes are authorized by these
worksheets. Remote deployment remains **NO-GO**.
