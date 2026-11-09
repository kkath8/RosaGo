// Visible, task-owned Edge session. Inspect no real credentials/cookies/storage.
import fs from 'node:fs';
const here = new URL('./', import.meta.url);
const read = name => JSON.parse(fs.readFileSync(new URL(name, here), 'utf8').replace(/^\uFEFF/, ''));
const ready = read('ready.json'), owned = read('browser-process.json');
const origin = ready.origin;
const outcomes = [];
function check(value, label) { if (!value) throw new Error(label); outcomes.push({check: label, result: 'PASS'}); }
const response = await fetch(origin + '/__edit_demo/status');
const status = await response.json();
check(response.headers.get('x-rosago-isolated-run') === ready.run_id && status.run_id === ready.run_id, 'HTTP path matches owned synthetic server');
check(status.providers === 'in-memory-mocks-only' && !status.real_configuration_loaded && !status.experimental_adapters, 'Only synthetic providers; no inherited credentials or experimental adapters');
check(status.guard_qualification_blocks === 1 && status.unexpected_guard_attempts === 0, 'Outbound guard qualified and no unexpected provider transport attempts');
function channel(url) {
  const ws = new WebSocket(url), pending = new Map(); let next = 0;
  const connected = new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = () => reject(new Error('Owned browser connection failed')); });
  ws.onmessage = async event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const item = pending.get(message.id); if (!item) return;
      pending.delete(message.id); clearTimeout(item.timeout);
      message.error ? item.reject(new Error('Browser protocol operation failed')) : item.resolve(message.result);
    } else if (message.method === 'Fetch.requestPaused') {
      const url = new URL(message.params.request.url);
      const allowed = url.origin === origin || ['data:', 'blob:', 'about:'].includes(url.protocol);
      await call(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest', {
        requestId: message.params.requestId, ...(!allowed ? {errorReason: 'BlockedByClient'} : {})});
    }
  };
  const call = async (method, params = {}) => {
    await connected;
    return new Promise((resolve, reject) => {
      const id = ++next;
      const timeout = setTimeout(() => { pending.delete(id); reject(new Error('Browser operation timeout')); }, 15000);
      pending.set(id, {resolve, reject, timeout}); ws.send(JSON.stringify({id, method, params}));
    });
  };
  return {call, close: () => ws.close()};
}
const metadata = await (await fetch('http://127.0.0.1:9258/json/version')).json();
const root = channel(metadata.webSocketDebuggerUrl);
const processInfo = await root.call('SystemInfo.getProcessInfo');
check(processInfo.processInfo.some(item => item.type === 'browser' && item.id === owned.pid), 'CDP browser process matches newly launched task-owned browser');
const target = await (await fetch('http://127.0.0.1:9258/json/new?about:blank', {method: 'PUT'})).json();
const tab = channel(target.webSocketDebuggerUrl);
await tab.call('Page.enable');
await tab.call('Fetch.enable', {patterns: [{urlPattern: '*', requestStage: 'Request'}]});
const evaluate = async expression => {
  const result = await tab.call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (result.exceptionDetails) throw new Error('Synthetic page operation failed');
  return result.result.value;
};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(expression) {
  for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await pause(100); }
  throw new Error('Synthetic page readiness timeout');
}
await tab.call('Page.navigate', {url: origin + '/admin/login'});
await wait("document.readyState==='complete' && !!document.querySelector('form.admin-login-form')");
check(await evaluate(`fetch('/__edit_demo/status').then(r=>r.json()).then(s=>s.run_id===${JSON.stringify(ready.run_id)})`), 'Actual visible browser path observes same isolated backend');
// These are the old, explicit synthetic fixture account constants, never real credentials.
await evaluate(`(()=>{const f=document.querySelector('form.admin-login-form'); f.elements.email.value='admin-b@example.invalid'; f.elements.password.value='Local-test-password-1!'; f.requestSubmit();})()`);
await wait("location.pathname==='/admin' && document.readyState==='complete'");
await tab.call('Page.navigate', {url: origin + '/admin/places'});
await wait("location.pathname==='/admin/places' && document.readyState==='complete'");
await evaluate("document.querySelector('a[href=\"/admin/places/manual-test-garden/edit\"]').click()");
await wait("location.pathname==='/admin/places/manual-test-garden/edit' && document.readyState==='complete'");
check(await evaluate("(()=>{const f=document.querySelector('[data-destination-form]'); return f.elements.name.value==='Manual Test Garden' && f.elements.description.value==='Isolated saved description.' && f.elements.category.value==='nature' && f.elements.address.value==='Isolated Santa Rosa test address' && f.elements.latitude.value==='14.3' && f.elements.longitude.value==='121.1' && f.elements.environment.value==='Indoor';})()"), 'Actual Edit link opens correct prepopulated destination fields');
await wait("document.querySelector('[data-photo-preview]').naturalWidth===8");
check(true, 'Saved mocked photo loads as actual browser pixels');
await tab.call('Page.bringToFront');
fs.writeFileSync(new URL('browser-ready.json', here), JSON.stringify({origin, checks: outcomes,
  visible_window: true, synthetic_admin_session_only: true, interception_active: true,
  human_manual_results: 'PENDING'}, null, 2));
console.log(JSON.stringify({ready: true, origin, checks_passed: outcomes.length, human_manual_results: 'PENDING'}));
// Keep interception alive throughout human use; only the exact loopback app is permitted.
while (!fs.existsSync(new URL('finish-browser.json', here))) await pause(1000);
await root.call('Browser.close');
tab.close(); root.close();
console.log('Owned manual browser closed');
