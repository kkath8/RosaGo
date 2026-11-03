# Checkpoint 3: conversational Preview adjustments

Only temporary, owned `preview_ready` drafts can be adjusted. Saved trips and
in-progress/finalized itineraries are not modified. This does not add weather
automation, ranking signals, streaming, or a conversation/history store.

## Required database step before browser testing

The user confirmed during Checkpoint 4B that
`migrations/0010_itinerary_preview_adjustment.sql` was **manually applied successfully**.
Do not rerun it. The
0006 preference validator and 0007 Preview lifecycle functions must already be
present. Do not rerun earlier migrations. Restart Flask after code updates.
No live database operation was performed during implementation.

The new RPC locks the owner-filtered draft and checks revision, state, schema,
expiry and read-committed isolation. Only interests and pace may differ in the
preference snapshot. Within one transaction, it privately clears Preview and
switches to editing without incrementing revision, then calls the unchanged
0007 store function. That function independently validates the Preview contract,
locks selected Place records, checks publication, category eligibility and
fingerprint, rechecks expiry after lock waits, and increments revision once.
Any error rolls back the intermediate preference/state changes. No errors are
caught in SQL and no application-level multi-step writes or retries occur.

Before production use, verify the RPC on PostgreSQL: reject a different owner,
stale revision, expired draft, changed unrelated preference, missing/unpublished
place, and incorrect catalog fingerprint. In each rejected case verify the full
draft row remains unchanged. Confirm a valid update advances revision exactly
once and remains readable through `get_itinerary_preview_draft`. Two concurrent
updates with the same revision must produce one success and one rejection.
The local tests mock RPC transport and check the SQL contract; they do not execute
PostgreSQL transactions or simulate its locks.

## Flow and enforceable constraints

`POST /user/itinerary/<draft_id>/preview/adjust` accepts exactly `csrf_token`,
`expected_revision`, and `message` (1–1000 characters, 8192-byte request bound).
The server verifies the owned, unexpired Preview and current catalog fingerprint
before interpreting the message. One Gemini request shares only the bounded user
message, system instructions, task and supported schema. No account, draft,
catalog destination, session or token data is included. The existing shared
two-second throttle, response size bounds, timeouts and no-retry policy apply.

Interpretation shape:

```json
{
  "intent": "modify",
  "changes": {
    "set_interests": ["heritage"],
    "add_interests": [],
    "remove_interests": [],
    "pace": null,
    "place_count": 2
  },
  "unsupported_requests": ["budget"]
}
```

`intent` is `modify` or `clarify`. Every key is required. Unknown keys, destination
IDs, unknown categories, duplicate categories, contradictory changes, and invalid
types/ranges fail validation. Exclusive interests cannot be combined with add or
remove operations. Clarification responses cannot contain modifications. The
server validates the result again before applying any change.

Supported changes are exclusive/add/remove category interests, relaxed/balanced/
packed pace, and a total destination count from 1–100. At least one and at most
six interests must remain, matching the existing preference contract. The existing
ranker supplies canonical deterministic matches. The category round-robin policy
now accepts an optional bounded count; it still emits the ranker's original order.
An explicit count overrides the pace count for this update. Without count, an
explicit pace uses 2/3/4 destinations per day. Category-only adjustments retain
the current total count. Counts are limited by available matching published
places, with a disclosure if fewer exist. No separate place-count preference is
stored: subsequent category changes use the current selection count, and a later
explicit pace change returns to the existing pace policy. Unrelated preferences
are preserved. Zero matches, ambiguity and failures leave the prior Preview.

The catalog has no verified cost, hours/duration, or indoor/outdoor fields. Budget,
time/opening-hours and environment constraints therefore receive fixed honest
messages. Existing budget, daily window and environment preference fields are
not evidence of enforceable scheduling/filtering. Individual place replacement
is unsupported because this form has no unambiguous place reference. Mixed
requests may apply supported parts and disclose unsupported ones. Pace promises
a smaller suggested count, not lower physical effort or accessibility.

After a successful atomic save, the server rereads and renders the stored Preview.
AI explanations are cleared; Explain with AI must be explicitly requested again.
The response uses existing private/no-store rendering and Jinja escaping. Gemini
text is never rendered as HTML. Provider failures do not mutate drafts. An
ambiguous database timeout uses the existing unconfirmed-mutation error, never
an assertion that a possibly committed write was rolled back.

## Manual browser cases

1. Generate a Preview with at least three attraction matches. Ask “I only want
   2 places.” Expect two when at least two matches exist, retained order and a
   fresh revision. Destination links and Edit Preferences must still work.
2. Ask “I prefer heritage places.” Expect only published heritage matches, or
   an unchanged Preview and no-match notice if none exist.
3. Ask “Add dining to my interests”, then “Remove dining destinations.” Check
   interests change without unrelated preference changes.
4. Ask “Make the itinerary less tiring.” Check relaxed pace uses at most two
   destinations per day and discloses that time/effort are not verified.
5. Separately ask “My budget is 500 pesos”, “I only have until 5 PM”, and “I
   don't want outdoor places.” Each must explain its limitation without changing
   the itinerary or claiming compliance.
6. Ask “Only 2 places and a PHP 1,000 budget.” Check the supported count update
   and honest cost-data warning together.
7. Ask “Replace this place” or an unclear request. Check clarification and no
   mutation. Ask for an unavailable category; check no fabricated fallback.
8. Explain with AI, adjust the Preview, and verify old explanations disappear.
   Request Explain with AI again; verify reasons attach to the new selected IDs.
9. Disable JavaScript and repeat an adjustment. Test missing provider config or
   provider failure: destination cards, details links and Edit Preferences stay
   usable. Rapid repeated requests may hit the existing shared AI throttle.
10. Open two Preview tabs, update one, then submit the old tab. Expect revision
    rejection, never overwrite. Saved/expired drafts and another user's draft
    must be rejected. Verify invalid CSRF, foreign Origin and added structured
    form fields are rejected without invoking Gemini.
