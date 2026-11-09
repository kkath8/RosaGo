"""Owned disposable local PG + independent authority qualification; no hosted IO."""
import importlib.util
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import qualify_evaluation_readiness as baseline
from prepare_provider_guards import prepare
spec=importlib.util.spec_from_file_location('external_local_pg_lab',ROOT/'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
lab_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab_module)
lab_module.NAME='rosago-external-'+secrets.token_hex(6);lab_module.IMAGE='postgres:17'
with socket.socket() as reserve:
    reserve.bind(('127.0.0.1',0));lab_module.PORT=reserve.getsockname()[1]
original=lab_module.docker
def cached(*args,**kwargs):
    return original(*(('run','--pull=never',*args[1:]) if args and args[0]=='run' else args),**kwargs)
lab_module.docker=cached

with lab_module.Lab() as lab,tempfile.TemporaryDirectory(prefix='rosago-external-results-') as temp:
    baseline.schema_checks(lab.operator,baseline.integrity())
    lab.operator.execute("""CREATE TABLE auth.sessions(id uuid PRIMARY KEY,user_id uuid,not_after timestamptz);
        CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS
        $$ SELECT current_setting('request.jwt.claims',true)::jsonb $$;""",prepare=False)
    review=prepare(lab.operator)
    (ROOT/'evaluation/infrastructure/sql/provider_access_guards.review.sql').write_text(review,encoding='utf-8')
    lab.operator.execute(review,prepare=False)
    lab.operator.execute((ROOT/'evaluation/infrastructure/sql/private_sessions.review.sql').read_text(encoding='utf-8'),prepare=False)
    # Test-only membership for existing generated throwaway login. Never part
    # of the hosted proposal. No session-role passwords enter SQL files.
    lab.operator.execute('GRANT rosago_session_app TO rosago_m_app')
    env={k:os.environ[k] for k in ('PATH','SystemRoot','TEMP','TMP','PATHEXT','USERPROFILE') if k in os.environ}
    env.update(ROSAGO_TEST_POSTGRES_DSN=lab.app_dsn,ROSAGO_TEST_POSTGRES_OPERATOR_DSN=lab.operator_dsn)
    xml=Path(temp)/'results.xml'
    run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--junitxml='+str(xml),'tests/test_external_session_infrastructure.py'],
        cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
    doc=ET.parse(xml).getroot();cases=list(doc.iter('testcase'))
    result={'scope':'Loopback PostgreSQL17, actual Worker/SQLite authority in separate local workerd process, authenticated loopback shim; synthetic provider only.',
        'exit_code':run.returncode,'cases':len(cases),'failures':len(list(doc.iter('failure'))),
        'errors':len(list(doc.iter('error'))),'failed_cases':[c.get('name') for c in cases if c.find('failure') is not None or c.find('error') is not None],
        'failure_locations':[{'case':c.get('name'),'type':f.get('type'),
            'safe_exception':__import__('re').findall(r'(?:SessionStorageUnavailable|RevisionConflict|TypeError|AttributeError|AssertionError): [A-Za-z .]+',f.text or ''),
            'locations':__import__('re').findall(r'(?:tests[/\\][A-Za-z_]+[.]py:\d+)',f.text or '')}
            for c in cases for f in list(c.findall('failure'))+list(c.findall('error'))],
        'hosted_requests':0,'live_signins':0,'production_enabled':False,'raw_output_saved':False}
    if run.returncode==0:
        sys.path.insert(0,str(ROOT/'tests'))
        from independent_authority_fixture import IndependentAuthorityFixture
        from externally_fenced_postgres import ExternalPgRealm,ExternalPgModel
        from postgres_session_store import isolated_pool
        from session_crypto import SessionCipher
        namespace='restart_'+secrets.token_hex(8)
        service=IndependentAuthorityFixture(Path(temp)/'restart-authority.sqlite',namespace)
        pool=isolated_pool(lab.app_dsn)
        try:
            logging.getLogger('psycopg.pool').setLevel(logging.CRITICAL)
            backend=ExternalPgRealm(pool,SessionCipher({'test':secrets.token_bytes(32)},'test'),namespace,'user','user_epoch',authority=service.client())
            model=ExternalPgModel(backend,'auth')
            handle=model.create(user_id='fixture',user_email='fixture@example.invalid',access_token='synthetic-access',
                refresh_token='synthetic-refresh',access_expires_at=time.time()+3600,session_id='synthetic-provider')
            def restart_database():
                # Lab created and owns this exact container, exclusively.
                lab_module.docker('restart',lab_module.NAME)
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    try:
                        with pool.connection() as c:c.execute('SELECT 1')
                        return
                    except Exception:time.sleep(.2)
                raise RuntimeError('Owned restart did not recover.')
            restart_database();service.restart();assert model.resolve(handle) is not None
            model.revoke(handle);restart_database();service.restart();assert model.resolve(handle) is None
            result['database_and_authority_restart_checks_passed']=2
        finally:pool.close();service.close()
    if '--diagnose' in sys.argv:
        # Explicit local development diagnostics. Pytest may contain synthetic
        # fixture data; no owner credentials are present in this child.
        print(run.stdout[-16000:])
        print(run.stderr[-1000:])
out=ROOT/'docs/production-readiness/remote-evaluation/external-infrastructure-results.json'
result['owned_fixture_removed']=True
out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
raise SystemExit(run.returncode)
