// Fresh headless browser + loopback-only, network-blocked Flask fixture. No real sessions.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';
import {spawn} from 'node:child_process';
const here='docs/admin-finalization/add-destination-isolated';
const requests=[],errors=[],checks=[];
let bridge,browser,ws,server;
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'rosago-submit-offline-'));
const queue=[];
let lastResponse;
const serverReady=new Promise(resolve=>{
 server=http.createServer(async(req,res)=>{
  try{
   if(req.url.startsWith('/static/')){
    if(req.url.split('?')[0]==='/static/js/admin.js'){res.setHeader('Content-Type','text/javascript');res.end(fs.readFileSync('static/js/admin.js'));}
    else res.end('');
    return;
   }
   const chunks=[];for await(const chunk of req)chunks.push(chunk);
   const fields=[],files=[];
   if(req.method==='POST'){
    assert.equal(req.headers.origin,origin);
    const form=await new Request(origin+req.url,{method:'POST',headers:{'Content-Type':req.headers['content-type']},body:Buffer.concat(chunks)}).formData();
    for(const [key,value]of form){if(typeof value==='string')fields.push([key,value]);else if(value.name)files.push({field:key,name:value.name,mime:value.type,body:Buffer.from(await value.arrayBuffer()).toString('base64')});}
   }
   const response=await rpc({method:req.method,path:req.url,fields,files});
   lastResponse=response;requests.push({method:req.method,path:req.url,status:response.status});
   res.statusCode=response.status;if(response.location)res.setHeader('Location',response.location);
   res.setHeader('Content-Type','text/html; charset=utf-8');res.end(response.body);
  }catch(error){errors.push(error.message);res.statusCode=500;res.end('Isolated test failed');}
 }).listen(0,'127.0.0.1',resolve);
});
await serverReady;
const origin='http://127.0.0.1:'+server.address().port;
function rpc(message){return new Promise((resolve,reject)=>{queue.push({resolve,reject});bridge.stdin.write(JSON.stringify(message)+'\n');});}
const pending=new Map();let next=0;
async function cdp(method,params={}){
 return new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},10000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
}
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
async function wait(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,50));}throw Error('Browser condition timeout');}
function pass(label){checks.push(label);}
try{
 bridge=spawn(path.resolve('.venv/Scripts/python.exe'),[here+'/offline_bridge.py',origin],{windowsHide:true,stdio:['pipe','pipe','pipe']});
 const lines=readline.createInterface({input:bridge.stdout});
 let first;const ready=new Promise(resolve=>first=resolve);
 lines.on('line',line=>{try{const value=JSON.parse(line);if(value.ready)first();else queue.shift()?.resolve(value);}catch(error){queue.shift()?.reject(error);}});
 bridge.stderr.on('data',data=>errors.push('Isolated Python stderr: '+data.toString().slice(0,600)));
 await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(Error('Fixture startup timeout')),15000))]);
 browser=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'--no-first-run','--disable-sync','--disable-extensions','--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1','about:blank'],{windowsHide:true,stdio:'ignore'});
 const active=path.join(profile,'DevToolsActivePort');
 for(let i=0;i<150&&!fs.existsSync(active);i++)await new Promise(r=>setTimeout(r,100));
 assert(fs.existsSync(active),'Fresh owned Chrome did not expose DevTools port');
 const port=fs.readFileSync(active,'utf8').split('\n')[0];
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 ws.onmessage=async event=>{
  const m=JSON.parse(event.data);
  if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}}
  else if(m.method==='Fetch.requestPaused'){
   const mocked=lastResponse?.images?.[m.params.request.url];
   if(mocked){await cdp('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:mocked.mime}],body:mocked.body});return;}
   const allow=m.params.request.url.startsWith(origin+'/');
   await cdp(allow?'Fetch.continueRequest':'Fetch.failRequest',{requestId:m.params.requestId,...(!allow?{errorReason:'BlockedByClient'}:{})});
  }else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
 };
 await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});

async function go(route,selector='main'){
 await cdp('Page.navigate',{url:origin+route});
 await wait("location.pathname==="+JSON.stringify(route)+"&&document.readyState==='complete'&&!!document.querySelector("+JSON.stringify(selector)+")");
}
async function fill(values){
 await evaluate("(()=>{const f=document.querySelector('[data-destination-form]');for(const [k,v]of Object.entries("+JSON.stringify(values)+"))f.elements.namedItem(k).value=v;})()");
}
async function save(targetRoute){
 await evaluate("(()=>{const b=document.querySelector('[data-destination-form] [type=submit]');b.click();b.click();})()");
 await wait("location.pathname==="+JSON.stringify(targetRoute)+"&&document.readyState==='complete'");
}
async function choose(filename){
 const doc=await cdp('DOM.getDocument');
 const input=await cdp('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'[data-photo-input]'});
 await cdp('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[path.resolve(here,filename)]});
}
function current(id){return structuredClone(lastResponse.records.find(p=>p.id===id));}
async function postConfirmation(route){
 await go(route);
 await evaluate("document.querySelector('main form [type=submit]').click()");
 await wait("location.pathname==="+JSON.stringify(detail)+"&&document.readyState==='complete'");
}
 await go('/admin/places/new','[data-destination-form]');
 const initial=structuredClone(lastResponse.records);
 const inputs={name:'Isolated Add Venue',category:'nature',description:'Synthetic destination for offline browser tests only.',address:'Isolated test address',latitude:'14.31',longitude:'121.12',environment:'Outdoor',tourism_type:'Local',tourism_category:'Park',tourism_opening_hours_raw:'9:00 AM*',tourism_closing_hours_raw:'6:00 PM*',tourism_hours_status:'unverified'};
 let count=requests.filter(r=>r.method==='POST').length;
 await evaluate("document.querySelector('[data-destination-form] [type=submit]').click()");
 assert.equal(requests.filter(r=>r.method==='POST').length,count);pass('Empty Add form: native required-field validation blocks POST');
 await fill({...inputs,longitude:''});
 await evaluate("document.querySelector('[data-destination-form] [type=submit]').click()");
 await wait("document.readyState==='complete'&&!![...document.querySelectorAll('[role=alert]')].find(e=>e.textContent.includes('Supply latitude and longitude together'))");
 assert.deepEqual(lastResponse.records,initial);assert.equal(lastResponse.operations.length,0);
 assert.equal(await evaluate("document.querySelector('[name=name]').value"),inputs.name);
 pass('Server validation retains entered Add fields and creates no destination');
 await fill({longitude:inputs.longitude});
 const createdSlug='fixture-destination-3',detail='/admin/places/'+createdSlug,edit=detail+'/edit';
 await save(detail);
 assert.equal(lastResponse.operations.length,1);assert.equal(lastResponse.operations[0].p_action,'create');
 const created=structuredClone(lastResponse.records.find(p=>p.slug===createdSlug)),id=created.id;
 assert.equal(created.status,'draft');assert.equal(lastResponse.records.length,initial.length+1);
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/admin/places/new'&&r.status===303).length,1);
 pass('Native Add POST creates exactly one persistent Draft; rapid second click does not duplicate');
 await go('/admin/places');assert(await evaluate("document.body.innerText.includes('Isolated Add Venue')"));pass('New Draft appears in Admin management');
 await go('/places');assert(!(await evaluate("document.body.innerText.includes('Isolated Add Venue')")));
 await go('/places/'+createdSlug);assert.equal(lastResponse.status,404);pass('Draft is absent from public Explore and public detail is 404');
 await go(edit,'[data-destination-form]');
 for(const [key,value]of Object.entries(inputs))assert.equal(await evaluate("document.querySelector('[name="+key+"]').value"),value,key);
 assert.equal(await evaluate("document.querySelector('[name=expected_updated_at]').value"),created.updated_at);
 pass('Reloaded Draft preserves every entered basic/Tourism/environment field and version');

 // Explicitly test malformed duplicate controls and the existing same-name policy.
 await go('/admin/places/new','[data-destination-form]');await fill(inputs);
 await evaluate("(()=>{const i=document.createElement('input');i.name='name';i.value='Injected duplicate';document.querySelector('[data-destination-form]').append(i);document.querySelector('[data-destination-form] [type=submit]').click();})()");
 await wait("document.readyState==='complete'&&document.body.innerText.includes('Please reload this page')");
 assert.equal(lastResponse.status,403);assert.equal(lastResponse.records.length,initial.length+1);
 pass('Duplicate form fields are rejected before creation');
 await go('/admin/places/new','[data-destination-form]');await fill(inputs);
 await save('/admin/places/fixture-destination-4');
 const sameName=structuredClone(lastResponse.records.find(p=>p.slug==='fixture-destination-4'));
 assert.notEqual(sameName.id,id);assert.equal(sameName.name,created.name);assert.equal(sameName.status,'draft');
 pass('Existing same-name policy: intentional repeat creates a distinct Draft ID/slug, never overwrites an existing place');

 await go(edit,'[data-destination-form]');await choose('valid.png');await save(detail);
 const uploaded=current(id),firstUrl=uploaded.image_url;
 assert(firstUrl);assert.equal(lastResponse.storage_requests,1);
 await wait("[...document.images].some(i=>i.src==="+JSON.stringify(firstUrl)+"&&i.naturalWidth===8)");
 pass('Valid photo is stored by mocked Storage and decoded/displayed in Admin');

 await go(edit,'[data-destination-form]');
 await choose('invalid.svg');
 assert.equal(await evaluate("document.querySelector('[data-photo-input]').files.length"),0);
 assert(await evaluate("document.querySelector('[data-photo-status]').textContent.includes('Choose a non-empty')"));
 assert.equal(lastResponse.storage_requests,1);
 await choose('oversized.png');
 assert.equal(await evaluate("document.querySelector('[data-photo-input]').files.length"),0);
 assert.equal(lastResponse.storage_requests,1);pass('Browser rejects SVG and oversized photo without upload');
 await choose('corrupt.png');
 await evaluate("document.querySelector('[data-destination-form] [type=submit]').click()");
 await wait("document.readyState==='complete'&&!!document.querySelector('[role=alert]')");
 assert.equal(lastResponse.status,400);assert.deepEqual(current(id),uploaded);assert.equal(lastResponse.storage_requests,1);
 pass('Server rejects a fake PNG that passes filename/type checks; stored photo/row remain intact');

 await go(edit,'[data-destination-form]');await choose('replacement.jpg');await save(detail);
 const replaced=current(id),secondUrl=replaced.image_url;
 assert.notEqual(secondUrl,firstUrl);assert.equal(lastResponse.storage_requests,2);
 await wait("[...document.images].some(i=>i.src==="+JSON.stringify(secondUrl)+"&&i.naturalWidth===12)");
 pass('Replacement uses a new mock object and its JPEG pixels display correctly');
 await go(edit,'[data-destination-form]');
 await evaluate("document.querySelector('[data-photo-remove]').click()");
 await save(detail);
 assert.equal(current(id).image_url,null);assert.equal(lastResponse.storage_requests,2);
 assert.deepEqual(lastResponse.storage_methods,['POST','POST']);
 pass('Photo removal detaches the reference; no existing object deletion/overwrite');

 await go(detail+'/publication/publish');
 assert.equal(current(id).status,'draft');
 await evaluate("document.querySelector('main form [type=submit]').click()");
 await wait("location.pathname==="+JSON.stringify(detail)+"&&document.readyState==='complete'");
 assert.equal(current(id).status,'published');
 await go('/places');assert(await evaluate("document.body.innerText.includes('Isolated Add Venue')"));
 await go('/places/'+createdSlug);assert(await evaluate("document.body.innerText.includes('Synthetic destination for offline browser tests only.')"));
 pass('Explicit publish confirmation makes the synthetic Draft visible in User Explore/detail');
 await go(edit,'[data-destination-form]');await fill({description:'Updated synthetic published description.'});await save(detail);
 await go('/places/'+createdSlug);
 assert(await evaluate("document.body.innerText.includes('Updated synthetic published description.')"));
 pass('Editing the newly published destination synchronizes its updated description');
 await postConfirmation(detail+'/publication/archive');
 assert.equal(current(id).status,'archived');
 await go('/places');assert(!(await evaluate("document.body.innerText.includes('Isolated Add Venue')")));
 await go('/places/'+createdSlug);assert.equal(lastResponse.status,404);
 pass('Archive retains Admin record and removes it from public Explore/detail');
 for(const row of initial)assert.deepEqual(lastResponse.records.find(p=>p.id===row.id),row);
 assert.deepEqual(lastResponse.records.find(p=>p.id===sameName.id),sameName);
 pass('All pre-existing destinations/photos and the unrelated same-name Draft remain unchanged');

 assert.deepEqual(errors,[]);
 fs.writeFileSync(here+'/browser-results.json',JSON.stringify({passed:checks.length,checks,requests,errors,hosted_requests:0,production_writes:0,application_js_changed:false,phases:['Draft creation','Photo management','Publication and synchronization']},null,2));
 console.log(JSON.stringify({passed:checks.length,checks,requests,errors},null,2));
}catch(error){
 fs.writeFileSync(here+'/browser-results.json',JSON.stringify({passed:checks.length,checks,requests,errors,failure:error.message},null,2));
 console.error(JSON.stringify({passed:checks.length,checks,requests,errors,failure:error.message},null,2));
 throw error;
}finally{
 if(ws?.readyState===1)ws.close();
 bridge?.stdin.end();bridge?.kill();
 browser?.kill();
 server?.close();
}
