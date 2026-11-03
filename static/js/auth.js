const form = document.getElementById("registration-form");
const statusMessage = document.getElementById("form-status");
const fields = {
    firstName: document.getElementById("first-name"),
    lastName: document.getElementById("last-name"),
    email: document.getElementById("email"),
    password: document.getElementById("password"),
    confirmPassword: document.getElementById("confirm-password"),
    terms: document.getElementById("terms"),
};
let submitted = false;
let consentInteracted = false;

const passwordPolicy = RosaGoPasswordPolicy.create(fields.password);

function updatePasswordChecklist() {
    passwordPolicy.update();
}

function validationMessage(field) {
    if (field === fields.terms) {
        return field.checked ? "" : "Please agree to the Terms and Privacy Policy.";
    }
    if (!field.value.trim()) {
        const labels = {
            "first-name": "your first name",
            "last-name": "your last name",
            email: "your email address",
            password: "a password",
            "confirm-password": "your password again",
        };
        return `Please enter ${labels[field.id]}.`;
    }
    if (field === fields.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(field.value.trim())) {
        return "Enter a valid email address, such as name@example.com.";
    }
    if (field === fields.password) {
        return passwordPolicy.message();
    }
    if (field === fields.confirmPassword && field.value !== fields.password.value) {
        return "Passwords do not match.";
    }
    return "";
}

function validateField(field) {
    const message = validationMessage(field);
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
        const label = input === fields.password ? "password" : "confirm password";
        button.setAttribute("aria-label", `${show ? "Hide" : "Show"} ${label}`);
        button.setAttribute("aria-pressed", String(show));
    });
});

Object.values(fields).forEach((field) => {
    const onEdit = () => {
        statusMessage.textContent = "";
        delete statusMessage.dataset.state;
        if (field === fields.password) updatePasswordChecklist();
        // Also clear server-rendered errors when editing after a failed POST.
        if (field === fields.terms) consentInteracted = true;
        if (submitted || field.getAttribute('aria-invalid') === 'true'
                || (field === fields.confirmPassword && field.value)
                || (field === fields.terms && consentInteracted)) {
            validateField(field);
        }
        if (field === fields.password && fields.confirmPassword.value) {
            validateField(fields.confirmPassword);
        }
    };
    field.addEventListener("input", onEdit);
    if (field === fields.terms) field.addEventListener("change", onEdit);
});

form.addEventListener("submit", (event) => {
    submitted = true;
    passwordPolicy.update();
    const invalidFields = Object.values(fields).filter((field) => !validateField(field));
    if (invalidFields.length) {
        event.preventDefault();
        statusMessage.textContent = "";
        delete statusMessage.dataset.state;
        invalidFields[0].focus();
        return;
    }
    // Let the browser POST valid details to Flask for server-side validation.
    document.getElementById("create-account").disabled = true;
    statusMessage.textContent = "Creating your account…";
});

updatePasswordChecklist();
if (statusMessage.textContent.trim()) {
    statusMessage.focus();
} else {
    Object.values(fields).find(field => field.getAttribute('aria-invalid') === 'true')?.focus();
}

window.addEventListener("pageshow", () => {
    document.getElementById("create-account").disabled = false;
    updatePasswordChecklist();
});
