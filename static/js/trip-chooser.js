/* A progressive dialog over the existing authenticated chooser and trip forms. */
(() => {
    'use strict';
    const dialog = document.querySelector('#trip-chooser');
    if (!dialog || !dialog.showModal || !window.fetch) return;
    const form = dialog.querySelector('[data-chooser-form]');
    const createForm = dialog.querySelector('[data-chooser-create-form]');
    const list = dialog.querySelector('[data-chooser-list]');
    const status = dialog.querySelector('[data-chooser-status]');
    const more = dialog.querySelector('[data-chooser-more]');
    let origin, endpoint, nextUrl, busy = false, generation = 0, loaded = false, addUncertain = false, createUncertain = false;
    const message = text => { status.textContent = text; status.hidden = !text; };
    const lock = value => {
        busy = value;
        dialog.querySelectorAll('button,input').forEach(node => { node.disabled = value; });
        if (!value && addUncertain) form.querySelector('[type=submit]').disabled = true;
        if (!value && createUncertain) createForm.querySelector('[type=submit]').disabled = true;
        if (!value && !loaded) {
            form.querySelector('[type=submit]').disabled = true;
            dialog.querySelector('[data-chooser-create]').disabled = true;
            createForm.querySelector('[type=submit]').disabled = true;
        }
        dialog.setAttribute('aria-busy', String(value));
    };
    function option(trip, selected = false) {
        const row = document.createElement('label'); row.className = 'trip-choice';
        const input = document.createElement('input');
        input.type = 'radio'; input.name = 'trip_id'; input.value = trip.id; input.required = true; input.checked = selected;
        const copy = document.createElement('span'); copy.className = 'trip-choice-copy';
        const name = document.createElement('strong'); name.textContent = trip.name;
        const date = document.createElement('span'); date.className = 'trip-choice-date'; date.textContent = trip.date_label;
        copy.append(name, date); row.append(input, copy); return row;
    }
    async function request(url, options = {}) {
        const response = await fetch(url, { credentials: 'same-origin', ...options, headers: { Accept: 'application/json' } });
        if (response.redirected) { window.location.assign(response.url); throw new Error('Please sign in to continue.'); }
        const json = response.headers.get('content-type')?.includes('application/json');
        let result;
        try { result = json ? await response.json() : null; }
        catch (_) {
            const error = new Error(options.method === 'POST' ? 'This change could not be confirmed. Check My Trips before trying again.' : 'Could not load your trips. Please try again.');
            error.uncertain = options.method === 'POST'; throw error;
        }
        if (!response.ok || !json) {
            const error = new Error(result?.message || (response.status === 403 ? 'Please reload this page and try again.' :
                response.status === 404 ? 'This trip or destination is no longer available.' :
                response.status >= 500 ? 'This change could not be confirmed. Check My Trips before trying again.' : 'Please check your selection and try again.'));
            error.uncertain = options.method === 'POST' && (response.status >= 500 || response.ok);
            throw error;
        }
        return result;
    }
    function close() {
        if (busy) return;
        generation++;
        dialog.close();
        origin?.element?.focus({ preventScroll: true });
        if (origin) window.scrollTo(origin.x, origin.y);
    }
    async function open(url, element) {
        if (dialog.open) return;
        origin = { element, x: window.scrollX, y: window.scrollY };
        endpoint = url; const current = ++generation; loaded = false; addUncertain = false; createUncertain = false;
        form.reset(); createForm.reset(); list.replaceChildren();
        form.hidden = false; createForm.hidden = true; more.hidden = true;
        dialog.querySelector('[data-chooser-name]').textContent = '';
        dialog.querySelector('[data-chooser-meta]').textContent = '';
        message('Loading your trips…'); dialog.showModal(); lock(true);
        try {
            const data = await request(endpoint);
            if (current !== generation) return;
            dialog.querySelector('[data-chooser-name]').textContent = data.place.name;
            const labels = { attraction:'Attractions', dining:'Dining', shopping:'Shopping', accommodation:'Accommodation', nature:'Nature', heritage:'Heritage', industrial:'Industrial Tourism' };
            dialog.querySelector('[data-chooser-meta]').textContent = [labels[data.place.category], data.place.address].filter(Boolean).join(' · ');
            form.action = endpoint; form.elements.csrf_token.value = data.csrf_token;
            createForm.action = data.create_url; createForm.elements.csrf_token.value = data.csrf_token;
            for (const trip of data.trips) list.append(option(trip));
            nextUrl = data.next_url; more.hidden = !nextUrl;
            loaded = true;
            message(data.trips.length ? '' : 'No trips yet. Create a trip to add this destination.');
        } catch (error) { message(error.message); }
        finally { lock(false); }
    }
    document.addEventListener('click', event => {
        const trigger = event.target.closest('[data-add-to-trip]');
        if (!trigger || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button) return;
        event.preventDefault(); open(trigger.href, trigger);
    });
    dialog.addEventListener('click', event => {
        if (event.target.closest('[data-chooser-close]')) close();
        if (event.target.closest('[data-chooser-create]') && !busy) {
            form.hidden = true; createForm.hidden = false; message(''); createForm.elements.name.focus();
        }
        if (event.target.closest('[data-chooser-back]') && !busy) {
            form.hidden = false; createForm.hidden = true; message(''); dialog.querySelector('[data-chooser-create]').focus();
        }
    });
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    form.addEventListener('change', event => {
        if (event.target.name === 'trip_id' && !form.querySelector('[type=submit]').disabled) message('');
    });
    more.addEventListener('click', async () => {
        if (busy || !nextUrl) return;
        lock(true);
        try { const data = await request(nextUrl); for (const trip of data.trips) list.append(option(trip)); nextUrl = data.next_url; more.hidden = !nextUrl; message(''); }
        catch (error) { message(error.message); }
        finally { lock(false); }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (busy || !loaded || addUncertain) return;
        if (!form.querySelector('[name=trip_id]:checked')) { message('Please choose a trip.'); list.querySelector('input')?.focus(); return; }
        const data = new FormData(form); lock(true); message('Adding destination…');
        let uncertain = false;
        try {
            const result = await request(endpoint, { method: 'POST', body: data });
            lock(false); close();
            const toast = document.querySelector('#ui-toast');
            if (toast) { toast.textContent = result.message; toast.hidden = false; setTimeout(() => { toast.hidden = true; }, 4500); }
        } catch (error) {
            message(error.message || 'This change could not be confirmed. Check My Trips before trying again.');
            uncertain = error.uncertain || error instanceof TypeError;
        } finally { addUncertain = uncertain; lock(false); }
    });
    createForm.addEventListener('submit', async event => {
        event.preventDefault(); if (busy || !loaded || createUncertain) return;
        const data = new FormData(createForm); let uncertain = false; lock(true); message('Creating your trip…');
        try {
            const result = await request(createForm.action, { method: 'POST', body: data });
            form.querySelectorAll('[name=trip_id]').forEach(input => { input.checked = false; });
            list.prepend(option(result.trip, true));
            form.hidden = false; createForm.hidden = true;
            message('Trip created. Choose Add to Trip to add this destination.');
        } catch (error) {
            message(error.message || 'This change could not be confirmed. Check My Trips before trying again.');
            uncertain = error.uncertain || error instanceof TypeError;
        } finally { createUncertain = uncertain; lock(false); }
    });
    const fallback = document.querySelector('[data-trip-chooser-page]');
    if (fallback) open(fallback.dataset.tripChooserPage, null);
})();
