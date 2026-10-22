// Run with: node tests/test_recovery_frontend.js
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const readScript = (name) => fs.readFileSync(path.join(__dirname, "../static/js", name), "utf8");

function mockDocument() {
    const elements = new Map();
    const get = (id) => {
        if (!elements.has(id)) elements.set(id, {
            id, value: "", type: "password", textContent: "", dataset: {}, attrs: {}, events: {},
            addEventListener(type, fn) { this.events[type] = fn; },
            setAttribute(key, value) { this.attrs[key] = value; },
            getAttribute(key) { return this.attrs[key]; },
            focus() { this.focused = true; },
        });
        return elements.get(id);
    };
    return { get, elements };
}

function testForm() {
    const { get, elements } = mockDocument();
    const unexpectedSubmission = () => assert.fail('JavaScript initiated a submission or timer');
    get('reset-password-form').submit = unexpectedSubmission;
    get('reset-password-form').requestSubmit = unexpectedSubmission;
    const toggles = ["new-password", "confirm-new-password"].map((id) => {
        const button = get(`${id}-toggle`);
        button.attrs["aria-controls"] = id;
        return button;
    });
    // No fetch/storage APIs: validation must never need them.
    vm.runInNewContext(readScript("reset-password.js"), {
        document: { getElementById: get, querySelectorAll: () => toggles },
        fetch: unexpectedSubmission, XMLHttpRequest: unexpectedSubmission,
        setTimeout: unexpectedSubmission, setInterval: unexpectedSubmission,
    });
    assert.equal(get('reset-submit').disabled, false);
    assert.equal(get('reset-status').textContent, '');
    for (const element of elements.values()) {
        assert.ok(Object.keys(element.events).every((type) => ['click', 'input', 'submit'].includes(type)));
    }
    for (const toggle of toggles) {
        toggle.events.click();
        toggle.events.click();
    }
    assert.equal(get('reset-submit').disabled, false);
    assert.equal(get('reset-status').textContent, '');
    function submit(password, confirm) {
        get("new-password").value = password;
        get("confirm-new-password").value = confirm;
        let prevented = false;
        get("reset-password-form").events.submit({ preventDefault() { prevented = true; } });
        return prevented;
    }
    for (const [password, confirm] of [["", ""], ["        ", "        "], ["short", "short"], ["long-password", ""], ["long-password", "different-password"]]) {
        assert.ok(submit(password, confirm));
        assert.equal(get("reset-status").dataset.state, "error");
    }
    assert.equal(submit("long-password", "long-password"), false);
    assert.equal(get("reset-status").textContent, "Updating your password?");
    get("new-password").value = "different-password";
    get("new-password").events.input();
    assert.equal(get("confirm-new-password").attrs["aria-invalid"], "true");
    assert.equal(get("reset-status").textContent, "");
    for (const toggle of toggles) {
        toggle.events.click();
        assert.equal(get(toggle.attrs["aria-controls"]).type, "text");
        assert.match(toggle.attrs["aria-label"], /^Hide /);
        toggle.events.click();
        assert.equal(get(toggle.attrs["aria-controls"]).type, "password");
    }
    assert.equal(get("reset-submit").disabled, true);
}

function testInitialRenderedPage(elements) {
    const controls = elements.map(({ tag, attrs, textContent }) => ({
        tag, attrs, textContent, id: attrs.id, value: attrs.value || "",
        type: attrs.type, dataset: {}, events: {}, disabled: "disabled" in attrs,
        addEventListener(type, fn) { this.events[type] = fn; },
        setAttribute(key, value) { this.attrs[key] = value; },
        getAttribute(key) { return this.attrs[key]; },
    }));
    const get = (id) => controls.find((element) => element.id === id) || null;
    const form = get("reset-password-form");
    assert.equal(form.attrs.method, "post");
    assert.equal(form.attrs.action, "/reset-password");
    const csrf = controls.filter((element) => element.attrs.name === "csrf_token");
    assert.equal(csrf.length, 1);
    assert.ok(csrf[0].value);
    const originalCSRF = csrf[0].value;
    assert.equal(get("reset-status").textContent.trim(), "");
    // Real rendered IDs; absent selectors return null, not invented elements.
    // No network, storage, or submission APIs: initialization must not use them.
    vm.runInNewContext(readScript("reset-password.js"), {
        document: {
            getElementById: get,
            querySelectorAll(selector) {
                assert.equal(selector, ".password-toggle");
                return controls.filter((element) => (element.attrs.class || "").split(" ").includes("password-toggle"));
            },
        },
    });
    assert.equal(get("reset-status").textContent.trim(), "");
    assert.equal(csrf[0].value === originalCSRF, true);
    assert.equal(csrf[0].disabled, false);
    assert.equal(get("reset-submit").disabled, false);
    assert.equal(get("new-password").value, "");
    assert.equal(get("confirm-new-password").value, "");
    assert.equal(typeof form.events.submit, "function");
}

if (process.argv.includes("--initial-page")) {
    testInitialRenderedPage(JSON.parse(fs.readFileSync(0, "utf8")));
    console.log("PASS: rendered recovery form initializes with CSRF intact and no error.");
} else {
    testForm();
    console.log("PASS: password validation and visibility controls (no network or storage).");
}
