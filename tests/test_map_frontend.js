// Run with node --test tests/test_map_frontend.js. No browser/network/framework required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../static/js/map.js'), 'utf8');
const place = (changes = {}) => ({ name: 'Synthetic place', detail_url: '/places/synthetic-place',
    category: 'nature', address: 'Synthetic address', latitude: 14.2, longitude: 121.1, ...changes });

function run(markers, options = {}) {
    const calls = { maps: [], tiles: [], markers: [], views: [], bounds: [], removed: 0 };
    const elements = new Map();
    function element(tag) {
        return { tag, children: [], hidden: true, textContent: '',
            appendChild(child) { this.children.push(child); },
            set innerHTML(_) { assert.fail('Unsafe HTML construction'); } };
    }
    for (const id of ['places-map', 'map-data', 'map-failure', 'map-tile-failure']) elements.set(id, element('div'));
    elements.get('map-data').textContent = options.json ?? JSON.stringify(markers);
    if (options.noContainer) elements.delete('places-map');
    if (options.noData) elements.delete('map-data');
    const map = { setView(...args) { calls.views.push(args); },
        fitBounds(...args) { calls.bounds.push(args); }, remove() { calls.removed++; } };
    const L = {
        map(container, settings) {
            calls.maps.push(settings);
            assert.equal(container.hidden, false);
            if (options.mapFailure) throw new Error('private initialization details');
            return map;
        },
        tileLayer(url, settings) {
            const tile = { url, settings, events: {}, on(type, handler) { this.events[type] = handler; return this; },
                addTo(target) { assert.equal(target, map); return this; } };
            calls.tiles.push(tile);
            return tile;
        },
        marker(position, settings) {
            if (options.markerFailure) throw new Error('private marker details');
            const marker = { position, settings, addTo(target) { assert.equal(target, map); return this; },
                bindPopup(content, popupOptions) {
                    assert.equal(typeof content, 'object');
                    this.popup = content; this.popupOptions = popupOptions; return this;
                } };
            calls.markers.push(marker);
            return marker;
        },
    };
    const forbidden = () => assert.fail('Unexpected network, geolocation, storage, or retry');
    const window = { L: options.noLeaflet ? undefined : L,
        location: { href: 'https://rosago.example/map', origin: 'https://rosago.example' } };
    vm.runInNewContext(source, { window, document: {
        getElementById: (id) => elements.get(id) ?? null, createElement: element,
    }, URL, navigator: { geolocation: { getCurrentPosition: forbidden, watchPosition: forbidden } },
    fetch: forbidden, XMLHttpRequest: forbidden, setTimeout: forbidden, setInterval: forbidden,
    localStorage: new Proxy({}, { get: forbidden }), sessionStorage: new Proxy({}, { get: forbidden }) });
    assert.deepEqual(Object.keys(window), ['L', 'location']);
    return { calls, elements };
}

test('empty page and empty payload never initialize or request tiles', () => {
    for (const options of [{ noContainer: true }, {}]) {
        const { calls, elements } = run([], options);
        assert.equal(calls.maps.length, 0);
        assert.equal(calls.tiles.length, 0);
        assert.equal(elements.get('map-failure').hidden, true);
    }
});
test('single place uses restrained zoom, local detail link and standard OSM tiles', () => {
    const { calls, elements } = run([place()]);
    assert.equal(calls.maps.length, 1);
    assert.equal(calls.maps[0].scrollWheelZoom, false);
    assert.equal(calls.maps[0].zoomAnimation, false);
    assert.equal(calls.tiles[0].url, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    assert.equal(calls.tiles[0].settings.maxZoom, 19);
    assert.equal(calls.tiles[0].settings.keepBuffer, 0);
    assert.equal(calls.tiles[0].settings.updateWhenIdle, true);
    assert.match(calls.tiles[0].settings.attribution, /https:\/\/www.openstreetmap.org\/copyright/);
    assert.match(calls.tiles[0].settings.attribution, /OpenStreetMap contributors/);
    assert.equal(JSON.stringify(calls.views), '[[[14.2,121.1],14]]');
    assert.equal(calls.markers[0].settings.keyboard, true);
    assert.equal(calls.markers[0].popup.children[3].href, '/places/synthetic-place');
    assert.equal(elements.get('map-failure').hidden, true);
});
test('multiple distinct positions fit bounds without excessive zoom', () => {
    const { calls } = run([place(), place({ latitude: 14.3, longitude: 121.2 })]);
    assert.equal(calls.markers.length, 2);
    assert.equal(calls.views.length, 0);
    assert.equal(calls.bounds[0][0].length, 2);
    assert.equal(calls.bounds[0][1].maxZoom, 16);
    assert.equal(JSON.stringify(calls.bounds[0][1].padding), '[24,24]');
});
test('coincident places retain all markers but use one-position viewport', () => {
    const { calls } = run([place(), place({ name: 'Another synthetic place' })]);
    assert.equal(calls.markers.length, 2);
    assert.equal(calls.views.length, 1);
    assert.equal(calls.bounds.length, 0);
});
test('hostile strings are text nodes, never HTML', () => {
    const name = '<img src=x onerror=alert(1)> " & </script> \u00f1';
    const address = '<script>alert(1)</script>';
    const { calls } = run([place({ name, address, category: 'attraction' })]);
    const children = calls.markers[0].popup.children;
    assert.deepEqual(children.map((node) => node.tag), ['strong', 'p', 'p', 'a']);
    assert.deepEqual(children.map((node) => node.textContent),
        [name, 'Attractions', address, `View details for ${name}`]);
    assert.equal(calls.markers[0].settings.alt, name);
});
test('malformed JSON and missing data/Leaflet reveal sanitized fallback', () => {
    for (const options of [{ json: '{' }, { noData: true }, { noLeaflet: true }]) {
        const { calls, elements } = run([place()], options);
        assert.equal(calls.maps.length, 0);
        assert.equal(elements.get('places-map').hidden, true);
        assert.equal(elements.get('map-failure').hidden, false);
    }
});
test('malformed payload refuses the whole map before requesting tiles', () => {
    const missing = place(); delete missing.address;
    for (const value of [null, {}, 'bad', [null], [missing], Array(51).fill(place()),
        [place(), place({ category: 'unknown' })], [place({ category: '__proto__' })],
        [place({ latitude: '14.2' })], [place({ latitude: null })], [place({ longitude: 181 })],
        [place({ latitude: -91 })], [place({ name: '' })], [place({ id: 'not-allowed' })]]) {
        const { calls, elements } = run(value);
        assert.equal(calls.maps.length, 0);
        assert.equal(calls.tiles.length, 0);
        assert.equal(elements.get('map-failure').hidden, false);
    }
});
test('external, executable and non-detail URLs are rejected', () => {
    for (const detail_url of ['https://evil.example/places/x', '//evil.example/places/x',
        'javascript:alert(1)', 'data:text/html,x', '/user', '/places/x?next=evil', '/places/x#x',
        '/places/%2e%2e', '/places/x\\evil', '/places/x\n', '/places/../user']) {
        const { calls, elements } = run([place({ detail_url })]);
        assert.equal(calls.maps.length, 0, detail_url);
        assert.equal(elements.get('map-failure').hidden, false);
    }
});
test('initialization exceptions keep sanitized fallback', () => {
    const { calls, elements } = run([place()], { mapFailure: true });
    assert.equal(calls.tiles.length, 0);
    assert.equal(elements.get('places-map').hidden, true);
    assert.equal(elements.get('map-failure').hidden, false);
});
test('later failures remove partial map and do not retry', () => {
    const { calls, elements } = run([place()], { markerFailure: true });
    assert.equal(calls.removed, 1);
    assert.equal(calls.views.length, 0);
    assert.equal(calls.bounds.length, 0);
    assert.equal(elements.get('places-map').hidden, true);
    assert.equal(elements.get('map-failure').hidden, false);
});
test('tile errors reveal background fallback without destroying destinations', () => {
    const { calls, elements } = run([place()]);
    calls.tiles[0].events.tileerror();
    assert.equal(elements.get('map-tile-failure').hidden, false);
    assert.equal(elements.get('map-failure').hidden, true);
    assert.equal(calls.removed, 0);
    assert.equal(calls.tiles.length, 1);
    assert.equal(calls.markers.length, 1);
});
test('no app-level HTML injection, credentials, geolocation or network fetch code', () => {
    assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML|eval\(|supabase|access_token|refresh_token|geolocation|fetch\(|XMLHttpRequest/);
});
