/* Admin disclosures only. Theme behavior remains in the shared theme.js. */
(() => {
    'use strict';
    const selector = '.admin-header details';
    document.addEventListener('toggle', event => {
        if (!event.target.matches(selector) || !event.target.open) return;
        for (const item of document.querySelectorAll(selector)) {
            if (item !== event.target) item.open = false;
        }
    }, true);
    document.addEventListener('click', event => {
        for (const item of document.querySelectorAll(selector)) {
            if (!item.contains(event.target)) item.open = false;
        }
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        for (const item of document.querySelectorAll(selector + '[open]')) {
            item.open = false;
            item.querySelector('summary').focus();
        }
    });
})();
