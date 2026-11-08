import fs from 'node:fs';
const ready = JSON.parse(fs.readFileSync(new URL('ready.json', import.meta.url), 'utf8'));
const response = await fetch(ready.origin + '/__isolated/state');
const state = await response.json();
if (state.run_id !== ready.run_id || response.headers.get('x-rosago-isolated-instance') !== ready.run_id ||
    state.providers !== 'in-memory-mocks-only') throw new Error('Owned fixture mismatch; shutdown refused');
await fetch(ready.origin + '/__edit_demo/stop', {method: 'POST'});
console.log('Owned isolated fixture shutdown requested');
