const resetForm = document.getElementById("reset-password-form");
const newPassword = document.getElementById("new-password");
const confirmPassword = document.getElementById("confirm-new-password");
const resetStatus = document.getElementById("reset-status");
let submitted = false;

function validatePassword(field) {
    let message = "";
    if (!field.value.trim()) {
        message = field === newPassword ? "Please enter a new password." : "Please confirm your new password.";
    } else if (field === newPassword && field.value.length < 8) {
        message = "Use at least 8 characters for your password.";
    } else if (field === confirmPassword && field.value !== newPassword.value) {
        message = "Passwords do not match. Enter the same password in both fields.";
    }
    const error = document.getElementById(`${field.id}-error`);
    error.textContent = message;
    error.hidden = !message;
    field.setAttribute("aria-invalid", String(Boolean(message)));
    return !message;
}

document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const input = document.getElementById(button.getAttribute("aria-controls"));
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        button.textContent = show ? "Hide" : "Show";
        const label = input === newPassword ? "new password" : "password confirmation";
        button.setAttribute("aria-label", `${show ? "Hide" : "Show"} ${label}`);
        button.setAttribute("aria-pressed", String(show));
    });
});

[newPassword, confirmPassword].forEach((field) => {
    field.addEventListener("input", () => {
        resetStatus.textContent = "";
        delete resetStatus.dataset.state;
        if (submitted) {
            validatePassword(field);
            if (field === newPassword && confirmPassword.value) validatePassword(confirmPassword);
        }
    });
});

resetForm.addEventListener("submit", (event) => {
    submitted = true;
    const invalid = [newPassword, confirmPassword].filter((field) => !validatePassword(field));
    if (invalid.length) {
        event.preventDefault();
        resetStatus.dataset.state = "error";
        resetStatus.textContent = "Please correct the highlighted fields and try again.";
        invalid[0].focus();
        return;
    }
    document.getElementById("reset-submit").disabled = true;
    resetStatus.textContent = "Updating your password?";
});

document.getElementById("reset-submit").disabled = false;
