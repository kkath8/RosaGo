import {browser,ready,save} from './browser_common.mjs';
const b=await browser();
try {
  await b.go('/__isolated');
  if(await b.evaluate("document.getElementById('instance-id').textContent")!==ready.run_id)throw new Error('Visible identity mismatch');
  await b.click('form[action="/__isolated/confirm"] button');
  await b.wait("location.pathname==='/admin/login'&&document.readyState==='complete'");
  const geometry=await b.evaluate(`(()=>{const e=document.getElementById('fill-synthetic-admin');e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();const h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {button_present:!!e,button_visible:getComputedStyle(e).visibility,button_display:getComputedStyle(e).display,button_rectangle:{x:r.x,y:r.y,width:r.width,height:r.height},hit_element:{tag:h?.tagName,id:h?.id,className:h?.className},button_reachable:h===e||e.contains(h)};})()`);
  save('browser-probe.json',{browser_identity_matches:true,geometry});
  console.log(JSON.stringify({browser_identity_matches:true,...geometry}));
} finally {await b.close();}
