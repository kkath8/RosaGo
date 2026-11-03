// Exercise the actual registration controller with no network or browser storage.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const rules = require('./password_policy_fixture');
const source = ['password-policy.js', 'auth.js'].map(file => fs.readFileSync(path.join(__dirname, '../static/js', file), 'utf8')).join('\n');

function fixture(serverInvalid = null) {
    const nodes = new Map();
    class Element {
        constructor(id) {
            this.id = id; this.value = ''; this.textContent = ''; this.checked = false;
            this.hidden = false; this.dataset = {}; this.attrs = {}; this.listeners = {};
        }
        addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
        emit(name, event = {}) { for (const handler of this.listeners[name] || []) handler(event); }
        setAttribute(name, value) { this.attrs[name] = value; }
        getAttribute(name) { return this.attrs[name] ?? null; }
        focus() { this.focused = true; }
    }
    const get = id => {
        if (!nodes.has(id)) nodes.set(id, new Element(id));
        return nodes.get(id);
    };
    const values = { 'first-name': 'Ana', 'last-name': 'Cruz', email: 'ana@example.com',
        password: 'Example-pass-123', 'confirm-password': 'Example-pass-123', terms: '' };
    for (const [id, value] of Object.entries(values)) {
        get(id).value = value; get(id + '-error').hidden = true;
    }
    get('terms').checked = true;
    const toggles = ['password', 'confirm-password'].map(id => {
        get(id).type = 'password';
        const toggle = get(id + '-toggle');
        toggle.attrs['aria-controls'] = id;
        return toggle;
    });
    if (serverInvalid) {
        get(serverInvalid).setAttribute('aria-invalid', 'true');
        get(serverInvalid + '-error').hidden = false;
        get(serverInvalid + '-error').textContent = 'Server field error';
    }
    get('password-help').attrs['data-password-rules'] = JSON.stringify(rules);
    const requirements = rules.map(({ key }) => {
        const item = get('password-rule-' + key);
        item.dataset.passwordRequirement = key;
        item.marker = get('password-rule-' + key + '-marker'); item.state = get('password-rule-' + key + '-state');
        item.querySelector = selector => selector === '.password-requirement-marker' ? item.marker : item.state;
        return item;
    });
    const window = new Element('window');
    vm.runInNewContext(source, { document: { getElementById: get,
        querySelectorAll: selector => selector === '.password-toggle' ? toggles : requirements }, window });
    return { get, requirements, toggles, window, submit() {
        let prevented = false;
        get('registration-form').emit('submit', { preventDefault() { prevented = true; } });
        return prevented;
    }};
}

test('consent-only error is local, not duplicated, and clears on checkbox change', () => {
    const f = fixture(); f.get('terms').checked = false;
    assert.equal(f.submit(), true);
    assert.equal(f.get('terms-error').textContent, 'Please agree to the Terms and Privacy Policy.');
    assert.equal(f.get('terms-error').hidden, false);
    assert.equal(f.get('terms').attrs['aria-invalid'], 'true');
    assert.equal(f.get('terms').focused, true);
    assert.equal(f.get('form-status').textContent, '');
    assert.notEqual(f.get('create-account').disabled, true);
    f.get('terms').checked = true; f.get('terms').emit('change');
    assert.equal(f.get('terms-error').hidden, true);
    assert.equal(f.get('terms').attrs['aria-invalid'], 'false');
});

test('other invalid fields remain specific without generic duplicate errors', () => {
    const f = fixture(); f.get('email').value = 'invalid'; f.get('terms').checked = false;
    assert.equal(f.submit(), true);
    assert.match(f.get('email-error').textContent, /valid email/);
    assert.equal(f.get('terms-error').hidden, false);
    assert.equal(f.get('form-status').textContent, '');
});

test('short, all-whitespace and short Unicode passwords block submission', () => {
    for (const password of ['short', '        ', '🐱'.repeat(4)]) {
        const f = fixture();
        f.get('password').value = f.get('confirm-password').value = password;
        assert.equal(f.submit(), true);
        assert.equal(f.get('password-error').hidden, false);
        assert.notEqual(f.get('create-account').disabled, true);
    }
});

test('missing character classes reject submission and a strong password submits normally', () => {
    for (const [password, reason] of [['abcdefgh', 'uppercase'], ['Abcdefgh', 'number'],
        ['Abcdefg1', 'special character'], ['abcdefg1!', 'uppercase'], ['ABCDEFG1!', 'lowercase']]) {
        const f = fixture();
        f.get('password').value = f.get('confirm-password').value = password;
        assert.equal(f.submit(), true);
        assert.match(f.get('password-error').textContent, new RegExp(reason));
        assert.notEqual(f.get('create-account').disabled, true);
    }
    const f = fixture();
    f.get('password').value = f.get('confirm-password').value = 'Abcdef1!';
    assert.equal(f.submit(), false);
    assert.equal(f.get('create-account').disabled, true);
    assert.match(f.get('form-status').textContent, /Creating your account/);
    f.window.emit('pageshow');
    assert.equal(f.get('create-account').disabled, false);
});

test('checklist updates with text and symbols while typing, before submit', () => {
    const f = fixture();
    f.get('password').value = ''; f.get('password').emit('input');
    assert.ok(f.requirements.every(item => item.state.textContent === 'Not met' && item.marker.textContent === '○'));
    f.get('password').value = 'abc'; f.get('password').emit('input');
    assert.equal(f.requirements[0].state.textContent, 'Not met');
    assert.equal(f.requirements[2].state.textContent, 'Met');
    f.get('password').value = 'Abcdefgh'; f.get('password').emit('input');
    assert.deepEqual(f.requirements.map(item => item.dataset.met), ['true', 'true', 'true', 'false', 'false']);
    f.get('password').value = 'Abcdef1!'; f.get('password').emit('input');
    assert.ok(f.requirements.every(item => item.dataset.met === 'true' && item.marker.textContent === '✓'));
    assert.equal(f.get('password-error').hidden, true);
});

test('confirmation mismatch is specific and revalidates after editing password', () => {
    const f = fixture(); f.get('confirm-password').value = 'different';
    assert.equal(f.submit(), true);
    assert.equal(f.get('confirm-password-error').textContent, 'Passwords do not match.');
    f.get('password').value = 'different'; f.get('password').emit('input');
    assert.equal(f.get('confirm-password-error').hidden, true);
});

test('server-rendered consent and confirmation errors clear when corrected', () => {
    const consent = fixture('terms'); consent.get('terms').emit('change');
    assert.equal(consent.get('terms-error').hidden, true);
    const confirmation = fixture('confirm-password');
    confirmation.get('password').emit('input');
    assert.equal(confirmation.get('confirm-password-error').hidden, true);
});

test('confirmation validates on input before submit and reacts to password edits', () => {
    const f = fixture();
    f.get('confirm-password').value = 'different'; f.get('confirm-password').emit('input');
    assert.equal(f.get('confirm-password-error').hidden, false);
    assert.equal(f.get('confirm-password-error').textContent, 'Passwords do not match.');
    f.get('confirm-password').value = f.get('password').value; f.get('confirm-password').emit('input');
    assert.equal(f.get('confirm-password-error').hidden, true);
    f.get('password').value = 'Changed1!'; f.get('password').emit('input');
    assert.equal(f.get('confirm-password-error').hidden, false);
});

test('consent revalidates after interaction and both visibility toggles still work', () => {
    const f = fixture();
    f.get('terms').emit('change');
    assert.equal(f.get('terms-error').hidden, true);
    f.get('terms').checked = false; f.get('terms').emit('change');
    assert.equal(f.get('terms-error').hidden, false);
    f.get('terms').checked = true; f.get('terms').emit('change');
    assert.equal(f.get('terms-error').hidden, true);
    for (const toggle of f.toggles) {
        const input = f.get(toggle.attrs['aria-controls']);
        toggle.emit('click'); assert.equal(input.type, 'text'); assert.equal(toggle.textContent, 'Hide');
        toggle.emit('click'); assert.equal(input.type, 'password'); assert.equal(toggle.textContent, 'Show');
    }
    assert.equal(f.get('form-status').textContent, '');
});
