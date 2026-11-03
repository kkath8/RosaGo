/* Non-sensitive browser defaults stay separate from protected account writes. */
(() => {
    'use strict';
    const P = typeof RosaGoPersonal === 'undefined' ? null : RosaGoPersonal;
    if (!P) return;
    const $ = selector => document.querySelector(selector);
    const personal = document.body.dataset.personalized !== 'false';
    const quiz = $('.itinerary-form');
    function defaults() {
        if (!quiz || !personal) return;
        const prefs = P.get().prefs;
        for (const input of quiz.querySelectorAll('[name=interests]')) input.checked = prefs.interests.includes(input.value);
        for (const [name,value] of Object.entries({companion_type:prefs.companions,trip_pace:prefs.pace,transportation:prefs.transportation})) {
            for (const input of quiz.querySelectorAll('[name="'+name+'"]')) input.checked = input.value === value;
        }
        const budget = $('[data-profile-budget-note]');
        if (budget) {
            const label = {low:'Low',mid:'Mid-range',high:'High'}[prefs.budgetPreference];
            budget.hidden = !label;
            budget.textContent = label ? 'Your budget preference: '+label+'. Destination prices are not verified; this does not filter or guarantee trip costs.' : '';
        }
    }
    if (quiz?.dataset.profileDefaultsEligible === 'true') defaults();
    $('[data-apply-profile-defaults]')?.addEventListener('click', defaults);
    const management = $('[data-profile-management]');
    if (management) {
        const form = $('[data-profile-account]'), travel = $('[data-travel-profile]'), status = $('[data-profile-status]');
        const state = P.get();
        const check = (name,value) => { for (const input of travel.querySelectorAll('[name="'+name+'"]')) input.checked = Array.isArray(value) ? value.includes(input.value) : input.value === value; };
        check('travel_interests',state.prefs.interests);check('traveler_type',state.prefs.companions);check('avatar_color',state.profile.color);
        check('pace',state.prefs.pace);check('transportation',state.prefs.transportation);check('budget_preference',state.prefs.budgetPreference);
        travel.querySelector('[name=stops]').value=String(state.options.stops);
        for(const key of ['indoor','skipVisited','savedFirst'])travel.querySelector('[name='+key+']').checked=state.options[key];
        const nameError = (key,text) => { const field=form.elements[key],node=$('[data-name-error='+key+']');node.textContent=text;node.hidden=!text;field.setAttribute('aria-invalid',String(!!text)); };
        for(const key of ['first_name','last_name'])form.elements[key].addEventListener('input',()=>nameError(key,''));
        let saving=false;
        form.addEventListener('submit',async event=>{
            if(!window.fetch)return;
            event.preventDefault();if(saving)return;
            let valid=true;
            for(const key of ['first_name','last_name']){
                const value=form.elements[key].value.trim();
                const error=!value?(key==='first_name'?'Enter your first name.':'Enter your last name.'):
                    value.length>100||/[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/u.test(value)?'Use up to 100 characters without control characters.':'';
                nameError(key,error);if(error)valid=false;
            }
            const interests=[...travel.querySelectorAll('[name=travel_interests]:checked')].map(input=>input.value);
            const error=$('[data-interests-error]');error.textContent=interests.length>6?'Choose up to six interests.':'';error.hidden=interests.length<=6;
            if(!valid||interests.length>6){form.querySelector('[aria-invalid=true]')?.focus();return;}
            const preferences={interests,pace:travel.querySelector('[name=pace]:checked').value,companions:travel.querySelector('[name=traveler_type]:checked')?.value||'friends',transportation:travel.querySelector('[name=transportation]:checked').value,budgetPreference:travel.querySelector('[name=budget_preference]:checked')?.value||''};
            const color=travel.querySelector('[name=avatar_color]:checked')?.value||'';
            const options={stops:Number(travel.querySelector('[name=stops]').value)};
            for(const key of ['indoor','skipVisited','savedFirst'])options[key]=travel.querySelector('[name='+key+']').checked;
            const data=new FormData(form),button=management.querySelector('[type=submit]');saving=true;button.disabled=true;status.textContent='Saving…';
            try{
                const response=await fetch(form.action,{method:'POST',body:data,credentials:'same-origin'});
                if(response.redirected&&new URL(response.url).pathname==='/login'){location.assign(response.url);return;}
                const page=new DOMParser().parseFromString(await response.text(),'text/html');
                if(!response.ok){
                    let specific=false;
                    for(const key of ['first_name','last_name']){const error=page.querySelector('[data-name-error='+key+']')?.textContent.trim();if(error){nameError(key,error);specific=true;}}
                    status.textContent=specific?'':'Your save could not be confirmed. Check your profile before trying again.';return;
                }
                if(!page.querySelector('[data-profile-management]'))throw new Error('Unconfirmed save');
                const persisted=P.change(next=>{Object.assign(next.prefs,preferences);next.profile.color=color;next.options=options;});
                $('[data-profile-full-name]').textContent=[form.elements.first_name.value.trim(),form.elements.last_name.value.trim()].join(' ');
                $('.profile-avatar').textContent=(form.elements.first_name.value.trim()[0]+form.elements.last_name.value.trim()[0]).toUpperCase();
                status.textContent=persisted?'Profile updated successfully.':'Your name was updated. Travel preferences could not be remembered; please try again.';
            }catch(_){status.textContent='Your save could not be confirmed. Check your profile before trying again.';}
            finally{saving=false;button.disabled=false;}
        });
    }
    const settings=$('[data-management-settings]');
    if(settings){
        const master=$('[data-setting-notifications]'),weather=$('[data-setting-weather]'),trips=$('[data-setting-trips]');
        function values(){
            weather.disabled=!master.checked;trips.disabled=!master.checked;
            settings.elements.alerts_display.value=!master.checked?'none':weather.checked&&trips.checked?'all':weather.checked?'weather':trips.checked?'trips':'none';
            settings.elements.personalized.value=String($('[data-setting-personalized]').checked);
            settings.elements.location_enabled.value=String($('[data-setting-location]').checked);
        }
        settings.addEventListener('change',event=>{if(event.target===master&&master.checked&&!weather.checked&&!trips.checked){weather.checked=true;trips.checked=true;}values();});
        settings.addEventListener('submit',values);values();
        document.querySelector('a[href="#about-rosago"]')?.addEventListener('click',()=>{$('#about-rosago').open=true;});
    }
})();
