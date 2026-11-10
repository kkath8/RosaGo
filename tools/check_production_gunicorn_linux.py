"""Cached Linux check of current production wiring; no build/pull/server/network."""
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from tools.prepare_full_existing_catalog_staging import inputs,ROOT

IMAGE='sha256:b5cf2d7a53257a0a733ae0f9aad8fb63698fb057006d3d8d682a7e0ca569c476'
CODE=r'''
import contextlib,io,importlib.metadata as metadata,json,os,pathlib,runpy,socket,sys,tempfile,unittest,zipfile
from unittest.mock import patch,Mock
assert os.geteuid()!=0
with tempfile.TemporaryDirectory(prefix='rosago-production-linux-') as folder:
 with zipfile.ZipFile('/source.zip') as archive:archive.extractall(folder)
 os.chdir(folder);sys.path[:0]=[folder,folder+'/tests']
 versions={}
 for name in ('requirements.txt','requirements-render.txt'):
  raw=pathlib.Path(name).read_bytes();text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
  for line in text.splitlines():
   if not line or line.startswith(('#','-r')):continue
   package,version=line.split('==');package=package.split('[')[0]
   versions[package]=metadata.version(package);assert versions[package]==version
 from test_production_shared_sessions import ProductionSessions
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(ProductionSessions)
 output=io.StringIO();result=unittest.TextTestRunner(stream=output).run(suite)
 assert result.wasSuccessful(),output.getvalue()
 case=ProductionSessions();case.setUp()
 try:
  with patch.dict(os.environ,case.env,clear=True),patch('production_session_runtime.open_worker',side_effect=case.worker),patch('dotenv.load_dotenv'),patch('supabase.create_client',return_value=Mock()):
   captured=io.StringIO()
   with patch.object(sys,'argv',['gunicorn','--check-config','--config','gunicorn.conf.py','production_wsgi:app']),contextlib.redirect_stdout(captured),contextlib.redirect_stderr(captured):
    try:runpy.run_module('gunicorn.__main__',run_name='__main__')
    except SystemExit as exit:assert exit.code==0,captured.getvalue()
  with patch.dict(os.environ,{'ROSAGO_AUTH_MODE':'production'},clear=True),patch('supabase.create_client') as sdk:
   try:runpy.run_path('production_wsgi.py')
   except RuntimeError:pass
   else:raise AssertionError('Unqualified startup succeeded')
   sdk.assert_not_called()
 finally:case.doCleanups()
 print(json.dumps(dict(python=sys.version.split()[0],dependency_pins=len(versions),all_pins_match=True,nonroot=True,
  production_tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
  production_wsgi_gunicorn_check_config=True,missing_release_denied_before_sdk=True,
  qualification_signature_and_io='synthetic test fixtures only',network='none',ports_published=0,server_started=False,
  managed_provider_qualified=False,deployment_authorized=False)))
'''


def main():
    with tempfile.TemporaryDirectory(prefix='rosago-production-source-') as temporary:
        archive=Path(temporary)/'source.zip';files=inputs()
        for name in ('production_runtime_fixture.py','test_production_shared_sessions.py','protected_authority_fixture.py','test_public_layout.py'):
            files['tests/'+name]=(ROOT/'tests'/name).read_bytes()
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as output:
            for name,value in files.items():output.writestr(name,value)
        run=subprocess.run(['docker','run','-i','--rm','--pull=never','--network','none',
            '--mount',f'type=bind,source={archive},target=/source.zip,readonly','--entrypoint','python',IMAGE,'-'],
            input=CODE.encode(),capture_output=True,timeout=120)
        if run.returncode:raise RuntimeError('Linux production qualification failed: '+run.stderr.decode(errors='replace')[-1400:])
        result=json.loads(run.stdout);result['image']=IMAGE
    (ROOT/'docs/production-shared-sessions/linux-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
