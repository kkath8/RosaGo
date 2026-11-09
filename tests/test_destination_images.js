// Offline DOM contracts; no browser, requests, downloaded-image reads or SDKs.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const fallbackSource = fs.readFileSync('static/js/destination-images.js','utf8');
const adminSource = fs.readFileSync('static/js/admin.js','utf8');

function element(attrs={}) {
    const classes=new Set(),listeners={};let value='',files=[];
    return {attrs,dataset:{},listeners,tagName:'IMG',hidden:false,checked:false,textContent:'',disabled:false,
        classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),contains:k=>classes.has(k),
            toggle(k,on){if(on)classes.add(k);else classes.delete(k);}},
        getAttribute:k=>attrs[k]??null,hasAttribute:k=>Object.hasOwn(attrs,k),
        setAttribute:(k,v)=>attrs[k]=String(v),removeAttribute:k=>delete attrs[k],
        addEventListener:(k,f)=>listeners[k]=f,dispatchEvent:e=>listeners[e.type]?.(e),
        set src(v){attrs.src=v;this.writes=(this.writes||0)+1;},get src(){return attrs.src;},
        set value(v){value=v;if(!v)files=[];},get value(){return value;},set files(v){files=v;},get files(){return files;},
        setCustomValidity(v){this.validityMessage=v;}};
}
function fallbackPage(images=[], source='/static/img/destination-placeholder.svg') {
    const events={},window={location:{href:'https://rosago.invalid/admin/places/new',origin:'https://rosago.invalid'}};
    const document={currentScript:{dataset:{destinationPlaceholder:source}},
        addEventListener:(name,callback,capture)=>events[name]={callback,capture},querySelectorAll:()=>images};
    vm.runInNewContext(fallbackSource,{window,document,URL});
    return {window,error:image=>events.error?.callback({target:image}),events};
}
test('failed recorded photo falls back once to the same-origin placeholder',()=>{
    const p=fallbackPage(),image=element({'data-destination-image':'',src:'https://photos.invalid/cover.jpg'});
    image.dataset.placeholderAlt='Photo unavailable for Synthetic venue';p.error(image);
    assert.equal(image.src,'https://rosago.invalid/static/img/destination-placeholder.svg');
    assert.equal(image.alt,'Photo unavailable for Synthetic venue');
    assert.equal(image.classList.contains('destination-photo-placeholder'),true);
    p.error(image);assert.equal(image.writes,1);assert.equal(p.events.error.capture,true);
});
test('cached failures and dynamically created cards use the same fallback',()=>{
    const cached=element({'data-destination-image':'',src:'/missing.jpg'});cached.complete=true;cached.naturalWidth=0;
    const p=fallbackPage([cached]);assert.equal(cached.writes,1);
    const added=element({'data-destination-image':'',src:'/later.jpg'});p.error(added);assert.equal(added.writes,1);
});
test('unrelated avatars and empty preview sources are left alone',()=>{
    const p=fallbackPage(),avatar=element({src:'/avatar.png'}),empty=element({'data-destination-image':''});
    p.error(avatar);p.error(empty);assert.equal(avatar.writes,undefined);assert.equal(empty.writes,undefined);
});
test('prefixed installations work and foreign or credential-bearing fallback config is rejected',()=>{
    const p=fallbackPage([], '/rosago/static/img/destination-placeholder.svg');
    assert.equal(p.window.RosaGoImages.placeholder,'https://rosago.invalid/rosago/static/img/destination-placeholder.svg');
    for(const url of ['https://foreign.invalid/static/img/destination-placeholder.svg',
        '/static/img/destination-placeholder.svg?token=private','https://user:private@rosago.invalid/static/img/destination-placeholder.svg']){
        assert.equal(fallbackPage([],url).window.RosaGoImages,undefined);
    }
});

function adminPage(saved=null) {
    const input=element(),preview=element(),remove=saved?element():null,reset=element(),status=element(),submit=element();
    preview.dataset={placeholderSrc:'/static/img/destination-placeholder.svg',...(saved?{savedSrc:saved}:{})};
    preview.src=saved||preview.dataset.placeholderSrc;submit.textContent='Save Changes';
    const nodes={'[data-photo-input]':input,'[data-photo-preview]':preview,'[data-photo-remove]':remove,
        '[data-photo-reset]':reset,'[data-photo-status]':status,'button[type="submit"]':submit};
    const form=element();form.querySelector=s=>nodes[s];form.checkValidity=()=>true;
    const events={},created=[],revoked=[];
    const document={querySelector:s=>s==='[data-destination-form]'?form:null,querySelectorAll:()=>[],addEventListener:()=>{}};
    const window={addEventListener:(k,f)=>events[k]=f};
    const URL={createObjectURL:f=>{created.push(f);return 'blob:synthetic-'+created.length;},revokeObjectURL:u=>revoked.push(u)};
    vm.runInNewContext(adminSource,{document,window,URL,Event:class{constructor(type){this.type=type;}}});
    return {input,preview,remove,reset,status,submit,form,events,created,revoked,
        choose(file){input.value='selected';input.files=file?[file]:[];input.listeners.change();}};
}
const photo={type:'image/jpeg',size:1024};
test('Admin create selects a local preview and cancellation returns to the placeholder',()=>{
    const p=adminPage();p.choose(photo);assert.equal(p.preview.src,'blob:synthetic-1');
    assert.equal(p.preview.hidden,false);assert.equal(p.reset.hidden,false);
    p.reset.listeners.click();assert.equal(p.preview.src,'/static/img/destination-placeholder.svg');
    assert.equal(p.preview.hidden,false);assert.equal(p.input.files.length,0);
    assert.deepEqual(p.revoked,['blob:synthetic-1']);
});
test('Admin edit cancellation preserves the hosted source; removal is explicit and reversible',()=>{
    const saved='https://storage.invalid/original.jpg',p=adminPage(saved);
    p.choose(photo);p.reset.listeners.click();assert.equal(p.preview.src,saved);
    assert.equal(p.preview.dataset.savedSrc,saved);
    p.remove.checked=true;p.remove.listeners.change();assert.equal(p.preview.src,p.preview.dataset.placeholderSrc);
    p.remove.checked=false;p.remove.listeners.change();assert.equal(p.preview.src,saved);
    p.remove.checked=true;p.choose(photo);assert.equal(p.remove.checked,false);
});
test('invalid MIME, empty and oversized inputs never create a preview object URL',()=>{
    const saved='https://storage.invalid/original.jpg';
    for(const file of [{type:'image/svg+xml',size:100},{type:'image/png',size:0},{type:'image/jpeg',size:5*1024*1024+1}]){
        const p=adminPage(saved);p.choose(file);assert.equal(p.created.length,0);assert.equal(p.preview.src,saved);
        assert.equal(p.input.files.length,0);assert.match(p.status.textContent,/5 MB/);
    }
});
test('page lifecycle releases blobs; submitting retains successful multipart controls',()=>{
    const p=adminPage();p.choose(photo);p.events.pagehide();assert.equal(p.revoked.length,1);
    p.events.pageshow({persisted:true});assert.equal(p.created.length,2);
    p.form.listeners.submit();assert.equal(p.submit.disabled,true);assert.equal(p.input.disabled,false);
    p.events.pageshow({persisted:true});assert.equal(p.submit.disabled,false);assert.equal(p.submit.textContent,'Save Changes');
});
