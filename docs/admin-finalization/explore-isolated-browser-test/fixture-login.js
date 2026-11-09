// Public dummy fixture constants only. Does not read/log existing credentials or submit.
(() => {
    'use strict';
    if (location.origin !== 'http://127.0.0.1:5096' || location.pathname !== '/admin/login') return;
    const button = document.getElementById('fill-synthetic-admin');
    const form = document.querySelector('form.admin-login-form');
    const status = document.getElementById('synthetic-fill-status');
    if (!button || !form || !status) return;
    button.addEventListener('click', () => {
        form.elements.email.value = 'admin-b@example.invalid';
        form.elements.password.value = 'Local-test-password-1!';
        form.elements.email.dispatchEvent(new Event('input', {bubbles: true}));
        form.elements.password.dispatchEvent(new Event('input', {bubbles: true}));
        status.textContent = 'Synthetic fixture values filled. Click the existing Log In button once.';
    });
})();
