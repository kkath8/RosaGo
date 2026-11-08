import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {browser,origin,save,here} from './browser_common.mjs';
const results=[];
const check=(value,label)=>{assert.ok(value,label);results.push({check:label,result:'PASS'});};
const state=async()=>await(await fetch(origin+'/__isolated/state')).json();
const b=await browser();
async function shot(name){const r=await b.tab.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync(new URL(name,here),Buffer.from(r.data,'base64'));}
async function saveForm(){await b.click('[data-destination-form] button[type="submit"]');await b.wait("location.pathname==='/admin/places/manual-test-garden'&&document.readyState==='complete'");}
try {
  const before=await state();save('before-browser-edit.json',before);
  await b.go('/admin/places/manual-test-garden/edit');
  check(await b.evaluate(`(()=>{const f=document.querySelector('[data-destination-form]');return f.elements.name.value==='Manual Test Garden'&&f.elements.description.value==='Isolated saved description.'&&f.elements.category.value==='nature'&&f.elements.address.value==='Isolated Santa Rosa test address'&&f.elements.latitude.value==='14.3'&&f.elements.longitude.value==='121.1'&&f.elements.environment.value==='Indoor';})()`),'Actual edit form prepopulates all existing fields');
  await b.evaluate(`(()=>{const f=document.querySelector('[data-destination-form]');for(const[k,v]of Object.entries({name:'Priority Edited Garden',description:'Priority isolated browser verification.',category:'attraction',address:'Isolated updated Santa Rosa test address',latitude:'14.31',longitude:'121.12',environment:'Outdoor'}))f.elements[k].value=v;})()`);
  await saveForm();
  const edited=await state();save('after-detail-save.json',edited);
  check(edited.mutation_actions.length===1&&edited.rows[1].name==='Priority Edited Garden','Actual browser Save updates selected existing record');
  check(edited.rows[1].id===before.rows[1].id&&edited.rows[1].slug===before.rows[1].slug&&edited.row_count===2,'Existing ID/slug preserved with no duplicate');
  assert.deepEqual(edited.rows[0],before.rows[0]);check(true,'Unrelated destination unchanged after Save');
  check(edited.rows[1].status==='published'&&edited.rows[1].image_url===before.rows[1].image_url,'Ordinary edit preserves publication and photo');
  await shot('admin-after-save.png');
  await b.go('/admin/places/manual-test-garden/edit');
  check(await b.evaluate("document.querySelector('[data-destination-form]').elements.name.value==='Priority Edited Garden'&&document.querySelector('[data-destination-form]').elements.environment.value==='Outdoor'"),'Refresh/reopen retains saved information');
  await b.go('/places');
  check(await b.evaluate("document.body.innerText.includes('Priority Edited Garden')&&document.body.innerText.includes('Unrelated Test Museum')&&!document.body.innerText.includes('Manual Test Garden')"),'Published edit appears in actual User Explore');
  await shot('explore-after-save.png');
  await b.go('/places/manual-test-garden');
  check(await b.evaluate("document.body.innerText.includes('Priority isolated browser verification.')&&document.body.innerText.includes('Outdoor')"),'User destination details show saved description/environment');

  await b.go('/admin/places/manual-test-garden/edit');
  const documentNode=await b.tab.call('DOM.getDocument');
  const fileNode=await b.tab.call('DOM.querySelector',{nodeId:documentNode.root.nodeId,selector:'[data-photo-input]'});
  await b.tab.call('DOM.setFileInputFiles',{nodeId:fileNode.nodeId,files:[fileURLToPath(new URL('replacement-test.png',here))]});
  await saveForm();
  const replaced=await state();save('after-photo-replacement.json',replaced);
  check(replaced.rows[1].image_url!==edited.rows[1].image_url&&replaced.synthetic_photo_count===3,'Replacement uses new mocked Storage object and URL');
  assert.deepEqual(replaced.rows[0],before.rows[0]);
  await b.go('/places/manual-test-garden');
  await b.wait("[...document.images].some(i=>i.getAttribute('src')?.startsWith('/__edit_demo/photos/')&&i.naturalWidth===8)");
  check(true,'Replacement photo pixels load in real browser User details');

  await b.go('/admin/places/manual-test-garden/edit');
  await b.evaluate("(()=>{const f=document.querySelector('[data-destination-form]');f.elements.description.value='Validation correction retained.';f.elements.longitude.value='';})()");
  await b.click('[data-photo-remove]');
  await b.click('[data-destination-form] button[type="submit"]');
  await b.wait("document.readyState==='complete'&&!![...document.querySelectorAll('[role=alert]')].find(e=>e.textContent.includes('Supply latitude and longitude together'))");
  check(await b.evaluate("(()=>{const f=document.querySelector('[data-destination-form]');return f.elements.remove_photo.checked&&f.elements.name.value==='Priority Edited Garden'&&f.elements.description.value==='Validation correction retained.'&&f.elements.category.value==='attraction'&&f.elements.address.value==='Isolated updated Santa Rosa test address'&&f.elements.latitude.value==='14.31'&&f.elements.longitude.value===''&&f.elements.environment.value==='Outdoor';})()"),'Server validation preserves entered fields and photo-removal selection');
  const rejected=await state();assert.deepEqual(rejected.rows,replaced.rows);
  check(rejected.mutation_actions.length===2&&rejected.synthetic_photo_count===3,'Rejected submission changes no destination or photo');
  await shot('validation-removal-retained.png');
  await b.evaluate("document.querySelector('[data-destination-form]').elements.longitude.value='121.12'");
  await saveForm();
  const removed=await state();save('after-removal-save.json',removed);
  check(removed.rows[1].image_url===null&&removed.rows[1].description==='Validation correction retained.','Corrected save performs intended photo detachment');
  check(removed.synthetic_photo_count===3,'Photo removal does not delete or overwrite Storage objects');
  assert.deepEqual(removed.rows[0],before.rows[0]);
  check(removed.row_count===2&&removed.same_target_id&&removed.unrelated_unchanged,'Final ID, row count and unrelated destination preserved');
  await b.go('/places');
  check(await b.evaluate("document.body.innerText.includes('Priority Edited Garden')&&document.body.innerText.includes('Unrelated Test Museum')"),'Final saved target remains published in Explore');
  await b.go('/places/manual-test-garden');
  check(await b.evaluate("document.body.innerText.includes('Validation correction retained.')&&![...document.images].some(i=>i.getAttribute('src')?.startsWith('/__edit_demo/photos/'))"),'User details reflect final description and removed photo');
  save('browser-edit-results.json',{results,passed:results.length,failures:0,real_provider_requests:0});
  console.log(JSON.stringify({passed:results.length,failures:0,actual_mock_edits:removed.mutation_actions.length}));
} catch(error){save('browser-edit-results.json',{results,passed:results.length,failures:1,failure:error.message});throw error;}
finally{await b.close();}
