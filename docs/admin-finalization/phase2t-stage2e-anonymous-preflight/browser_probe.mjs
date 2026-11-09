// Fresh anonymous headless profile. No cookies/headers/bodies are exported.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../../..');
const expected=JSON.parse(fs.readFileSync(path.join(here,'ready.json'),'utf8'));
const profile=path.join(root,'p2e_'+Math.random().toString(16).slice(2,8));
fs.mkdirSync(profile);
const result={passed:false,run_id:expected.run_id,forms_submitted:0,cookies_inspected:0,
  external_page_requests_blocked:0,navigations:[],profile_fresh:true};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let browser,ws;
try{
 browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[
  '--headless=new','--inprivate','--no-first-run','--disable-sync','--disable-extensions',
  '--disable-background-networking','--disable-component-update',
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
  {windowsHide:true,stdio:'ignore'});
 browser.on('error',()=>{});
 let port;
 for(let n=0;n<80;n++){try{port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);if(port)break;}catch{}await pause(100);}
 if(!port)throw new Error('Browser debugging unavailable');
 const targets=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 const target=targets.find(t=>t.type==='page');
 ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
 let serial=0;const pending=new Map();
 const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 ws.onmessage=e=>{const value=JSON.parse(e.data);if(value.id){const p=pending.get(value.id);pending.delete(value.id);value.error?p?.reject(new Error('Browser command failed')):p?.resolve(value.result);}
  if(value.method==='Fetch.requestPaused'){
   const r=value.params;let allowed=false;try{const u=new URL(r.request.url);allowed=u.origin===expected.origin&&['GET','HEAD'].includes(r.request.method);}catch{}
   if(!allowed)result.external_page_requests_blocked++;
   call(allowed?'Fetch.continueRequest':'Fetch.failRequest',allowed?{requestId:r.requestId}:{requestId:r.requestId,errorReason:'BlockedByClient'}).catch(()=>{});
  }};
 const evaluate=async expression=>(await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})).result.value;
 await call('Page.enable');await call('Runtime.enable');await call('Fetch.enable',{patterns:[{urlPattern:'*'}]});
 for(const pathname of ['/__verify/start','/__verify/confirm','/login']){
  await call('Page.navigate',{url:expected.origin+pathname});
  let ready=false;
  for(let n=0;n<60;n++){ready=await evaluate(`location.origin===${JSON.stringify(expected.origin)}&&location.pathname===${JSON.stringify(pathname)}&&document.readyState==='complete'`);if(ready)break;await pause(100);}
  result.navigations.push({path:pathname,ready:!!ready});if(!ready)throw new Error('Navigation mismatch');
 }
 const identity=await evaluate(`fetch('/__verify/identity',{cache:'no-store'}).then(async r=>({status:r.status,run:r.headers.get('X-RosaGo-Verification-Run'),body:await r.json()}))`);
 result.identity_status=identity.status;result.pid_matches=identity.body.pid===expected.pid;
 result.marker_confirmed=identity.body.browser_preflight===true;
 result.login_get_captured=identity.body.browser_login_get===true;
 result.armed=identity.body.armed;result.spent=identity.body.spent;
 result.passed=identity.status===200&&identity.run===expected.run_id&&identity.body.run_id===expected.run_id
  &&result.pid_matches&&result.marker_confirmed&&result.login_get_captured&&!result.armed&&!result.spent;
}catch{result.failure='anonymous_browser_path_not_qualified';}
finally{
 ws?.close();browser?.kill();await pause(500);
 // Delete only this verified test-owned workspace profile; never inspect its files.
 if(path.dirname(profile)===root&&path.basename(profile).startsWith('p2e_')){
  try{fs.rmSync(profile,{recursive:true,force:true,maxRetries:4,retryDelay:250});result.profile_removed=true;}catch{result.profile_removed=false;}
 }
 fs.writeFileSync(path.join(here,'browser-results.json'),JSON.stringify(result,null,2)+'\n');
}
console.log(JSON.stringify(result));
process.exit(result.passed?0:1);
