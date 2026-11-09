"""Rehearse prepared SQL in disposable loopback PostgreSQL; no Supabase access.

Minimal auth schema/functions are local stubs, not a hosted Auth qualification.
No passwords or raw SQL error text are recorded.
"""
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_evaluation_setup import prepare, OUTPUT

spec = importlib.util.spec_from_file_location('schema_local_lab', ROOT /
    'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
lab_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_module)
lab_module.NAME = 'rosago-schema-check-' + secrets.token_hex(6)
lab_module.IMAGE = 'postgres:17'
with socket.socket() as reserve:
    reserve.bind(('127.0.0.1', 0))
    lab_module.PORT = reserve.getsockname()[1]
original_docker = lab_module.docker
def cached_docker(*args, **kwargs):
    if args and args[0] == 'run':
        args = (args[0], '--pull=never', *args[1:])
    return original_docker(*args, **kwargs)
lab_module.docker = cached_docker

result = {'hosted_changes': 0, 'hosted_auth_verified': False,
          'scope': 'Disposable PostgreSQL with minimal local Auth stubs', 'applied': []}
stage = 'fixture'
try:
    manifest = prepare()
    with lab_module.Lab() as lab:
        db = lab.operator
        db.execute("""
            CREATE ROLE anon NOLOGIN;
            CREATE ROLE authenticated NOLOGIN;
            CREATE ROLE service_role NOLOGIN;
            CREATE SCHEMA auth;
            CREATE TABLE auth.users (id uuid PRIMARY KEY, email text,
                created_at timestamptz DEFAULT now(), raw_user_meta_data jsonb DEFAULT '{}');
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
            GRANT USAGE ON SCHEMA public, auth TO anon, authenticated;
            GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated;
        """, prepare=False)
        for item in manifest['ordered_files']:
            stage = item['file']
            db.execute((OUTPUT / stage).read_text(encoding='utf-8'), prepare=False)
            result['applied'].append(stage)
        stage = 'synthetic_seed.sql'
        db.execute((OUTPUT / stage).read_text(encoding='utf-8'), prepare=False)
        rows = db.execute('SELECT count(*) FROM public.places').fetchone()[0]
        result['synthetic_places'] = rows
        result['tables_with_rls'] = db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity").fetchone()[0]
        stage = 'role_visibility'
        published = db.execute("SELECT count(*) FROM public.places WHERE status='published'").fetchone()[0]
        with db.transaction():
            db.execute('SET LOCAL ROLE anon')
            assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == published
        actor = 'f0000000-0000-4000-8000-000000000001'
        db.execute("INSERT INTO auth.users(id,email) VALUES (%s,'synthetic@example.invalid')", (actor,))
        with db.transaction():
            db.execute('SET LOCAL ROLE authenticated')
            db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
            assert db.execute('SELECT public.rosago_is_admin()').fetchone()[0] is False
            assert db.execute('SELECT count(*) FROM public.profiles').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == published
        db.execute('INSERT INTO public.admin_memberships(user_id) VALUES (%s)', (actor,))
        with db.transaction():
            db.execute('SET LOCAL ROLE authenticated')
            db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
            assert db.execute('SELECT public.rosago_is_admin()').fetchone()[0] is True
            assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == rows
        result['published_and_admin_visibility'] = 'passed'
        result['local_profile_trigger'] = 'passed'
        result['status'] = 'passed'
except Exception as error:
    result.update(status='failed', stage=stage, error_class=type(error).__name__)
    # Compare only against fixed messages in the reviewed input; never copy a
    # provider/connection exception or an arbitrary database response into logs.
    import re
    if stage.endswith('.sql') and (OUTPUT / stage).exists():
        messages = re.findall(r"RAISE EXCEPTION '([^']+)'", (OUTPUT / stage).read_text(encoding='utf-8'))
        primary = getattr(getattr(error, 'diag', None), 'message_primary', None)
        if primary in messages:
            result['reviewed_guard_message'] = primary
    if getattr(error, 'sqlstate', None):
        result['sqlstate'] = error.sqlstate
output = ROOT / 'docs/production-readiness/remote-evaluation/evaluation-schema-results.json'
output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result.get('status') == 'passed' else 1)
