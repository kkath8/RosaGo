import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
import {Miniflare,Log,LogLevel,convertV4MiniflareOptions} from 'miniflare';
import {build} from 'esbuild';
const appToken='app-'+ 'a'.repeat(40),operatorToken='operator-'+ 'b'.repeat(40);
const binding={authority_id:'i'.repeat(24),incarnation:'n'.repeat(24)};
test('actual workerd: authentication, distinct operator permission, SQLite restart and blocked recovery',async()=>{
  const path=mkdtempSync(join(tmpdir(),'rosago-workerd-'));
  const bundle=await build({entryPoints:[fileURLToPath(new URL('../worker.mjs',import.meta.url))],
    bundle:true,write:false,format:'esm',platform:'neutral',external:['cloudflare:workers']});
  const options=convertV4MiniflareOptions({name:'rosago-local-fixture',modules:true,script:bundle.outputFiles[0].text,compatibilityDate:'2026-11-07',
    host:'127.0.0.1',port:0,inspectorPort:0,log:new Log(LogLevel.NONE),telemetry:{enabled:false},cf:false,
    durableObjects:{AUTHORITY:{className:'SessionAuthority',useSQLite:true}},resourcePersistencePath:path,isolatedResourcePersistencePath:path,
    bindings:{AUTHORITY_ID:binding.authority_id,AUTHORITY_INCARNATION:binding.incarnation,
      AUTHORITY_OBJECT:'local-fixture',APPLICATION_TOKEN:appToken,OPERATOR_TOKEN:operatorToken}});
  let mf=new Miniflare(options);
  const call=(route,token,body)=>mf.dispatchFetch('https://authority.invalid'+route,
    {method:'POST',headers:{Authorization:'Bearer '+token},body:JSON.stringify(body)});
  const request=(operation,args)=>({version:1,request_id:randomBytes(24).toString('hex'),...binding,operation,arguments:args});
  try {
    assert.equal((await call('/operator/initialize',appToken,{})).status,403);
    assert.equal((await call('/v1/authority','wrong',{})).status,403);
    const config={...binding,namespace:'fixture',epochs:{user:'user_epoch',admin:'admin_epoch'}};
    assert.equal((await call('/operator/initialize',operatorToken,config)).status,200);
    const key='fixture:sessions:v3:user:user_epoch:auth:'+'c'.repeat(64);
    const now=Date.now()/1000;
    const meta={digest:'d'.repeat(64),expires:now+1000,size:400,
      realm_scope:'fixture:sessions:v3:user:user_epoch',scope:'fixture:sessions:v3:user:user_epoch:auth'};
    const args={namespace:'fixture',realm:'user',epoch:'user_epoch',generation:1,now};
    assert.equal((await (await call('/v1/authority',appToken,request('commit',{...args,expected:{[key]:null},changes:{[key]:meta}}))).json()).status,'ok');
    assert.equal(options.isolatedResourcePersistencePath,path);
    assert.deepEqual((await (await call('/v1/authority',appToken,request('read',{...args,now:Date.now()/1000,key}))).json()).payload,meta);
    await mf.dispose();mf=new Miniflare(options);
    const restored=await (await call('/v1/authority',appToken,request('read',{...args,now:Date.now()/1000,key}))).json();
    assert.equal(restored.status,'ok','restored authority must remain open');
    assert.deepEqual(restored.payload,meta);
    assert.equal((await call('/operator/block',appToken,{})).status,403);
    assert.equal((await call('/operator/block',operatorToken,{})).status,200);
    await mf.dispose();mf=new Miniflare(options);
    assert.equal((await (await call('/v1/authority',appToken,request('health',{}))).json()).status,'closed');
    assert.equal((await call('/operator/initialize',operatorToken,config)).status,503);
  } finally {await mf.dispose();rmSync(path,{recursive:true,force:true});}
});
