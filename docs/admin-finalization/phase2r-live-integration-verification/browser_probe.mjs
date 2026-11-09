// Read-only localhost/CDP navigation. No forms submitted; no screenshots/text saved.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const result={forms_submitted:0,real_logins:0,javascript_exception_count:0,pages:{}};
let ws;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
try{
  for(let n=0;n<50;n++){try{await fetch('http://127.0.0.1:9252/json/version');break}catch{await pause(100)}}
  const target=await(await fetch('http://127.0.0.1:9252/json/new?about:blank',{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
  let id=0;const pending=new Map();
  ws.onmessage=e=>{const v=JSON.parse(e.data);if(v.method==='Runtime.exceptionThrown')result.javascript_exception_count++;
    if(v.id){const p=pending.get(v.id);pending.delete(v.id);v.error?p.reject(new Error('CDP command failed')):p.resolve(v.result)}};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const current=++id;pending.set(current,{resolve,reject});ws.send(JSON.stringify({id:current,method,params}))});
  const evaluate=async expression=>(await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})).result.value;
  await call('Runtime.enable');await call('Network.enable');await call('Network.clearBrowserCookies');await call('Page.enable');await call('Page.bringToFront');
  for(const page of ['/login','/admin/login','/places','/map']){
    await call('Page.navigate',{url:'http://127.0.0.1:5099'+page});
    for(let n=0;n<100;n++){if(await evaluate(`location.pathname===${JSON.stringify(page)}&&document.readyState==='complete'`))break;await pause(100)}
    result.pages[page]=await evaluate(`({pathMatches:location.pathname===${JSON.stringify(page)},documentReady:document.readyState==='complete'})`);
  }
  await pause(4000);
  result.map=await evaluate(`({leafletLoaded:!!window.L,leafletVersion:window.L?.version||null,mapInitialized:!!document.querySelector('#places-map.leaflet-container:not([hidden])'),markers:document.querySelectorAll('.leaflet-marker-icon').length,loadedTiles:Array.from(document.querySelectorAll('img.leaflet-tile')).filter(i=>i.complete&&i.naturalWidth>0).length,tileFailureShown:document.querySelector('#map-tile-failure')?.hidden===false})`);
  const cookies=(await call('Network.getAllCookies')).cookies;
  result.cookies=cookies.filter(c=>['session','rosago_admin_session_dev'].includes(c.name)).map(c=>({name:c.name,path:c.path,httpOnly:c.httpOnly,secure:c.secure,sameSite:c.sameSite||'not explicitly set'}));
  result.navigation_completed=true;
}catch(error){result.navigation_completed=false;result.error='Local browser probe failed; no provider details retained'}
finally{ws?.close();fs.writeFileSync(path.join(here,'browser-results.json'),JSON.stringify(result,null,2));fs.writeFileSync(path.join(here,'browser-done.json'),JSON.stringify({done:true}));}
console.log(JSON.stringify({navigation_completed:result.navigation_completed,map:result.map||null,real_logins:0}));
