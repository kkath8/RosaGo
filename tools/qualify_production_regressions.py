"""Network-forbidden application/security regression suite; no server or Git writes."""
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0,str(ROOT/'tests'))
    historical=json.loads((ROOT/'docs/full-system-render/offline-tests.json').read_text())
    names=list(dict.fromkeys(historical['modules']+['test_production_shared_sessions','test_session_readiness',
        'test_session_release_blockers','test_provider_session_transport','test_normal_auth_coordinator',
        'test_normal_auth_store','test_normal_auth_flask','test_recovery_callback','test_password_reset']))
    with (patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')),
          patch.object(socket,'getaddrinfo',side_effect=AssertionError('DNS forbidden')),
          patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden'))):
        result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames(names))
    data=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        modules=names,network_forbidden=True,hosted_requests=0,real_credentials_used=False,
        production_mode_positive_cases_use_synthetic_signature_and_mocked_io=True,
        real_provider_qualified=False,deployment_authorized=False)
    (ROOT/'docs/production-shared-sessions/regression-results.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k!='modules'},indent=2))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
