/* Progressive enhancement: existing POST forms remain the source of truth. */
(() => {
    'use strict';
    let pending = false;
    document.addEventListener('click', (event) => {
        const opener = event.target.closest('[data-open-save], [data-open-weather]');
        if (opener) {
            const panel = document.querySelector(opener.getAttribute('href'));
            if (panel) {
                event.preventDefault();
                panel.open = true;
                panel.scrollIntoView({ block: 'nearest' });
                (panel.querySelector('input:not([type="hidden"])') || panel.querySelector('summary')).focus();
            }
        }
        const quick = event.target.closest('[data-ai-prompt]');
        if (!quick || pending) return;
        const input = document.querySelector('#preview-adjust-message');
        input.value = quick.dataset.aiPrompt;
        input.focus();
        if (quick.dataset.aiPrompt === 'Make it 2 places') input.form.requestSubmit();
    });
    document.addEventListener('submit', async (event) => {
        const form = event.target.closest('[data-ai-form]');
        if (!form || !window.fetch) return;
        event.preventDefault();
        if (pending) return;
        pending = true;
        const page = document.querySelector('.preview-page');
        const thread = page.querySelector('.preview-chat');
        const oldBubbles = [...thread.children].map((bubble) => bubble.cloneNode(true));
        const progress = page.querySelector('.preview-ai-progress');
        const data = new FormData(form);
        page.querySelectorAll('button').forEach((button) => { button.disabled = true; });
        page.setAttribute('aria-busy', 'true');
        progress.hidden = false;
        try {
            const response = await fetch(form.action, { method: 'POST', body: data, credentials: 'same-origin' });
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            const html = new DOMParser().parseFromString(await response.text(), 'text/html');
            const updated = html.querySelector('.preview-page');
            const updatedThread = updated?.querySelector('.preview-chat');
            if (!updated || !updatedThread) throw new Error('Request could not be completed');
            const changed = updated.dataset.revision !== page.dataset.revision;
            const history = oldBubbles.filter((bubble) => !changed || bubble.dataset.messageKind !== 'explanation');
            updatedThread.prepend(...history.slice(-12));
            updatedThread.hidden = !updatedThread.children.length;
            page.replaceWith(updated);
            updatedThread.scrollTop = updatedThread.scrollHeight;
            if (changed) {
                updated.querySelector('#recommended-title').setAttribute('tabindex', '-1');
                updated.querySelector('#recommended-title').focus();
            } else {
                updated.querySelector('#preview-adjust-message')?.focus({ preventScroll: true });
            }
        } catch (_) {
            // A failed response may follow a successful write. Reload before retrying.
            progress.textContent = 'We could not confirm the result. Reload this preview before trying again.';
            const reload = document.createElement('a');
            reload.href = window.location.pathname;
            reload.textContent = ' Reload preview';
            progress.append(reload);
            progress.dataset.failed = 'true';
        } finally {
            pending = false;
            page.removeAttribute('aria-busy');
            if (!progress.dataset.failed) {
                progress.hidden = true;
                page.querySelectorAll('button').forEach((button) => { button.disabled = false; });
            }
        }
    });
})();
