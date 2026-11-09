import fs from 'node:fs';
import {browser,save,here} from './browser_common.mjs';
const b=await browser();
try {
  await b.click('#fill-synthetic-admin');
  // Public fixed dummy comparisons only, in this fresh automated profile.
  const preparation=await b.evaluate(`(()=>{const f=document.querySelector('form.admin-login-form'),d=new FormData(f);return {email_matches_fixture:d.get('email')==='admin-b@example.invalid',password_matches_fixture:d.get('password')==='Local-test-password-1!',helper_executed:document.getElementById('synthetic-fill-status').textContent.includes('values filled')};})()`);
  if(!preparation.email_matches_fixture||!preparation.password_matches_fixture) {
    save('browser-login-result.json',{preparation,submitted:false,reason:'Fixture fill did not prepare expected successful controls'});
    throw new Error('Synthetic fill mismatch; no login submitted');
  }
  await b.click('button.admin-login-submit');
  await b.wait("document.readyState==='complete' && (location.pathname==='/admin'||!!document.querySelector('#admin-login-message'))");
  const authenticated=await b.evaluate("location.pathname==='/admin'");
  const authEvents=JSON.parse(fs.readFileSync(new URL('auth-events.json',here),'utf8'));
  const result={preparation,submitted:true,authenticated,auth_events:authEvents};
  if(authenticated) {
    await b.go('/admin/places');
    result.admin_navigation_continuity=await b.evaluate("!!document.querySelector('a[href=\"/admin/places/manual-test-garden/edit\"]')");
    await b.click('a[href="/admin/places/manual-test-garden/edit"]');
    await b.wait("location.pathname==='/admin/places/manual-test-garden/edit'&&document.readyState==='complete'");
    result.correct_existing_record_loaded=await b.evaluate("document.querySelector('[data-destination-form]').elements.name.value==='Manual Test Garden'");
  }
  save('browser-login-result.json',result);
  console.log(JSON.stringify(result));
  if(!authenticated)process.exitCode=1;
} finally {await b.close();}
