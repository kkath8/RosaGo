// Fresh headless browser + loopback-only, network-blocked Flask fixture. No real sessions.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';
import {spawn} from 'node:child_process';
const here='docs/admin-finalization/explore-save-diagnosis', edit='/admin/places/existing-garden/edit';
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
   const fields=[];
   if(req.method==='POST'){
    assert.equal(req.headers.origin,origin);
    const form=await new Request(origin+req.url,{method:'POST',headers:{'Content-Type':req.headers['content-type']},body:Buffer.concat(chunks)}).formData();
    for(const [key,value]of form)if(typeof value==='string')fields.push([key,value]);
   }
   const response=await rpc({method:req.method,path:req.url,fields});
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
   const allow=m.params.request.url.startsWith(origin+'/');
   await cdp(allow?'Fetch.continueRequest':'Fetch.failRequest',{requestId:m.params.requestId,...(!allow?{errorReason:'BlockedByClient'}:{})});
  }else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
 };
 await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
 await cdp('Page.navigate',{url:origin+edit});
 await wait("document.readyState==='complete'&&!!document.querySelector('[data-destination-form]')");
 const initial=structuredClone(lastResponse.records);
 const form=await evaluate("(()=>{const f=document.querySelector('[data-destination-form]'),b=f.querySelector('[type=submit]');return {method:f.method,action:f.action,valid:f.checkValidity(),disabled:b.disabled};})()");
 assert.equal(form.method,'post');assert.equal(form.action,origin+edit);assert(form.valid&&!form.disabled);pass('Actual rendered form: correct POST/action/valid enabled submit');
 await evaluate("document.querySelector('[name=description]').value='Offline description check.'");
 assert.equal(requests.filter(r=>r.method==='POST').length,0);pass('Typing marker alone sends no POST and is unsaved');
 await evaluate("(()=>{const b=document.querySelector('[data-destination-form] [type=submit]');b.click();b.click();})()");
 await wait("location.pathname==='/admin/places/existing-garden'&&document.readyState==='complete'");
 assert.equal(requests.filter(r=>r.method==='POST').length,1);
 assert.equal(lastResponse.operations.length,1);
 assert.equal(lastResponse.records[1].description,'Offline description check.');
 assert.equal(lastResponse.records[1].image_url,initial[1].image_url);
 assert.deepEqual(lastResponse.records[0],initial[0]);assert.equal(lastResponse.storage_requests,0);
 pass('Synchronous disabling does NOT cancel native POST; immediate second click produces no duplicate');
 pass('Real Flask route + mocked SDK persist description, preserve photo/unrelated row, redirect 303');
 await cdp('Page.navigate',{url:origin+'/places/existing-garden'});
 await wait("document.readyState==='complete'&&document.body.innerText.includes('Offline description check.')");pass('User public detail reflects mocked saved published description');
 await cdp('Page.navigate',{url:origin+edit});await wait("document.readyState==='complete'&&!!document.querySelector('[data-destination-form]')");
 await evaluate("document.querySelector('[name=name]').value='';document.querySelector('[data-destination-form] [type=submit]').click()");
 assert.equal(requests.filter(r=>r.method==='POST').length,1);
 assert.equal(await evaluate("document.querySelector('[data-destination-form]').checkValidity()"),false);
 pass('Native validation failure blocks POST; not a database/JavaScript Save success');
 assert.deepEqual(errors,[]);
 fs.writeFileSync(here+'/browser-results.json',JSON.stringify({passed:checks.length,checks,requests,errors,hosted_requests:0,production_writes:0,application_js_changed:false},null,2));
 console.log(JSON.stringify({passed:checks.length,checks,requests,errors},null,2));
}finally{
 if(ws?.readyState===1)ws.close();
 bridge?.stdin.end();bridge?.kill();
 browser?.kill();
 server?.close();
}
