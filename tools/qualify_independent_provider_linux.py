"""Supplemental Linux runtime checks against current security files, no rebuild."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
IMAGE='rosago-evaluation:restore-replay-local-check'
FILES=['authority_http_transport.py','independent_provider_sessions.py','normal_auth_coordinator.py',
       'normal_auth_flask.py','admin_session_flask.py','shared_session_runtime.py']
PATTERNS=['test_independent_provider_sessions.py','test_provider_session_check.py',
    'test_provider_session_transport.py','test_shared_session_runtime.py','test_authority_http_transport.py',
    'test_normal_auth_adapters.py','test_normal_auth_coordinator.py','test_normal_auth_store.py',
    'test_normal_auth_flask.py','test_protected_session_authority.py']
ORIGINAL=ROOT/'docs/production-readiness/remote-evaluation/linux-build-results.json'
ORIGINAL_HASH='b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d'
assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==ORIGINAL_HASH
source="""
import json,os,sys,unittest
sys.path.insert(0,'/app/tests')
patterns=PATTERNS
suite=unittest.TestSuite(unittest.defaultTestLoader.discover('/app/tests',pattern=p) for p in patterns)
result=unittest.TestResult();suite.run(result)
from flask import Flask
from session_realms import init_session_realms
blocked=False
try:init_session_realms(Flask('still-closed'),mode='production')
except RuntimeError:blocked=True
answer=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
    failed_cases=[str(c) for c,_ in result.failures+result.errors],
    production_startup_blocked=blocked,nonroot=os.getuid()==10001)
print(json.dumps(answer));sys.exit(0 if result.wasSuccessful() and blocked and os.getuid()==10001 else 1)
""".replace('patterns=PATTERNS','patterns='+repr(PATTERNS))
args=['docker','--context','desktop-linux','run','--pull=never','--rm','-i','--network','none','--read-only',
      '--tmpfs','/tmp:rw,noexec,nosuid,size=128m','--mount','type=bind,source='+str(ROOT/'tests')+',target=/app/tests,readonly']
for name in FILES:args+=['--mount','type=bind,source='+str(ROOT/name)+',target=/app/'+name+',readonly']
args+=['--entrypoint','python',IMAGE,'-']
run=subprocess.run(args,input=source,capture_output=True,text=True,timeout=90)
result=json.loads(run.stdout.strip())
result.update(exit_code=run.returncode,network='none',ports_published=False,hosted_requests=0,
    image=IMAGE,current_file_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES},
    original_linux_evidence_preserved=hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==ORIGINAL_HASH,
    remote_deployment='NO-GO')
(ROOT/'docs/production-readiness/remote-evaluation/independent-provider-linux-results.json').write_text(
    json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2));raise SystemExit(run.returncode)
