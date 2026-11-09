// Offline VM checks. No browser, HTTP, credentials from environment or storage.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('fixture-login.js', import.meta.url), 'utf8');
function setup(origin = 'http://127.0.0.1:5096', pathname = '/admin/login') {
  const listeners = {}, state = {textContent: ''};
  const field = () => ({value: '', dispatchEvent() {}});
  const form = {elements: {email: field(), password: field()},
    submit() {throw new Error('Autofill must never submit');}, requestSubmit() {throw new Error('Autofill must never submit');}};
  const button = {addEventListener(name, fn) {listeners[name] = fn;}};
  vm.runInNewContext(source, {location: {origin, pathname}, Event: class {},
    document: {getElementById: id => id === 'fill-synthetic-admin' ? button : state,
      querySelector: () => form}, fetch() {throw new Error('No network allowed');}});
  return {listeners, state, form};
}
const fixture = setup();
fixture.listeners.click();
assert.equal(fixture.form.elements.email.value, 'admin-b@example.invalid');
assert.equal(fixture.form.elements.password.value, 'Local-test-password-1!');
assert.match(fixture.state.textContent, /existing Log In button once/);
assert.equal(setup('https://unrelated.invalid').listeners.click, undefined);
assert.equal(setup('http://127.0.0.1:5096', '/admin/places').listeners.click, undefined);
console.log('PASS: synthetic fill, no automatic submit/network, exact origin/path guards');
