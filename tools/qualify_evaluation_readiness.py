"""Local-only qualification. No hosted clients, production activation or accounts.

Uses one owned disposable loopback PostgreSQL container. Child-process inputs
travel over stdin; credentials, keys, handles and raw exceptions are not logged.
Recovery providers are deliberately test fixtures, never production evidence.
"""
import base64
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from postgres_session_fixture import TestRecoveryController
from postgres_session_recovery import RecoveryBinding, RecoveryFence
from postgres_session_store import PgModel, PgRealm, isolated_pool
from session_crypto import SessionCipher

OUT = ROOT / 'docs/production-readiness/remote-evaluation'


def stores(config):
    binding = RecoveryBinding(**config['binding'])
    controller = TestRecoveryController(binding)
    pool = isolated_pool(config['dsn'])
    cipher = SessionCipher({'test': base64.b64decode(config['key'])}, 'test')
    realms = {realm: PgRealm(pool, cipher, config['namespace'], realm,
              recovery=RecoveryFence(controller, binding)) for realm in ('user', 'admin')}
    return pool, {realm: PgModel(backend, 'auth') for realm, backend in realms.items()}


def child(config):
    pool, models = stores(config)
    try:
        if config['operation'] == 'revoke':
            assert models['user'].revoke(config['handles']['user'])
        answer = {realm: models[realm].resolve(handle) is not None
                  for realm, handle in config['handles'].items()}
        assert models['admin'].resolve(config['handles']['user']) is None
        return answer
    finally:
        pool.close()


def probe(config, operation='read'):
    env = {key: os.environ[key] for key in
           ('PATH', 'SystemRoot', 'TEMP', 'TMP', 'PATHEXT') if key in os.environ}
    run = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'],
                         input=json.dumps(dict(config, operation=operation)),
                         capture_output=True, text=True, timeout=20, cwd=ROOT, env=env)
    if run.returncode:
        raise RuntimeError('Isolated child failed')
    return json.loads(run.stdout)


def integrity():
    setup = ROOT / 'evaluation/setup'
    manifest = json.loads((setup / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['target_project_ref'] == 'jfaufpfzfhysqkhcdsrs'
    assert manifest['hosted_execution_authorized'] is False
    assert len(manifest['ordered_files']) == 15
    files = []
    for item in manifest['ordered_files']:
        source = (ROOT / item['source']).read_bytes()
        prepared = (setup / item['file']).read_bytes()
        assert hashlib.sha256(source).hexdigest() == item['source_sha256']
        assert hashlib.sha256(prepared).hexdigest() == item['prepared_sha256']
        original = source.decode('utf-8').replace('\r\n', '\n')
        candidate = prepared.decode('utf-8').split('\n', 1)[1]
        expected = original
        if item['file'] in ('0013b_destination_photo_contract.sql', '0014_destination_environment.sql'):
            expected = expected.replace('brnkigrrqdrywahvcbvc', 'jfaufpfzfhysqkhcdsrs')
        if item['file'] == '0014_destination_environment.sql':
            expected = expected.replace('aa4441116ded963faa4e1ee8e3024e4b', '148b4df23e340c9a434ad16013200e92')
            expected = expected.replace('399faf695b6a607f33bf1fb7c2dd9386', 'a45875ef215c9713bc4c7d32ef6601e1')
        assert candidate == expected
        assert 'brnkigrrqdrywahvcbvc' not in candidate
        files.append(item['file'])
    assert hashlib.sha256((setup / 'synthetic_seed.sql').read_bytes()).hexdigest() == manifest['synthetic_seed_sha256']
    return files


def schema_checks(db, files):
    db.execute("""
        CREATE ROLE anon NOLOGIN;
        CREATE ROLE authenticated NOLOGIN;
        CREATE ROLE service_role NOLOGIN;
        CREATE SCHEMA auth;
        CREATE TABLE auth.users(id uuid PRIMARY KEY, email text,
            created_at timestamptz DEFAULT now(), raw_user_meta_data jsonb DEFAULT '{}');
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
            $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
        GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
            GRANT ALL ON TABLES TO anon,authenticated,service_role;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
            GRANT ALL ON FUNCTIONS TO anon,authenticated,service_role;
        ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
            GRANT ALL ON SEQUENCES TO anon,authenticated,service_role;
    """, prepare=False)
    for name in files:
        db.execute((ROOT / 'evaluation/setup' / name).read_text(encoding='utf-8'), prepare=False)
    db.execute((ROOT / 'evaluation/setup/synthetic_seed.sql').read_text(encoding='utf-8'), prepare=False)
    assert db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity").fetchone()[0] == 9
    for role in ('anon', 'authenticated', 'service_role'):
        assert not db.execute("SELECT has_table_privilege(%s,'public.places','INSERT,UPDATE,DELETE,TRUNCATE')", (role,)).fetchone()[0]
        assert not db.execute("SELECT has_table_privilege(%s,'public.admin_memberships','INSERT,UPDATE,DELETE,TRUNCATE')", (role,)).fetchone()[0]
        assert not db.execute("SELECT has_function_privilege(%s,'public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)','EXECUTE')", (role,)).fetchone()[0]
    # Every function must pin its search path, and none may retain PUBLIC EXECUTE.
    assert db.execute("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND (NOT coalesce(p.proconfig && ARRAY['search_path=', 'search_path=""'],false)
        OR EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                  WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))""").fetchone()[0] == 0
    actors = ['f0000000-0000-4000-8000-000000000001', 'f0000000-0000-4000-8000-000000000002']
    for actor in actors:
        db.execute('INSERT INTO auth.users(id,email) VALUES(%s,%s)', (actor, 'fixture@example.invalid'))
    for actor in actors:
        with db.transaction():
            db.execute('SET LOCAL ROLE authenticated')
            db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
            assert db.execute('SELECT count(*) FROM public.profiles').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == 1
            assert not db.execute('SELECT public.rosago_is_admin()').fetchone()[0]
    db.execute('INSERT INTO public.admin_memberships(user_id) VALUES(%s)', (actors[1],))
    for actor, expected in zip(actors, (0, 1)):
        with db.transaction():
            db.execute('SET LOCAL ROLE authenticated')
            db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
            assert db.execute('SELECT count(*) FROM public.admin_memberships').fetchone()[0] == expected
            assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == 1 + expected
    with db.transaction():
        db.execute('SET LOCAL ROLE anon')
        assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == 1
    return {'all_15_transactions_and_seed': 'passed', 'hosted_style_default_grants': 'passed',
            'nine_rls_tables': 'passed', 'private_mutator_and_direct_write_denial': 'passed',
            'function_search_paths_and_public_execute_denial': 'passed',
            'profile_and_membership_ownership_and_published_visibility': 'passed',
            'hosted_auth_storage_or_full_rpc_acceptance': False}


def main():
    result = {'hosted_changes': 0, 'hosted_requests_by_this_script': 0,
              'production_adapter_qualified': False, 'protected_authority_qualified': False,
              'scope': 'Real disposable loopback PostgreSQL, separate Python processes, synthetic records, per-process test recovery controllers.'}
    stage = 'integrity'
    try:
        files = integrity()
        result['manifest_and_exact_source_diffs'] = 'passed'
        result['reviewed_order'] = files
        spec = importlib.util.spec_from_file_location('owned_local_lab', ROOT / 'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.NAME = 'rosago-readiness-' + secrets.token_hex(6)
        module.IMAGE = 'postgres:17'
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            module.PORT = reserve.getsockname()[1]
        original = module.docker
        def cached(*args, **kwargs):
            if args and args[0] == 'run':
                args = (args[0], '--pull=never', *args[1:])
            return original(*args, **kwargs)
        module.docker = cached
        stage = 'fixture'
        with module.Lab() as lab:
            stage = 'schema'
            result['schema'] = schema_checks(lab.operator, files)
            stage = 'cross_process'
            config = {'dsn': lab.app_dsn, 'namespace': 'probe_' + secrets.token_hex(8),
                      'key': base64.b64encode(secrets.token_bytes(32)).decode(),
                      'binding': asdict(RecoveryBinding(*(secrets.token_hex(16) for _ in range(4))))}
            b = config['binding']
            lab.operator.execute('INSERT INTO rosago_session_m.gate VALUES(%s,1,%s,%s,%s,%s,%s)',
                (config['namespace'], b['authority_id'], b['incarnation'], b['user_epoch'], b['admin_epoch'], 'OPEN'))
            pool, models = stores(config)
            try:
                config['handles'] = {realm: model.create(user_id='11111111-1111-4111-8111-111111111111',
                    user_email='fixture@example.invalid', access_token='synthetic-access',
                    refresh_token='synthetic-refresh', access_expires_at=time.time()+3600,
                    session_id='synthetic-provider-session') for realm, model in models.items()}
                assert probe(config) == {'user': True, 'admin': True}
                assert probe(config, 'revoke') == {'user': False, 'admin': True}
                assert models['user'].resolve(config['handles']['user']) is None
                assert models['admin'].resolve(config['handles']['admin']) is not None
                assert probe(config) == {'user': False, 'admin': True}
            finally:
                pool.close()
            result['cross_process_reads_revocation_and_fresh_process_restart'] = 'passed'
            stage = 'database_restart'
            value = json.loads(module.docker('inspect', module.NAME))[0]
            assert value['Id'] == lab.identity and value['Config']['Labels']['rosago.phase'] == '2m'
            assert value['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': str(module.PORT)}]
            module.docker('restart', module.NAME)
            # Each attempt is a fresh READ-only process, never a mutation retry.
            deadline = time.monotonic()+15
            while True:
                try:
                    assert probe(config) == {'user': False, 'admin': True}
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.2)
            result['database_restart_persistence_and_revocation'] = 'passed'
        result['owned_fixture_removed'] = True
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', stage=stage, error_class=type(error).__name__)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'continued-local-qualification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    if '--child' in sys.argv:
        try:
            print(json.dumps(child(json.load(sys.stdin))))
        except Exception:
            raise SystemExit(1) from None
    else:
        raise SystemExit(main())
