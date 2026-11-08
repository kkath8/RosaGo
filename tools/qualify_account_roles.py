"""Local account/role rehearsal only: no hosted Auth accounts or credentials."""
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import qualify_evaluation_readiness as schema
import psycopg


def main():
    result = {'hosted_requests': 0, 'hosted_accounts_created': 0,
              'scope': 'Disposable loopback PostgreSQL; two local Auth stub rows, not live Supabase identities.'}
    stage = 'fixture'
    try:
        spec = importlib.util.spec_from_file_location('account_role_lab', ROOT / 'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
        lab_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lab_module)
        lab_module.NAME = 'rosago-account-roles-' + secrets.token_hex(6)
        lab_module.IMAGE = 'postgres:17'
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            lab_module.PORT = reserve.getsockname()[1]
        original = lab_module.docker
        def cached(*args, **kwargs):
            if args and args[0] == 'run':
                args = (args[0], '--pull=never', *args[1:])
            return original(*args, **kwargs)
        lab_module.docker = cached
        with lab_module.Lab() as lab:
            db = lab.operator
            stage = 'reviewed_schema_seed_and_stub_accounts'
            schema.schema_checks(db, schema.integrity())
            user = 'f0000000-0000-4000-8000-000000000001'
            admin = 'f0000000-0000-4000-8000-000000000002'
            # The baseline already checked membership behavior. Rehearse the
            # newly prepared owner transaction against exactly two local stubs.
            db.execute('DELETE FROM public.admin_memberships')
            db.execute('ALTER TABLE auth.users ADD COLUMN email_confirmed_at timestamptz DEFAULT now()')
            stage = 'guarded_membership_transaction'
            grant = (ROOT / 'evaluation/account-setup/grant_admin_membership.review.sql').read_text(encoding='utf-8')
            db.execute(grant.replace('<SYNTHETIC_USER_UUID>', user).replace('<SYNTHETIC_ADMIN_UUID>', admin), prepare=False)
            assert db.execute('SELECT user_id::text FROM public.admin_memberships').fetchall() == [(admin,)]
            stage = 'role_acceptance'
            checks = []
            with db.transaction():
                db.execute('SET LOCAL ROLE anon')
                assert db.execute('SELECT slug FROM public.places ORDER BY slug').fetchall() == [('evaluation-garden',)]
            checks.append('anonymous_published_only')
            for actor, is_admin in ((user, False), (admin, True)):
                with db.transaction():
                    db.execute('SET LOCAL ROLE authenticated')
                    db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
                    assert db.execute('SELECT public.rosago_is_admin()').fetchone()[0] is is_admin
                    expected = [('evaluation-draft',), ('evaluation-garden',)] if is_admin else [('evaluation-garden',)]
                    assert db.execute('SELECT slug FROM public.places ORDER BY slug').fetchall() == expected
                    assert db.execute('SELECT id::text FROM public.profiles').fetchall() == [(actor,)]
                    assert db.execute('SELECT user_id::text FROM public.admin_memberships').fetchall() == ([(admin,)] if is_admin else [])
                checks.append('admin_visibility_and_ownership' if is_admin else 'user_visibility_and_ownership')
                denials = [
                    ('membership_self_grant_denied', 'INSERT INTO public.admin_memberships(user_id) VALUES(%s)', (actor,)),
                    ('direct_destination_delete_denied', 'DELETE FROM public.places WHERE false', ()),
                    ('private_mutator_execute_denied', 'SELECT public.rosago_admin_mutate_destination_unlogged(NULL,NULL,NULL,NULL)', ()),
                ]
                if not is_admin:
                    denials.append(('nonmember_admin_overview_denied', "SELECT public.rosago_admin_operational_overview('',0)", ()))
                for label, statement, params in denials:
                    try:
                        with db.transaction():
                            db.execute('SET LOCAL ROLE authenticated')
                            db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
                            db.execute(statement, params)
                    except psycopg.errors.InsufficientPrivilege:
                        checks.append(('admin_' if is_admin else 'user_') + label)
                    else:
                        raise AssertionError('Denied operation unexpectedly allowed')
            with db.transaction():
                db.execute('SET LOCAL ROLE authenticated')
                db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (admin,))
                assert db.execute("SELECT public.rosago_admin_operational_overview('',0)").fetchone()[0]['users_total'] == 2
            checks.append('admin_overview_allowed')
            if '--provider-rpc' in sys.argv:
                stage = 'local_provider_rpc_draft'
                db.execute("""
                    CREATE TABLE auth.sessions(id uuid PRIMARY KEY,user_id uuid,not_after timestamptz);
                    CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS
                        $$ SELECT current_setting('request.jwt.claims',true)::jsonb $$;
                """, prepare=False)
                db.execute((ROOT / 'evaluation/auth-testing/provider_session_rpc.review.sql').read_text(encoding='utf-8'), prepare=False)
                session = 'd0000000-0000-4000-8000-000000000001'
                db.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)', (session,user))
                claims = {'sub':user,'session_id':session,'role':'authenticated',
                          'aud':'authenticated','iss':'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1','exp':4102444800}
                scenarios = [('current_session',claims,True),
                             ('foreign_subject_session',dict(claims,sub=admin),False),
                             ('wrong_issuer',dict(claims,iss='https://other.invalid/auth/v1'),False),
                             ('expired_claim',dict(claims,exp=1),False),
                             ('missing_session',dict(claims,session_id=''),False)]
                for label, candidate, expected in scenarios:
                    with db.transaction():
                        db.execute('SET LOCAL ROLE authenticated')
                        db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (candidate['sub'],))
                        db.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps(candidate),))
                        assert db.execute('SELECT public.rosago_provider_session_current()').fetchone()[0] is expected
                    checks.append('provider_rpc_'+label)
                db.execute("UPDATE auth.sessions SET not_after=now()-interval '1 second'")
                with db.transaction():
                    db.execute('SET LOCAL ROLE authenticated')
                    db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (user,))
                    db.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps(claims),))
                    assert db.execute('SELECT public.rosago_provider_session_current()').fetchone()[0] is False
                checks.append('provider_rpc_not_after_denied')
                db.execute('DELETE FROM auth.sessions')
                with db.transaction():
                    db.execute('SET LOCAL ROLE authenticated')
                    db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (user,))
                    db.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps(claims),))
                    assert db.execute('SELECT public.rosago_provider_session_current()').fetchone()[0] is False
                checks.append('provider_rpc_removed_session_denied')
                for role in ('anon','service_role'):
                    assert not db.execute("SELECT has_function_privilege(%s,'public.rosago_provider_session_current()','EXECUTE')", (role,)).fetchone()[0]
                checks.append('provider_rpc_ordinary_grants_restricted')
            assert db.execute('SELECT count(*) FROM public.places').fetchone()[0] == 2
            assert db.execute('SELECT count(*) FROM public.profiles').fetchone()[0] == 2
            assert db.execute('SELECT count(*) FROM public.admin_memberships').fetchone()[0] == 1
            result.update(checks=checks, checks_passed=len(checks), guarded_membership_rehearsal='passed')
        result.update(status='passed', owned_local_fixture_removed=True)
    except Exception as error:
        result.update(status='failed', stage=stage, error_class=type(error).__name__)
    name = 'provider-rpc-local-results.json' if '--provider-rpc' in sys.argv else 'account-role-local-results.json'
    output = ROOT / 'docs/production-readiness/remote-evaluation' / name
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
