const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function screen(){
 const listeners={},events={},status={textContent:''},counts=[{textContent:''},{textContent:''}],buttons=[{},{}];
 const inputs=[true,true,false].map(checked=>({checked,label:{textContent:''},closest(){return {querySelector:()=>this.label};}}));
 const form={dataset:{requestedCount:'0'},querySelectorAll:s=>s.includes('selected_place_ids')?inputs:s==='[data-selection-count]'?counts:buttons,querySelector:()=>status,addEventListener:(n,f)=>events[n]=f};
 const document={body:{dataset:{uiScope:'guest'}},querySelector:s=>s==='[data-personalized-recommendations]'?form:null,addEventListener:(n,f)=>listeners[n]=f};
 vm.runInNewContext(fs.readFileSync('static/js/recommendations.js','utf8'),{document,location:{pathname:'/'},URL});
 listeners.DOMContentLoaded();return {inputs,counts,buttons,status,events};
}
test('server-selected recommendations stay selected and counts appear twice',()=>{const p=screen();assert.deepEqual(p.inputs.map(n=>n.checked),[true,true,false]);assert.deepEqual(p.counts.map(n=>n.textContent),['2 destinations selected','2 destinations selected']);assert.equal(p.inputs[2].label.textContent,'+ Add');});
test('selection changes update counts and labels without submitting',()=>{const p=screen();p.inputs[0].checked=false;p.events.change();assert.equal(p.counts[0].textContent,'1 destination selected');assert.equal(p.inputs[0].label.textContent,'+ Add');p.inputs[2].checked=true;p.events.change();assert.equal(p.counts[1].textContent,'2 destinations selected');assert.equal(p.inputs[2].label.textContent,'Selected');});
test('zero selections disables both actions and blocks native submission',()=>{const p=screen();p.inputs.forEach(n=>n.checked=false);p.events.change();assert.ok(p.buttons.every(n=>n.disabled));let prevented=false;p.events.submit({preventDefault(){prevented=true;}});assert.ok(prevented);assert.match(p.status.textContent,/at least one/);p.inputs[0].checked=true;p.events.change();assert.ok(p.buttons.every(n=>!n.disabled));});
