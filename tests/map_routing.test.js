// Exercise the actual map controller without external tiles, providers or packages.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/map.js'), 'utf8');

class Element {
    constructor(tag = 'div') {
        this.tag = tag; this.listeners = {}; this.children = []; this.hidden = true;
        this.value = ''; this.textContent = '';
    }
    addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
    async emit(name) {
        await Promise.all((this.listeners[name] || []).map(handler => handler({ preventDefault() {} })));
    }
    dispatchEvent(event) { return this.emit(event.type); }
    appendChild(child) { this.children.push(child); }
    set innerHTML(_) { throw new Error('Untrusted popup HTML must not be used'); }
    scrollIntoView() {}
    focus() { this.focused = true; }
}

function fixture(options = {}) {
    const ids = {};
    for (const id of ['places-map', 'map-failure', 'map-tile-failure', 'map-data', 'route-form',
        'route-status', 'route-pick-start', 'route-use-location', 'route-summary', 'route-summary-body', 'route-result-title']) ids[id] = new Element();
    const marker = { name: 'Synthetic destination', category: 'heritage', address: 'Synthetic address',
        detail_url: '/places/synthetic-destination', latitude: 14, longitude: 121 };
    ids['map-data'].textContent = JSON.stringify(options.markers || [marker]);
    const form = ids['route-form'];
    form.elements = {};
    for (const name of ['start_latitude', 'start_longitude', 'mode', 'destination_slug']) {
        form.elements[name] = new Element('input');
    }
    form.elements.mode.value = 'driving';
    form.elements.destination_slug.value = options.initialDestination || 'synthetic-destination';
    form.elements.destination_slug.options = (options.markers || [marker]).map(
        item => ({ value: item.detail_url.split('/').pop() }));
    form.action = 'http://localhost/api/route';
    const submit = new Element('button');
    form.querySelector = () => submit;
    form.reportValidity = () => true;
    const lines = [], popups = [], removed = [], handlers = {}, requests = [];
    const map = {
        setView() {}, fitBounds() {}, closePopup() {}, remove() {},
        on(name, handler) { handlers[name] = handler; return this; },
        removeLayer(layer) { removed.push(layer); },
    };
    const layer = () => ({ addTo() { return this; }, bindPopup(popup) { popups.push(popup); return this; } });
    const L = {
        map: () => map,
        tileLayer: () => ({ on() { return this; }, addTo() {} }),
        marker: () => layer(),
        geoJSON(feature) {
            lines.push(feature.geometry);
            return { addTo() { return this; }, getBounds() { return { extend() { return this; } }; } };
        },
    };
    const geometry = { type: 'LineString', coordinates: [[121.1, 14.1], [121.05, 14.06], [121, 14]] };
    const result = { geometry, distance_m: 2345, duration_s: 181, mode: 'driving', estimated: true };
    const fetch = async (url, init) => {
        requests.push({ url, init });
        return options.fetch ? options.fetch(url, init) : { ok: true, json: async () => result };
    };
    vm.runInNewContext(source, {
        document: { body: { dataset: { locationEnabled: options.locationEnabled === false ? 'false' : 'true' } }, getElementById: id => ids[id], createElement: tag => new Element(tag) },
        window: { L: options.noLeaflet ? null : L, location: { href: 'http://localhost/map',
            origin: 'http://localhost', search: options.search || '' }, setTimeout, clearTimeout },
        navigator: options.navigator || {}, URL, URLSearchParams, AbortController, Event, fetch,
    });
    form.elements.start_latitude.value = '14.1';
    form.elements.start_longitude.value = '121.1';
    return { ids, form, submit, lines, popups, removed, handlers, requests, geometry };
}

test('provider geometry is drawn and estimates are displayed after explicit submission', async () => {
    const f = fixture();
    assert.equal(f.requests.length, 0);
    assert.equal(f.form.hidden, false);
    await f.form.emit('submit');
    assert.equal(JSON.stringify(f.lines[0]), JSON.stringify(f.geometry));
    assert.match(f.ids['route-status'].textContent, /2.35 km/);
    assert.match(f.ids['route-status'].textContent, /4 minutes/);
    assert.match(f.ids['route-status'].textContent, /exclude live traffic/);
    const request = f.requests[0];
    assert.equal(request.url, 'http://localhost/api/route');
    assert.equal(request.init.method, 'POST');
    assert.equal(request.init.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(request.init.body), { destination_slug: 'synthetic-destination',
        start_latitude: 14.1, start_longitude: 121.1, mode: 'driving' });
    assert.equal(request.init.headers.Authorization, undefined);
    assert.equal(f.submit.disabled, false);
});

test('provider errors do not draw a fallback straight line or expose messages', async () => {
    const f = fixture({ fetch: async () => ({ ok: false,
        json: async () => ({ error: 'no_route', message: 'private-provider-secret' }) }) });
    await f.form.emit('submit');
    assert.equal(f.lines.length, 0);
    assert.match(f.ids['route-status'].textContent, /couldn't calculate a route/);
    assert.doesNotMatch(f.ids['route-status'].textContent, /private-provider-secret/);
});

test('map-click starting point and popup navigation select actual values', async () => {
    const f = fixture();
    await f.ids['route-pick-start'].emit('click');
    f.handlers.click({ latlng: { lat: 14.22, lng: 121.33 } });
    assert.equal(f.form.elements.start_latitude.value, '14.22');
    assert.equal(f.form.elements.start_longitude.value, '121.33');
    const button = f.popups[0].children.find(child => child.tag === 'button');
    assert.equal(button.textContent, 'Plan Route');
    await button.emit('click');
    assert.equal(f.form.elements.destination_slug.value, 'synthetic-destination');
    assert.equal(f.ids['route-use-location'].focused, true);
});

test('changing inputs aborts pending routing and ignores stale results', async () => {
    let resolve;
    const pending = new Promise(done => { resolve = done; });
    const f = fixture({ fetch: () => pending });
    const work = f.form.emit('submit');
    await f.form.emit('input');
    assert.equal(f.requests[0].init.signal.aborted, true);
    resolve({ ok: true, json: async () => ({ geometry: f.geometry,
        distance_m: 200, duration_s: 20, mode: 'driving' }) });
    await work;
    assert.equal(f.lines.length, 0);
    assert.equal(f.ids['route-status'].textContent, '');
    assert.equal(f.submit.disabled, false);
});

test('device location is requested only on explicit action and denial has a fallback', async () => {
    let permissionRequests = 0;
    const f = fixture({ navigator: { geolocation: {
        getCurrentPosition(_success, failure) { permissionRequests += 1; failure({ code: 1 }); },
    } } });
    assert.equal(permissionRequests, 0);
    await f.ids['route-use-location'].emit('click');
    assert.equal(permissionRequests, 1);
    assert.match(f.ids['route-status'].textContent, /Enter coordinates or select a point/);
    assert.equal(f.requests.length, 0);
});

test('location preference off prevents browser permission requests', async () => {
    let permissionRequests = 0;
    const f = fixture({ locationEnabled: false, navigator: { geolocation: {
        getCurrentPosition() { permissionRequests++; },
    } } });
    await f.ids['route-use-location'].emit('click');
    assert.equal(permissionRequests, 0);
    assert.match(f.ids['route-status'].textContent, /turned off in Settings/);
    assert.equal(f.requests.length, 0);
});

test('empty coordinates catalog creates no fake map or requests', () => {
    const f = fixture({ markers: [] });
    assert.equal(f.form.hidden, true);
    assert.equal(f.ids['places-map'].hidden, true);
    assert.equal(f.requests.length, 0);
    assert.equal(f.lines.length, 0);
});

test('Leaflet failure leaves the text fallback available', () => {
    const f = fixture({ noLeaflet: true });
    assert.equal(f.ids['places-map'].hidden, true);
    assert.equal(f.ids['map-failure'].hidden, false);
    assert.equal(f.requests.length, 0);
});

test('located marker provides safe external search, panorama and satellite actions', () => {
    const f = fixture();
    assert.equal(f.popups.length, 1);
    const popup = f.popups[0];
    assert.equal(popup.children[0].textContent, 'Synthetic destination');
    assert.equal(popup.children[1].textContent, 'Heritage');
    assert.equal(popup.children[2].textContent, 'Synthetic address');
    const links = popup.children.flatMap(child=>[child,...child.children]).filter(child => child.tag === 'a');
    assert.deepEqual(links.map(link => link.textContent),
        ['View Details', 'Google Maps', 'Street View', 'Satellite']);
    assert.equal(links[0].href, '/places/synthetic-destination');
    assert.equal(links[0].target, undefined);
    assert.equal(links[1].href, 'https://www.google.com/maps/search/?api=1&query=14%2C121');
    assert.equal(links[2].href, 'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=14%2C121');
    assert.equal(links[3].href,
        'https://www.google.com/maps/@?api=1&map_action=map&center=14%2C121&zoom=18&basemap=satellite');
    for (const link of links.slice(1)) {
        assert.equal(link.target, '_blank');
        assert.equal(link.rel, 'noopener noreferrer');
        assert.equal(new URL(link.href).origin, 'https://www.google.com');
    }
    assert.match(popup.children.at(-1).textContent, /Street View coverage is not guaranteed/);
    assert.equal(f.requests.length, 0);
    assert.equal(f.lines.length, 0);
});

test('external URLs encode the validated signed decimal and boundary coordinate pairs', () => {
    for (const [latitude, longitude] of [[-14.123456, 121.987654], [0, 0], [-90, -180], [90, 180]]) {
        const f = fixture({ markers: [{ name: 'Fixture', address: 'Fixture address', category: 'industrial',
            detail_url: '/places/fixture', latitude, longitude }] });
        const links = f.popups[0].children.flatMap(child=>[child,...child.children]).filter(child => child.target === '_blank');
        const pair = `${latitude},${longitude}`;
        for (const [index, key] of ['query', 'viewpoint', 'center'].entries()) {
            assert.equal(new URL(links[index].href).searchParams.get(key), pair);
            assert.ok(links[index].href.includes(encodeURIComponent(pair)));
        }
    }
});

test('missing, incomplete, nonnumeric and out-of-range coordinates create no popup actions', () => {
    for (const [latitude, longitude] of [[null, null], [null, 121], [14, null],
        ['14', 121], [true, 121], [91, 121], [14, -181], [NaN, 121], [14, Infinity]]) {
        const f = fixture({ markers: [{ name: 'Fixture', address: 'Fixture address', category: 'heritage',
            detail_url: '/places/fixture', latitude, longitude }] });
        assert.equal(f.popups.length, 0);
        assert.equal(f.ids['places-map'].hidden, true);
        assert.equal(f.requests.length, 0);
    }
    assert.equal(fixture({ markers: [] }).popups.length, 0);
});

test('hostile database text stays plain text and cannot alter Google URLs or link attributes', () => {
    const hostile = '<img src=x onerror=alert(1)> & query=javascript:alert(1) " </script>';
    const f = fixture({ markers: [{ name: hostile, address: hostile, category: 'heritage',
        detail_url: '/places/fixture', latitude: 14, longitude: 121 }] });
    const popup = f.popups[0];
    assert.equal(popup.children[0].textContent, hostile);
    assert.equal(popup.children[2].textContent, hostile);
    assert.equal(popup.children.filter(child => child.tag === 'img' || child.tag === 'script').length, 0);
    for (const link of popup.children.filter(child => child.target === '_blank')) {
        assert.ok(!link.href.includes('javascript'));
        assert.equal(new URL(link.href).hostname, 'www.google.com');
        assert.equal(link.rel, 'noopener noreferrer');
        assert.equal(link.children.length, 0);
    }
    const invalid = fixture({ markers: [{ name: 'Fixture', address: 'Address', category: hostile,
        detail_url: '/places/fixture', latitude: 14, longitude: 121 }] });
    assert.equal(invalid.popups.length, 0);
});

test('detail map links preselect only an existing published destination', () => {
    const markers = ['first', 'second'].map(slug => ({ name: slug, category: 'heritage',
        address: 'Synthetic address', detail_url: '/places/' + slug, latitude: 14, longitude: 121 }));
    const selected = fixture({ markers, initialDestination: 'first', search: '?destination=second' });
    assert.equal(selected.form.elements.destination_slug.value, 'second');
    assert.equal(selected.requests.length, 0);
    const invalid = fixture({ markers, initialDestination: 'first', search: '?destination=https://invalid.example' });
    assert.equal(invalid.form.elements.destination_slug.value, 'first');
    assert.equal(invalid.requests.length, 0);
});

test('dedicated summary shows provider values and clears on input changes', async()=>{
 const f=fixture();await f.form.emit('submit');
 assert.equal(f.ids['route-summary'].hidden,false);
 assert.equal(f.ids['route-result-title'].textContent,'Route Summary');
 const rows=f.ids['route-summary-body'].children.filter(n=>n.className==='route-summary-row');
 assert.deepEqual(rows.map(r=>r.children.map(n=>n.textContent)),[['Destination','Synthetic destination'],['Mode','Driving'],['Distance','2.35 km'],['Estimated travel time','4 minutes']]);
 await f.form.emit('change');assert.equal(f.ids['route-summary'].hidden,true);
});
test('failure card offers real external destination link without technical provider details',async()=>{
 const f=fixture({fetch:async()=>({ok:false,json:async()=>({error:'no_route',message:'private-provider-secret 422'})})});
 await f.form.emit('submit');assert.equal(f.ids['route-result-title'].textContent,'Route unavailable');
 const text=f.ids['route-summary-body'].children.map(n=>n.textContent).join(' ');assert.doesNotMatch(text,/422|private-provider-secret/);
 assert.ok(f.ids['route-summary-body'].children.some(n=>n.href?.startsWith('https://www.google.com/maps/')));
});
test('empty starting coordinates request a starting point without fetching a route',async()=>{
 const f=fixture();f.form.elements.start_latitude.value='';await f.form.emit('submit');assert.equal(f.requests.length,0);assert.match(f.ids['route-status'].textContent,/Starting Point/);
});
