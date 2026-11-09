// Test-only local workerd process. Nothing is deployed; tokens are synthetic
// and remain in this process. The parent authenticates its own loopback shim.
import readline from 'node:readline';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {Miniflare,Log,LogLevel,convertV4MiniflareOptions} from 'miniflare';
const [path,id,incarnation]=process.argv.slice(2);
const application=randomBytes(32).toString('hex'),operator=randomBytes(32).toString('hex');
const bundle=await build({entryPoints:[fileURLToPath(new URL('../worker.mjs',import.meta.url))],
  bundle:true,write:false,format:'esm',platform:'neutral',external:['cloudflare:workers']});
const options=convertV4MiniflareOptions({name:'rosago-local-integration',modules:true,
  script:bundle.outputFiles[0].text,compatibilityDate:'2026-11-07',host:'127.0.0.1',
  port:0,inspectorPort:0,log:new Log(LogLevel.NONE),telemetry:{enabled:false},cf:false,
  durableObjects:{AUTHORITY:{className:'SessionAuthority',useSQLite:true}},
  resourcePersistencePath:path,isolatedResourcePersistencePath:path,
  bindings:{AUTHORITY_ID:id,AUTHORITY_INCARNATION:incarnation,AUTHORITY_OBJECT:'local-integration',
    APPLICATION_TOKEN:application,OPERATOR_TOKEN:operator}});
const mf=new Miniflare(options);
await mf.ready;
process.stdout.write(JSON.stringify({fixture_ready:true})+'\n');
try {
  for await(const line of readline.createInterface({input:process.stdin})) {
    try {
      const request=JSON.parse(line);const control=request.test_control;
      const route=control==='initialize' ? '/operator/initialize' : control==='block' ? '/operator/block' : '/v1/authority';
      const response=await mf.dispatchFetch('https://authority.invalid'+route,{method:'POST',
        headers:{Authorization:'Bearer '+(control ? operator : application)},
        body:JSON.stringify(control==='initialize' ? request.config : control ? {} : request)});
      const value=response.status===200 ? await response.json() : {test_error:true};
      process.stdout.write(JSON.stringify(value)+'\n');
    } catch {process.stdout.write(JSON.stringify({test_error:true})+'\n');}
  }
} finally {await mf.dispose();}
