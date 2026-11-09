import assert from 'node:assert/strict';
import {browser,ready,origin,save} from './browser_common.mjs';
const b=await browser({newContext:true});
const results=[];
const check=(value,label)=>{assert.ok(value,label);results.push({check:label,result:'PASS'});};
async function loginPage(){await b.go('/admin/login');await b.click('#fill-synthetic-admin');}
async function deniedEdit(){await b.tab.call('Page.navigate',{url:origin+'/admin/places/manual-test-garden/edit'});await b.wait("location.pathname==='/admin/login'&&document.readyState==='complete'");}
try {
  await b.go('/__isolated');
  check(await b.evaluate("document.getElementById('instance-id').textContent")===ready.run_id,'Separate private context reaches same isolated server');
  await b.click('form[action="/__isolated/confirm"] button');
  await b.wait("location.pathname==='/admin/login'&&document.readyState==='complete'");
  await b.click('#fill-synthetic-admin');
  await b.evaluate("document.querySelector('form.admin-login-form').elements.password.value='intentionally-wrong-synthetic-input'");
  await b.click('button.admin-login-submit');
  await b.wait("document.readyState==='complete'&&!!document.querySelector('#admin-login-message')");
  check(await b.evaluate("document.getElementById('admin-login-message').textContent.includes('Invalid email or password')"),'Known invalid dummy input reproduces 401 failure message');
  await deniedEdit();check(true,'Failed authentication grants no access to Admin editing');
  await loginPage();
  await b.evaluate("document.querySelector('form.admin-login-form').elements.email.value='user-a@example.invalid'");
  await b.click('button.admin-login-submit');
  await b.wait("document.readyState==='complete'&&!!document.querySelector('#admin-login-message')");
  check(await b.evaluate("document.getElementById('admin-login-message').textContent.includes('Admin access required')"),'Valid synthetic User identity fails current Admin membership check');
  await deniedEdit();check(true,'Ordinary User cannot access destination editing');
  check((await(await fetch(origin+'/__isolated/state')).json()).mutation_actions.length===3,'Negative auth checks make no additional destination writes');
  save('browser-auth-results.json',{results,passed:results.length,failures:0,real_auth_requests:0});
  console.log(JSON.stringify({passed:results.length,failures:0}));
} catch(error){save('browser-auth-results.json',{results,passed:results.length,failures:1,failure:error.message});throw error;}
finally{await b.close();}
