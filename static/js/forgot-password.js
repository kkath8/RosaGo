const recoveryForm = document.getElementById("forgot-password-form");
const recoveryEmail = document.getElementById("recovery-email");
const recoveryError = document.getElementById("recovery-email-error");
const recoveryStatus = document.getElementById("recovery-status");
const recoveryButton = document.getElementById("send-reset-link");
let submitted = false;
let processing = false;

function validateRecoveryEmail() {
    const email = recoveryEmail.value.trim();
    let message = "";
    if (!email) {
        message = "Please enter your email address.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        message = "Enter a valid email address, such as name@example.com.";
    }
    recoveryError.textContent = message;
    recoveryError.hidden = !message;
    recoveryEmail.setAttribute("aria-invalid", String(Boolean(message)));
    return !message;
}

recoveryForm.addEventListener("submit", (event) => {
    if (processing) {
        event.preventDefault();
        return;
    }
    submitted = true;
    if (!validateRecoveryEmail()) {
        event.preventDefault();
        recoveryStatus.dataset.state = "error";
        recoveryStatus.textContent = "Please correct your email address and try again.";
        recoveryEmail.focus();
        return;
    }
    // Allow a normal POST to Flask; only the server contacts Supabase.
    processing = true;
    recoveryButton.disabled = true;
    recoveryButton.textContent = "Sending…";
    recoveryForm.setAttribute("aria-busy", "true");
    delete recoveryStatus.dataset.state;
    recoveryStatus.textContent = "Processing your request…";
});

recoveryEmail.addEventListener("input", () => {
    recoveryStatus.textContent = "";
    delete recoveryStatus.dataset.state;
    if (submitted) validateRecoveryEmail();
});

if (recoveryStatus.textContent.trim()) {
    recoveryStatus.focus();
}

window.addEventListener("pageshow", () => {
    processing = false;
    recoveryButton.disabled = false;
    recoveryButton.textContent = "Send Reset Link";
    recoveryForm.setAttribute("aria-busy", "false");
});
