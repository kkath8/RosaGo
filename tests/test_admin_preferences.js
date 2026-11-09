const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/admin-preferences.js', 'utf8');
const key = 'rosago.admin.preferences.v1';
function page(raw, {blocked=false, timestamp='2026-11-03T04:05:06Z', catalogURL=null,
    withForm=false, writeFailure=false, dropWrites=false}={}) {
    const root={dataset:{}}, events={}, windowEvents={}, reads=[], redirects=[];
    let stored=raw;
    const formEvents={},writes=[],status={dataset:{},textContent:''},save={disabled:true};
    const controls=Object.fromEntries(['density','reduceMotion','reviewAlerts','successNotices','sort','pageSize','status','timeFormat','dateFormat'].map(name=>[name,{value:'',checked:false}]));
    const form={elements:{namedItem:name=>controls[name]},
        querySelector:s=>s==='[data-save-preferences]'?save:status,
        addEventListener:(name,fn)=>formEvents[name]=fn};
    const node={dataset:{adminDate:'split'},textContent:'original',attrs:{datetime:timestamp},
        getAttribute(k){return this.attrs[k];},setAttribute(k,v){this.attrs[k]=v;},
        append(child){this.textContent+=' '+child.textContent;}};
    vm.runInNewContext(source, {
        document:{documentElement:root,querySelectorAll:()=>[node],
            querySelector:s=>s==='[data-admin-catalog]' && catalogURL ? {} :
                s==='[data-admin-preferences-form]' && withForm ? form :
                s==='[data-preferences-status]' && withForm ? status : null,
            createElement:()=>({}),addEventListener:(k,f)=>events[k]=f},
        localStorage:{getItem:k=>{reads.push(k);if(blocked)throw Error();return stored;},
            setItem:(k,value)=>{if(writeFailure)throw Error();writes.push([k,value]);if(!dropWrites)stored=value;}},
        window:{addEventListener:(k,f)=>windowEvents[k]=f,
            location:{href:catalogURL,replace:url=>redirects.push(url)}}, URL, Date, Intl
    });
    return {root,node,events,windowEvents,reads,redirects,controls,formEvents,status,save,writes,saved:()=>stored};
}
test('only allowlisted browser-local values affect the Admin display',()=>{
    const p=page(JSON.stringify({density:'compact',reduceMotion:true,reviewAlerts:false,
        successNotices:false,timeFormat:'24',dateFormat:'iso',role:'admin',access_token:'ignored'}));
    assert.equal(p.root.dataset.adminDensity,'compact');
    assert.equal(p.root.dataset.adminReduceMotion,'true');
    assert.equal(p.root.dataset.adminReviewAlerts,'hide');
    assert.equal(p.root.dataset.adminSuccessNotices,'hide');
    assert.equal(p.node.textContent,'2026-11-03 12:05:06');
    assert.deepEqual(p.reads,[key]);assert.equal(p.root.dataset.theme,undefined);
    assert.equal(p.root.dataset.role,undefined);
});
test('invalid, oversized and blocked storage fail back to display defaults',()=>{
    for(const raw of ['bad','null','[]','"password"','x'.repeat(3000),JSON.stringify({density:'tiny',reduceMotion:'true',reviewAlerts:0})]) {
        const p=page(raw);assert.equal(p.root.dataset.adminDensity,'comfortable');
        assert.equal(p.root.dataset.adminReduceMotion,'false');assert.equal(p.root.dataset.adminReviewAlerts,'show');
    }
    assert.equal(page('{}',{blocked:true}).root.dataset.adminDensity,'comfortable');
});
test('clock/date formatting is Asia/Manila and never mutates original datetime',()=>{
    const p=page(JSON.stringify({timeFormat:'24',dateFormat:'iso'}),{timestamp:'2026-11-02T20:05:06-08:00'});
    assert.equal(p.node.textContent,'2026-11-03 12:05:06');
    assert.equal(p.node.attrs.datetime,'2026-11-02T20:05:06-08:00');
    const night=page(JSON.stringify({timeFormat:'24',dateFormat:'iso'}),{timestamp:'2026-11-03T16:05:06Z'});
    assert.equal(night.node.textContent,'2026-11-04 00:05:06');
    assert.match(page('{}').node.textContent,/03 Nov 2026 12:05:06 PM/);
    assert.match(page('{"dateFormat":"mdy"}').node.textContent,/Nov 03, 2026/);
    assert.equal(page('{}',{timestamp:'2026-11-03'}).node.textContent,'original');
});
test('other tabs and cleared storage update presentation without changing theme',()=>{
    const p=page('{}');p.windowEvents.storage({key,newValue:'{"density":"compact"}'});
    assert.equal(p.root.dataset.adminDensity,'compact');
    p.windowEvents.storage({key:'rosago.theme.v1',newValue:'dark'});
    assert.equal(p.root.dataset.adminDensity,'compact');
    p.windowEvents.storage({key:null});assert.equal(p.root.dataset.adminDensity,'comfortable');
});
test('saved catalog defaults drive full catalog URLs and preserve explicit selections',()=>{
    const prefs=JSON.stringify({sort:'newest',pageSize:'10',status:'draft'});
    const p=page(prefs,{catalogURL:'http://localhost/admin/places'});p.events.DOMContentLoaded();
    assert.equal(p.redirects[0],'/admin/places?sort=newest&page_size=10&status=draft');
    const explicit=page(prefs,{catalogURL:'http://localhost/admin/places?status=published&sort=name&page_size=50&offset=50'});
    explicit.events.DOMContentLoaded();assert.deepEqual(explicit.redirects,[]);
    const all=page(prefs,{catalogURL:'http://localhost/admin/places?status='});all.events.DOMContentLoaded();
    assert.equal(all.redirects[0],'/admin/places?status=&sort=newest&page_size=10');
    const again=page(prefs,{catalogURL:'http://localhost/admin/places?sort=newest&page_size=10&status=draft'});
    again.events.DOMContentLoaded();assert.deepEqual(again.redirects,[]);
});

test('saving every setting changes real display state and restores the controls after reload',()=>{
    const p=page('{}',{withForm:true});p.events.DOMContentLoaded();
    assert.equal(p.save.disabled,false);assert.equal(p.controls.reviewAlerts.checked,true);
    p.controls.density.value='compact';p.controls.reduceMotion.checked=true;
    p.controls.reviewAlerts.checked=false;p.controls.successNotices.checked=false;
    p.controls.sort.value='oldest';p.controls.pageSize.value='10';p.controls.status.value='draft';
    p.controls.timeFormat.value='24';p.controls.dateFormat.value='iso';
    p.formEvents.change();assert.equal(p.status.dataset.state,'pending');
    assert.equal(p.root.dataset.adminDensity,'comfortable');
    let prevented=false;p.formEvents.submit({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);assert.equal(p.status.dataset.state,'success');
    assert.equal(p.root.dataset.adminDensity,'compact');assert.equal(p.root.dataset.adminReduceMotion,'true');
    assert.equal(p.root.dataset.adminReviewAlerts,'hide');assert.equal(p.root.dataset.adminSuccessNotices,'hide');
    assert.equal(p.node.textContent,'2026-11-03 12:05:06');
    assert.equal(p.writes.length,1);assert.equal(p.writes[0][0],key);
    const restored=page(p.saved(),{withForm:true});restored.events.DOMContentLoaded();
    for(const name of Object.keys(p.controls))assert.deepEqual(restored.controls[name],p.controls[name]);
    const destination=page(p.saved(),{catalogURL:'http://localhost/admin/places'});
    destination.events.DOMContentLoaded();assert.equal(destination.redirects[0],'/admin/places?sort=oldest&page_size=10&status=draft');
});
test('invalid controls and failed or discarded writes cannot display saved success',()=>{
    for(const options of [{writeFailure:true},{dropWrites:true}]){
        const p=page('{}',{withForm:true,...options});p.events.DOMContentLoaded();
        p.controls.density.value='compact';p.formEvents.submit({preventDefault(){}});
        assert.equal(p.status.dataset.state,'error');assert.equal(p.root.dataset.adminDensity,'comfortable');
    }
    const p=page('{}',{withForm:true});p.events.DOMContentLoaded();p.controls.pageSize.value='1000';
    p.formEvents.submit({preventDefault(){}});assert.equal(p.status.dataset.state,'error');assert.equal(p.writes.length,0);
});
test('pagination-only links retain their current implicit sort and page size',()=>{
    const p=page('{"sort":"newest","pageSize":"10"}',{catalogURL:'http://localhost/admin/places?offset=25&q=park'});
    p.events.DOMContentLoaded();assert.deepEqual(p.redirects,[]);
});
test('cross-tab changes update form controls and dates without replacing theme',()=>{
    const p=page('{}',{withForm:true});p.events.DOMContentLoaded();
    p.windowEvents.storage({key,newValue:'{"timeFormat":"24","dateFormat":"iso","density":"compact"}'});
    assert.equal(p.controls.density.value,'compact');assert.equal(p.node.textContent,'2026-11-03 12:05:06');
    assert.equal(p.status.dataset.state,'info');assert.equal(p.root.dataset.theme,undefined);
});
