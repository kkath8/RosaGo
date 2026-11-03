# Personalized recommendations verification

Task scope: the Recommendations redesign in the existing dirty worktree. Earlier
Light/Dark, Profile, Dashboard, Budget, Alerts and other changes were preserved.

## Behavior and ranking

The previous screen was a manual shortlist with oversized destination selectors
and repeated generic reasons. The new screen presents the deterministic engine's
initially selected suggestions, factual metadata-based reasons, compact controls,
live counts, top/bottom Create My Itinerary actions, and up to six alternatives.
Cards use two columns at desktop and one on mobile. The four Planner steps are
Preferences, Review, Recommendations, Itinerary; mobile steps use two rows.

Ranking is category eligibility first, then database tourism_type Local, NULL,
Common, then canonical UUID. Category-match score remains 1 (not inflated to 2).
Selection preserves existing pace/day limits and category round-robin diversity;
within each diversity round, available category heads use the tourism priority.
Common remains eligible, and NULL is never inferred to mean Local. No Gemini
selection or classification is introduced. Basic recommendation reasons are pure
metadata-based text. Rich optional AI remains in Preview.

The engine revision is category-interest-tourism-v2. The existing database preview
RPC pins the source identifier category-interest-v1. That wire identifier remains
unchanged, independently of ranking version, so the UI requires no schema or SQL
change. A regression test covers this separation and original digest vectors.

## Files in this task

Application: app.py; recommendation_engine.py; itinerary_selection_policy.py;
itinerary_preview.py (stored contract compatibility only);
static/js/user-ui.js (per-draft options and Review link);
static/js/recommendations.js; static/css/recommendations.css;
static/css/site.css (readable mobile Planner progress);
templates/partials/planner_progress.html;
templates/itinerary/preferences.html, review.html, recommendations.html,
preview.html (shared progress).

Tests: test_personalized_recommendations.py,
test_personalized_recommendations_ui.py, test_recommendations_ui.js;
existing recommendation, selection, quiz, runtime, Preview, AI, metadata, layout
and weather assertions updated for the intended UI/policy. Existing runtime guards
and protected Preview routes remain exercised. No weather/Gemini/auth logic edits.

This directory intentionally retains browser screenshots, verification scripts and
results. Scripts write only through normal application forms and need explicit
permission for temporary records. Do not rerun live_checks.py casually: it creates
three drafts. preview_checks.py reuses the existing mixed-interest draft.

## Automated checks

- Final focused Planner/recommendation/Preview/AI/weather suite: 213 passed,
  323 subtests (final-focused-tests.txt).
- Public layout suite: 19 passed, 22 subtests.
- Recommendation selection JavaScript: 3 passed.
- Theme JavaScript: 6 passed.
- Personal-state assertions passed; both changed JavaScript files parse.
- Node's isolated multi-file test runner cannot spawn children in this sandbox
  (EPERM); running the test files directly passes.

## Live evidence and limitations

Signed-in real app at port 5000; Chrome verification window on CDP 9226.
Shopping, Heritage and mixed interests exercised at 1440px and 390px in Light and
Dark. Checked initial selection, count, eligibility, Local/NULL/Common ordering,
bounded alternatives, two/one-column cards, compact controls, text contrast,
no horizontal overflow, and toggling without reload or scroll jump.
The mobile progress wrap found in these checks was fixed and rechecked.

The real Shopping catalog currently contains no Local Shopping records. Therefore
the live Shopping check establishes NULL-before-Common and Common availability;
a focused synthetic test establishes Local Shopping before Common Shopping.
Real Heritage has Local records and the browser check confirms their priority.

The first Preview attempt exposed the deployed wire-version restriction. Its
failure remains in live-results.json as evidence, not a passing completion claim.
The final Preview run is recorded separately in preview-results.json.

No SQL, migrations, schema edits or catalog/metadata writes were performed.
The user authorized three temporary drafts plus one named verification trip via
normal app forms. Drafts expire normally; existing saved trips must remain intact.
The named verification trip was saved and deleted successfully. Original saved trips
compare unchanged before/after. The approved drafts remain to expire normally.

## Final live results

After the user signed in again, all 11 final flow checks passed (preview-results.json):
Create My Itinerary produced exactly the four selected destinations in order;
optional real AI returned per-destination explanations; conversational adjustment
"Make it 2 places" advanced the revision and produced two destinations; Save to My
Trips succeeded with memberships; only the named verification trip was deleted;
original saved trips compared unchanged. No browser JavaScript exceptions occurred.

Nine additional read-only checks passed (preview-visual-results.json), covering
Preview in Light/Dark at 1440px/390px with expanded weather details and Save inputs.
No horizontal overflow or text-contrast audit failures were found. Screenshots
include preview-*.png and weather-*.png. The actual weather advisory displayed the
forecast concern and source. Unknown exposure metadata correctly retained the
existing destinations; no replacement proposal was offered, so no weather
acceptance mutation was performed. Protected weather behavior remains covered by
the focused tests. No Gemini, weather or authentication implementation was changed.

The initial 77 Recommendations checks remain in live-results.json, alongside the
initial Preview failure subsequently corrected and successfully reverified. The
version fix preserves the deployed v1 wire contract without changing the database.

The updated Flask server remains running on port 5000; the verification browser
remains signed in, with original theme and browser preferences restored. Exactly
three approved temporary drafts were used; one named test trip was created and
deleted. No pre-existing trips or catalog records were edited.

`git diff --check` passes. The final full worktree status is git-status.txt. The
shared worktree includes extensive pre-existing changes. No staging, commit or
push was performed.
