import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Ledger} from '../ledger.mjs';
import {sqliteStorage} from './sqlite-storage.mjs';
const binding={authority_id:'a'.repeat(24),incarnation:'b'.repeat(24)};
const config={...binding,namespace:'fixture',epochs:{user:'user_epoch',admin:'admin_epoch'}};
const key='fixture:sessions:v3:user:user_epoch:auth:'+ 'c'.repeat(64);
const now=1900000000;
const metadata={digest:'d'.repeat(64),size:300,expires:now+1000,
  scope:key.slice(0,key.lastIndexOf(':')),realm_scope:'fixture:sessions:v3:user:user_epoch'};
function request(operation,arguments_) {return {version:1,request_id:randomBytes(24).toString('hex'),...binding,operation,arguments:arguments_};}
const args={namespace:'fixture',realm:'user',epoch:'user_epoch',generation:1,now};
test('durable CAS, nonce replay, scope, expiry and block survive SQLite restart',()=>{
  const dir=mkdtempSync(join(tmpdir(),'rosago-ledger-')); const path=join(dir,'ledger.sqlite');
  let storage=sqliteStorage(path);let ledger=new Ledger(storage,binding,()=>now);
  try {
    assert.equal(ledger.exchange(request('health',{})).status,'closed');
    ledger.initialize(config);
    assert.throws(()=>ledger.initialize(config));
    const create=request('commit',{...args,expected:{[key]:null},changes:{[key]:metadata}});
    const first=ledger.exchange(create);assert.equal(first.status,'ok');assert.equal(first.sequence,1);
    assert.deepEqual(ledger.exchange(create),first);
    assert.equal(ledger.exchange(request('commit',{...args,expected:{[key]:null},changes:{[key]:metadata}})).status,'conflict');
    assert.equal(ledger.exchange({...request('read',{...args,key}),incarnation:'z'.repeat(24)}).status,'closed');
    assert.equal(ledger.exchange(request('read',{...args,realm:'admin',epoch:'admin_epoch',key})).status,'closed');
    assert.equal(ledger.exchange(request('read',{...args,key,now:now-3})).status,'closed');
    storage.db.close();storage=sqliteStorage(path);ledger=new Ledger(storage,binding,()=>now);
    assert.deepEqual(ledger.exchange(request('read',{...args,key})).payload,metadata);
    assert.equal(ledger.exchange(request('commit',{...args,expected:{[key]:metadata},changes:{[key]:null}})).status,'ok');
    assert.equal(ledger.exchange(create).sequence,1); // replay cannot recreate deleted data
    assert.equal(ledger.exchange(request('read',{...args,key})).payload,null);
    assert.equal(ledger.exchange(request('commit',{...args,expected:{[key]:null},changes:{[key]:metadata}})).status,'conflict');
    ledger.block(); storage.db.close();storage=sqliteStorage(path);ledger=new Ledger(storage,binding,()=>now);
    assert.equal(ledger.exchange(request('health',{})).status,'closed');
    assert.throws(()=>ledger.initialize(config));
  } finally {storage.db.close();rmSync(dir,{recursive:true,force:true});}
});
test('malformed multi-record mutation rolls back all records and sequence',()=>{
  const storage=sqliteStorage(':memory:');const ledger=new Ledger(storage,binding,()=>now);
  try {
    ledger.initialize(config);
    const second=key.slice(0,-64)+'e'.repeat(64);
    assert.equal(ledger.exchange(request('commit',{...args,expected:{[key]:null,[second]:null},
      changes:{[key]:metadata,[second]:{...metadata,size:45001}}})).status,'closed');
    assert.equal(ledger.exchange(request('read',{...args,key})).payload,null);
    assert.equal(ledger.control().sequence,0);
  } finally {storage.db.close();}
});
