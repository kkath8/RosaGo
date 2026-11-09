import fs from 'node:fs';
export const here = new URL('./', import.meta.url);
export const ready = JSON.parse(fs.readFileSync(new URL('ready.json', here), 'utf8'));
export const origin = ready.origin;
export function save(name, data) {fs.writeFileSync(new URL(name, here), JSON.stringify(data, null, 2));}
function channel(url) {
  const ws = new WebSocket(url), pending = new Map(); let next = 0;
  const connected = new Promise((resolve, reject) => {ws.onopen=resolve;ws.onerror=()=>reject(new Error('Browser connection failed'));});
  ws.onmessage = async event => {
    const message=JSON.parse(event.data);
    if (message.id) {
      const item=pending.get(message.id);if(!item)return;pending.delete(message.id);clearTimeout(item.timer);
      message.error?item.reject(new Error('Browser protocol rejected '+item.method)):item.resolve(message.result);
    } else if(message.method==='Fetch.requestPaused') {
      const u=new URL(message.params.request.url);
      const allow=u.origin===origin||['data:','blob:','about:'].includes(u.protocol);
      await call(allow?'Fetch.continueRequest':'Fetch.failRequest', {requestId:message.params.requestId,...(!allow?{errorReason:'BlockedByClient'}:{})});
    }
  };
  async function call(method,params={}) {await connected;return new Promise((resolve,reject)=>{const id=++next;
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Browser timeout: '+method));},15000);
    pending.set(id,{resolve,reject,timer,method});ws.send(JSON.stringify({id,method,params}));});}
  return {call,close:()=>ws.close()};
}
export async function browser({newContext=false}={}) {
  const stateResponse=await fetch(origin+'/__isolated/state'), state=await stateResponse.json();
  if(state.run_id!==ready.run_id||stateResponse.headers.get('x-rosago-isolated-instance')!==ready.run_id||state.unexpected_guard_attempts) throw new Error('Isolated app mismatch');
  const meta=await(await fetch('http://127.0.0.1:9266/json/version')).json();
  const root=channel(meta.webSocketDebuggerUrl);
  const owner=JSON.parse(fs.readFileSync(new URL('browser-process.json',here),'utf8').replace(/^\uFEFF/,''));
  const processes=await root.call('SystemInfo.getProcessInfo');
  if(!processes.processInfo.some(p=>p.type==='browser'&&p.id===owner.pid))throw new Error('Task-owned browser mismatch');
  let context, selected;
  if(newContext){context=(await root.call('Target.createBrowserContext')).browserContextId;selected=(await root.call('Target.createTarget',{url:'about:blank',browserContextId:context})).targetId;}
  const pages=await(await fetch('http://127.0.0.1:9266/json/list')).json();
  const target=(selected?pages.find(p=>p.id===selected):pages.find(p=>p.type==='page'&&p.url.startsWith(origin)))||await(await fetch('http://127.0.0.1:9266/json/new?about:blank',{method:'PUT'})).json();
  const tab=channel(target.webSocketDebuggerUrl);
  await tab.call('Page.enable');await tab.call('Network.enable');
  await tab.call('Network.setBlockedURLs',{urls:['https://*']});
  await tab.call('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  async function evaluate(expression){const r=await tab.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error('Page operation failed');return r.result.value;}
  async function wait(expression){for(let i=0;i<150;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}throw new Error('Page readiness timeout');}
  async function go(path){await tab.call('Page.navigate',{url:origin+path});await wait(`location.pathname===${JSON.stringify(path)}&&document.readyState==='complete'`);}
  async function click(selector){const rect=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();const h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {x:r.x+r.width/2,y:r.y+r.height/2,reachable:h===e||e.contains(h)};})()`);
    if(!rect?.reachable)throw new Error('Control is covered or unavailable: '+selector);
    await tab.call('Input.dispatchMouseEvent',{type:'mousePressed',x:rect.x,y:rect.y,button:'left',clickCount:1});
    await tab.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:rect.x,y:rect.y,button:'left',clickCount:1});}
  return {root,tab,evaluate,wait,go,click,close:async()=>{await tab.call('Fetch.disable');if(context)await root.call('Target.disposeBrowserContext',{browserContextId:context});tab.close();root.close();}};
}
