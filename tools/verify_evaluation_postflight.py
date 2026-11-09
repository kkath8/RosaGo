"""Compare captured hosted metadata to exact reviewed SQL in disposable local PG.

No hosted requests or mutations. No seed/accounts, real credentials or listeners
for the application. Uses the existing owned loopback-only PostgreSQL fixture.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/production-readiness/remote-evaluation'


def main():
    result = {'hosted_mutations_by_verifier': 0, 'seed_or_accounts_inserted': False}
    stage = 'integrity'
    try:
        manifest = json.loads((ROOT / 'evaluation/setup/manifest.json').read_text(encoding='utf-8'))
        assert manifest['target_project_ref'] == 'jfaufpfzfhysqkhcdsrs'
        assert len(manifest['ordered_files']) == 15
        for item in manifest['ordered_files']:
            assert hashlib.sha256((ROOT / 'evaluation/setup' / item['file']).read_bytes()).hexdigest() == item['prepared_sha256']
        hosted = json.loads((OUT / 'hosted-schema-postflight-catalog.json').read_text(encoding='utf-8'))
        assert hosted['role'] == 'supabase_read_only_user' and hosted['read_only'] == 'on'
        assert all(value == 0 for value in hosted['counts'].values())
        spec = importlib.util.spec_from_file_location('postflight_local_lab', ROOT / 'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.NAME = 'rosago-postflight-' + secrets.token_hex(6)
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
        stage = 'local_fixture'
        with module.Lab() as lab:
            db = lab.operator
            db.execute("""
                CREATE ROLE anon NOLOGIN;
                CREATE ROLE authenticated NOLOGIN;
                CREATE ROLE service_role NOLOGIN;
                CREATE SCHEMA auth;
                CREATE TABLE auth.users(id uuid PRIMARY KEY, email text,
                    created_at timestamptz DEFAULT now(),raw_user_meta_data jsonb DEFAULT '{}');
                CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                    $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
                GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
                ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
                    GRANT ALL ON TABLES TO anon,authenticated,service_role;
                ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
                    GRANT ALL ON FUNCTIONS TO anon,authenticated,service_role;
                CREATE SCHEMA storage;
                CREATE TABLE storage.buckets(id text);
                CREATE TABLE storage.objects(id text);
            """, prepare=False)
            stage = 'local_schema_reconstruction'
            for item in manifest['ordered_files']:
                db.execute((ROOT / 'evaluation/setup' / item['file']).read_text(encoding='utf-8'), prepare=False)
            local = db.execute((ROOT / 'evaluation/verification/schema_catalog_readonly.sql').read_text(encoding='utf-8')).fetchone()[0]
            stage = 'catalog_comparison'
            keys = ('tables','columns','constraints','indexes','policies','functions','triggers','counts')
            result['sections'] = {key: {'match': hosted[key] == local[key], 'entries': len(hosted[key])} for key in keys}
            result['differences'] = [key for key in keys if hosted[key] != local[key]]
        result['owned_local_fixture_removed'] = True
        result['status'] = 'passed' if not result['differences'] else 'mismatch'
    except Exception as error:
        result.update(status='failed', stage=stage, error_class=type(error).__name__)
    (OUT / 'hosted-schema-catalog-comparison.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
