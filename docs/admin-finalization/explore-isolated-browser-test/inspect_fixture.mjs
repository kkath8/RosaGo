// Read-only, exact-instance loopback inspection. No authentication/cookie access.
import fs from 'node:fs';
const here = new URL('./', import.meta.url);
const ready = JSON.parse(fs.readFileSync(new URL('ready.json', here), 'utf8'));
if (ready.origin !== 'http://127.0.0.1:5096' || ready.reloader_enabled !== false || ready.server_processes !== 1) {
  throw new Error('Unexpected fixture configuration; stop testing');
}
const response = await fetch(ready.origin + '/__isolated/state');
const state = await response.json();
if (response.headers.get('x-rosago-isolated-instance') !== ready.run_id || state.run_id !== ready.run_id ||
    state.providers !== 'in-memory-mocks-only' || state.real_configuration_loaded || state.experimental_adapters ||
    state.unexpected_guard_attempts || !state.unrelated_unchanged || !state.same_target_id || state.row_count !== 2) {
  throw new Error('Fixture identity/isolation/state mismatch; stop testing');
}
fs.writeFileSync(new URL('latest-state.json', here), JSON.stringify(state, null, 2));
const events = JSON.parse(fs.readFileSync(new URL('identity-events.json', here), 'utf8'));
console.log(JSON.stringify({run_id: state.run_id, isolation_verified: true,
  identity_pages_served: events.filter(e => e.event === 'identity_page_served').length,
  browser_confirmations: events.filter(e => e.event === 'browser_instance_confirmed').length,
  saves_observed: events.filter(e => e.event === 'save_response').length,
  successful_mock_edits: state.mutation_actions.length, target_name: state.rows[1].name,
  unrelated_unchanged: state.unrelated_unchanged, target_id_preserved: state.same_target_id}));
