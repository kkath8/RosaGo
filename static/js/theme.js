/* Presentation only: one validated device preference, applied before paint. */
(() => {
    'use strict';
    const key = 'rosago.theme.v1';
    const valid = value => value === 'light' || value === 'dark';
    const root = document.documentElement;
    let current = 'light';
    try { const saved = localStorage.getItem(key); if (valid(saved)) current = saved; } catch (_) { /* Storage may be unavailable. */ }
    root.dataset.theme = current;
    function reflect() {
        for (const button of document.querySelectorAll('[data-set-theme]')) {
            button.setAttribute('aria-pressed', String(button.dataset.setTheme === current));
        }
    }
    function apply(value, save) {
        if (!valid(value)) return;
        current = value;
        root.dataset.theme = current;
        let persisted = true;
        if (save) { try { localStorage.setItem(key, current); } catch (_) { persisted = false; } }
        reflect();
        const status = document.querySelector('[data-theme-status]');
        if (save && status) status.textContent = persisted ?
            (current === 'dark' ? 'Dark' : 'Light') + ' theme saved on this device.' :
            'Theme applied. Your browser could not remember it for your next visit.';
    }
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-set-theme]');
        if (button) apply(button.dataset.setTheme, true);
    });
    document.addEventListener('DOMContentLoaded', reflect);
    window.addEventListener('storage', event => {
        if (event.key === key) apply(valid(event.newValue) ? event.newValue : 'light', false);
        else if (event.key === null) apply('light', false);
    });
})();
