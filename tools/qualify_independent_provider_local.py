"""Offline native RLS + pgsql-http TLS + actual workerd/SQLite qualification.

Cached images only; network-none shared loopback; private file relay connects
the TLS byte server to workerd. No real Auth API, PostgREST or Vault is claimed.
Never executes either installed security SQL script or any hosted operation.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT=Path(__file__).resolve().parents[1]
PG='public.ecr.aws/supabase/postgres:17.11.0.002'
PYTHON='rosago-evaluation:restore-replay-local-check'
ISSUER='https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1'
UID='11111111-1111-4111-8111-111111111111'
SID='22222222-2222-4222-8222-222222222222'
TABLES=['admin_destination_audit','admin_memberships','itinerary_drafts','places','profiles',
        'trip_itinerary','trip_places','trip_stop_plans','trips']

def docker(*args,input=None,check=True):
    return subprocess.run(['docker','--context','desktop-linux',*args],input=input,
        capture_output=True,text=True,timeout=45,check=check)

def certificate(folder):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
    now=dt.datetime.now(dt.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=1))
        .not_valid_after(now+dt.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256()))
    (folder/'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (folder/'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))

def main():
    checks=[];containers=[];node=None;relay=None;stop=threading.Event();lock=threading.Lock()
    binding={'authority_id':secrets.token_hex(16),'incarnation':secrets.token_hex(16),'namespace':'native_fixture'}
    migration=ROOT/'evaluation/infrastructure/sql/independent_provider_authority.review.sql'
    migration_hash=hashlib.sha256(migration.read_bytes()).hexdigest()
    preserved={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        ROOT/'evaluation/infrastructure/sql/private_sessions.review.sql',
        ROOT/'evaluation/infrastructure/sql/provider_access_guards.review.sql',
        ROOT/'docs/production-readiness/remote-evaluation/linux-build-results.json']}
    result={}
    with tempfile.TemporaryDirectory(prefix='rosago-independent-provider-') as directory:
        folder=Path(directory);certificate(folder)
        keys={op:secrets.token_hex(24) for op in ('check','revoke')}
        (folder/'secrets.json').write_text(json.dumps(keys));(folder/'mode').write_text('normal')
        def authority(operation,request=None,head=False):
            with lock:
                node.stdin.write(json.dumps(dict(operation=operation,request=request or {},head=head))+'\n');node.stdin.flush()
                return json.loads(node.stdout.readline())
        def provider(operation,sid=SID,uid=UID,**extra):
            request=dict(version=1,**binding,issuer=ISSUER,uid=uid,sid=sid,
                nonce=secrets.token_hex(24),now=time.time(),deadline=time.time()+1000)
            return authority(operation,{**request,**extra})
        def relay_loop():
            while not stop.wait(.005):
                for path in folder.glob('*.request'):
                    try:
                        request=json.loads(path.read_text());path.unlink()
                        answer=authority(**request)
                        target=path.with_suffix('.response');part=path.with_suffix('.reply-part')
                        part.write_text(json.dumps(answer));part.replace(target)
                    except Exception: stop.set();return
        try:
            node=subprocess.Popen(['node',str(ROOT/'evaluation/infrastructure/authority/test/stdio-provider-workerd-service.mjs'),
                str(folder/'sqlite'),binding['authority_id'],binding['incarnation']],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            assert json.loads(node.stdout.readline())=={'fixture_ready':True}
            assert authority('initialize',{**binding,'epochs':{'user':'user_epoch','admin':'admin_epoch'}})['status']==200
            relay=threading.Thread(target=relay_loop,daemon=True);relay.start()
            mount='type=bind,source='+str(folder)+',target=/fixture'
            pg=docker('run','--pull=never','--detach','--network','none','--user','postgres',
                '--mount',mount+',readonly','--mount','type=bind,source='+str(folder/'server.pem')+
                ',target=/etc/ssl/certs/ca-certificates.crt,readonly',
                '--entrypoint','sh',PG,'-c',
                'initdb -D /tmp/rosago-db -A trust --locale=C --encoding=UTF8 >/tmp/init.log && exec postgres -D /tmp/rosago-db -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp').stdout.strip()
            assert len(pg)==64;containers.append(pg)
            operator='postgres'
            def sql(statement,check=True):
                result=docker('exec','-i','-e','PGOPTIONS=-c statement_timeout=5000 -c lock_timeout=1500',pg,
                    'psql','-X','-h','127.0.0.1','-U',operator,'-d','postgres',
                    '-v','ON_ERROR_STOP=1','-At','-q',input=statement,check=False)
                if check and result.returncode:
                    line=next((v for v in result.stderr.splitlines() if v.startswith('ERROR:')),'SQL fixture failed')
                    raise RuntimeError(line)
                return result
            deadline=time.monotonic()+30
            while sql('SELECT 1',False).returncode:
                if time.monotonic()>deadline:raise RuntimeError('Owned PostgreSQL fixture readiness timeout')
                time.sleep(.1)
            tls=docker('run','--pull=never','--detach','--network','container:'+pg,'--user','0:0',
                '--mount',mount,'--mount','type=bind,source='+str(ROOT/'evaluation/infrastructure/authority/test/native-https-relay.py')+
                ',target=/relay.py,readonly','--entrypoint','python',PYTHON,'/relay.py').stdout.strip()
            assert len(tls)==64;containers.append(tls)
            deadline=time.monotonic()+15
            while not (folder/'tls-ready').exists():
                if time.monotonic()>deadline:raise RuntimeError('Owned TLS fixture readiness timeout')
                time.sleep(.1)
            sql("""CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role;
              CREATE SCHEMA extensions;CREATE EXTENSION http SCHEMA extensions;
              CREATE SCHEMA auth;CREATE SCHEMA vault;
              CREATE TABLE vault.decrypted_secrets(id uuid PRIMARY KEY,decrypted_secret text);
              CREATE TABLE auth.users(id uuid PRIMARY KEY);
              CREATE TABLE auth.sessions(id uuid PRIMARY KEY,user_id uuid,not_after timestamptz);
              CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS
                $$ SELECT current_setting('request.jwt.claims',true)::jsonb $$;
              CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                $$ SELECT (auth.jwt()->>'sub')::uuid $$;
              GRANT USAGE ON SCHEMA auth TO authenticated;
              CREATE FUNCTION public.rosago_provider_session_current() RETURNS boolean
                LANGUAGE sql SECURITY DEFINER SET search_path='' AS
                $$ SELECT EXISTS(SELECT 1 FROM auth.sessions WHERE id=(auth.jwt()->>'session_id')::uuid
                  AND user_id=auth.uid()) /* https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1 */ $$;
            """)
            for table in TABLES:
                sql(f"""CREATE TABLE public.{table}(id uuid PRIMARY KEY,user_id uuid,status text);
                  ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
                  GRANT SELECT,INSERT,UPDATE,DELETE ON public.{table} TO authenticated;
                  CREATE POLICY fixture_permissive ON public.{table} TO authenticated
                    USING(status='Published') WITH CHECK(status='Published');
                  CREATE POLICY rosago_current_provider_session ON public.{table} AS RESTRICTIVE
                    TO authenticated USING((SELECT public.rosago_provider_session_current()))
                    WITH CHECK((SELECT public.rosago_provider_session_current()));
                  INSERT INTO public.{table} VALUES('{SID}','{UID}','Published');""")
            claims=dict(iss=ISSUER,sub=UID,session_id=SID,role='authenticated',aud='authenticated',exp=int(time.time())+1000)
            definitions=json.loads((ROOT/'docs/production-readiness/remote-evaluation/hosted-provider-guards-rpc-definitions.json').read_text())
            for definition in definitions.values():sql(definition)
            verification=(ROOT/'evaluation/infrastructure/sql/independent_provider_authority.verify.readonly.sql').read_text()
            preflight=(ROOT/'evaluation/infrastructure/sql/independent_provider_authority.preflight.readonly.sql').read_text()
            compatibility=json.loads(sql(preflight).stdout)
            assert compatibility['evaluation_helper_issuer_present'] and compatibility['read_only']
            before=json.loads(sql(verification).stdout)
            def api(query,patch=None,check=True):
                encoded=json.dumps({**claims,**(patch or {})}).replace("'","''")
                return sql("SET ROLE authenticated; SET request.jwt.claims='"+encoded+"';"+query,check)
            sql(f"INSERT INTO auth.sessions VALUES('{SID}','{UID}',NULL)")
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='t'
            sql(f"DELETE FROM auth.sessions; INSERT INTO auth.sessions VALUES('{SID}','{UID}',NULL)")
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='t'
            checks.append('old_row_only_restore_bypass_reproduced')
            source=migration.read_text(encoding='utf-8')
            assert source.count("  RAISE EXCEPTION 'UNQUALIFIED_INDEPENDENT_PROVIDER_AUTHORITY'; -- LOCAL_QUALIFICATION_GATE")==1
            sql(source.replace("  RAISE EXCEPTION 'UNQUALIFIED_INDEPENDENT_PROVIDER_AUTHORITY'; -- LOCAL_QUALIFICATION_GATE",
                               '  NULL; -- disposable local qualification only'))
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            checks.append('missing_configuration_denies')
            for op,key in keys.items():
                sql(f"INSERT INTO vault.decrypted_secrets VALUES('{ '33333333-3333-4333-8333-333333333333' if op=='check' else '44444444-4444-4444-8444-444444444444'}','{key}')")
            sql(f"INSERT INTO rosago_provider_authority.config VALUES(true,'https://localhost','{binding['authority_id']}',"
                f"'{binding['incarnation']}','{binding['namespace']}','33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444')")
            # Record fixture privileges; never infer hosted operator permissions.
            attributes=json.loads(sql("SELECT json_build_object('superuser',rolsuper,'bypassrls',rolbypassrls) FROM pg_roles WHERE rolname='postgres'").stdout)
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            checks.append('existing_unenrolled_session_denies')
            assert provider('enroll')['status']==200
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='t'
            checks.append('real_pgsql_http_tls_actual_workerd_admits_enrolled_session')
            sql("UPDATE rosago_provider_authority.config SET origin='https://127.0.0.1'")
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            checks.append('tls_hostname_mismatch_denied_without_insecure_override')
            sql("UPDATE rosago_provider_authority.config SET origin='https://localhost'")
            for table in TABLES:
                assert api(f'SELECT count(*) FROM public.{table}').stdout.strip()=='1'
            checks.append('all_nine_rls_policies_admit_active_session')
            assert api("UPDATE public.places SET status='Draft'",check=False).returncode!=0
            checks.append('existing_permissive_policy_still_applies_with_active_authority')
            for patch in ({'exp':int(time.time())-1},{'iss':'https://other.invalid'},{'session_id':'invalid'},
                          {'role':'service_role'},{'sub':'55555555-5555-4555-8555-555555555555'}):
                assert api('SELECT public.rosago_provider_session_current()',patch).stdout.strip()=='f'
            checks.append('expired_wrong_issuer_identity_role_and_malformed_claims_deny')
            for mode in ('outage','timeout','redirect','wrong-nonce','malformed','duplicate'):
                (folder/'mode').write_text(mode)
                assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
                checks.append(mode+'_fails_closed')
            (folder/'mode').write_text('normal')
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='t'
            checks.append('outage_recovery_preserves_active_admission')
            sid2='66666666-6666-4666-8666-666666666666'
            assert provider('enroll',sid=sid2)['status']==200
            sql(f"INSERT INTO auth.sessions VALUES('{sid2}','{UID}',NULL)")
            sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()+interval '0.5 seconds' WHERE id='{sid2}'")
            sql('ALTER TABLE auth.sessions DISABLE TRIGGER rosago_independent_provider_session;'
                f"UPDATE auth.sessions SET not_after=NULL WHERE id='{sid2}';"
                'ALTER TABLE auth.sessions ENABLE ALWAYS TRIGGER rosago_independent_provider_session;')
            time.sleep(.6)
            assert api('SELECT public.rosago_provider_session_current()',{'session_id':sid2}).stdout.strip()=='f'
            checks.append('future_provider_expiry_survives_restored_not_after_column')
            assert sql('TRUNCATE auth.sessions',False).returncode!=0
            checks.append('truncate_cannot_bypass_per_session_revocation')
            sql('BEGIN; DELETE FROM auth.sessions; ROLLBACK;')
            assert api('SELECT public.rosago_provider_session_present()').stdout.strip()=='t'
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            checks.append('rolled_back_delete_cannot_roll_back_external_revocation')
            sql(f"DELETE FROM auth.sessions WHERE id='{SID}'")
            assert provider('check')['value']['revoked'] is True
            checks.append('provider_delete_trigger_durably_revokes_before_commit')
            assert sql(f"INSERT INTO auth.sessions VALUES('{SID}','{UID}',NULL)",False).returncode!=0
            checks.append('logical_auth_row_restore_rejected')
            sql(f"ALTER TABLE auth.sessions DISABLE TRIGGER rosago_independent_provider_session;"
                f"INSERT INTO auth.sessions VALUES('{SID}','{UID}',NULL);"
                'ALTER TABLE auth.sessions ENABLE ALWAYS TRIGGER rosago_independent_provider_session;')
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            assert api('SELECT public.rosago_provider_session_present()').stdout.strip()=='t'
            checks.append('physical_row_restore_simulation_still_denies_without_false_logout_confirmation')
            for table in TABLES:
                assert api(f'SELECT count(*) FROM public.{table}').stdout.strip()=='0'
            checks.append('all_nine_direct_api_role_rls_tables_deny_restored_jwt_claims')
            for table in TABLES:
                assert api(f"INSERT INTO public.{table} VALUES('{sid2}','{UID}','Published')",check=False).returncode!=0
                api(f"UPDATE public.{table} SET status='Draft'")
                api(f"DELETE FROM public.{table}")
                assert sql(f'SELECT count(*) FROM public.{table}').stdout.strip()=='1'
            checks.append('all_nine_rls_write_checks_and_mutation_filters_deny_restored_session')
            after=json.loads(sql(verification).stdout)
            assert before['existing_record_counts']==after['existing_record_counts']
            assert before['migration_history']==after['migration_history']
            assert all(p['permissive']=='RESTRICTIVE' for p in after['policies'] if p['schemaname']=='public')
            assert len(after['auth_session_triggers'])==2 and all(t['enabled']=='A' for t in after['auth_session_triggers'])
            assert all(not f['anon_execute'] and not f['authenticated_execute'] and not f['service_execute']
                for f in after['functions'] if f['signature'].startswith('rosago_provider_authority.'))
            checks.append('readonly_verification_helper_confirms_triggers_permissions_counts_and_history')
            calls=['rosago_itinerary_draft_create()',"rosago_admin_mutate_destination('create','fixture',NULL,'{}')",
                "rosago_admin_operational_overview('',0)",f"rosago_itinerary_draft_store_preview('{SID}',1,'{{}}')",
                f"rosago_itinerary_draft_adjust_preview('{SID}',1,'{{}}','{{}}')",
                f"rosago_itinerary_draft_return_to_editing('{SID}',1)",
                f"rosago_itinerary_draft_update_preferences('{SID}',1,'{{}}')"]
            for call in calls:
                response=api('SELECT * FROM public.'+call,check=False)
                assert response.returncode!=0 and 'Current provider session required' in response.stderr
            checks.append('all_seven_captured_rpc_entry_checks_deny_restored_session')
            for forbidden in ('SELECT * FROM rosago_provider_authority.config',
                f"SELECT rosago_provider_authority.exchange('enroll','{UID}','{SID}')"):
                assert api(forbidden,check=False).returncode!=0
            checks.append('ordinary_api_role_cannot_read_credentials_or_call_private_exchange')
            assert authority('restart')=={'restarted':True}
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            assert provider('enroll')['status']==503
            checks.append('actual_authority_process_restart_and_old_enrollment_replay_stay_denied')
            assert authority('block')['status']==200
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            checks.append('independent_operator_block_fails_closed')
            quarantine=ROOT/'evaluation/infrastructure/sql/independent_provider_authority.quarantine.review.sql'
            sql(quarantine.read_text().replace("  RAISE EXCEPTION 'UNAPPROVED_EVALUATION_QUARANTINE'; -- LOCAL_QUALIFICATION_GATE",
                '  NULL; -- disposable local rollback qualification only'))
            assert api('SELECT public.rosago_provider_session_current()').stdout.strip()=='f'
            assert provider('enroll')['status']==503
            checks.append('emergency_quarantine_keeps_guards_tombstones_and_denial')
            result=dict(passed=len(checks),checks=checks,hosted_requests=0,live_signins=0,
                scope='Native PostgreSQL17 RLS/7 captured RPC entry guards, real pgsql-http HTTPS, actual local workerd SQLite authority via private byte relay.',
                network='none; two disposable containers share loopback only; no published ports',
                fixtures='Synthetic Auth rows/claims, simplified application rows and Vault secret view; NOT a live Supabase Auth/PostgREST/Vault qualification.',
                local_direct_data_restore_replay_protected=True,hosted_qualification=False,
                managed_auth_endpoints_qualified=False,full_schema_restore_protected=False,
                native_helper_owner_attributes=attributes,
                function_body_md5={f['signature']:f['body_md5'] for f in after['functions']},
                migration_sha256=migration_hash,remote_deployment='NO-GO')
        finally:
            for container in reversed(containers):docker('rm','-f','-v',container,check=False)
            stop.set()
            if relay:relay.join(timeout=3)
            if node:
                node.stdin.close()
                try:node.wait(timeout=10)
                except subprocess.TimeoutExpired:node.kill();node.wait()
                node.stdout.close()
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in preserved.items())
    assert hashlib.sha256(migration.read_bytes()).hexdigest()==migration_hash
    result.update(owned_fixtures_removed=True,installed_sql_and_original_linux_evidence_preserved=True)
    output=ROOT/'docs/production-readiness/remote-evaluation/independent-provider-local-results.json'
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
