"""Compare captured read-only hosted metadata with the approved security SQL.

Offline only. No database connection, account credentials or application import.
"""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/production-readiness/remote-evaluation'
baseline=json.loads((OUT/'hosted-schema-postflight-catalog.json').read_text(encoding='utf-8'))
hosted=json.loads((OUT/'hosted-provider-guards-postflight-catalog.json').read_text(encoding='utf-8'))
extra=json.loads((OUT/'hosted-provider-guards-additional-postflight.json').read_text(encoding='utf-8'))
path=ROOT/'evaluation/infrastructure/sql/provider_access_guards.review.sql'
checks={}
checks['approved_sql_hash']=hashlib.sha256(path.read_bytes()).hexdigest()=='4136cd079ad39201e3fb185c0de8410374a556cb38631f25ac51e81c19983307'
checks['read_only_inspection']=hosted['role']==extra['inspector']=='supabase_read_only_user' and hosted['read_only']==extra['read_only']=='on'
sql=path.read_text(encoding='utf-8')
blocks=re.findall(r'EXECUTE \$review_definition\$(.*?)\$review_definition\$;',sql,re.S)
expected_bodies={}
for definition in blocks:
    name=re.search(r'FUNCTION public\.([a-z_]+)\(',definition).group(1)
    body=definition.split('AS $function$',1)[1].rsplit('$function$',1)[0]
    expected_bodies[name]=hashlib.md5(body.encode()).hexdigest()
helper='rosago_provider_session_current'
expected_bodies[helper]=hashlib.md5(sql.split('AS $$',1)[1].split('$$;',1)[0].encode()).hexdigest()
checks['exactly_seven_reviewed_replacements']=len(blocks)==7 and len(expected_bodies)==8
definitions=json.loads((OUT/'hosted-provider-guards-rpc-definitions.json').read_text(encoding='utf-8'))
expected_definitions={re.search(r'FUNCTION public\.([a-z_]+)\(',d).group(1):d.strip() for d in blocks}
checks['seven_complete_rpc_definitions_match']=len(definitions)==7 and set(definitions)==set(expected_definitions) and all(
    definitions[name].replace('\r\n','\n').strip()==definition for name,definition in expected_definitions.items())
checks['all_eight_exact_function_bodies']=all(
    len(matches:=[f for f in hosted['functions'] if f['name']==name])==1 and matches[0]['body_md5']==digest
    for name,digest in expected_bodies.items())
original_functions={(f['name'],f['arguments']):f for f in baseline['functions']}
expected_functions=[]
for original in baseline['functions']:
    expected_functions.append({**original,**({'body_md5':expected_bodies[original['name']]} if original['name'] in expected_bodies else {})})
expected_functions.append({'name':helper,'arguments':'','owner':'postgres','definer':True,
    'config':['search_path=""'],'acl':'{postgres=X/postgres,authenticated=X/postgres}',
    'body_md5':expected_bodies[helper],'anon_execute':False,'authenticated_execute':True,'service_execute':False})
checks['all_function_signatures_owners_paths_acls_and_bodies']=sorted(expected_functions,key=lambda f:(f['name'],f['arguments']))==hosted['functions']
checks['helper_return_type_and_language']=extra['helper']=={
    'signature':helper+'()','return_type':'boolean','argument_count':0,'language':'plpgsql',
    'owner':'postgres','definer':True,'config':['search_path=""'],
    'acl':'{postgres=X/postgres,authenticated=X/postgres}','volatility':'v','leakproof':False}
old_policies=[p for p in hosted['policies'] if p['policyname']!='rosago_current_provider_session']
checks['original_seventeen_policies_unchanged']=old_policies==baseline['policies'] and len(old_policies)==17
new_policies=[p for p in hosted['policies'] if p['policyname']=='rosago_current_provider_session']
tables={t['name'] for t in baseline['tables']}
expression='( SELECT rosago_provider_session_current() AS rosago_provider_session_current)'
checks['all_nine_exact_restrictive_policies']=(len(new_policies)==9 and {p['tablename'] for p in new_policies}==tables
    and all(p=={'schemaname':'public','tablename':p['tablename'],'policyname':'rosago_current_provider_session',
        'permissive':'RESTRICTIVE','roles':['authenticated'],'cmd':'ALL','qual':expression,'with_check':expression} for p in new_policies))
for section in ('tables','columns','constraints','indexes','triggers'):
    checks['unchanged_public_'+section]=hosted[section]==baseline[section]
counts={name:0 for name in baseline['counts']}
counts.update(profiles=2,places=2,auth_users=2,admin_memberships=1)
checks['application_auth_storage_counts_unchanged']=hosted['counts']==counts
checks['verified_accounts_profiles_and_membership_unchanged']=extra['accounts']==[
    {'id':'3c572202-c1da-4e5a-aa20-d89be25b2d9f','profile':True,'admin':False},
    {'id':'4bc67593-c979-4441-b42a-99b6d3da2885','profile':True,'admin':True}]
operator=json.loads((ROOT/'evaluation/schema-operator/manifest.json').read_text(encoding='utf-8'))
expected_migrations=[{'version':m['file'].split('_',1)[0],'name':m['file'].split('_',1)[1][:-4]} for m in operator['ordered_migrations']]
checks['all_fifteen_migration_versions_and_names_unchanged']=extra['migrations']==expected_migrations and len(expected_migrations)==15
checks['private_role_stays_disabled_and_unprivileged']=all(v is False for v in extra['private_role'].values())
checks['private_schema_and_table_grants_unchanged']=(extra['private_schema']=={
    'owner':'postgres','acl':'{postgres=UC/postgres,rosago_session_app=U/postgres}'} and extra['private_table']=={
    'owner':'postgres','rls':True,'force_rls':True,'acl':'{postgres=arwdDxtm/postgres,rosago_session_app=arwd/postgres}'})
checks['private_policy_unchanged']=extra['private_policies']==[
    {'name':'session_payload_role','roles':['rosago_session_app'],'cmd':'ALL','using':'true','check':'true'}]
checks['no_api_role_private_access']=len(extra['private_exposure'])==3 and all(
    p['schema_usage'] is False and p['table_dml'] is False and p['can_assume'] is False for p in extra['private_exposure'])
checks['private_payloads_and_provider_sessions_empty']=extra['payload_count']==extra['provider_session_count']==0
destinations=json.loads((OUT/'hosted-provider-guards-destination-postflight.json').read_text(encoding='utf-8'))
checks['every_approved_destination_field_unchanged']=destinations=={
    'exactly_two_destinations':True,'every_approved_destination_field_matches':True}
result={'status':'passed' if all(checks.values()) else 'mismatch','checks':checks,
    'checks_passed':sum(checks.values()),'checks_total':len(checks),'failures':[k for k,v in checks.items() if not v],
    'hosted_mutations_by_verifier':0,'live_signins':0,'deployment_qualified':False,
    'restore_replay_blocker_resolved':False,'scope':'Captured metadata comparison only; not live provider/API acceptance.'}
(OUT/'provider-guards-postflight-comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='passed' else 1)
