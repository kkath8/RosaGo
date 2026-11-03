/* Presentation only: post existing protected forms and render their HTML result. */
(() => {
    'use strict';
    const panel = document.querySelector('[data-chat-panel]');
    const messages = document.querySelector('[data-chat-messages]');
    const send = document.querySelector('[data-chat-send]');
    const clear = document.querySelector('[data-chat-clear]');
    if (!panel || !messages || !send || !clear) return;
    const composer = send.elements.message;
    const sendButton = send.querySelector('[type=submit]');
    const clearButton = clear.querySelector('[type=submit]');
    const announcement = document.querySelector('[data-chat-announcement]');
    const available = !sendButton.disabled;
    let pending = false, uncertain = false, initialRender = true;
    function latest() {
        requestAnimationFrame(() => { panel.scrollTop = panel.scrollHeight; });
    }
    function busy(value) {
        pending = value;
        sendButton.disabled = value || !available || uncertain;
        clearButton.disabled = value;
        panel.setAttribute('aria-busy', String(value));
    }
    function bubble(role, text, extra = '') {
        const row = document.createElement('li');
        row.className = 'chat-message chat-' + role + (extra ? ' ' + extra : '');
        const speaker = document.createElement('span'); speaker.className = 'chat-speaker';
        speaker.textContent = role === 'user' ? 'You' : 'RosaGo';
        const body = document.createElement('p'); body.textContent = text;
        row.append(speaker, body); messages.append(row); return row;
    }
    function sync(page) {
        const returned = page.querySelector('[data-chat-messages]');
        messages.replaceChildren(...returned.children);
        panel.querySelector('[data-chat-server-error]')?.remove();
        panel.querySelector('[data-chat-empty]')?.remove();
        const empty = page.querySelector('[data-chat-empty]');
        if (empty) panel.append(empty);
        for (const [form, selector] of [[send, '[data-chat-send]'], [clear, '[data-chat-clear]']]) {
            const token = page.querySelector(selector)?.elements.csrf_token.value;
            if (token) form.elements.csrf_token.value = token;
        }
    }
    async function submit(form, data) {
        const response = await fetch(form.action, { method: 'POST', body: data, credentials: 'same-origin', headers: { Accept: 'text/html' } });
        if (response.redirected && new URL(response.url).pathname !== new URL(send.action).pathname) {
            window.location.assign(response.url);
            throw new Error('Please sign in to continue.');
        }
        const page = new DOMParser().parseFromString(await response.text(), 'text/html');
        if (!page.querySelector('[data-chat-messages]')) throw new Error('The conversation could not be confirmed. Reload it before sending again.');
        const error = page.querySelector('[data-chat-server-error]');
        if (!response.ok || error) {
            const failure = new Error(error?.textContent || 'This request could not be completed. Please reload the conversation.');
            failure.known = !!error; throw failure;
        }
        return page;
    }
    latest();
    // Web fonts can change wrapping after the first paint. Finish only the
    // initial positioning, and stop if the visitor starts reading older rows.
    for (const name of ['wheel', 'touchstart', 'pointerdown', 'keydown']) {
        panel.addEventListener(name, () => { initialRender = false; }, { once: true, passive: true });
    }
    document.fonts?.ready.then(() => { if (initialRender) latest(); });
    if (!window.fetch) return; // Native protected forms remain the fallback.
    send.addEventListener('submit', async event => {
        event.preventDefault();
        if (pending || uncertain || !available || !composer.value.trim()) return;
        initialRender = false;
        const text = composer.value;
        const data = new FormData(send);
        panel.querySelector('[data-chat-empty]')?.remove();
        const user = bubble('user', text);
        const thinking = bubble('assistant', 'RosaGo is thinking…', 'chat-loading');
        thinking.dataset.chatLoading = '';
        composer.value = ''; composer.focus({ preventScroll: true });
        announcement.textContent = 'RosaGo is thinking…'; busy(true); latest();
        try {
            const page = await submit(send, data);
            sync(page);
            const replies = messages.querySelectorAll('.chat-assistant');
            announcement.textContent = replies[replies.length - 1]?.querySelector('p')?.textContent || 'Reply received.';
        } catch (error) {
            thinking.remove(); user.querySelector('.chat-speaker').textContent = error.known ? 'You · not sent' : 'You · unconfirmed';
            uncertain = !error.known;
            const text = error.known ? error.message : 'The reply could not be confirmed. Reload the conversation before sending again.';
            const row = bubble('assistant', text, 'chat-error');
            if (uncertain) { const reload = document.createElement('a'); reload.href = send.action; reload.textContent = 'Reload conversation'; row.append(reload); }
            if (!composer.value) composer.value = data.get('message');
            announcement.textContent = text;
        } finally {
            busy(false); latest();
            // Preserve a draft typed while waiting, without moving page focus.
            if (document.activeElement === composer) composer.focus({ preventScroll: true });
        }
    });
    clear.addEventListener('submit', async event => {
        event.preventDefault(); if (pending) return;
        initialRender = false;
        const data = new FormData(clear); busy(true);
        try {
            const page = await submit(clear, data); sync(page); uncertain = false;
            composer.value = ''; announcement.textContent = 'Conversation cleared.';
            composer.focus({ preventScroll: true });
        } catch (_) {
            bubble('assistant', 'The conversation could not be cleared. Reload it before trying again.', 'chat-error');
            announcement.textContent = 'The conversation could not be cleared.';
        } finally { busy(false); latest(); }
    });
})();
