(() => {
    'use strict';
    const button = document.getElementById('verification-resend');
    if (!button) return;
    const seconds = Number(button.dataset.cooldown);
    if (!Number.isFinite(seconds) || seconds < 0) return;
    const deadline = Date.now() + seconds * 1000;
    function update() {
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        button.disabled = remaining > 0;
        button.textContent = remaining ? `Resend code in ${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}` : 'Resend verification code';
        if (remaining) window.setTimeout(update, 250);
    }
    update();
})();
