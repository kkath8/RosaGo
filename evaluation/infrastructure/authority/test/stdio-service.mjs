// Test-only separate authority process. No sockets, credentials or remote APIs.
import readline from 'node:readline';
import { Ledger } from '../ledger.mjs';
import { sqliteStorage } from './sqlite-storage.mjs';
const [path,id,incarnation]=process.argv.slice(2);
const storage=sqliteStorage(path);
const ledger=new Ledger(storage,{authority_id:id,incarnation});
process.stdout.write(JSON.stringify({fixture_ready:true})+'\n');
for await(const line of readline.createInterface({input:process.stdin})) {
  try {
    const request=JSON.parse(line);
    const value=request.test_control==='initialize' ? ledger.initialize(request.config)
      : request.test_control==='block' ? ledger.block() : ledger.exchange(request);
    process.stdout.write(JSON.stringify(value)+'\n');
  } catch {process.stdout.write(JSON.stringify({test_error:true})+'\n');}
}
storage.db.close();
