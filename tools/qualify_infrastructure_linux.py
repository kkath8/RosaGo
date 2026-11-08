"""Network-disabled Linux candidate smoke checks; no serving or deployment."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
original=ROOT/'docs/production-readiness/remote-evaluation/linux-build-results.json'
expected='b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d'
assert hashlib.sha256(original.read_bytes()).hexdigest()==expected
source=r'''
import json,os,pathlib,subprocess,sys,unittest
sys.path.insert(0,'/app/tests')
patterns=['test_shared_session_runtime.py','test_provider_session_check.py',
          'test_provider_session_transport.py','test_evaluation_isolation.py',
          'test_session_readiness.py','test_authority_http_transport.py']
suite=unittest.TestSuite(unittest.defaultTestLoader.discover('/app/tests',pattern=p) for p in patterns)
result=unittest.TestResult();suite.run(result)
from flask import Flask
from session_realms import init_session_realms
blocked=False
try:init_session_realms(Flask('production-refusal'),mode='production')
except RuntimeError:blocked=True
deps=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True).returncode==0
excluded=all(not pathlib.Path('/app',p).exists() for p in ('.env','.git','evaluation/infrastructure','evaluation/setup','evaluation/account-setup'))
answer={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
 'production_startup_blocked':blocked,'nonroot':os.getuid()==10001,'pip_check':deps,
 'private_files_excluded':excluded,'network':'none','ports_published':False}
print(json.dumps(answer));sys.exit(0 if result.wasSuccessful() and blocked and deps and excluded and os.getuid()==10001 else 1)
'''
image='rosago-evaluation:infrastructure-local-check'
run=subprocess.run(['docker','--context','desktop-linux','run','--rm','-i','--network','none','--read-only',
    '--mount','type=bind,source='+str(ROOT/'tests')+',target=/app/tests,readonly',
    '--entrypoint','python',image,'-'],input=source,capture_output=True,text=True,timeout=60)
result=json.loads(run.stdout.strip())
result.update(exit_code=run.returncode,image=image,
    image_id=subprocess.check_output(['docker','--context','desktop-linux','image','inspect',image,'--format','{{.Id}}'],text=True).strip(),
    original_build_evidence_preserved=hashlib.sha256(original.read_bytes()).hexdigest()==expected)
(ROOT/'docs/production-readiness/remote-evaluation/infrastructure-linux-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2));raise SystemExit(run.returncode)
