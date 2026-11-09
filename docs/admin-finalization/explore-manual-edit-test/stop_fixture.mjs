import fs from 'node:fs';
const ready = JSON.parse(fs.readFileSync(new URL('./ready.json', import.meta.url)));
const response = await fetch(ready.origin + '/__edit_demo/status');
const status = await response.json();
if (status.run_id !== ready.run_id || status.providers !== 'in-memory-mocks-only') throw new Error('Fixture mismatch; stopping refused');
await fetch(ready.origin + '/__edit_demo/stop', {method: 'POST'});
console.log('Owned isolated fixture shutdown requested');
