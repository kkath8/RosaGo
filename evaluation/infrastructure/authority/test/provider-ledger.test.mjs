import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Ledger} from '../ledger.mjs';
import {ProviderLedger} from '../provider-ledger.mjs';
import {sqliteStorage} from './sqlite-storage.mjs';
const binding={authority_id:'a'.repeat(24),incarnation:'b'.repeat(24)};
const issuer='https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1';
const uid='11111111-1111-4111-8111-111111111111',sid='22222222-2222-4222-8222-222222222222';
function fixture() {
  const path=mkdtempSync(join(tmpdir(),'rosago-provider-'));
  let storage,ledger,provider,now=1900000000;
  const open=()=>{storage=sqliteStorage(join(path,'authority.sqlite'));ledger=new Ledger(storage,binding,()=>now);
    provider=new ProviderLedger(storage,ledger,issuer,()=>now);};open();
  ledger.initialize({...binding,namespace:'fixture',epochs:{user:'user_epoch',admin:'admin_epoch'}});
  const call=(operation,overrides={})=>provider.exchange(operation,{version:1,...binding,namespace:'fixture',
    issuer,uid,sid,nonce:randomBytes(24).toString('hex'),now,deadline:now+100,...overrides});
  return {call,restart(){storage.db.close();open();},advance(v){now+=v;},block(){ledger.block();},
    close(){storage.db.close();rmSync(path,{recursive:true,force:true});}};
}
test('provider admission, logout and permanent tombstone survive restart and old admission replay',()=>{
  const f=fixture();try{
    assert.equal(f.call('check').active,false);
    assert.equal(f.call('enroll').active,true);
    assert.equal(f.call('check').active,true);
    assert.equal(f.call('revoke').revoked,true);
    f.restart();assert.equal(f.call('check').active,false);
    assert.throws(()=>f.call('enroll'));
    assert.equal(f.call('revoke').revoked,true);
    f.advance(40000);assert.equal(f.call('inspect').revoked,true);
    assert.throws(()=>f.call('enroll'));
  }finally{f.close();}
});
test('expired admission cannot be renewed by refresh or replay',()=>{
  const f=fixture();try{
    f.call('enroll');f.advance(101);assert.equal(f.call('check').active,false);
    assert.throws(()=>f.call('enroll'));
  }finally{f.close();}
});
test('provider expiry constraints never extend or admit sessions, even after Auth rollback',()=>{
  const f=fixture();try{
    assert.equal(f.call('constrain',{deadline:1900000050}).active,false);
    f.call('enroll');f.call('constrain',{deadline:1900001000});
    f.restart();f.advance(51);assert.equal(f.call('check').active,false);
    assert.equal(f.call('inspect').expired,true);assert.throws(()=>f.call('enroll'));
  }finally{f.close();}
});
test('identity, issuer, incarnation, freshness and irreversible operator block fail closed',()=>{
  const f=fixture();try{
    f.call('enroll');
    for(const patch of [{uid:'33333333-3333-4333-8333-333333333333'},
      {issuer:'https://brnkigrrqdrywahvcbvc.supabase.co/auth/v1'}, {incarnation:'z'.repeat(24)},
      {now:0},{nonce:'short'},{deadline:1900000000+28801}]) {
      assert.throws(()=>f.call('enroll',patch));
    }
    f.block();f.restart();assert.throws(()=>f.call('check'));assert.throws(()=>f.call('enroll'));
  }finally{f.close();}
});
