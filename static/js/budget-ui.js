/* A browser-local budget plan. The saved-trip selector only reads metadata. */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const form=document.querySelector('#budget-plan-form');if(!form)return;
    const P=RosaGoPersonal,B=RosaGoBudget,$=s=>form.querySelector(s);
    const money=c=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'}).format(c/100);
    const el=(tag,text='',cls='')=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;};
    let plan=P.get().budgetPlan||B.fromLegacy(P.get().budget),saving=false;
    const fingerprint=()=>{const state=P.get();return JSON.stringify([state.budgetPlan,state.budget]);};
    let storedFingerprint=fingerprint();
    const trips=new Map();
    const tripDate=value=>value?new Intl.DateTimeFormat('en-PH',{month:'short',day:'numeric',year:'numeric',timeZone:'Asia/Manila'}).format(new Date(value+'T00:00:00+08:00')):'Date not set';
    function numeric(id,value,max=1000000000,step='.01') {
        const input=document.createElement('input');Object.assign(input,{id,type:'number',min:'0',max:String(max),step,value:String(value)});input.required=true;return input;
    }
    function field(label,input) {const host=el('div','','field'),caption=el('label',label);caption.htmlFor=input.id;host.append(caption,input);return host;}
    function renderAllocations() {
        const host=$('[data-plan-allocations]');host.replaceChildren();
        B.categories.forEach(([key,label],i)=>{
            const row=el('div','','allocation-row');row.append(el('h3',label));
            const percent=numeric('allocate-percent-'+key,plan.total?(plan.allocations[i]/plan.total*100).toFixed(2):B.categories[i][2],100);
            const amount=numeric('allocate-amount-'+key,(plan.allocations[i]/100).toFixed(2));
            percent.dataset.allocationPercent=i;amount.dataset.allocationAmount=i;
            row.append(field('Percent (%)',percent),field('Amount (PHP)',amount));host.append(row);
        });
    }
    function renderEntries() {
        const host=$('[data-plan-entries]');host.replaceChildren();
        plan.entries.forEach((entry,i)=>{
            const row=el('div','','planned-expense'),name=document.createElement('input');
            Object.assign(name,{id:'expense-name-'+i,value:entry.label,maxLength:100,required:true});name.dataset.entryLabel=i;
            const category=document.createElement('select');category.id='expense-category-'+i;category.dataset.entryCategory=i;
            for(const [key,label] of B.categories){const option=el('option',label);option.value=key;category.append(option);}category.value=entry.category;
            const amount=numeric('expense-amount-'+i,(entry.amount/100).toFixed(2));amount.dataset.entryAmount=i;
            const remove=el('button','Remove','mini-button');remove.type='button';remove.dataset.entryRemove=i;
            row.append(field('Expense name',name),field('Category',category),field('Estimated amount (PHP)',amount),remove);host.append(row);
        });
    }
    function update(dirty=false) {
        const sum=B.summary(plan);$('[data-plan-per-person]').textContent=money(sum.perPerson);
        $('[data-allocation-total]').textContent='Allocated: '+money(sum.allocated)+' / '+money(plan.total)+' ('+(plan.total?(sum.allocated/plan.total*100).toFixed(2):'0')+'%)';
        $('[data-allocation-error]').textContent=sum.allocationGap>0?'Allocate '+money(sum.allocationGap)+' more to reach 100%.':sum.allocationGap<0?'Reduce allocations by '+money(-sum.allocationGap)+' to reach 100%.':'';
        const host=$('[data-plan-summary]');host.replaceChildren();
        const dl=el('dl','','budget-totals');
        for(const [label,value] of [['Total Budget',plan.total],['Planned Expenses',sum.planned],['Remaining Budget',sum.remaining]])dl.append(el('dt',label),el('dd',money(value)));
        host.append(dl,el('p',money(sum.perPerson)+' budget per person'));
        const status=el('p',sum.status,'budget-status');status.dataset.state=sum.status==='Over budget'?'over':sum.status==='Near budget'?'near':'within';host.append(status);
        if(sum.remaining<0)host.append(el('p','Over budget by '+money(-sum.remaining),'budget-overage'));
        const categories=$('[data-plan-category-summary]');categories.replaceChildren();
        for(const category of sum.categories){const row=el('section','','category-budget'+(category.remaining<0?' is-over':''));row.dataset.categoryBudget=category.key;row.append(el('h3',category.label),el('p','Allocated: '+money(category.allocated)),el('p','Planned: '+money(category.planned)),el('p','Remaining: '+money(category.remaining)));if(category.remaining<0)row.append(el('strong','Over allocation by '+money(-category.remaining)));categories.append(row);}
        form.querySelector('[type=submit]').disabled=plan.total<=0||sum.allocationGap!==0||!form.checkValidity();
        if(dirty)$('[data-plan-status]').textContent='Changes are not saved yet. Save budget plan to keep them on this device.';
    }
    function render() {
        $('#plan-total').value=(plan.total/100).toFixed(2);$('#plan-people').value=plan.people;$('#plan-trip').value=plan.trip;
        renderAllocations();renderEntries();update();
    }
    function association() {
        const trip=trips.get(plan.trip);
        $('[data-plan-trip-status]').textContent=trip?trip.name+' - '+(trip.visit_date?new Intl.DateTimeFormat('en-PH',{dateStyle:'long',timeZone:'Asia/Manila'}).format(new Date(trip.visit_date+'T00:00:00+08:00')):'Date not set'):plan.trip?'The previously selected trip is unavailable. Your budget plan is still here.':'Personal budget plan. No saved itinerary will be changed.';
    }
    form.addEventListener('input',event=>{
        const input=event.target;try{
            if(input.id==='plan-total'){plan=B.resize(plan,B.amount(input.value));renderAllocations();}
            else if(input.id==='plan-people'){const n=Number(input.value);if(!Number.isInteger(n)||n<1||n>50)throw Error('Use 1 to 50 travelers.');plan.people=n;}
            else if(input.dataset.allocationPercent!==undefined){const i=Number(input.dataset.allocationPercent),percent=Number(input.value);if(input.value===''||!Number.isFinite(percent)||percent<0||percent>100)throw Error('Use a percentage from 0 to 100.');plan.allocations[i]=Math.round(plan.total*percent/100);$('#allocate-amount-'+B.categories[i][0]).value=(plan.allocations[i]/100).toFixed(2);}
            else if(input.dataset.allocationAmount!==undefined){const i=Number(input.dataset.allocationAmount);plan.allocations[i]=B.amount(input.value);$('#allocate-percent-'+B.categories[i][0]).value=plan.total?(plan.allocations[i]/plan.total*100).toFixed(2):'0';}
            else if(input.dataset.entryLabel!==undefined)plan.entries[Number(input.dataset.entryLabel)].label=input.value;
            else if(input.dataset.entryAmount!==undefined)plan.entries[Number(input.dataset.entryAmount)].amount=B.amount(input.value);
            $('[data-plan-error]').textContent='';update(true);
        }catch(error){$('[data-plan-error]').textContent=error.message;form.querySelector('[type=submit]').disabled=true;}
    });
    form.addEventListener('change',event=>{const input=event.target;if(input.dataset.entryCategory!==undefined)plan.entries[Number(input.dataset.entryCategory)].category=input.value;if(input.id==='plan-trip'){plan.trip=input.value;association();}update(true);});
    form.addEventListener('click',event=>{
        if(event.target.closest('[data-plan-add]')){if(plan.entries.length>=200){$('[data-plan-error]').textContent='Use at most 200 planned expenses.';return;}plan.entries.push({label:'',category:'food',amount:0});renderEntries();$('#expense-name-'+(plan.entries.length-1)).focus({preventScroll:true});update(true);}
        if(event.target.dataset.entryRemove!==undefined){plan.entries.splice(Number(event.target.dataset.entryRemove),1);renderEntries();update(true);}
        if(event.target.closest('[data-plan-defaults]')){plan.allocations=B.suggested(plan.total);renderAllocations();update(true);}
    });
    form.addEventListener('submit',event=>{
        event.preventDefault();if(!form.reportValidity()||!plan.total||B.summary(plan).allocationGap!==0)return;
        try{saving=true;const persisted=P.change(s=>{s.budgetPlan=structuredClone(plan);});$('[data-plan-status]').textContent=persisted?'Budget plan saved on this device.':'Your browser could not save this plan. Keep this page open to retain your changes.';}
        catch(error){$('[data-plan-error]').textContent=error.message;}finally{saving=false;}
    });
    addEventListener('rosago:personal',()=>{const next=fingerprint();if(next===storedFingerprint)return;storedFingerprint=next;if(!saving){plan=P.get().budgetPlan||B.fromLegacy(P.get().budget);render();association();}});
    render();
    if(P.get().budgetPlan===null&&(P.get().budget.cap||P.get().budget.entries.length||P.get().budget.transport))$('[data-plan-status]').textContent='Your previous estimate was carried into this plan. Uncategorized expenses are in Emergency / Extra. Save to keep this allocation.';
    if(!P.hasAccountScope()){$('[data-plan-trip-status]').textContent='Sign in to choose a saved trip. You can still make a personal budget plan.';return;}
    fetch('/api/user/trips',{credentials:'same-origin',headers:{Accept:'application/json'}}).then(async response=>{if(!response.ok)throw Error();return response.json();}).then(data=>{
        for(const trip of data.trips){trips.set(trip.id,trip);const option=el('option',trip.name+' - '+tripDate(trip.visit_date));option.value=trip.id;$('#plan-trip').append(option);}
        if(plan.trip&&!trips.has(plan.trip)){const option=el('option','Previously selected trip (unavailable)');option.value=plan.trip;$('#plan-trip').append(option);}
        $('#plan-trip').value=plan.trip;association();
    }).catch(()=>{$('[data-plan-trip-status]').textContent='Saved trips could not be loaded. Your budget plan remains separate and usable.';});
});
