const loginForm = document.getElementById("login-form");
const emailInput = document.getElementById("login-email");
const passwordInput = document.getElementById("login-password");
const passwordToggle = document.getElementById("login-password-toggle");
const loginStatus = document.getElementById("login-status");
let submitted = false;

function validateLoginField(field) {
    let message = "";
    if (!field.value.trim()) {
        message = field === emailInput ? "Please enter your email address." : "Please enter your password.";
    } else if (field === emailInput && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(field.value.trim())) {
        message = "Enter a valid email address, such as name@example.com.";
    }
    const error = document.getElementById(`${field.id}-error`);
    error.textContent = message;
    error.hidden = !message;
    field.setAttribute("aria-invalid", String(Boolean(message)));
    return !message;
}

passwordToggle.addEventListener("click", () => {
    const show = passwordInput.type === "password";
    passwordInput.type = show ? "text" : "password";
    passwordToggle.textContent = show ? "Hide" : "Show";
    passwordToggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
    passwordToggle.setAttribute("aria-pressed", String(show));
});

[emailInput, passwordInput].forEach((field) => {
    field.addEventListener("input", () => {
        loginStatus.textContent = "";
        delete loginStatus.dataset.state;
        if (submitted) validateLoginField(field);
    });
});

loginForm.addEventListener("submit", (event) => {
    submitted = true;
    const invalidFields = [emailInput, passwordInput].filter((field) => !validateLoginField(field));
    if (invalidFields.length) {
        event.preventDefault();
        loginStatus.dataset.state = "error";
        loginStatus.textContent = "Please correct the highlighted fields and try again.";
        invalidFields[0].focus();
        return;
    }
    // Valid details are posted to Flask for server-side validation and authentication.
    document.getElementById("login-submit").disabled = true;
    delete loginStatus.dataset.state;
    loginStatus.textContent = "Checking your login…";
});

if (loginStatus.textContent.trim()) {
    loginStatus.focus();
}

window.addEventListener("pageshow", () => {
    document.getElementById("login-submit").disabled = false;
});
