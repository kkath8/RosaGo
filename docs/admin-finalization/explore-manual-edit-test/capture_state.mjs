// Only the owned synthetic server; never inspect browser cookies or credentials.
import fs from 'node:fs';
const ready = JSON.parse(fs.readFileSync(new URL('./ready.json', import.meta.url), 'utf8'));
const response = await fetch(ready.origin + '/__edit_demo/status');
const state = await response.json();
if (response.headers.get('x-rosago-isolated-run') !== ready.run_id || state.run_id !== ready.run_id ||
    state.providers !== 'in-memory-mocks-only' || state.real_configuration_loaded || state.experimental_adapters ||
    state.unexpected_guard_attempts || !state.unrelated_unchanged || !state.same_target_id || state.row_count !== 2) {
  throw new Error('Isolation/identity check failed; manual writes must stop');
}
fs.writeFileSync(new URL('./observed-state.json', import.meta.url), JSON.stringify(state, null, 2));
console.log(JSON.stringify({isolation_passed: true, run_matches: true, row_count: state.row_count,
  target_id_preserved: state.same_target_id, unrelated_unchanged: state.unrelated_unchanged,
  mutations: state.mutation_actions.length, synthetic_photo_count: state.synthetic_photo_count,
  unexpected_transport_attempts: state.unexpected_guard_attempts}));
