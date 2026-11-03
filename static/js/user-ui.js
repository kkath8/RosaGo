/* Flask owns authentication, catalog eligibility and all real trip/draft writes. */
(() => {
    'use strict';
    const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
    const P=RosaGoPersonal, labels={accommodation:'Accommodation',attraction:'Attractions',dining:'Dining',shopping:'Shopping',nature:'Nature',heritage:'Heritage',industrial:'Industrial Tourism'};
    const make=(tag,text='',className='')=>{const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;};
    const action=(label,name,id)=>{const b=make('button',label,'mini-button');b.type='button';b.dataset.action=name;if(id)b.dataset.id=id;return b;};
    const link=(label,url,className='secondary-button')=>{const a=make('a',label,className);a.href=url;return a;};
    const money=cents=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'}).format(cents/100);
    let catalog=[],catalogReady=false,notices=[],noticesReady=!P.hasAccountScope(),eventFilter='All';
    const initialNotices=$('#notifications-data');
    if(initialNotices){try{notices=JSON.parse(initialNotices.textContent);noticesReady=true;}catch(_){/* Keep the server-rendered fallback. */}}
    const neutralOptions={skipVisited:false,savedFirst:false,indoor:false,stops:0};
    let tripOptions=null;
    const planningDraft=location.pathname.match(/^\/user\/itinerary\/([0-9a-f-]{36})\//)?.[1];
    const planningKey=planningDraft?'rosago.planning.options.'+(document.body.dataset.uiScope||'guest')+'.'+planningDraft:null;
    if(planningKey){try{const value=JSON.parse(sessionStorage.getItem(planningKey));if(value&&['skipVisited','savedFirst','indoor'].every(k=>typeof value[k]==='boolean')&&Number.isInteger(value.stops)&&value.stops>=0&&value.stops<=100)tripOptions=value;}catch(_){}}
    const planningOptions=()=>tripOptions||(document.body.dataset.personalized==='false'?neutralOptions:P.get().options);
    // Category and search results belong to the server. Device filters narrow
    // this exact result set rather than rebuilding it from the full catalog.
    const exploreHost=$('[data-explore-grid]');
    let savingExplorePlace=false;
    const exploreCards=exploreHost?[...exploreHost.querySelectorAll('[data-place-id]')].map(node=>({node:node.closest('li')||node,id:node.dataset.placeId,name:node.querySelector('h2').textContent,category:node.dataset.category})):[];
    const categoryRow=$('.category-nav ul'),activeCategory=$('.category-nav [aria-current]');
    if(categoryRow&&activeCategory&&categoryRow.scrollWidth>categoryRow.clientWidth){
        const row=categoryRow.getBoundingClientRect(),active=activeCategory.getBoundingClientRect();
        categoryRow.scrollLeft+=active.left-row.left-(row.width-active.width)/2;
    }
    const samples=[['Event','Community market day','Poblacion','Weekend mornings'],['Event','Lakeside walk','Nuvali','Early mornings and late afternoons'],['Closure','Lakeside District redevelopment','Nuvali','Ongoing, check access'],['Closure','Mall expansion works','SM City Santa Rosa and Ayala Malls Nuvali','Some areas may be closed'],['Road','Heavier traffic near malls','Santa Rosa','Weekend afternoons']];
    function toast(message){const box=$('#ui-toast');if(!box)return;box.textContent=message;box.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>{box.hidden=true;},3500);}
    function changed(persistent){if(!persistent)toast('Browser storage is unavailable. Changes last only on this page.');}
    async function requestJSON(url){const response=await fetch(url,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))throw new Error('Unavailable');return response.json();}
    function validIds(ids){const known=new Set(catalog.map(p=>p.id));return ids.filter(id=>known.has(id));}
    function localButton(label,name,id,pressed){const b=action(label,name,id);b.setAttribute('aria-pressed',String(pressed));return b;}
    function card(place){
        const state=P.get(),article=make('article','','local-place-card');article.dataset.placeId=place.id;
        const visual=make('div','','local-card-art'),img=document.createElement('img');img.className='local-place-visual';img.alt=place.image_url?place.name:'';
        img.src=place.image_url||('/static/img/categories/'+place.category+'.svg');visual.append(img,make('span',labels[place.category]||place.category,'local-card-category'));
        const body=make('div');body.append(make('h2',place.name));
        if(place.tourism_type||place.tourism_category)body.append(make('p',[place.tourism_type,place.tourism_category].filter(Boolean).join(' · ')));
        body.append(make('p',place.address),make('p',place.description,'destination-excerpt'));
        const buttons=make('div','','local-actions');buttons.append(link('View Details →',place.detail_url,'site-button site-button-secondary'),localButton(state.saved.includes(place.id)?'Saved':'Save','save',place.id,state.saved.includes(place.id)));
        if($('[data-library="visited"]'))buttons.append(action('Unmark visited','visit',place.id));
        body.append(buttons);article.append(visual,body);return article;
    }
    function drawCards(host,places){host.replaceChildren();if(!places.length){const empty=make('section','','card'),library=host.dataset.library;empty.append(make('h2',library==='saved'?'Nothing saved yet':library==='visited'?'No visits recorded yet':'Nothing matches'),make('p',library?'Use Save or Mark Visited on a published destination to keep it here.':'Try another word or clear your filters.'),link('Explore places','/places','site-button'));host.append(empty);return;}for(const place of places){if(host.tagName==='UL'){const li=make('li');li.append(card(place));host.append(li);}else host.append(card(place));}}
    function applyExplore(){const host=$('[data-explore-grid]');if(!host||!catalogReady)return;
        const setting=$('#explore-setting')?.value||'all',only=$('#explore-saved')?.checked,sort=$('#explore-sort')?.value||'name',state=P.get(),byId=new Map(catalog.map(p=>[p.id,p]));
        const cards=[...exploreCards].sort((a,b)=>(sort==='category'?a.category.localeCompare(b.category):0)||a.name.localeCompare(b.name));
        let count=0;
        for(const [index,card] of cards.entries()){const place=byId.get(card.id);card.node.hidden=!!((only&&!state.saved.includes(card.id))||(setting!=='all'&&place?.exposure!==setting));if(!card.node.hidden)count++;if(host.children[index]!==card.node)host.insertBefore(card.node,host.children[index]||null);}
        const counter=$('[data-result-count]');if(counter)counter.textContent=count+' destination'+(count===1?'':'s');
        let empty=host.querySelector('[data-device-filter-empty]');
        if(!count&&cards.length){if(!empty){empty=make('li','No destinations match these filters. Try another setting or turn off Saved only.','card');empty.dataset.deviceFilterEmpty='';host.append(empty);}empty.hidden=false;}else if(empty)empty.hidden=true;
    }
    function drawLibraries(){const state=P.get();for(const host of $$('[data-library]')){const kind=host.dataset.library,places=catalog.filter(p=>state[kind].includes(p.id));drawCards(host,places);const count=$('[data-library-count]');if(count)count.textContent=places.length+' currently published '+kind+' places';}}
    function drawBag(){const state=P.get(),places=catalog.filter(p=>state.bag.includes(p.id));for(const host of $$('[data-bag-list]')){host.replaceChildren();if(!places.length)host.append(make('p',catalogReady?'Your bag is empty. Add published places from Explore.':'Loading destinations…'));for(const place of places){const row=make('article','','bag-place-row'),info=make('div');info.append(make('h3',place.name),make('p',[labels[place.category],place.tourism_type].filter(Boolean).join(' \u00b7 '),'bag-place-meta'),make('p',place.address,'bag-place-address'));const controls=make('div','','bag-row-actions');controls.append(link('View',place.detail_url,'mini-button'),action('Remove','bag',place.id));row.append(info,controls);host.append(row);}}
        for(const save of $$('[data-bag-save]'))save.hidden=!places.length;
        const inputs=$('[data-bag-inputs]');if(inputs){inputs.replaceChildren();for(const place of places){const input=document.createElement('input');input.type='hidden';input.name='selected_place_ids';input.value=place.id;inputs.append(input);}const submit=$('[data-bag-submit]');submit.disabled=!places.length||places.length>20;if(places.length>20)toast('Choose at most 20 destinations before saving.');}}
    function activeNotices(){const state=P.get();return notices.filter(n=>!state.dismissed.includes(n.id));}
    function drawNotices(){const state=P.get(),rows=activeNotices(),unread=rows.filter(n=>!state.read.includes(n.id)).length;
        for(const node of $$('[data-count="unread"]')){node.textContent=noticesReady?String(unread):'…';if(node.closest('.header-bell'))node.hidden=!noticesReady||!unread;}
        const bell=$('.header-bell');if(bell)bell.setAttribute('aria-label',noticesReady?'Alerts, '+unread+' unread':'Alerts, count unavailable');
        const host=$('[data-notices]');if(!host)return;
        if(!noticesReady)return;
        host.replaceChildren();
        const readAll=$('[data-action="notices-read-all"]'),clearDismissed=$('[data-action="notices-clear-dismissed"]');
        if(readAll)readAll.disabled=!unread;
        if(clearDismissed)clearDismissed.disabled=!notices.some(n=>state.dismissed.includes(n.id));
        if(!rows.length)host.append(make('li','No notifications right now.','notification-empty'));
        for(const notice of rows){
            const isNew=!state.read.includes(notice.id),row=make('li','','notification-card'+(isNew?' is-unread':'')),body=make('div');row.dataset.noticeId=notice.id;
            body.append(make('span',notice.kind==='trip'?'Trip reminder':'Trip weather','notification-kind'));
            if(isNew)body.append(make('span','New','badge'));
            body.append(make('h3',notice.title));
            if(notice.name)body.append(make('strong',notice.name));
            if(notice.date_label){const date=make('time',notice.date_label);date.dateTime=notice.day;body.append(make('p'));body.lastChild.append(date);}
            body.append(make('p',notice.message));
            const buttons=make('div','','local-actions');
            // Only known, same-origin destinations get a navigation action.
            let destination;
            try{const url=new URL(notice.url,location.origin);if(notice.url&&url.origin===location.origin&&((/^\/user\/trips\/[0-9a-f-]{36}$/.test(url.pathname))||(notice.kind==='weather'&&url.pathname==='/user/alerts'&&url.hash==='#weather')))destination=url;}catch(_){}
            if(destination){const open=link(destination.pathname.startsWith('/user/trips/')?'View Trip':'View Weather',destination.href,'site-button');open.dataset.noticeRead=notice.id;buttons.append(open);}
            buttons.append(action('Dismiss','notice-dismiss',notice.id));row.append(body,buttons);host.append(row);
        }
    }
    function drawEvents(){const host=$('[data-events]');if(!host)return;host.replaceChildren();const state=P.get();samples.forEach((item,index)=>{if(eventFilter!=='All'&&item[0]!==eventFilter)return;const row=make('li'),body=make('div');body.append(make('span','Sample '+item[0],'badge'),make('strong',item[1]),make('p',item[2]+' · '+item[3]));const b=localButton(state.reminders.includes(index)?'Reminder set':'Remind me','event-reminder',String(index),state.reminders.includes(index));row.append(body,b,link('Browse related places','/places?q='+encodeURIComponent(item[2])));host.append(row);});}
    function applyDisplay(){const state=P.get();document.documentElement.style.fontSize='';document.body.classList.remove('ui-compact','ui-high-contrast');for(const node of $$('[data-avatar]')){node.style.backgroundColor=state.profile.color;node.style.color=state.profile.color==='#c99a1c'?'#2e1a14':state.profile.color?'#fff':'';}}
    function drawCounts(){const state=P.get();for(const key of ['saved','visited','bag'])for(const node of $$('[data-count="'+key+'"]'))node.textContent=String(catalogReady?validIds(state[key]).length:state[key].length);for(const node of $$('[data-category-count]'))if(catalogReady)node.textContent=catalog.filter(p=>p.category===node.dataset.categoryCount).length+' places';
        for(const node of $$('[data-action="save"],[data-action="visit"]')){const kind=node.dataset.action==='save'?'saved':'visited',yes=state[kind].includes(node.dataset.id);node.setAttribute('aria-pressed',String(yes));node.textContent=kind==='saved'?(yes?'Saved':'Save'):(yes?'✓ Visited':'Mark Visited');}
        const stats=$('[data-travel-stats]');if(stats&&catalogReady){stats.replaceChildren(make('p',validIds(state.visited).length+' of '+catalog.length+' published destinations visited · '+validIds(state.saved).length+' saved'));
            for(const [key,label] of Object.entries(labels)){const total=catalog.filter(p=>p.category===key).length,visited=catalog.filter(p=>p.category===key&&state.visited.includes(p.id)).length;const row=make('div','','section-header');row.append(make('span',label),make('strong',visited+'/'+total));stats.append(row);}}
    }
    function drawChecklist(){const host=$('[data-trip-checklist]');if(!host)return;const id=host.dataset.tripChecklist,items=P.get().checklists[id]||defaultChecklist();host.replaceChildren();items.forEach((item,index)=>{const row=make('li'),label=make('label','','checkbox-label'),input=document.createElement('input');input.type='checkbox';input.checked=item.done;input.dataset.checklistIndex=String(index);const text=make('span',item.text,item.done?'checklist-done':'');label.append(input,text);const remove=action('Remove','checklist-remove',String(index));row.append(label,remove);host.append(row);});}
    function defaultChecklist(){return ['Valid ID','Water bottle','Sunscreen or umbrella','Cash and e-wallet','Charged phone'].map(text=>({text,done:false}));}
    function editChecklist(callback){const host=$('[data-trip-checklist]');if(!host)return;changed(P.change(state=>{const id=host.dataset.tripChecklist;state.checklists[id]??=defaultChecklist();callback(state.checklists[id]);}));}
    function drawFeedback(){const host=$('[data-feedback-list]');if(!host)return;host.replaceChildren();P.get().feedback.forEach(item=>{const li=make('li');li.append(make('strong',item.topic),make('p',item.message));host.append(li);});}
    function refresh(){applyDisplay();drawCounts();drawBag();drawNotices();drawEvents();drawChecklist();drawFeedback();if(catalogReady){drawLibraries();if(!savingExplorePlace)applyExplore();}}
    function setupSettings(){const form=$('[data-device-settings]');if(form){const prefs=P.get().prefs;for(const key of ['size','pace','companions','home'])form.elements[key].value=prefs[key];for(const key of ['compact','contrast','weather','trips'])form.elements[key].checked=prefs[key];for(const input of form.querySelectorAll('[name="default_interests"]'))input.checked=prefs.interests.includes(input.value);}
        const profile=$('[data-device-profile]');if(profile){const values=P.get().profile;for(const key of ['bio','city','color'])profile.elements[key].value=values[key];}
        const note=$('[data-place-note]');if(note)note.elements.note.value=P.get().notes[note.dataset.placeNote]||'';
        for(const host of $$('[data-smart-options]')){const options=planningOptions();for(const key of ['skipVisited','savedFirst','indoor'])host.querySelector('[name="'+key+'"]').checked=options[key];const stops=host.querySelector('[name="stops"]');if(![...stops.options].some(n=>n.value===String(options.stops))){const option=make('option',options.stops+' stops');option.value=String(options.stops);stops.append(option);}stops.value=String(options.stops);}
    }
    function saveSmart(host){tripOptions={skipVisited:host.querySelector('[name="skipVisited"]').checked,savedFirst:host.querySelector('[name="savedFirst"]').checked,indoor:host.querySelector('[name="indoor"]').checked,stops:Number(host.querySelector('[name="stops"]').value)};if(planningKey){try{sessionStorage.setItem(planningKey,JSON.stringify(tripOptions));}catch(_){}}}
    function applySmart(){const form=$('[data-recommendations-form]'),status=$('[data-smart-status]');if(!form){if(status)status.textContent='Options saved. Continue through Review to Recommendations to apply them.';return;}if(!catalogReady){if(status)status.textContent='Wait for verified destination data before applying options.';return;}
        const state=P.get(),options=planningOptions(),byId=new Map(catalog.map(p=>[p.id,p])),inputs=[...form.querySelectorAll('[name="selected_place_ids"]')];
        if(form.hasAttribute('data-personalized-recommendations')&&options.stops!==Number(form.dataset.requestedCount||0)){const next=new URL(location.href);next.searchParams.set('stops',String(options.stops));location.assign(next.href);return;}
        let eligible=inputs.filter(input=>byId.has(input.value)&&!(options.skipVisited&&state.visited.includes(input.value))&&(!options.indoor||['indoor','covered'].includes(byId.get(input.value).exposure)));
        if(options.savedFirst)eligible.sort((a,b)=>Number(state.saved.includes(b.value))-Number(state.saved.includes(a.value)));
        const count=options.stops||Number(form.dataset.paceCount||3),selected=new Set(eligible.slice(0,count).map(i=>i.value));for(const input of inputs)input.checked=selected.has(input.value);
        if(options.savedFirst&&!form.hasAttribute('data-personalized-recommendations')){const list=form.querySelector('ul');if(list)for(const input of [...eligible,...inputs.filter(i=>!eligible.includes(i))]){const li=input.closest('li');if(li)list.append(li);}}
        form.dispatchEvent(new Event('change',{bubbles:true}));
        if(status)status.textContent=selected.size?selected.size+' destinations selected. Review them before building your itinerary.':'No destinations match your interests and these options. Change your options or select destinations manually.';
    }
    function applyDefaults(){const form=$('.itinerary-form');if(!form)return;const prefs=P.get().prefs;for(const key of ['interests','companion_type','trip_pace'])for(const input of form.querySelectorAll('[name="'+key+'"]'))input.checked=key==='interests'?prefs.interests.includes(input.value):input.value===(key==='trip_pace'?prefs.pace:prefs.companions);toast('Device defaults applied. Check all required fields before saving.');}
    async function loadTrips(){if(!P.hasAccountScope())return;try{const data=await requestJSON('/api/user/trips');for(const node of $$('[data-count="trips"]'))node.textContent=data.trips.length+(data.bounded?'+':'');}catch(_){}}
    document.addEventListener('click',event=>{const target=event.target.closest('button,a');if(!target)return;
        if(target.hasAttribute('data-recommendations-link')){const count=planningOptions().stops;if(count){const destination=new URL(target.href);destination.searchParams.set('stops',String(count));target.href=destination.href;}}
        if(target.dataset.openDialog){const dialog=document.getElementById(target.dataset.openDialog);if(dialog){dialog.showModal();target.setAttribute('aria-expanded','true');dialog.addEventListener('close',()=>target.setAttribute('aria-expanded','false'),{once:true});}return;}
        if(target.closest('dialog')&&target.tagName==='A')target.closest('dialog').close();
        if(target.dataset.noticeRead){event.preventDefault();const destination=target.href;changed(P.change(s=>{if(!s.read.includes(target.dataset.noticeRead))s.read.push(target.dataset.noticeRead);}));location.assign(destination);return;}
        if(target.dataset.eventFilter){eventFilter=target.dataset.eventFilter;for(const b of $$('[data-event-filter]'))b.setAttribute('aria-pressed',String(b===target));drawEvents();return;}
        if(target.dataset.mood){const moods={heritage:[['heritage','attraction'],'relaxed','couple'],food:[['dining','shopping'],'balanced','friends'],family:[['attraction','nature'],'balanced','family'],rain:[['shopping','dining'],'relaxed','group']},m=moods[target.dataset.mood];if(m)changed(P.change(s=>{[s.prefs.interests,s.prefs.pace,s.prefs.companions]=m;}));}
        const name=target.dataset.action,id=target.dataset.id;if(!name)return;
        if(name==='save'&&target.closest('[data-explore-grid]')){
            event.preventDefault();
            const previous=P.get().saved;
            savingExplorePlace=true;
            try{
                if(P.toggle('saved',id))toast(P.get().saved.includes(id)?'Place saved.':'Place removed from Saved.');
                else{P.change(state=>{state.saved=previous;});toast('Could not update this saved place. Please try again.');}
            }catch(_){toast('Could not update this saved place. Please try again.');}
            finally{savingExplorePlace=false;}
            return;
        }
        try{
            if(['save','visit','bag'].includes(name)){changed(P.toggle(({save:'saved',visit:'visited',bag:'bag'})[name],id));toast(name==='bag'?'Trip bag updated.':'Personal library updated.');}
            else if(name==='bag-clear'&&(!P.get().bag.length||confirm('Clear all places from your Trip Bag?'))){changed(P.change(s=>{s.bag=[];}));toast('Bag cleared. Saved trips were not changed.');}
            else if(name==='saved-to-bag')changed(P.change(s=>{s.bag=[...new Set([...s.bag,...validIds(s.saved)])];}));
            else if(name==='clear-library'&&confirm('Clear this personal library on this device?'))changed(P.change(s=>{s[target.dataset.kind]=[];}));
            else if(name==='event-reminder')changed(P.change(s=>{const n=Number(id);s.reminders=s.reminders.includes(n)?s.reminders.filter(i=>i!==n):[...s.reminders,n];}));
            else if(name==='notice-read')changed(P.change(s=>{s.read=[...new Set([...s.read,id])];}));
            else if(name==='notice-dismiss')changed(P.change(s=>{s.dismissed=[...new Set([...s.dismissed,id])];}));
            else if(name==='notices-read-all')changed(P.change(s=>{s.read=[...new Set([...s.read,...activeNotices().map(n=>n.id)])];}));
            else if(name==='notices-clear-dismissed'){notices=activeNotices();drawNotices();toast('Dismissed notifications cleared. New notifications are kept.');}
            else if(name==='backup'){$('#device-backup').value=P.exportData();$('[data-backup-status]').textContent='Local preferences and personal state shown. Real trips and account credentials are not included.';}
            else if(name==='restore'&&confirm('Replace your personal local state with this backup?')){changed(P.restore($('#device-backup').value));setupSettings();toast('Local state restored.');}
            else if(name==='reset-local'&&confirm('Reset only personal local state? Your account and real trips will remain.')){changed(P.reset());setupSettings();toast('Personal local state reset.');}
            else if(name==='apply-defaults')applyDefaults();
            else if(name==='apply-smart'){const host=target.closest('[data-smart-options]');if(host)saveSmart(host);applySmart();}
            else if(name==='checklist-remove')editChecklist(items=>items.splice(Number(id),1));
            else if(name==='location')location.assign('/map#route-use-location');
            else if(name==='assistant-prompt'){const field=$('#assistant-message');field.value=target.dataset.prompt;field.focus({preventScroll:true});}
        }catch(error){toast(error.message||'This device action could not be completed.');}
    });
    document.addEventListener('submit',event=>{const form=event.target;
        if(form.matches('[data-confirm-delete]')&&!confirm('Delete this saved trip and its destinations?')){event.preventDefault();return;}
        if(form.action&&new URL(form.action,location.href).pathname==='/logout')P.clearActive();
        try{
            if(form.matches('[data-place-note]')){event.preventDefault();const note=form.elements.note.value.trim(),id=form.dataset.placeNote;changed(P.change(s=>{if(note)s.notes[id]=note;else delete s.notes[id];}));toast(note?'Private note saved on this device.':'Note cleared.');}
            else if(form.matches('[data-device-settings]')){event.preventDefault();changed(P.change(s=>{s.prefs={size:form.elements.size.value,compact:form.elements.compact.checked,contrast:form.elements.contrast.checked,interests:[...form.querySelectorAll('[name="default_interests"]:checked')].map(i=>i.value),pace:form.elements.pace.value,companions:form.elements.companions.value,home:form.elements.home.value.trim(),weather:form.elements.weather.checked,events:s.prefs.events,trips:form.elements.trips.checked};}));toast('Device preferences saved.');}
            else if(form.matches('[data-device-profile]')){event.preventDefault();changed(P.change(s=>{s.profile={bio:form.elements.bio.value.trim(),city:form.elements.city.value.trim(),color:form.elements.color.value};}));toast('Personal profile presentation saved on this device.');}
            else if(form.matches('[data-trip-checklist-form]')){event.preventDefault();const field=form.elements.namedItem('item'),text=field.value.trim();if(!text)throw new Error('Type a checklist item first.');editChecklist(items=>items.push({text,done:false}));field.value='';}
            else if(form.matches('[data-feedback-form]')){event.preventDefault();const message=$('#feedback-message').value.trim();if(!message)throw new Error('Write feedback first.');changed(P.change(s=>{s.feedback.unshift({topic:$('#feedback-topic').value,message});s.feedback=s.feedback.slice(0,30);}));$('#feedback-message').value='';toast('Feedback saved on this device; nothing was sent.');}
            else if(form.matches('[data-auto-generate]')){const o=planningOptions();if(o.skipVisited||o.savedFirst||o.indoor||o.stops){event.preventDefault();location.assign(form.dataset.recommendationsUrl);}}
        }catch(error){event.preventDefault();toast(error.message||'Check your entries and try again.');}
    });
    document.addEventListener('change',event=>{const input=event.target;if(['explore-setting','explore-saved','explore-sort'].includes(input.id))applyExplore();if(input.dataset.checklistIndex)editChecklist(items=>{items[Number(input.dataset.checklistIndex)].done=input.checked;});const smart=input.closest('[data-smart-options]');if(smart)saveSmart(smart);});
    document.addEventListener('click',event=>{for(const dropdown of $$('.nav-dropdown[open]'))if(!dropdown.contains(event.target))dropdown.open=false;});
    document.addEventListener('keydown',event=>{if(event.key==='Escape')for(const dropdown of $$('.nav-dropdown[open]')){dropdown.open=false;dropdown.querySelector('summary').focus();}});
    addEventListener('scroll',()=>$('.site-header')?.classList.toggle('scrolled',scrollY>8),{passive:true});
    addEventListener('rosago:personal',refresh);
    if(P.hasAccountScope()&&document.body.dataset.authenticated!=='true'){
        for(const account of $$('.header-account')){const form=document.createElement('form');form.method='post';form.action='/logout';const button=make('button','Logout','account-logout-button');button.type='submit';form.append(button);account.replaceChildren(form);}
    }
    setupSettings();refresh();loadTrips();
    if($('[data-dashboard-weather]'))requestJSON('/api/weather').then(data=>{
        const host=$('[data-dashboard-weather]');
        if(!Number.isFinite(data.temperature_c)||!data.condition)throw new Error('Unavailable');
        host.replaceChildren(make('h2',Math.round(data.temperature_c)+' \u00b0C','dashboard-temperature'),make('p',data.condition));

        const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()),part=key=>parts.find(p=>p.type===key).value,today=part('year')+'-'+part('month')+'-'+part('day');
        const forecast=data.forecast?.find(day=>day.day===today);
        if(Number.isFinite(forecast?.maximum_c)&&Number.isFinite(forecast?.minimum_c))host.append(make('p','High '+Math.round(forecast.maximum_c)+' \u00b0 \u00b7 Low '+Math.round(forecast.minimum_c)+' \u00b0'));
        if(Number.isFinite(forecast?.precipitation_probability))host.append(make('p',"Today's rain chance "+Math.round(forecast.precipitation_probability)+'%'));
    }).catch(()=>{const host=$('[data-dashboard-weather]');host.replaceChildren(make('p','Weather is temporarily unavailable.'));});
    requestJSON('/api/places').then(data=>{catalog=data.places;catalogReady=true;refresh();for(const host of $$('[data-catalog-limit]'))drawCards(host,catalog.slice(0,Number(host.dataset.catalogLimit)));}).catch(()=>{for(const host of $$('[data-library],[data-bag-list]'))host.replaceChildren(make('p','Published destinations are temporarily unavailable. Your stored selections have not been deleted.'));});
    if(P.hasAccountScope())requestJSON('/api/user/notices').then(data=>{notices=data.notices;noticesReady=true;drawNotices();}).catch(()=>{if(!initialNotices)noticesReady=false;drawNotices();});
})();
