"""Local restoration/BFF candidate qualification. Never accesses a hosted project.

Reconstructs the previously captured schema in a disposable database, without
rerunning either installed security SQL file. No application/owner credentials.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import qualify_evaluation_readiness as baseline
from psycopg import sql
from psycopg.conninfo import make_conninfo

def main():
    spec=importlib.util.spec_from_file_location('restore_replay_lab',ROOT/'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.NAME='rosago-replay-'+secrets.token_hex(6);module.IMAGE='postgres:17'
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));module.PORT=reserve.getsockname()[1]
    original=module.docker
    module.docker=lambda *args,**kw:original(*(('run','--pull=never',*args[1:]) if args and args[0]=='run' else args),**kw)
    import hashlib
    protected={name:hashlib.sha256((ROOT/'evaluation/infrastructure/sql'/name).read_bytes()).hexdigest()
        for name in ('private_sessions.review.sql','provider_access_guards.review.sql')}
    with module.Lab() as lab,tempfile.TemporaryDirectory(prefix='rosago-replay-results-') as temp:
        baseline.schema_checks(lab.operator,baseline.integrity())
        lab.operator.execute("""CREATE TABLE auth.sessions(id uuid PRIMARY KEY,user_id uuid,not_after timestamptz);
            CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS
            $$ SELECT current_setting('request.jwt.claims',true)::jsonb $$;
            CREATE SCHEMA rosago_session;
            CREATE TABLE rosago_session.payloads(key text PRIMARY KEY,ciphertext bytea NOT NULL,expires float8 NOT NULL);
            ALTER TABLE rosago_session.payloads ENABLE ROW LEVEL SECURITY;
            ALTER TABLE rosago_session.payloads FORCE ROW LEVEL SECURITY;
            GRANT USAGE ON SCHEMA rosago_session TO rosago_m_app;
            GRANT SELECT,INSERT,UPDATE,DELETE ON rosago_session.payloads TO rosago_m_app;
            CREATE POLICY local_lab_cache ON rosago_session.payloads TO rosago_m_app USING(true) WITH CHECK(true);
            """,prepare=False)
        # Standalone old helper proposal and captured postflight definitions are
        # used only as local fixtures. Neither installed security file is run.
        lab.operator.execute((ROOT/'evaluation/auth-testing/provider_session_rpc.review.sql').read_text(encoding='utf-8'),prepare=False)
        definitions=json.loads((ROOT/'docs/production-readiness/remote-evaluation/hosted-provider-guards-rpc-definitions.json').read_text(encoding='utf-8'))
        for definition in definitions.values():lab.operator.execute(definition,prepare=False)
        captured=json.loads((ROOT/'docs/production-readiness/remote-evaluation/hosted-provider-guards-postflight-catalog.json').read_text(encoding='utf-8'))
        for p in captured['policies']:
            if p['policyname']=='rosago_current_provider_session':
                lab.operator.execute(sql.SQL('CREATE POLICY rosago_current_provider_session ON public.{} AS RESTRICTIVE '
                    'FOR ALL TO authenticated USING ((SELECT public.rosago_provider_session_current())) '
                    'WITH CHECK ((SELECT public.rosago_provider_session_current()))').format(sql.Identifier(p['tablename'])))
        lab.operator.execute((ROOT/'evaluation/infrastructure/sql/data_gateway.review.sql').read_text(encoding='utf-8'),prepare=False)
        secret=secrets.token_urlsafe(40)
        lab.operator.execute(sql.SQL('CREATE ROLE rosago_gateway_lab LOGIN NOINHERIT PASSWORD {}').format(sql.Literal(secret)))
        lab.operator.execute('GRANT rosago_data_gateway TO rosago_gateway_lab WITH INHERIT FALSE, SET TRUE')
        gateway_dsn=make_conninfo(lab.app_dsn,user='rosago_gateway_lab',password=secret)
        env={k:os.environ[k] for k in ('PATH','SystemRoot','TEMP','TMP','PATHEXT','USERPROFILE') if k in os.environ}
        env.update(ROSAGO_TEST_POSTGRES_DSN=lab.app_dsn,ROSAGO_TEST_POSTGRES_OPERATOR_DSN=lab.operator_dsn,
                   ROSAGO_TEST_GATEWAY_DSN=gateway_dsn)
        xml=Path(temp)/'result.xml'
        run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','--junitxml='+str(xml),
            'tests/test_server_data_gateway.py'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=150)
        document=ET.parse(xml).getroot();cases=list(document.iter('testcase'))
        result={'scope':'Owned loopback PostgreSQL17, local workerd independent authority, synthetic provider only.',
            'exit_code':run.returncode,'cases':len(cases),'failures':len(list(document.iter('failure'))),
            'errors':len(list(document.iter('error'))),'failed_cases':[c.get('name') for c in cases if c.find('failure') is not None or c.find('error') is not None],
            'failure_locations':[{'case':c.get('name'),'locations':re.findall(r'tests[/\\][A-Za-z_]+[.]py:\d+',f.text or ''),
                'safe_error':re.findall(r'(?:GatewayDenied|GatewayUnavailable|AttributeError|TypeError|AssertionError): [A-Za-z .]+',f.text or '')}
                for c in cases for f in list(c.findall('failure'))+list(c.findall('error'))],
            'hosted_requests':0,'live_signins':0,'approved_security_sql_files_rerun':False,
            'full_auth_restore_replay_resolved':False,'hosted_data_api_disable_verified':False,'hosted_data_api_changed':False,
            'remote_deployment':'NO-GO','raw_output_saved':False}
        result['approved_sql_hashes_preserved']=all(hashlib.sha256((ROOT/'evaluation/infrastructure/sql'/n).read_bytes()).hexdigest()==h for n,h in protected.items())
    result['owned_fixture_removed']=True
    (ROOT/'docs/production-readiness/remote-evaluation/restore-replay-local-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return run.returncode

if __name__=='__main__':raise SystemExit(main())
