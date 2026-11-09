const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/admin.js','utf8');
function page(admin) {
    const events={},body={style:{},classList:{contains:value=>typeof admin==='string' ? value===admin : admin && value==='admin-shell'}};
    let reloads=0,replacements=[];
    vm.runInNewContext(source,{
        document:{body,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}},
        window:{addEventListener:(name,fn)=>events[name]=fn,location:{reload(){reloads++;},replace(path){replacements.push(path);}}}
    });
    return {events,body,reloads:()=>reloads,replacements};
}
test('cached Admin history is hidden and revalidated through the existing protected route',()=>{
    const p=page(true);p.events.pagehide({persisted:true});assert.equal(p.body.style.visibility,'hidden');
    p.events.pageshow({persisted:true});assert.equal(p.reloads(),1);
});
test('cached Admin login pages reload rather than resubmit a consumed challenge',()=>{
    const login=page('admin-login-page');login.events.pagehide({persisted:true});
    login.events.pageshow({persisted:true});assert.equal(login.reloads(),0);
    assert.deepEqual(login.replacements,['/admin/login']);
});
test('Admin login sends one native submission and blocks duplicate clicks',()=>{
    const handlers={},button={disabled:false},attrs={};
    const form={addEventListener:(name,fn)=>handlers[name]=fn,
        querySelector:()=>button,setAttribute:(key,value)=>attrs[key]=value};
    vm.runInNewContext(source,{
        document:{body:{classList:{contains:()=>false}},querySelector:selector=>selector==='.admin-login-form'?form:null,
            querySelectorAll:()=>[],addEventListener(){}},
        window:{addEventListener(){},location:{reload(){throw Error('No navigation from submit handler');}}}
    });
    let prevented=0;const event=()=>({defaultPrevented:false,preventDefault(){prevented++;}});
    handlers.submit(event());assert.equal(prevented,0);assert.equal(button.disabled,true);
    assert.equal(attrs['aria-busy'],'true');handlers.submit(event());assert.equal(prevented,1);
});
test('ordinary navigation and non-workspace pages do not trigger reload loops',()=>{
    const p=page(true);p.events.pagehide({persisted:false});p.events.pageshow({persisted:false});
    assert.equal(p.reloads(),0);assert.equal(p.body.style.visibility,undefined);
    const login=page(false);login.events.pagehide({persisted:true});login.events.pageshow({persisted:true});
    assert.equal(login.reloads(),0);assert.equal(login.body.style.visibility,undefined);
});
