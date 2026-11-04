/* Admin disclosures and password visibility. Theme behavior stays in theme.js. */
(() => {
    'use strict';

    const destinationForm = document.querySelector('[data-destination-form]');
    if (destinationForm) {
        const input = destinationForm.querySelector('[data-photo-input]');
        const preview = destinationForm.querySelector('[data-photo-preview]');
        const remove = destinationForm.querySelector('[data-photo-remove]');
        const reset = destinationForm.querySelector('[data-photo-reset]');
        const status = destinationForm.querySelector('[data-photo-status]');
        const originalSubmitLabel = destinationForm.querySelector('button[type="submit"]').textContent;
        let previewUrl;
        function releasePreview() {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            previewUrl = undefined;
        }
        function restoreSaved() {
            releasePreview();
            const src = preview.dataset.savedSrc;
            preview.hidden = !src || Boolean(remove && remove.checked);
            if (src) preview.src = src;
            else preview.removeAttribute('src');
        }
        input.addEventListener('change', () => {
            releasePreview();
            input.setCustomValidity('');
            const file = input.files[0];
            if (!file) { restoreSaved(); reset.hidden = true; return; }
            if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024 || file.size === 0) {
                input.value = '';
                restoreSaved();
                reset.hidden = true;
                status.textContent = 'Choose a non-empty JPG, PNG, or WebP photo no larger than 5 MB.';
                return;
            }
            if (remove) remove.checked = false;
            previewUrl = URL.createObjectURL(file);
            preview.src = previewUrl;
            preview.hidden = false;
            reset.hidden = false;
            status.textContent = 'Replacement selected. Save the destination to upload it.';
        });
        if (remove) remove.addEventListener('change', () => {
            input.value = '';
            reset.hidden = true;
            restoreSaved();
            status.textContent = remove.checked ? 'The saved photo will be removed when you save the destination.' : 'The saved photo will be kept.';
        });
        reset.addEventListener('click', () => {
            input.value = '';
            reset.hidden = true;
            restoreSaved();
            status.textContent = 'Selected replacement cancelled.';
        });
        destinationForm.addEventListener('submit', () => {
            if (!destinationForm.checkValidity()) return;
            const submit = destinationForm.querySelector('button[type="submit"]');
            // Keep successful form controls enabled so multipart data is sent.
            submit.disabled = true;
            submit.textContent = 'Saving destination…';
            destinationForm.setAttribute('aria-busy', 'true');
            status.textContent = input.files.length ? 'Uploading photo and saving destination. Please wait…' : 'Saving destination. Please wait…';
        });
        window.addEventListener('pagehide', releasePreview);
        window.addEventListener('pageshow', event => {
            if (!event.persisted) return;
            const submit = destinationForm.querySelector('button[type="submit"]');
            submit.disabled = false;
            submit.textContent = originalSubmitLabel;
            destinationForm.removeAttribute('aria-busy');
            if (input.files.length) input.dispatchEvent(new Event('change'));
        });
    }
    const passwordToggle = document.querySelector('[data-admin-password-toggle]');
    const passwordField = passwordToggle && document.getElementById(passwordToggle.getAttribute('aria-controls'));
    if (passwordField && passwordField.type === 'password') {
        passwordToggle.hidden = false;
        passwordToggle.addEventListener('click', () => {
            const reveal = passwordField.type === 'password';
            passwordField.type = reveal ? 'text' : 'password';
            passwordToggle.textContent = reveal ? 'Hide' : 'Show';
            passwordToggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
            passwordToggle.setAttribute('aria-pressed', String(reveal));
        });
    }

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
