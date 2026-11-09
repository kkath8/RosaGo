/* Browser-local Admin display defaults. Never an account or security authority. */
(() => {
    'use strict';
    const key = 'rosago.admin.preferences.v1';
    const choices = {
        density: ['comfortable', 'compact'], reduceMotion: [false, true],
        reviewAlerts: [true, false], successNotices: [true, false],
        sort: ['slug', 'newest', 'oldest', 'name'], pageSize: ['25', '10', '50'],
        status: ['all', 'published', 'draft', 'archived'],
        timeFormat: ['12', '24'], dateFormat: ['dmy', 'mdy', 'iso']
    };
    const defaults = () => Object.fromEntries(Object.entries(choices).map(([name, values]) => [name, values[0]]));
    function decode(raw) {
        try {
            if (typeof raw !== 'string' || raw.length > 2048) return defaults();
            const value = JSON.parse(raw);
            if (!value || typeof value !== 'object' || Array.isArray(value)) return defaults();
            return Object.fromEntries(Object.entries(choices).map(([name, values]) =>
                [name, values.includes(value[name]) ? value[name] : values[0]]));
        } catch (_) { return defaults(); }
    }
    let preferences = defaults();
    try { preferences = decode(localStorage.getItem(key)); } catch (_) { /* Display defaults remain usable. */ }
    const root = document.documentElement;
    function apply() {
        root.dataset.adminDensity = preferences.density;
        root.dataset.adminReduceMotion = String(preferences.reduceMotion);
        root.dataset.adminReviewAlerts = preferences.reviewAlerts ? 'show' : 'hide';
        root.dataset.adminSuccessNotices = preferences.successNotices ? 'show' : 'hide';
        formatDates();
    }
    function formatDates() {
        for (const node of document.querySelectorAll('[data-admin-date]')) {
            const raw = node.getAttribute('datetime');
            // Only timezone-qualified timestamps; never interpret a date in the device's timezone.
            if (!raw || !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(raw)) continue;
            const value = new Date(raw);
            if (Number.isNaN(value.getTime())) continue;
            const zone = {timeZone: 'Asia/Manila'};
            let date;
            if (preferences.dateFormat === 'iso') {
                const parts = new Intl.DateTimeFormat('en-GB', {...zone, year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts(value);
                const part = name => parts.find(item => item.type === name).value;
                date = `${part('year')}-${part('month')}-${part('day')}`;
            } else {
                date = new Intl.DateTimeFormat(preferences.dateFormat === 'mdy' ? 'en-US' : 'en-GB',
                    {...zone, day:'2-digit', month:'short', year:'numeric'}).format(value);
            }
            const time = new Intl.DateTimeFormat('en-GB', {...zone, hour:'2-digit', minute:'2-digit', second:'2-digit',
                hour12: preferences.timeFormat === '12'}).format(value).toUpperCase();
            node.textContent = node.dataset.adminDate === 'split' ? date : `${date} · ${time}`;
            if (node.dataset.adminDate === 'split') {
                const clock = document.createElement('span');
                clock.className = 'admin-audit-subline'; clock.textContent = time; node.append(clock);
            }
            node.setAttribute('title', 'Asia/Manila · ' + raw);
        }
    }
    function reflect(form) {
        if (!form) return;
        for (const name of Object.keys(choices)) {
            const control = form.elements.namedItem(name);
            if (typeof preferences[name] === 'boolean') control.checked = preferences[name];
            else control.value = preferences[name];
        }
    }
    function catalogDefaults() {
        const catalog = document.querySelector('[data-admin-catalog]');
        if (!catalog) return;
        const url = new URL(window.location.href);
        const params = url.searchParams;
        // A pagination URL already represents a chosen view, including implicit defaults.
        if (params.has('offset')) return;
        const bare = !url.search;
        let changed = false;
        for (const [name, value, baseline] of [['sort', preferences.sort, 'slug'], ['page_size', preferences.pageSize, '25']]) {
            if (!params.has(name) && value !== baseline) { params.set(name, value); changed = true; }
        }
        if (bare && preferences.status !== 'all') { params.set('status', preferences.status); changed = true; }
        if (changed) window.location.replace(url.pathname + '?' + params.toString() + url.hash);
    }
    apply();
    document.addEventListener('DOMContentLoaded', () => {
        apply(); catalogDefaults();
        const form = document.querySelector('[data-admin-preferences-form]');
        reflect(form);
        if (!form) return;
        const save = form.querySelector('[data-save-preferences]');
        const status = form.querySelector('[data-preferences-status]');
        save.disabled = false;
        form.addEventListener('change', () => {
            status.dataset.state = 'pending';
            status.textContent = 'Unsaved changes. Select Save Preferences to apply them.';
        });
        form.addEventListener('submit', event => {
            event.preventDefault();
            const candidate = {};
            for (const [name, values] of Object.entries(choices)) {
                const control = form.elements.namedItem(name);
                candidate[name] = typeof values[0] === 'boolean' ? control.checked : control.value;
                if (!values.includes(candidate[name])) { status.dataset.state = 'error'; status.textContent = 'Choose supported preference values before saving.'; return; }
            }
            try {
                const encoded = JSON.stringify(candidate);
                localStorage.setItem(key, encoded);
                if (localStorage.getItem(key) !== encoded) throw new Error('Unconfirmed write');
            } catch (_) {
                status.dataset.state = 'error';
                status.textContent = 'Could not confirm preferences were saved. Current workspace preferences have not changed.';
                return;
            }
            preferences = candidate; apply();
            status.dataset.state = 'success';
            status.textContent = 'Preferences saved in this browser. Destination defaults apply when you next open Destinations.';
        });
    });
    window.addEventListener('storage', event => {
        if (event.key !== key && event.key !== null) return;
        preferences = decode(event.key === null ? null : event.newValue);
        apply(); reflect(document.querySelector('[data-admin-preferences-form]'));
        const status = document.querySelector('[data-preferences-status]');
        if (status) { status.dataset.state = 'info'; status.textContent = 'Workspace preferences changed in another tab. Review the current values.'; }
    });
})();
