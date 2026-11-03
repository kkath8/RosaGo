# Gemini explanation and tourism assistant

## Existing authority and integration

The existing `rank_candidates` engine is unchanged: it uses validated published
Place IDs and category-interest matches, sorting by match and canonical ID. Its
candidate boundary remains 100. The existing preference, shortlist, automatic
selection, revision checks, shared builder and catalog fingerprint flow remain
authoritative. Gemini is never consulted during selection or preview generation.

The shortlist adds an optional **Explain with AI** POST. The server rechecks
authentication, CSRF, origin, owned editable draft, revision and deterministic
candidates before requesting an explanation for at most the first 12 matches.
Only interests and bounded public candidate metadata are sent; budget, companion
suitability, free-text preferences and other unevaluated signals are not claimed
as ranking evidence. A failed AI explanation leaves the normal shortlist usable.
No Gemini request occurs simply by opening recommendations or creating a preview.

## Configuration

Keep server configuration in the ignored `.env` or private process environment:

```dotenv
GEMINI_API_KEY=your_private_google_ai_studio_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

The key is required to enable AI. The model variable is optional; the illustrated
stable model is the default. Confirm access to a supported text model in your
Google project; model availability, quotas and billing depend on that project.
Restart the actual Flask process after configuring it. Do not put keys in source,
templates, browser JavaScript, screenshots, chat messages or version control.

The dedicated service uses Google's documented REST `models.generateContent`
API through the project's existing httpx dependency; no SDK/package installation
is required. The key is an `x-goog-api-key` request header, never a URL parameter.
The API host is fixed and the configurable model name cannot contain URLs or
paths. Redirects, environment proxies and retries are disabled; timeout is 12
seconds per operation, provider output is capped at 256 KB, the complete request
at 64 KB, and output tokens at 1800. One outgoing Gemini call is allowed per two
seconds per serving process across chat and explanations. There are no automatic
calls on GET or automatic retries after failures.

Missing/invalid configuration, rate limiting, timeout, quota, refusal, malformed
JSON, empty/truncated output, unknown IDs or invalid evidence produce a fixed
unavailable state. No raw provider exception, prompt, response body or credential
is logged. Existing deterministic recommendations remain available.

## Structured output and grounding

Both functions request `application/json` with an explicit JSON schema. Python
independently validates the result. Explanation IDs must belong to the supplied
candidate set; interest evidence must equal that candidate's category and a
selected interest. Unknown identifiers invalidate the whole explanation.
Duplicate IDs within output bounds are deduplicated, with presentation restored
to the original catalog candidate order. AI never changes scores or selection.

The authenticated `/user/assistant` page uses the existing shell and a small
navigation link. Before POSTing, users see what is sent to Google. The assistant
receives deterministic lexical retrieval of at most eight relevant published
places from a bounded 50-place read (the current 28-place catalog fits this read).
Each description is capped at 400 characters and address at 200. The prompt
states whether the subset is complete. Requests also include application usage
guidance and actual configured routing modes. No profile, email, auth handle,
token, saved-trip records or other-user data is sent automatically.

Weather-related questions/follow-ups reuse the existing cached WeatherService;
unavailable weather is explicitly represented as unavailable. Weather is city
model/forecast context, never invented destination-specific conditions. Actual
route calculations still belong exclusively to RoutingService; AI gets supported
modes and `calculated_route=null`, never a fabricated route. Google has no tools,
SQL executor, browsing or action callbacks in this integration.

Chat output must contain a bounded answer, an in-scope flag and destination IDs
from the supplied current subset. Unknown IDs invalidate it; duplicates are
removed. Out-of-scope output becomes an application-controlled scope reminder.
Catalog reference links use server-owned names/slugs, not model-created URLs.
AI text and user messages are rendered as escaped plain text without Markdown or
`|safe`. System instructions explicitly distinguish authoritative catalog fields
from user text, untrusted descriptions and prior assistant replies, and forbid
invented destinations, hours, fees, ratings, historical details, availability,
traffic, weather or government warnings.

Schema validation guarantees structural/identifier bounds, not the truth of
every natural-language sentence. Prompt injection and factual errors cannot be
eliminated by instructions alone. Text is labelled advisory, references point to
the actual catalog, and the model has no ability to perform application writes.

## History, authentication and privacy

All chat/clear/explanation POSTs require the existing verified normal session,
CSRF token, exact form fields and the existing same-origin Origin check. Chat
accepts one nonblank string of at most 1000 characters, rejecting controls and
invalid surrogate characters; request bodies are capped at 16 KB. User-supplied
identity fields are rejected. Authority/client objects are removed before Jinja.

History is keyed by both verified user ID and opaque auth-session handle in a
process-local store. There are at most 128 conversations, each with at most 12
messages (six turns), 8000 total text/reference characters, 1000 characters per
user message, 2000 per answer, and eight catalog references per reply. Oldest
complete turns are dropped. Entries expire after 30 idle minutes; capacity uses
LRU eviction of inactive conversations. They are not cookies or database rows.
Concurrent replies for a session are rejected while one is in progress. Clear
uses a protected POST and invalidates pending reply reservations. Completed chat
POSTs redirect to GET, so refreshing the page does not resend a Gemini request.

Provider context is capped at 48 KB, dropping oldest complete history turns if
needed. No history is shared across users or sessions. Logging out revokes access
to that session's history; memory expires or is lost on restart. Separate workers
have separate histories and rate limits, matching the current process-local auth
architecture. Production would need reviewed shared state and global rate limits.

## Focused automated verification

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_gemini_service.py tests/test_assistant_context_store.py tests/test_ai_routes.py tests/test_itinerary_recommendations.py tests/test_itinerary_selection.py tests/test_itinerary_preview_routes.py tests/test_final_ui.py tests/test_public_layout.py tests/test_map_routes.py -q --tb=short -p no:cacheprovider
git diff --check
git status --short
```

Every Gemini request in automated tests uses a mock transport/service. Tests
cover valid output, missing keys, timeout, quota, malformed/refused responses,
unknown/duplicate IDs, unchanged deterministic candidates, escaping, CSRF,
authentication, bounds, isolation, grounding and unavailable weather. No live
Gemini calls were performed during implementation.

## Minimum manual live verification: two successful Gemini requests

1. Configure the private key/model, restart Flask and sign in. Open recommendations
   for an owned draft with at least one category match. These GETs consume no
   Gemini quota. Click **Explain with AI** once: request **1**. Check that the
   explanation is grounded and the candidate list/ranking remain unchanged.
2. Open AI Assistant and send one question, for example: “Which catalog heritage
   destinations could I compare, what weather context is available, and which
   routing modes are supported?” This is request **2**. Check known catalog
   references, truthful city weather availability and supported routing modes.
3. Refresh the assistant GET and clear history using its button. These require
   no additional Gemini requests. Verify logout blocks the assistant. Continue
   through normal selection and preview; those also need no Gemini requests.

Two successful live calls are the minimum for the two independent integration
paths. Do not repeat calls for automated failure tests; those are already mocked.
Real model availability, permission, quota and latency remain to be verified
after configuration. Chat does not automatically load private trips or draft
preferences; users can describe their needs, while recommendation explanations
use the owned draft's supported interest context. No application actions are
performed by AI.

References:

- [Google generateContent REST API](https://ai.google.dev/api/generate-content)
- [Google structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Google model availability](https://ai.google.dev/gemini-api/docs/models)
