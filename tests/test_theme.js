const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/theme.js', 'utf8');
function page(saved, blocked = false) {
    const events = {}, windowEvents = {}, reads = [], writes = [];
    const root = {dataset:{}}, status = {textContent:''};
    const buttons = ['light','dark'].map(value=>({dataset:{setTheme:value},attrs:{},setAttribute(k,v){this.attrs[k]=v;}}));
    const storage = new Map(saved === undefined ? [] : [['rosago.theme.v1',saved]]);
    vm.runInNewContext(source, {
        document:{documentElement:root,querySelectorAll:()=>buttons,querySelector:()=>status,addEventListener:(n,f)=>events[n]=f},
        localStorage:{getItem:k=>{reads.push(k);if(blocked)throw Error();return storage.get(k);},setItem:(k,v)=>{if(blocked)throw Error();writes.push([k,v]);storage.set(k,v);}},
        window:{addEventListener:(n,f)=>windowEvents[n]=f}
    });
    return {root,status,buttons,storage,reads,writes,events,windowEvents,click:value=>events.click({target:{closest:()=>({dataset:{setTheme:value}})}})};
}
test('saved Dark is applied synchronously before DOM ready or page styles',()=>{
    const p=page('dark');assert.equal(p.root.dataset.theme,'dark');assert.deepEqual(p.writes,[]);
    p.events.DOMContentLoaded();assert.equal(p.buttons[1].attrs['aria-pressed'],'true');
});
test('Light and Dark selections apply immediately and persist for navigation/reload',()=>{
    const p=page();p.click('dark');assert.equal(p.root.dataset.theme,'dark');assert.equal(p.buttons[0].attrs['aria-pressed'],'false');
    assert.equal(page(p.storage.get('rosago.theme.v1')).root.dataset.theme,'dark');
    p.click('light');assert.equal(page(p.storage.get('rosago.theme.v1')).root.dataset.theme,'light');
});
test('only a validated scalar presentation value is stored, with no account/session data',()=>{
    const p=page();p.click('dark');p.click('light');p.click('system');p.click('password');
    assert.deepEqual(p.reads,['rosago.theme.v1']);assert.deepEqual(p.writes,[['rosago.theme.v1','dark'],['rosago.theme.v1','light']]);
});
test('invalid stored data falls back safely without evaluating it',()=>{
    for(const value of ['system','{"access_token":"secret"}','<script>','DARK',''])assert.equal(page(value).root.dataset.theme,'light');
});
test('blocked storage still allows theme changes and gives honest persistence feedback',()=>{
    const p=page('dark',true);assert.equal(p.root.dataset.theme,'light');p.click('dark');
    assert.equal(p.root.dataset.theme,'dark');assert.match(p.status.textContent,/could not remember/);
});
test('other tabs synchronize valid changes, removals and cleared storage without writing',()=>{
    const p=page('light');p.windowEvents.storage({key:'rosago.theme.v1',newValue:'dark'});assert.equal(p.root.dataset.theme,'dark');
    p.windowEvents.storage({key:'unrelated',newValue:'light'});assert.equal(p.root.dataset.theme,'dark');
    p.windowEvents.storage({key:'rosago.theme.v1',newValue:null});assert.equal(p.root.dataset.theme,'light');
    p.click('dark');p.windowEvents.storage({key:null});assert.equal(p.root.dataset.theme,'light');
    assert.equal(p.writes.length,1);
});
