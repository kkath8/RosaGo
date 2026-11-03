RosaGo Explore alignment and Save UX — local verification report

1. Sidebar root cause: the content already used a two-column grid with start alignment. Its sticky sidebar had a 190px top inset, which pushed it below the results as the content row moved upward. The browser reproduced a panel top of 190px versus results at 129.8px with that old rule.

2. Alignment fix: retain the existing content row and sticky sidebar, reduce the sticky inset to 96px (below the current header), explicitly align the panel at the start, and remove panel margins. Initial left/right top edges align; the old-offset reproduction also aligns after applying the correction. No negative margins or vertical-centering patches were added. Result count keeps a compact 12px bottom gap and aligns with the first card column.

3. Save jump root cause: existing localStorage persistence dispatches `rosago:personal`. The shared refresh handler then called Explore filtering, which unconditionally appended every destination node back into the grid. That moved all rows through the DOM during each Save and could disrupt layout and browser scroll anchoring. Save was already a non-submitting button; it needed a stable update path.

4. In-place Save: Explore Save explicitly prevents default behavior, uses the existing saved-place toggle, and skips reapplying Explore filters during that synchronous storage update. Card label, `aria-pressed` and counts still refresh. The generic filter/sort routine now moves a node only if its position actually differs. No navigation, page reload, Trip Bag opening or forced scroll restoration was introduced. Storage failures roll back the saved selection and show a short toast while keeping position and cards intact.

5. Persistence: unchanged `RosaGoPersonal` account/guest-scoped localStorage remains the only saved-place mechanism. Save and Unsave work; browser checks verify Saved initializes after a page refresh for both search results and All. No new storage, API or backend contract was added.

6. Filter/search preservation: real mouse clicks on Dining and Heritage results preserve active category, query, sort setting, weather filter value, URL and the exact destination rows. Saved-only Unsave keeps the focused card in place; changing filters afterward reevaluates results normally. Trip Bag state is unchanged by Save/Unsave.

7. Scroll verification: **18 measured interactions, all with a 0px scrollY delta** at 1440px and 390px. These include Save/Unsave after scrolling several rows, search results, All, keyboard activation, storage failure, and Saved-only Unsave. Grid child nodes and clicked-card identity also remain unchanged. See [browser-results.json](browser-results.json).

8. Card actions: View Details and Save now share one compact action row anchored near the bottom of the card body. Save and Saved use a fixed minimum width, preserving button dimensions and card height. Descriptions retain their existing truncation. The three-column desktop grid is unchanged.

9. Mobile: 390px cards remain stacked, category/search controls work, Save updates without a jump, and the page remains 390px wide with no horizontal overflow. Keyboard focus stays on the Save control. Screenshots: [desktop layout](layout-1440.png), [desktop saved card](saved-1440.png), [mobile layout](layout-390.png), [mobile saved card](saved-390.png).

10. Files changed by this task:

    - `templates/places/list.html`: shared destination action row.
    - `static/css/tourism.css`: sticky/start alignment, count spacing and Explore action-row styles.
    - `static/js/user-ui.js`: stable grid updates and in-place Explore Save with rollback feedback.
    - `tests/test_explore_save_ui.py`: new Explore structure and button contracts.
    - `tests/test_personal_state.js`: refresh persistence, Save/Unsave and Trip Bag separation assertions.
    - `docs/explore-save-ux/`: report, isolated browser fixture/check scripts, screenshots and verification logs.

11. Focused Python tests: **56 passed, 108 subtests passed**. Includes the new Explore UI contracts and existing category/search combinations, draft/archived exclusions, catalog pagination, publication validation and saved/trip feature boundaries. See [focused-tests.txt](focused-tests.txt).

    ```text
    .venv/Scripts/python.exe -m pytest tests/test_explore_save_ui.py tests/test_interaction_polish.py tests/test_places_routes.py tests/test_places_service.py tests/test_user_features.py -q -p no:cacheprovider --tb=short
    ```

12. JavaScript/browser: the existing personal-state JavaScript suite passes with added persistence/separation assertions. `node --check static/js/user-ui.js` passes. **125 browser checks passed**, no JavaScript exceptions. Actual Flask routes, published-only catalog service, CSS and JavaScript ran against 54 synthetic published records plus excluded draft/archived records in an isolated GET-only fixture. Mouse and keyboard events exercised the existing localStorage implementation. No live destination records were changed. See [javascript-tests.txt](javascript-tests.txt) and [browser-results.json](browser-results.json).

13. Database unchanged: no Supabase changes, SQL, migrations or destination-record edits. Tourism metadata, weather, authentication, Gemini and Planner/Preview were untouched by this task. Existing worktree changes were preserved.

14. Ranking unchanged: no recommendation ranking, selection or itinerary behavior changes.

15. `git diff --check`: **passed, exit code 0**. See [diff-check.txt](diff-check.txt).

16. `git status --short --branch`: **dev...origin/dev**, with pre-existing modified/untracked files preserved. Full output: [git-status.txt](git-status.txt). Nothing staged, committed or pushed. The owned browser and loopback fixture server were stopped after verification.

ROSAGO EXPLORE SAVE UX: READY FOR LIVE VERIFICATION
