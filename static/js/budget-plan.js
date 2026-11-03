/* User-entered allocation arithmetic only. No prices, fares or trip writes. */
((root) => {
    'use strict';
    const categories = [
        ['food','Food',30], ['transport','Transportation',25],
        ['activities','Activities / Entrance',20], ['shopping','Shopping',15], ['extra','Emergency / Extra',10]
    ];
    function distribute(total, weights) {
        const sum=weights.reduce((a,b)=>a+b,0);
        const exact=weights.map(w=>total*w/sum), result=exact.map(Math.floor);
        const order=exact.map((n,i)=>({i,remainder:n-result[i]})).sort((a,b)=>b.remainder-a.remainder||a.i-b.i);
        for(let n=0,left=total-result.reduce((a,b)=>a+b,0);n<left;n++)result[order[n].i]++;
        return result;
    }
    const suggested=total=>distribute(total,categories.map(c=>c[2]));
    function fromLegacy(old) {
        const entries=old.entries.map(e=>({label:e.label,category:'extra',amount:e.amount*old.people}));
        if(old.transport)entries.push({label:'Transportation',category:'transport',amount:old.transport*old.people});
        const total=old.cap?old.cap*old.people:entries.reduce((a,e)=>a+e.amount,0);
        return {version:1,trip:old.trip,people:old.people,total,allocations:suggested(total),entries};
    }
    function resize(plan,total) {
        const weights=plan.allocations.reduce((a,b)=>a+b,0)>0?plan.allocations:categories.map(c=>c[2]);
        return {...plan,total,allocations:distribute(total,weights)};
    }
    function summary(plan) {
        const planned=plan.entries.reduce((a,e)=>a+e.amount,0);
        const allocated=plan.allocations.reduce((a,b)=>a+b,0);
        return {planned,allocated,remaining:plan.total-planned,perPerson:plan.total/plan.people,
            allocationGap:plan.total-allocated,
            status:!plan.total?'Set a budget':planned>plan.total?'Over budget':planned>=plan.total*.9?'Near budget':'Within budget',
            categories:categories.map(([key,label],i)=>{const spent=plan.entries.filter(e=>e.category===key).reduce((a,e)=>a+e.amount,0);return {key,label,allocated:plan.allocations[i],planned:spent,remaining:plan.allocations[i]-spent};})};
    }
    function amount(value) {
        if(!/^\d+(\.\d{0,2})?$/.test(String(value)))throw Error('Enter an amount with up to two decimal places.');
        const cents=Math.round(Number(value)*100);
        if(!Number.isSafeInteger(cents)||cents<0||cents>100000000000)throw Error('Use an amount from PHP 0 to 1,000,000,000.');
        return cents;
    }
    const api=Object.freeze({categories,suggested,fromLegacy,resize,summary,amount});
    if(typeof module!=='undefined'&&module.exports)module.exports=api;
    else root.RosaGoBudget=api;
})(globalThis);
