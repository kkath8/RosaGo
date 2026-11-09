// Local fixture diagnostics only; no cookies, storage or credentials read.
const targets=await(await fetch('http://127.0.0.1:9251/json/list')).json();
for(const target of targets.filter(t=>t.type==='page'&&t.url.startsWith('http://127.0.0.1:5089/places/'))){
  const ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise(r=>ws.onopen=r);
  ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:'JSON.stringify(Array.from(document.images).map(i=>({src:i.getAttribute("src"),width:i.naturalWidth,height:i.naturalHeight,loading:i.loading,complete:i.complete})))',returnByValue:true}}));
  await new Promise(resolve=>{ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.id===1){console.log(r.result.result.value);ws.close();resolve()}}});
}
