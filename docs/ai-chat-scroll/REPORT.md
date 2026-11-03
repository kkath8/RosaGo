RosaGo AI Assistant auto-scroll — local verification report

1. Root cause: the Assistant used normal full-page form submissions and had no client behavior to position existing or newly rendered conversation history at the latest message. The outer conversation panel and inner history list also both had height/overflow rules, producing nested conversation scrolling at smaller viewports.

2. Auto-scroll: a small page-specific script updates only the conversation panel's `scrollTop`, scheduled through `requestAnimationFrame` after rendering. It does not call page scrolling or `scrollIntoView`. Scrolling happens on initial rendering, user send/thinking, response completion and clear. There is no mutation observer, continuous scroll enforcement or arbitrary production timeout.

3. Initial load/reload: existing server-rendered history starts at the latest message. Initial positioning also waits for font readiness because late text wrapping can change conversation height. That initial font adjustment is cancelled if the visitor begins interacting with older messages. Empty conversations keep their normal empty state.

4. Send: the existing protected form is posted asynchronously with its unchanged fields and CSRF token. The user message appears immediately, followed by exactly one compact RosaGo is thinking bubble. The composer clears, retains focus without moving the page, and remains available for drafting the next message. Send/Clear are disabled while a request is pending. No new Enter shortcut was added: Enter and Shift+Enter retain textarea newline behavior. Native forms remain the no-JavaScript fallback.

5. Response: the client renders the existing endpoint's escaped HTML history, including its original text and sources. The thinking bubble disappears and the panel scrolls to the bottom of the completed response, including long responses. The existing bounded store remains authoritative. A new draft typed while waiting is preserved. A separate polite live region announces only the latest result/status; historical messages are not made a live region and replies do not steal focus. Known failures restore the draft with compact feedback; unconfirmed responses require reloading instead of blindly repeating a request.

6. Suggested prompts: existing populate-only behavior is preserved. Prompt clicks populate and focus the composer using `preventScroll`; they do not silently submit. Sending the populated prompt then uses the same immediate-user/thinking/reply scrolling behavior as ordinary messages.

7. Scrollbar cleanup: the conversation panel is the sole conversation scroll container. The history list has no independent height cap or overflow scrollbar. Chat height stays bounded, so long replies do not grow the whole page; the composer sits below the panel. Clear uses the existing endpoint asynchronously and resets the empty panel to scrollTop 0. Minor stray closing tags in the touched template were also removed.

8. Mobile: at 390px the newest message/reply is visible internally, composer and Send remain accessible, and there is no horizontal overflow. Browser page scroll remains unchanged. Screenshots: [desktop latest reply](latest-1440.png), [mobile latest reply](latest-390.png), [desktop empty state](empty-1440.png), [mobile empty state](empty-390.png).

9. Files changed by this task:

    - `templates/user/assistant.html`: page assets, stable panel/history/form hooks, separate live announcer and error placement.
    - `static/js/assistant-chat.js`: initial positioning and asynchronous rendering using the existing endpoints.
    - `static/css/assistant-chat.css`: one bounded conversation scroller and responsive sizing.
    - `static/js/user-ui.js`: suggested-prompt focus now uses `preventScroll`.
    - `tests/test_assistant_chat_ui.py`: markup, accessibility, existing form, escaping and unavailable-state checks.
    - `tests/test_public_layout.py`: recognize the page-specific deferred script.
    - `docs/ai-chat-scroll/`: isolated fixture/check scripts, screenshots, results and this report.

10. JavaScript/browser checks: **39 browser checks passed**, no JavaScript exceptions. Desktop 1440px and mobile 390px used real Flask Assistant routes and the existing AssistantStore with isolated Gemini/auth/catalog doubles. Tests covered overflowing history on open/reload, manual reading, immediate user/thinking bubbles, long replies, drafting during a request, live announcements, suggested prompts, failure feedback, clear, keyboard newline behavior, one internal conversation scrollbar, composer visibility and no overflow. All eight measured send/reply, suggested-prompt, failure and clear flows had **0px browser-page scroll delta**. Ordinary sends were also tested with the page already scrolled to 70px. See [browser-results.json](browser-results.json).

    `node --check static/js/assistant-chat.js` and `node --check static/js/user-ui.js` passed. The existing personal-state JavaScript suite passed; see [javascript-tests.txt](javascript-tests.txt).

11. Focused Python tests: **37 passed, 13 subtests passed**. Existing authentication, CSRF/origin, grounded context, response escaping, history bounds, session isolation and Clear behavior remain covered alongside the new presentation contracts. See [focused-tests.txt](focused-tests.txt).

    ```text
    .venv/Scripts/python.exe -m pytest tests/test_assistant_chat_ui.py tests/test_ai_routes.py tests/test_assistant_context_store.py tests/test_final_ui.py -q -p no:cacheprovider --tb=short
    ```

12. Gemini logic unchanged: no changes to application routes, Gemini service, prompts, model configuration, context building, history/store architecture, capabilities or real response content. Recommendation ranking, itinerary adjustment, weather and authentication are unchanged. No live model requests were needed for these deterministic checks.

13. Database unchanged: no SQL, database, migration, Supabase, destination-data or Tourism metadata changes. Existing worktree changes were preserved.

14. `git diff --check`: **passed, exit code 0**. See [diff-check.txt](diff-check.txt).

15. `git status --short --branch`: **dev...origin/dev**, with the pre-existing modified/untracked worktree preserved. Full output: [git-status.txt](git-status.txt). Nothing staged, committed or pushed. The owned isolated browser and loopback fixture server were stopped after verification.

ROSAGO AI CHAT AUTO-SCROLL: READY FOR LIVE VERIFICATION
