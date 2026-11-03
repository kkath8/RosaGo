const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function page(scope, storage = new Map()) {
    const listeners = {}, session = new Map();
    const context = vm.createContext({structuredClone, console,
        document:{body:{dataset:{uiScope:scope}}},
        localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
        sessionStorage:{getItem:k=>session.get(k),setItem:(k,v)=>session.set(k,v),removeItem:k=>session.delete(k)},
        CustomEvent:class {constructor(type){this.type=type;}},
        window:{addEventListener:(n,f)=>listeners[n]=f,dispatchEvent:e=>listeners[e.type]?.(e)}});
    vm.runInContext(fs.readFileSync('static/js/personal-state.js','utf8')+';globalThis.P=RosaGoPersonal;',context);
    return {p:context.P,storage,listeners};
}
const id='00000000-0000-0000-0000-000000000001';
const a=page('aaaaaaaaaaaaaaaaaaaaaaaa'), b=page('bbbbbbbbbbbbbbbbbbbbbbbb',a.storage);
a.p.toggle('saved',id);assert.equal(a.p.get().saved[0],id);assert.equal(b.p.get().saved.length,0);
// Reload uses the same existing namespace; favorites never populate Trip Bag.
assert.equal(page('aaaaaaaaaaaaaaaaaaaaaaaa',a.storage).p.get().saved[0],id);
assert.equal(a.p.get().bag.length,0);
a.p.toggle('saved',id);assert.equal(a.p.get().saved.length,0);
a.p.toggle('saved',id);assert.equal(a.p.get().saved[0],id);
assert.equal(a.p.get().bag.length,0);
const backup=a.p.exportData();a.p.reset();a.p.restore(backup);assert.equal(a.p.get().saved[0],id);
const legacy=JSON.parse(backup);delete legacy.prefs.transportation;
delete legacy.prefs.budgetPreference;
a.p.restore(JSON.stringify(legacy));assert.equal(a.p.get().prefs.transportation,'private_car');
assert.equal(a.p.get().prefs.budgetPreference,'');
const unsupported=JSON.parse(backup);unsupported.prefs.transportation='flying';
assert.throws(()=>a.p.restore(JSON.stringify(unsupported)));
unsupported.prefs.transportation='walking';unsupported.prefs.budgetPreference='guaranteed-cheap';
assert.throws(()=>a.p.restore(JSON.stringify(unsupported)));
a.p.change(s=>{s.prefs.budgetPreference='mid';});
assert.equal(page('aaaaaaaaaaaaaaaaaaaaaaaa',a.storage).p.get().prefs.budgetPreference,'mid');
for(const field of ['password','access_token','refresh_token','otp','session','api_key','__proto__']) {
    const malicious=JSON.parse(backup);Object.defineProperty(malicious,field,{value:'secret',enumerable:true});
    assert.throws(()=>a.p.restore(JSON.stringify(malicious)));assert.equal(a.p.get().saved[0],id);
}
for(const edit of [s=>s.saved.push('1'),s=>s.profile.color='url(javascript:bad)',s=>s.prefs.size='200px',s=>s.budget.people=1.5,s=>s.budget.transport=.5,s=>s.options.indoor='yes']) {
    const data=JSON.parse(backup);edit(data);
    assert.throws(()=>a.p.restore(JSON.stringify(data)));
}
assert.throws(()=>a.p.restore('x'.repeat(256001)));
assert.deepEqual(JSON.parse(JSON.stringify(a.p.budgetTotal({people:3,entries:[{amount:12550},{amount:5000}],transport:2000,cap:25000}))),{per:19550,total:58650,balance:5450});
const copy=a.p.get();copy.saved=[];assert.equal(a.p.get().saved.length,1);
a.listeners.storage({key:'rosago.personal.v1.aaaaaaaaaaaaaaaaaaaaaaaa',newValue:null});assert.equal(a.p.get().saved.length,0);
// A cached page must observe notice changes made after it was left behind.
const cached=page('aaaaaaaaaaaaaaaaaaaaaaaa',a.storage);
a.p.change(s=>{s.read=['notice-one'];s.dismissed=['notice-two'];});
assert.equal(cached.p.get().read.length,0);
cached.listeners.pageshow({persisted:true});
assert.equal(cached.p.get().read[0],'notice-one');
assert.equal(cached.p.get().dismissed[0],'notice-two');
console.log('Personal state: scope isolation, strict backups, budget arithmetic and storage synchronization passed.');
// New allocation plans do not erase old calculator amounts or other device state.
const legacyBudget=structuredClone(a.p.get().budget);
a.p.change(s=>{s.budgetPlan={version:1,trip:'',people:2,total:500000,allocations:[150000,125000,100000,75000,50000],entries:[{label:'Lunch',category:'food',amount:60000}]};});
const reload=page('aaaaaaaaaaaaaaaaaaaaaaaa',a.storage);
assert.equal(reload.p.get().budgetPlan.total,500000);
assert.equal(reload.p.get().budgetPlan.entries[0].amount,60000);
assert.deepEqual(JSON.parse(JSON.stringify(reload.p.get().budget)),JSON.parse(JSON.stringify(legacyBudget)));
const oldBackup=JSON.parse(backup);delete oldBackup.budgetPlan;
a.p.restore(JSON.stringify(oldBackup));assert.equal(a.p.get().budgetPlan,null);
for(const mutation of [b=>b.total=-1,b=>b.people=0,b=>b.allocations[0]=.5,b=>b.entries[0].category='invented',b=>b.trip='bad']) {
    const invalid=reload.p.get();mutation(invalid.budgetPlan);assert.throws(()=>reload.p.restore(JSON.stringify(invalid)));
}
