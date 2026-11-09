// Test-only stdin bridge. No listener, deployment, real credentials or accounts.
import readline from 'node:readline';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {Miniflare,Log,LogLevel,convertV4MiniflareOptions} from 'miniflare';
const [path,id,incarnation]=process.argv.slice(2);
const keys=Object.fromEntries(['APPLICATION_TOKEN','OPERATOR_TOKEN','PROVIDER_ENROLL_TOKEN',
  'PROVIDER_CHECK_TOKEN','PROVIDER_REVOKE_TOKEN'].map(k=>[k,randomBytes(32).toString('hex')]));
const bundle=await build({entryPoints:[fileURLToPath(new URL('../worker.mjs',import.meta.url))],
  bundle:true,write:false,format:'esm',platform:'neutral',external:['cloudflare:workers']});
const options=convertV4MiniflareOptions({name:'rosago-provider-native-fixture',modules:true,
  script:bundle.outputFiles[0].text,compatibilityDate:'2026-11-07',host:'127.0.0.1',
  port:0,inspectorPort:0,log:new Log(LogLevel.NONE),telemetry:{enabled:false},cf:false,
  durableObjects:{AUTHORITY:{className:'SessionAuthority',useSQLite:true}},
  resourcePersistencePath:path,isolatedResourcePersistencePath:path,
  bindings:{...keys,AUTHORITY_ID:id,AUTHORITY_INCARNATION:incarnation,AUTHORITY_OBJECT:'fixture',
    PROVIDER_ISSUER:'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1'}});
let mf=new Miniflare(options);await mf.ready;
process.stdout.write('{"fixture_ready":true}\n');
try {
  for await(const line of readline.createInterface({input:process.stdin})) {
    try {
      const {operation,request,head=false}=JSON.parse(line);
      if(operation==='restart') {await mf.dispose();mf=new Miniflare(options);await mf.ready;
        process.stdout.write('{"restarted":true}\n');continue;}
      const route=operation==='initialize'?'/operator/initialize':operation==='block'?'/operator/block':'/v1/provider/'+operation;
      const key=keys[operation==='enroll'?'PROVIDER_ENROLL_TOKEN':['revoke','constrain'].includes(operation)?'PROVIDER_REVOKE_TOKEN':
        ['initialize','block'].includes(operation)?'OPERATOR_TOKEN':'PROVIDER_CHECK_TOKEN'];
      const r=await mf.dispatchFetch('https://authority.invalid'+route,{method:head?'HEAD':'POST',
        headers:{Authorization:'Bearer '+key,...(head?{'X-RosaGo-Request':JSON.stringify(request)}:{})},
        ...(head?{}:{body:JSON.stringify(request)})});
      const value=r.status===200 ? head?JSON.parse(r.headers.get('X-RosaGo-Result')):await r.json():null;
      process.stdout.write(JSON.stringify({status:r.status,value})+'\n');
    } catch {process.stdout.write('{"fixture_error":true}\n');}
  }
}finally{await mf.dispose();}
