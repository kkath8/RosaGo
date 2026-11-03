// Auth-only countdown checks, without a browser, network, or real waiting.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/verification.js'), 'utf8');

function fixture(seconds, missing = false) {
    const clock = { now: 1000 };
    const button = { dataset: { cooldown: String(seconds) }, disabled: true, textContent: '' };
    const tasks = [];
    vm.runInNewContext(source, {
        document: { getElementById: () => missing ? null : button },
        Date: { now: () => clock.now },
        window: { setTimeout: callback => tasks.push(callback) },
    });
    return { clock, button, tasks };
}

test('resend countdown disables the button and enables it only at the deadline', () => {
    const f = fixture(60);
    assert.equal(f.button.textContent, 'Resend code in 01:00');
    assert.equal(f.button.disabled, true);
    f.clock.now += 1000;
    f.tasks.shift()();
    assert.equal(f.button.textContent, 'Resend code in 00:59');
    assert.equal(f.button.disabled, true);
    f.clock.now += 59000;
    f.tasks.shift()();
    assert.equal(f.button.textContent, 'Resend verification code');
    assert.equal(f.button.disabled, false);
    assert.equal(f.tasks.length, 0);
});

test('ready state and a freshly rendered resend countdown use server-provided seconds', () => {
    const ready = fixture(0);
    assert.equal(ready.button.disabled, false);
    assert.equal(ready.tasks.length, 0);
    const reset = fixture(60);
    assert.equal(reset.button.disabled, true);
    assert.equal(reset.button.textContent, 'Resend code in 01:00');
});

test('missing and malformed countdown controls do not crash the page or enable resend', () => {
    assert.doesNotThrow(() => fixture(0, true));
    for (const value of ['invalid', -1, Infinity]) {
        const f = fixture(value);
        assert.equal(f.button.disabled, true);
        assert.equal(f.tasks.length, 0);
    }
});
