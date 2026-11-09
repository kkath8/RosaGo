import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
import {Miniflare,Log,LogLevel,convertV4MiniflareOptions} from 'miniflare';
import {build} from 'esbuild';
test('actual workerd provider endpoints enforce scoped credentials, HEAD decisions and restart revocation',async()=>{
  const path=mkdtempSync(join(tmpdir(),'rosago-provider-worker-'));
  const keys=Object.fromEntries(['APPLICATION_TOKEN','OPERATOR_TOKEN','PROVIDER_ENROLL_TOKEN',
    'PROVIDER_CHECK_TOKEN','PROVIDER_REVOKE_TOKEN'].map(k=>[k,randomBytes(32).toString('hex')]));
  const binding={authority_id:'a'.repeat(24),incarnation:'b'.repeat(24)};
  const issuer='https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1';
  const bundle=await build({entryPoints:[fileURLToPath(new URL('../worker.mjs',import.meta.url))],
    bundle:true,write:false,format:'esm',platform:'neutral',external:['cloudflare:workers']});
  const options=convertV4MiniflareOptions({name:'rosago-provider-test',modules:true,script:bundle.outputFiles[0].text,
    compatibilityDate:'2026-11-07',host:'127.0.0.1',port:0,inspectorPort:0,log:new Log(LogLevel.NONE),
    telemetry:{enabled:false},cf:false,durableObjects:{AUTHORITY:{className:'SessionAuthority',useSQLite:true}},
    resourcePersistencePath:path,isolatedResourcePersistencePath:path,
    bindings:{...keys,AUTHORITY_ID:binding.authority_id,AUTHORITY_INCARNATION:binding.incarnation,
      AUTHORITY_OBJECT:'fixture',PROVIDER_ISSUER:issuer}});
  let mf=new Miniflare(options);
  const call=(route,token,body,method='POST')=>mf.dispatchFetch('https://authority.invalid'+route,{method,
    headers:{Authorization:'Bearer '+token,...(method==='HEAD'?{'X-RosaGo-Request':JSON.stringify(body)}:{})},
    ...(method==='HEAD'?{}:{body:JSON.stringify(body)})});
  const request=()=>({version:1,...binding,namespace:'fixture',issuer,
    uid:'11111111-1111-4111-8111-111111111111',sid:'22222222-2222-4222-8222-222222222222',
    now:Date.now()/1000,deadline:Date.now()/1000+100,nonce:randomBytes(24).toString('hex')});
  try {
    assert.equal((await call('/operator/initialize',keys.OPERATOR_TOKEN,{...binding,namespace:'fixture',
      epochs:{user:'user_epoch',admin:'admin_epoch'}})).status,200);
    for(const token of [keys.APPLICATION_TOKEN,keys.PROVIDER_CHECK_TOKEN,keys.PROVIDER_REVOKE_TOKEN,'JWT'])
      assert.equal((await call('/v1/provider/enroll',token,request())).status,403);
    assert.equal((await call('/v1/provider/enroll',keys.PROVIDER_ENROLL_TOKEN,request())).status,200);
    let r=await call('/v1/provider/check',keys.PROVIDER_CHECK_TOKEN,request(),'HEAD');
    assert.equal(r.status,200);assert.equal(JSON.parse(r.headers.get('X-RosaGo-Result')).active,true);
    assert.equal(await r.text(),'');assert.equal(r.headers.get('Cache-Control'),'no-store');
    assert.equal((await call('/v1/provider/revoke',keys.PROVIDER_CHECK_TOKEN,request(),'HEAD')).status,403);
    r=await call('/v1/provider/revoke',keys.PROVIDER_REVOKE_TOKEN,request(),'HEAD');
    assert.equal(JSON.parse(r.headers.get('X-RosaGo-Result')).revoked,true);
    await mf.dispose();mf=new Miniflare(options);
    r=await call('/v1/provider/check',keys.PROVIDER_CHECK_TOKEN,request(),'HEAD');
    assert.equal(JSON.parse(r.headers.get('X-RosaGo-Result')).active,false);
    assert.equal((await call('/v1/provider/enroll',keys.PROVIDER_ENROLL_TOKEN,request())).status,503);
  } finally {await mf.dispose();rmSync(path,{recursive:true,force:true});}
});
