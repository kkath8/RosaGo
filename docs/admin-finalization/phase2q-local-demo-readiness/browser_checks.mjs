// Chromium CDP smoke test, two tabs sharing ONE temporary browser profile.
// Targets only the synthetic fixture at 127.0.0.1:5079.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const out=path.dirname(fileURLToPath(import.meta.url));
const base='http://127.0.0.1:5089';
const results=[];
const assert=(value,note)=>{if(!value)throw new Error(note);results.push({check:note,result:'PASS'});};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function tab(){
  const target=await(await fetch('http://127.0.0.1:9251/json/new?about:blank',{method:'PUT'})).json();
  const ws=new WebSocket(target.webSocketDebuggerUrl);let id=0;const pending=new Map();
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(m.error)p.reject(new Error(m.error.message));else p.resolve(m.result);}};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value;};
  await call('Page.enable');
  return {call,evaluate,close:()=>ws.close()};
}
async function wait(t,expression){for(let n=0;n<100;n++){if(await t.evaluate(expression))return;await pause(100);}throw new Error('Timeout: '+expression);}
async function go(t,url){await t.call('Page.bringToFront');await t.call('Page.navigate',{url:base+url});await wait(t,`location.pathname===${JSON.stringify(url.split('?')[0])}&&document.readyState==='complete'`);}
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
async function destinationDemo(u,a){
  await go(a,'/admin/places/new');
  await a.evaluate(`(()=>{const f=document.querySelector('[data-destination-form]');for(const [k,v] of Object.entries({name:'Q Synthetic Destination',category:'nature',description:'Synthetic demonstration record only.',address:'Synthetic Santa Rosa address',latitude:'14.31222',longitude:'121.11139'}))f.elements[k].value=v;f.requestSubmit()})()`);
  await wait(a,"/^\\/admin\\/places\\/demo-destination-/.test(location.pathname)&&document.readyState==='complete'");
  const detail=await a.evaluate('location.pathname');const slug=detail.split('/').pop();
  assert(await a.evaluate("document.body.innerText.includes('Not recorded')"),'New synthetic Draft has Environment NULL');
  assert((await u.evaluate(`fetch('/places/${slug}').then(r=>r.status)`))===404,'Draft excluded from User details');
  async function edit(environment,photo=false,remove=false,omit=false){
    await go(a,detail+'/edit');
    await a.evaluate(`(async()=>{const f=document.querySelector('[data-destination-form]');f.elements.name.value='Q Synthetic Edited';f.elements.environment.value=${JSON.stringify(environment)};
      ${photo?"const c=document.createElement('canvas');c.width=8;c.height=8;c.getContext('2d').fillRect(0,0,8,8);const b=await new Promise(r=>c.toBlob(r,'image/png'));const d=new DataTransfer();d.items.add(new File([b],'demo.png',{type:'image/png'}));f.elements.photo.files=d.files;":''}
      ${remove?"f.elements.remove_photo.checked=true;":''}
      ${omit?"f.elements.environment.disabled=true;":''}f.requestSubmit()})()`);
    await wait(a,`location.pathname===${JSON.stringify(detail)}&&document.readyState==='complete'`);
  }
  async function publication(action){
    await go(a,detail+'/publication/'+action);await a.evaluate("document.querySelector('input[name=expected_updated_at]').closest('form').requestSubmit()");
    await wait(a,`location.pathname===${JSON.stringify(detail)}&&document.readyState==='complete'`);
  }
  await edit('Indoor',true);assert(await a.evaluate("document.body.innerText.includes('Indoor')"),'Admin saves Indoor with synthetic photo');
  await publication('publish');await go(u,'/places/'+slug);
  assert(await u.evaluate("document.body.innerText.includes('Q Synthetic Edited')&&document.body.innerText.includes('Indoor')"),'Published Admin name and Environment synchronize to User');
  const first=await u.evaluate("document.querySelector('img[src*=\"/__demo/photos/\"]')?.getAttribute('src')");
  assert(!!first,'User details share uploaded synthetic photo');
  await u.evaluate("document.querySelector('img[src*=\"/__demo/photos/\"]').scrollIntoView()");
  await wait(u,"document.querySelector('img[src*=\"/__demo/photos/\"]').naturalWidth===8");assert(true,'Synthetic photo pixels load in browser');
  await edit('Outdoor',true);await go(u,'/places/'+slug);
  assert(await u.evaluate("document.body.innerText.includes('Outdoor')"),'Published Environment edit synchronizes to User');
  const replacement=await u.evaluate("document.querySelector('img[src*=\"/__demo/photos/\"]')?.getAttribute('src')");
  assert(!!replacement&&replacement!==first,'Photo replacement synchronizes to User');
  await edit('Outdoor',false,false,true);await go(u,'/places/'+slug);
  assert(await u.evaluate("document.body.innerText.includes('Outdoor')"),'Omitted Environment preserves Outdoor');
  assert((await u.evaluate("document.querySelector('img[src*=\"/__demo/photos/\"]')?.getAttribute('src')"))===replacement,'Unrelated save preserves photo');
  await edit('Mix of Both',false,true);await go(u,'/places/'+slug);
  assert(await u.evaluate("document.body.innerText.includes('Mix of Both')&&!document.querySelector('img[src*=\"/__demo/photos/\"]')"),'Mix of Both and photo unlink synchronize to User');
  await edit('');await go(u,'/places/'+slug);
  assert(await u.evaluate("document.body.innerText.includes('Not recorded')"),'Explicit clearing displays Not recorded');
  await publication('archive');
  assert((await u.evaluate(`fetch('/places/${slug}').then(r=>r.status)`))===404,'Archived synthetic destination excluded from User');
  await go(a,'/admin/audit-logs');
  assert(await a.evaluate("document.body.innerText.includes('admin-b@example.invalid')&&document.body.innerText.includes('Q Synthetic Edited')"),'Synthetic audit history attributes destination changes to Admin B');
}
let u,a;
try{
  for(let n=0;n<50;n++){try{await fetch('http://127.0.0.1:9251/json/version');break}catch{await pause(100)}}
  u=await tab();a=await tab();await u.call('Network.clearBrowserCookies');
  for(const t of [u,a])await t.call('Emulation.setDeviceMetricsOverride',{width:1440,height:960,deviceScaleFactor:1,mobile:false});
  await login(u,'user');await login(a,'admin');await identity(u,a);
  await destinationDemo(u,a);
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
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'Local synthetic fixture only; two tabs, one browser profile; outbound server connections blocked',results,passed:true},null,2));
  console.log(JSON.stringify({passed:true,checks:results.length}));
}catch(error){
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({passed:false,error:error.message,results},null,2));
  console.error(error.message);process.exitCode=1;
}finally{u?.close();a?.close();}
