/* Native checkbox form contract; only presentation/counts update on selection. */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const form=document.querySelector('[data-personalized-recommendations]');if(!form)return;
    const requested=Number(form.dataset.requestedCount||0),scope=document.body.dataset.uiScope||'guest';
    const draft=location.pathname.match(/^\/user\/itinerary\/([0-9a-f-]{36})\//)?.[1];
    if(draft&&new URL(location.href).searchParams.has('stops')){try{const key='rosago.planning.options.'+scope+'.'+draft;const options=JSON.parse(sessionStorage.getItem(key))||(document.body.dataset.personalized==='false'?{skipVisited:false,savedFirst:false,indoor:false,stops:0}:RosaGoPersonal.get().options);options.stops=requested;sessionStorage.setItem(key,JSON.stringify(options));}catch(_){}}
    const stops=document.querySelector('[data-smart-options] [name=stops]');
    if(stops){if(![...stops.options].some(n=>n.value===String(requested))){const option=document.createElement('option');option.value=String(requested);option.textContent=requested+' stops';stops.append(option);}stops.value=String(requested);}
    const inputs=[...form.querySelectorAll('[name=selected_place_ids]')];
    function reflect() {
        const count=inputs.filter(input=>input.checked).length;
        for(const input of inputs)input.closest('label').querySelector('[data-selection-label]').textContent=input.checked?'Selected':'+ Add';
        for(const node of form.querySelectorAll('[data-selection-count]'))node.textContent=count+' destination'+(count===1?'':'s')+' selected';
        for(const button of form.querySelectorAll('[type=submit]'))button.disabled=count<1||count>100;
        const status=form.querySelector('[data-selection-status]');
        status.textContent=count<1?'Choose at least one destination to create your itinerary.':count>100?'Choose no more than 100 destinations.':'';
    }
    form.addEventListener('change',reflect);
    form.addEventListener('submit',event=>{const count=inputs.filter(input=>input.checked).length;if(count<1||count>100){event.preventDefault();reflect();}});
    reflect();
});
