const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/account-management.js', 'utf8');

function screen({profile = false, api = 'KU', ok = true, failure = false, saved = 'KU'} = {}) {
    const avatar = {textContent: profile ? 'AC' : 'RG', style: {backgroundColor: '#c99a1c'}};
    const navigation = {textContent: 'RG', style: {backgroundColor: '#c99a1c'}};
    const nodes = profile ? [navigation, avatar] : [navigation];
    const events = {}, calls = [], status = {textContent: ''}, fullName = {textContent: 'Ana Cruz'};
    const button = {disabled: false};
    const field = value => ({value, setAttribute() {}, addEventListener() {}});
    const form = {elements: {first_name: field('Kath'), last_name: field('Userr')},
        action: 'http://localhost/user/profile/edit', addEventListener: (name, handler) => events[name] = handler,
        querySelector: () => null};
    const options = {stops: {value: '0'}, indoor: {checked: false}, skipVisited: {checked: false}, savedFirst: {checked: false}};
    const values = {pace: 'balanced', transportation: 'car', traveler_type: 'friends', budget_preference: '', avatar_color: '#c99a1c'};
    const travel = {querySelectorAll: () => [], querySelector(selector) {
        const name = selector.match(/name=([^\]]+)/)[1];
        return options[name] || {value: values[name]};
    }};
    const state = {prefs: {}, profile: {color: '#c99a1c'}, options: {stops: 0, indoor: false, skipVisited: false, savedFirst: false}};
    const document = {
        body: {dataset: {userAvatarUrl: '/api/user/avatar'}},
        querySelectorAll: selector => selector === '[data-user-initials]' ? nodes : [],
        querySelector(selector) {
            if (selector === '.profile-avatar[data-user-initials]') return profile ? avatar : null;
            if (!profile) return null;
            if (selector === '[data-profile-management]') return {querySelector: () => button};
            if (selector === '[data-profile-account]') return form;
            if (selector === '[data-travel-profile]') return travel;
            if (selector === '[data-profile-status]') return status;
            if (selector === '[data-profile-full-name]') return fullName;
            if (selector.startsWith('[data-name-error=') || selector === '[data-interests-error]') return {textContent: '', hidden: true};
            return null;
        }
    };
    const fetch = async (url, settings) => {
        calls.push({url, settings});
        if (failure) throw new Error('Unavailable');
        return {ok, headers: {get: () => 'application/json'},
            json: async () => ({initials: api}), text: async () => 'server-confirmed profile'};
    };
    const context = {document, window: {fetch}, fetch, URL,
        FormData: class {constructor(value) {this.form = value;}},
        DOMParser: class {parseFromString() {return {querySelector(selector) {
            if (selector === '[data-profile-management]') return {};
            if (selector === '.profile-avatar[data-user-initials]') return {textContent: saved};
            return null;
        }};}},
        RosaGoPersonal: {get: () => state, change: callback => {callback(state); return true;}},
        localStorage: {setItem() {throw new Error('Identity must not be persisted');}},
        location: {assign() {throw new Error('Unexpected redirect');}}};
    vm.runInNewContext(source, context);
    return {navigation, avatar, nodes, events, calls, status, button, state, form};
}
const settled = () => new Promise(resolve => setImmediate(resolve));

test('navigation uses authenticated server initials without changing avatar colors', async () => {
    const page = screen(); await settled();
    assert.equal(page.navigation.textContent, 'KU');
    assert.equal(page.navigation.style.backgroundColor, '#c99a1c');
    assert.equal(page.calls[0].url, '/api/user/avatar');
    assert.equal(page.calls[0].settings.credentials, 'same-origin');
    assert.equal(page.calls[0].settings.cache, 'no-store');
});
test('one-name and missing-name server values are used without another initials rule', async () => {
    for (const initials of ['K', 'U', 'RG', 'É王']) {
        const page = screen({api: initials}); await settled();
        assert.equal(page.navigation.textContent, initials);
    }
});
test('unavailable, unauthenticated and malformed identity keep the safe fallback', async () => {
    for (const options of [{failure: true}, {ok: false}, {api: ''}, {api: null}, {api: 'too long'}]) {
        const page = screen(options); await settled();
        assert.equal(page.navigation.textContent, 'RG');
    }
});
test('Profile shares its server-rendered initials with navigation without an extra request', () => {
    const page = screen({profile: true});
    assert.deepEqual(page.nodes.map(node => node.textContent), ['AC', 'AC']);
    assert.equal(page.calls.length, 0);
});
test('successful name save updates both avatars from confirmed server output', async () => {
    const page = screen({profile: true, saved: 'KU'});
    await page.events.submit({preventDefault() {}});
    assert.deepEqual(page.nodes.map(node => node.textContent), ['KU', 'KU']);
    assert.equal(page.status.textContent, 'Profile updated successfully.');
    assert.equal(page.calls[0].settings.method, 'POST');
    assert.equal(page.calls[0].settings.body.form, page.form);
    assert.equal(page.state.profile.color, '#c99a1c');
    assert.ok(page.nodes.every(node => node.style.backgroundColor === '#c99a1c'));
    assert.equal(page.button.disabled, false);
});
test('initials use saved response rather than names edited while the save is in progress', async () => {
    const page = screen({profile: true, saved: 'KU'});
    page.form.elements.first_name.value = 'Unsaved';
    page.form.elements.last_name.value = 'Change';
    await page.events.submit({preventDefault() {}});
    assert.deepEqual(page.nodes.map(node => node.textContent), ['KU', 'KU']);
});
test('failed save preserves both current initials', async () => {
    const page = screen({profile: true, ok: false});
    await page.events.submit({preventDefault() {}});
    assert.deepEqual(page.nodes.map(node => node.textContent), ['AC', 'AC']);
    assert.equal(page.button.disabled, false);
});
