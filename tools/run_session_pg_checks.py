"""Focused REAL loopback PostgreSQL session checks; no application exposure.

Uses a cached postgres:17 image, generated throwaway credentials and the existing
local schema/test recovery controller. This is not production recovery approval.
"""
import importlib.util
import json
import os
import re
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py'
spec=importlib.util.spec_from_file_location('existing_local_pg_lab',source)
lab_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_module)
lab_module.NAME='rosago-session-scope-'+secrets.token_hex(6)
lab_module.IMAGE='postgres:17'
with socket.socket() as reserve:
    reserve.bind(('127.0.0.1',0))
    lab_module.PORT=reserve.getsockname()[1]
original_docker=lab_module.docker
def cached_docker(*args,**kwargs):
    if args and args[0]=='run':
        args=(args[0],'--pull=never',*args[1:])
    return original_docker(*args,**kwargs)
lab_module.docker=cached_docker
selected=(
'test_encryption_scope_ttl_and_renewal',
'test_terminal_revocation_blocks_record_only_restore',
'test_concurrent_refresh_and_revocation',
'test_runtime_role_cannot_change_gate_or_history',
'test_unknown_post_commit_result_does_not_retry_refresh',
'test_independent_family_expiry_and_fixed_rate_window',
)
qualification = '--application-qualification' in sys.argv
targets = ['PgStoreTests::' + name for name in selected]
if qualification:
    targets = [
        'PgApplicationTests::test_both_orders_two_workers_independent_logout',
        'PgApplicationTests::test_cross_realm_csrf_nonmember_and_actor_identity',
        'PgApplicationTests::test_recovery_callback_reset_and_verification_across_workers',
        'PgApplicationTests::test_pg_service_failure_keeps_both_cookies',
        'PgStoreTests::test_independent_recovery_gate_and_unavailable_authority',
        'RecoveryContractTests::test_stale_corrupt_replayed_and_uncertain_proof',
    ]
if '--runtime-wiring' in sys.argv:
    targets = [
        'PgApplicationTests::test_explicit_runtime_wires_all_stores_and_provider_checks',
        'PgApplicationTests::test_real_routes_enforce_provider_outage_and_terminal_revocation',
        'PgApplicationTests::test_both_orders_two_workers_independent_logout',
        'PgApplicationTests::test_recovery_callback_reset_and_verification_across_workers',
    ]
out=ROOT/'docs/production-readiness/remote-evaluation'
with lab_module.Lab() as lab,tempfile.TemporaryDirectory(prefix='rosago-pg-results-') as temp:
    env={key:os.environ[key] for key in ('PATH','SystemRoot','TEMP','TMP','PATHEXT','USERPROFILE') if key in os.environ}
    env.update(ROSAGO_TEST_POSTGRES_DSN=lab.app_dsn,
               ROSAGO_TEST_POSTGRES_OPERATOR_DSN=lab.operator_dsn)
    xml=Path(temp)/'results.xml'
    run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--junitxml='+str(xml),
        *('tests/test_postgres_sessions.py::'+name for name in targets)],
        cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
    document=ET.parse(xml).getroot()
    cases=list(document.iter('testcase'))
    result={'scope':'Real PostgreSQL in owned throwaway loopback-only container; synthetic credentials and local test recovery controller.',
            'selected_tests':targets,'exit_code':run.returncode,
            'cases_reported':len(cases),
            'failures':len(list(document.iter('failure'))),
            'errors':len(list(document.iter('error'))),
            'failed_case_names':[c.get('name') for c in cases if c.find('failure') is not None or c.find('error') is not None],
            'sanitized_failure_locations':[
                {'case': c.get('name'),
                 'locations': re.findall(r'(tests/[A-Za-z0-9_]+[.]py:\d+)', failure.text or ''),
                 'status_assertions': re.findall(r'E\s+assert (\d+ == \d+)', failure.text or ''),
                 'exception_types': re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):', failure.text or '')}
                for c in cases for failure in c.findall('failure')],
            'database_image':'cached postgres:17; no pull',
            'hosted_requests':0,'application_deployed':False,
            'production_recovery_authority_verified':False,
            'real_supabase_authentication_exercised':False,
            'raw_test_output_or_credentials_saved':False}
    out.mkdir(exist_ok=True,parents=True)
    output_name = 'real-local-pg-application-results.json' if qualification else 'real-local-pg-results.json'
    if '--runtime-wiring' in sys.argv:
        output_name='local-runtime-wiring-results.json'
    (out/output_name).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
# Existing Lab verifies its exact owned container ID, label and loopback binding
# before removing only that container and its anonymous volumes.
print('Owned local PostgreSQL fixture removed; real application and Supabase untouched.')
raise SystemExit(run.returncode)

