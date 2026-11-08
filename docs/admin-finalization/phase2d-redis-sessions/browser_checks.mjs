// Chromium CDP smoke test, two tabs sharing ONE temporary browser profile.
// Targets only the synthetic fixture at 127.0.0.1:5080, alternating Redis workers.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const out=path.dirname(fileURLToPath(import.meta.url));
const base='http://127.0.0.1:5080';
const results=[];
const assert=(value,note)=>{if(!value)throw new Error(note);results.push({check:note,result:'PASS'});};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function tab(){
  const target=await(await fetch('http://127.0.0.1:9248/json/new?about:blank',{method:'PUT'})).json();
  const ws=new WebSocket(target.webSocketDebuggerUrl);let id=0;const pending=new Map();
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(m.error)p.reject(new Error(m.error.message));else p.resolve(m.result);}};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value;};
  await call('Page.enable');
  return {call,evaluate,close:()=>ws.close()};
}
async function wait(t,expression){for(let n=0;n<100;n++){if(await t.evaluate(expression))return;await pause(100);}throw new Error('Timeout: '+expression);}
async function go(t,url){await t.call('Page.navigate',{url:base+url});await wait(t,`location.pathname===${JSON.stringify(url.split('?')[0])}&&document.readyState==='complete'`);}
async function login(t,realm){
  await go(t,realm==='admin'?'/admin/login':'/login');
  const email=realm==='admin'?'admin-b@example.invalid':'user-a@example.invalid';
  await t.evaluate(`(()=>{const f=document.querySelector(${JSON.stringify(realm==='admin'?'form.admin-login-form':'#login-form')});f.querySelector('[name=email]').value=${JSON.stringify(email)};f.querySelector('[name=password]').value='Local-test-password-1!';f.requestSubmit();})()`);
  await wait(t,`location.pathname===${JSON.stringify(realm==='admin'?'/admin':'/')}&&document.readyState==='complete'`);
}
async function logout(t,realm){
  await go(t,realm==='admin'?'/admin/account':'/user');
  await t.evaluate(`document.querySelector('form[action="${realm==='admin'?'/admin/logout':'/logout'}"]').requestSubmit()`);
  await wait(t,`location.pathname===${JSON.stringify(realm==='admin'?'/admin/login':'/login')}&&document.readyState==='complete'`);
}
async function identity(u,a){
  assert((await u.evaluate("fetch('/auth/status').then(r=>r.json())")).email==='user-a@example.invalid','User identity remains A');
  await go(a,'/admin/account');
  assert(await a.evaluate("document.body.innerText.includes('admin-b@example.invalid')&&!document.body.innerText.includes('user-a@example.invalid')"),'Admin account remains B');
}
async function shot(t,name){
  await pause(200);
  assert(await t.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),name+' has no horizontal overflow');
  const r=await t.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync(path.join(out,name+'.png'),Buffer.from(r.data,'base64'));
}
let u,a;
try{
  u=await tab();a=await tab();
  for(const t of [u,a])await t.call('Emulation.setDeviceMetricsOverride',{width:1440,height:960,deviceScaleFactor:1,mobile:false});
  await login(u,'user');await login(a,'admin');await identity(u,a);
  await go(u,'/user');await shot(u,'desktop-user-a');await shot(a,'desktop-admin-b');
  await logout(u,'user');
  assert(!(await u.evaluate("fetch('/auth/status').then(r=>r.json())")).authenticated,'Desktop User logout clears User');
  await go(a,'/admin/account');assert(await a.evaluate("document.body.innerText.includes('admin-b@example.invalid')"),'Desktop User logout preserves Admin B');
  await logout(a,'admin');
  for(const t of [u,a])await t.call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await go(u,'/login');await shot(u,'mobile-user-login');await go(a,'/admin/login');await shot(a,'mobile-admin-login');
  await login(a,'admin');await login(u,'user');await identity(u,a);
  await go(u,'/user');
  assert(await u.evaluate("!!document.querySelector('[aria-label=\"More navigation\"]')"),'Mobile User navigation available');
  await u.evaluate("document.querySelector('[aria-label=\"More navigation\"]').click()");
  await wait(u,"document.querySelector('#more-dialog').open");
  assert(true,'Mobile navigation dialog opens');
  await u.evaluate("document.querySelector('#more-dialog').close()");
  await a.evaluate("document.querySelector('.admin-mobile-menu>summary').click()");
  await wait(a,"document.querySelector('.admin-mobile-menu').open");
  assert(true,'Mobile Admin navigation opens');
  await a.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
  await wait(a,"!document.querySelector('.admin-mobile-menu').open");
  assert(true,'Mobile Admin navigation closes with Escape');
  await shot(u,'mobile-user-a');await shot(a,'mobile-admin-b');
  await logout(a,'admin');
  assert((await u.evaluate("fetch('/auth/status').then(r=>r.json())")).email==='user-a@example.invalid','Mobile Admin logout preserves User A');
  await logout(u,'user');
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'Local synthetic fixture; two alternating app instances, shared loopback Redis; two tabs, one browser profile; external socket connects blocked',results,passed:true},null,2));
  console.log(JSON.stringify({passed:true,checks:results.length}));
}catch(error){
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({passed:false,error:error.message,results},null,2));
  console.error(error.message);process.exitCode=1;
}finally{u?.close();a?.close();}
