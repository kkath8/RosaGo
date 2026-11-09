"""Hash the local review package only. Never applies or authorizes hosted changes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'evaluation/infrastructure'
sql=['sql/private_sessions.review.sql','sql/provider_access_guards.review.sql']
files=['README.md','PLAN.md','runtime.env.review.example','authority/ledger.mjs',
    'authority/worker.mjs','authority/wrangler.review.toml','authority/package.json','authority/package-lock.json']
def entry(path):
    return {'file':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
original=ROOT/'docs/production-readiness/remote-evaluation/linux-build-results.json'
assert hashlib.sha256(original.read_bytes()).hexdigest()=='b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d'
manifest={'target_project_ref':'jfaufpfzfhysqkhcdsrs','local_implementation_approved':True,
    'hosted_execution_authorized':False,'deployment_authorized':False,'spending_authorized':False,
    'ordered_sql':[entry(PACKAGE/name) for name in sql],
    'review_files':[entry(PACKAGE/name) for name in files],
    'runtime_source':[entry(ROOT/name) for name in ('authority_http_transport.py','externally_fenced_postgres.py',
        'durable_session_logout.py','shared_session_runtime.py','redis_session_flask.py','app.py','admin_routes.py')],
    'qualification_source':[entry(ROOT/name) for name in ('tests/test_external_session_infrastructure.py',
        'tests/independent_authority_fixture.py','tests/test_authority_tls_local.py','tests/test_authority_http_transport.py',
        'tools/qualify_external_infrastructure.py','tools/qualify_infrastructure_linux.py','tools/prepare_provider_guards.py')],
    'worker_qualification_source':[entry(path) for path in sorted((PACKAGE/'authority/test').glob('*.mjs'))],
    'original_linux_evidence':entry(original),
    'note':'Review hashes are integrity evidence, not approval. No hosted commands are provided or executed.'}
(PACKAGE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
status_path=ROOT/'docs/production-readiness/remote-evaluation/render-infrastructure-plan-status.json'
status=json.loads(status_path.read_text(encoding='utf-8'))
status.update(planning_only=False,local_implementation_approved=True,authority_provider_approved_for_local_implementation=True,
    authority_provider_approved_for_hosting=False,
    next_approval='After SQL review: owner-operated application of exactly the two manifest-pinned evaluation SQL files only. No deployment, credentials, services, spending or sign-ins. Open recovery/API gates remain.',
    local_implementation_report='evaluation/infrastructure/README.md')
status_path.write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'review_manifest_prepared':True,'hosted_changes':0,'sql':manifest['ordered_sql']},indent=2))
