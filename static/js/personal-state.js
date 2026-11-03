/* Personal device state only. Never stores credentials, identity or real trips. */
const RosaGoPersonal = (() => {
    'use strict';
    const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
    const categories = ['accommodation','attraction','dining','shopping','nature','heritage','industrial'];
    const colors = ['', '#8e3b2c', '#c99a1c', '#3b6ea5', '#2f6b4f', '#6b3a6b'];
    const defaults = () => ({version:1,saved:[],visited:[],bag:[],notes:{},checklists:{},reminders:[],read:[],dismissed:[],
        prefs:{size:'medium',compact:false,interests:[],pace:'balanced',companions:'friends',transportation:'private_car',budgetPreference:'',weather:true,events:true,trips:true,home:'',contrast:false},
        profile:{bio:'',city:'',color:''},options:{skipVisited:false,savedFirst:false,indoor:false,stops:0},
        budget:{trip:'',people:1,cap:0,transport:0,entries:[]},budgetPlan:null,feedback:[]});
    const plain = value => value && typeof value === 'object' && !Array.isArray(value);
    function keys(value, allowed) {
        if (!plain(value) || Object.keys(value).some(k => !allowed.includes(k))) throw new Error('Invalid RosaGo backup fields.');
    }
    function text(value, max) {
        if (typeof value !== 'string' || value.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)) throw new Error('Invalid text in local data.');
        return value;
    }
    function list(value, max, validate) {
        if (!Array.isArray(value) || value.length > max || value.some(v => !validate(v))) throw new Error('Invalid local data list.');
        return [...new Set(value)];
    }
    const ids = value => list(value,500,v=>typeof v === 'string' && UUID.test(v));
    const number = (v,max,min=0) => {if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max)throw new Error('Invalid amount in local data.');return v;};
    function normalize(value) {
        const d=defaults(); keys(value,Object.keys(d));
        if(value.version!==1)throw new Error('Unsupported RosaGo backup version.');
        for(const key of ['saved','visited','bag']) d[key]=ids(value[key]);
        for(const key of ['read','dismissed']) d[key]=list(value[key],500,v=>typeof v==='string'&&v.length<=160);
        d.reminders=list(value.reminders,10,v=>Number.isInteger(v)&&v>=0&&v<5);
        keys(value.prefs,Object.keys(d.prefs)); keys(value.profile,Object.keys(d.profile));keys(value.options,Object.keys(d.options));keys(value.budget,Object.keys(d.budget));
        d.prefs.interests=list(value.prefs.interests,7,v=>categories.includes(v));
        for(const key of ['compact','weather','events','trips','contrast']) {if(typeof value.prefs[key]!=='boolean')throw new Error('Invalid preference.');d.prefs[key]=value.prefs[key];}
        if(!['small','medium','large'].includes(value.prefs.size)||!['relaxed','balanced','packed'].includes(value.prefs.pace)||!['solo','couple','family','friends','group'].includes(value.prefs.companions))throw new Error('Invalid default preference.');
        for(const key of ['size','pace','companions'])d.prefs[key]=value.prefs[key];d.prefs.home=text(value.prefs.home,80);
        const transportation=value.prefs.transportation??'private_car';
        if(!['private_car','walking','bicycle','public_transport','motorcycle','ride_hailing','mixed_transport'].includes(transportation))throw new Error('Invalid transportation preference.');
        d.prefs.transportation=transportation;
        const budgetPreference=value.prefs.budgetPreference??'';
        if(!['','low','mid','high'].includes(budgetPreference))throw new Error('Invalid budget preference.');
        d.prefs.budgetPreference=budgetPreference;
        d.profile={bio:text(value.profile.bio,160),city:text(value.profile.city,40),color:value.profile.color};
        if(!colors.includes(d.profile.color))throw new Error('Invalid avatar color.');
        for(const key of ['skipVisited','savedFirst','indoor']) {if(typeof value.options[key]!=='boolean')throw new Error('Invalid Smart Option.');d.options[key]=value.options[key];}
        if(![0,2,3,4,5,6,10,20].includes(value.options.stops))throw new Error('Invalid stop count.');d.options.stops=value.options.stops;
        if(!plain(value.notes)||Object.keys(value.notes).length>500)throw new Error('Invalid notes.');
        for(const [id,note] of Object.entries(value.notes)){if(!UUID.test(id))throw new Error('Invalid note destination.');d.notes[id]=text(note,500);}
        if(!plain(value.checklists)||Object.keys(value.checklists).length>100)throw new Error('Invalid checklists.');
        for(const [id,items] of Object.entries(value.checklists)){
            if(!UUID.test(id)||!Array.isArray(items)||items.length>100)throw new Error('Invalid trip checklist.');
            d.checklists[id]=items.map(item=>{keys(item,['text','done']);if(typeof item.done!=='boolean')throw new Error('Invalid checklist state.');return {text:text(item.text,60),done:item.done};});
        }
        if(!Number.isInteger(value.budget.people)||[value.budget.cap,value.budget.transport,...(value.budget.entries||[]).map(e=>e.amount)].some(v=>!Number.isInteger(v)))throw new Error('Use whole people and integer centavos.');
        d.budget={trip:text(value.budget.trip,36),people:number(value.budget.people,50,1),cap:number(value.budget.cap,10000000),transport:number(value.budget.transport,10000000),entries:[]};
        if(!Array.isArray(value.budget.entries)||value.budget.entries.length>100)throw new Error('Too many budget entries.');
        d.budget.entries=value.budget.entries.map(entry=>{keys(entry,['label','amount']);return {label:text(entry.label,100),amount:number(entry.amount,10000000)};});
        // Optional extension: old backups and the former calculator remain intact.
        if(value.budgetPlan!=null){
            const b=value.budgetPlan;keys(b,['version','trip','people','total','allocations','entries']);
            if(b.version!==1||!Number.isInteger(b.people)||!Number.isInteger(b.total)||!Array.isArray(b.allocations)||b.allocations.length!==5||!Array.isArray(b.entries)||b.entries.length>200)throw new Error('Invalid budget plan.');
            const cents=v=>{if(!Number.isInteger(v))throw new Error('Use integer centavos.');return number(v,100000000000);};
            const trip=text(b.trip,36);if(trip&&!UUID.test(trip))throw new Error('Invalid budget trip.');
            d.budgetPlan={version:1,trip,people:number(b.people,50,1),total:cents(b.total),allocations:b.allocations.map(cents),entries:b.entries.map(e=>{keys(e,['label','category','amount']);if(!['food','transport','activities','shopping','extra'].includes(e.category))throw new Error('Invalid budget category.');return {label:text(e.label,100),category:e.category,amount:cents(e.amount)};})};
        }
        if(!Array.isArray(value.feedback)||value.feedback.length>30)throw new Error('Invalid feedback.');
        d.feedback=value.feedback.map(item=>{keys(item,['topic','message']);return {topic:text(item.topic,60),message:text(item.message,500)};});
        return d;
    }
    let scope='guest';
    try {
        const candidate=document.body.dataset.uiScope;
        if(candidate==='guest'||/^[a-f0-9]{24}$/.test(candidate||'')){scope=candidate;sessionStorage.setItem('rosago.ui.scope',scope);}
        else {const previous=sessionStorage.getItem('rosago.ui.scope');if(/^[a-f0-9]{24}$/.test(previous||''))scope=previous;}
    }catch(_){/* Device storage may be blocked. No server authority is affected. */}
    const storageKey='rosago.personal.v1.'+scope;
    let state=defaults(),persistent=true;
    try {const raw=localStorage.getItem(storageKey);if(raw)state=normalize(JSON.parse(raw));}catch(_){persistent=false;}
    function persist(next) {
        state=normalize(next);
        try{localStorage.setItem(storageKey,JSON.stringify(state));persistent=true;}catch(_){persistent=false;}
        window.dispatchEvent(new CustomEvent('rosago:personal'));
        return persistent;
    }
    function change(callback){const next=structuredClone(state);callback(next);return persist(next);}
    function toggle(key,id){if(!['saved','visited','bag'].includes(key)||!UUID.test(id))throw new Error('Invalid destination.');return change(s=>{s[key]=s[key].includes(id)?s[key].filter(x=>x!==id):[...s[key],id];});}
    function exportData(){return JSON.stringify(normalize(state),null,2);}
    function restore(raw){if(typeof raw!=='string'||raw.length>256000)throw new Error('Backup must be at most 256 KB.');return persist(normalize(JSON.parse(raw)));}
    function reset(){return persist(defaults());}
    function budgetTotal(budget){const per=budget.entries.reduce((sum,e)=>sum+Math.round(e.amount),0)+Math.round(budget.transport);return {per,total:per*budget.people,balance:budget.cap-per};}
    window.addEventListener('storage',event=>{if(event.key!==storageKey)return;try{state=event.newValue?normalize(JSON.parse(event.newValue)):defaults();window.dispatchEvent(new CustomEvent('rosago:personal'));}catch(_){}});
    // Back/forward can restore an older page object after notices changed elsewhere.
    window.addEventListener('pageshow',event=>{if(!event.persisted)return;try{const raw=localStorage.getItem(storageKey);state=raw?normalize(JSON.parse(raw)):defaults();window.dispatchEvent(new CustomEvent('rosago:personal'));}catch(_){}});
    return Object.freeze({get:()=>structuredClone(state),change,toggle,exportData,restore,reset,budgetTotal,
        hasAccountScope:()=>scope!=='guest',persistent:()=>persistent,colors,categories,clearActive:()=>{try{sessionStorage.removeItem('rosago.ui.scope');}catch(_){}}});
})();
