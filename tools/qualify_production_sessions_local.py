"""Owned loopback PG + real local SQLite/workerd. No hosted access or app server."""
import importlib.util
import argparse
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

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT=Path(__file__).resolve().parents[1]
GATE="DO $release_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_EXTERNAL_SESSION_STORE_SETUP'; END $release_gate$;"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('test_encrypted_cross_worker_and_new_worker_after_authority_restart',))
    selection=parser.parse_args().case
    source=ROOT/'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py'
    spec=importlib.util.spec_from_file_location('owned_production_session_lab',source)
    lab_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab_module)
    lab_module.NAME='rosago-production-sessions-'+secrets.token_hex(8)
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));lab_module.PORT=reserve.getsockname()[1]
    original=lab_module.docker
    def cached(*args,**kwargs):
        if args and args[0]=='run':args=(args[0],'--pull=never',*args[1:])
        return original(*args,**kwargs)
    lab_module.docker=cached
    with lab_module.Lab() as lab,tempfile.TemporaryDirectory(prefix='rosago-prod-results-') as temp:
        lab.operator.execute('CREATE DATABASE rosago_sessions_native')
        operator_dsn=make_conninfo(lab.operator_dsn,dbname='rosago_sessions_native')
        with psycopg.connect(operator_dsn,autocommit=True) as owner:
            source=(ROOT/'docs/production-shared-sessions/external-store.review.sql').read_text()
            assert source.count(GATE)==1
            # Test authorization replaces the release gate only in memory and is
            # bound to this verified owned database/system ID. Never a release.
            system=owner.execute('SELECT system_identifier::text FROM pg_control_system()').fetchone()[0]
            fence="DO $local_only$ BEGIN IF current_database()<>'rosago_sessions_native' OR current_user<>'postgres' OR (SELECT system_identifier::text FROM pg_control_system())<>'"+system+"' THEN RAISE EXCEPTION 'LOCAL_FIXTURE_REQUIRED'; END IF; END $local_only$;"
            owner.execute(source.replace(GATE,fence,1),prepare=False)
            password=secrets.token_urlsafe(32)
            owner.execute(sql.SQL('ALTER ROLE rosago_session_app LOGIN PASSWORD {}').format(sql.Literal(password)))
            application_dsn=make_conninfo(operator_dsn,user='rosago_session_app',password=password)
        env={k:os.environ[k] for k in ('PATH','SystemRoot','TEMP','TMP','PATHEXT','USERPROFILE') if k in os.environ}
        env.update(ROSAGO_PRODUCTION_TEST_STORE_DSN=application_dsn,ROSAGO_PRODUCTION_TEST_OPERATOR_DSN=operator_dsn)
        xml=Path(temp)/'results.xml'
        test_path='tests/test_production_sessions_native.py'+('::NativeProductionSessions::'+selection if selection else '')
        run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',test_path,
            '--junitxml='+str(xml)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        document=ET.parse(xml).getroot();cases=list(document.iter('testcase'))
        result=dict(tests=len(cases),failures=len(list(document.iter('failure'))),errors=len(list(document.iter('error'))),
            skipped=len(list(document.iter('skipped'))),exit_code=run.returncode,
            failed_cases=[c.get('name') for c in cases if c.find('failure') is not None or c.find('error') is not None],
            local_error_types=[re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):',(node.text or '')) for node in document.iter('error')],
            sanitized_failures=[dict(case=c.get('name'),locations=re.findall(r'tests[/\\][A-Za-z0-9_.]+\.py:\d+',f.text or ''),
                stages=re.findall(r'"stage":\s*"([a-z_]+)"',f.text or ''),
                phases=re.findall(r'"phases":\s*\["([a-z_]+)"\]',f.text or ''),
                types=re.findall(r'"failure_type":\s*"([A-Za-z_]+)"',f.text or ''),
                flag_diagnostics=re.findall(r'"flags":\s*(\{[^}]+\})',f.text or ''),
                identity_types=re.findall(r'"identity_types":\s*(\{[^}]+\})',f.text or ''),
                assertions=re.findall(r'^E\s+(assert .{0,180})$',f.text or '',re.MULTILINE)) for c in cases for f in c.findall('failure')],
            scope='Owned loopback PostgreSQL, real local SQLite/workerd; synthetic signed release/provider. No hosted/TLS qualification.',
            production_mode_store_exercised=True,hosted_requests=0,real_signins=0,application_server_started=False,
            database_tls_qualified=False,managed_provider_qualified=False,release_approved=False)
    folder=ROOT/'docs/production-shared-sessions';folder.mkdir(exist_ok=True)
    (folder/'native-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    if run.returncode:raise SystemExit(run.returncode)


if __name__=='__main__':main()
