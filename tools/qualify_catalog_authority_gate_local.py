"""New NULL-authority regression only; cached network-isolated PostgreSQL fixture."""
import hashlib
import json
import re
import secrets
import tempfile
import time
from pathlib import Path

from tools.qualify_catalog_migrations_local import command
from tools.local_destination_catalog import write_new

ROOT=Path(__file__).resolve().parents[1]


def gate(source):
    match=re.search(r"    IF pg_catalog.to_regprocedure\('public.rosago_provider_session_current\(\)'\) IS NULL THEN.*?(?=    -- After the caller-bound)",source,re.S)
    assert match,'Expected exact provider entry gate'
    return match.group(0)


def main():
    old=ROOT/'local_catalog/mapped_publication_guard.review.sql'
    new=ROOT/'local_catalog/mapped_publication_guard.authority-fail-closed.review.sql'
    old_gate,new_gate=gate(old.read_text()),gate(new.read_text())
    image=command('image','inspect','postgres:17','--format','{{.Id}}').stdout.strip()
    assert re.fullmatch(r'sha256:[a-f0-9]{64}',image)
    owned=None;checks=[]
    with tempfile.TemporaryDirectory(prefix='rosago-authority-gate-') as directory:
        env=Path(directory)/'fixture.env';env.write_text('POSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\n',encoding='utf-8')
        try:
            owned=command('run','--pull=never','--detach','--network','none','--env-file',str(env),image).stdout.strip()
            assert re.fullmatch(r'[a-f0-9]{64}',owned)
            deadline=time.monotonic()+25
            while command('exec',owned,'pg_isready','-U','postgres',check=False).returncode:
                if time.monotonic()>deadline:raise RuntimeError('Local PostgreSQL readiness timeout')
                time.sleep(.2)
            def sql(statement):
                return command('exec','-i',owned,'psql','-X','-U','postgres','-v','ON_ERROR_STOP=1','-At',input=statement).stdout
            sql("CREATE TABLE synthetic_gate_calls(n int); INSERT INTO synthetic_gate_calls VALUES(0);")
            for name,body in [('old_gate',old_gate),('new_gate',new_gate)]:
                sql('CREATE FUNCTION public.'+name+'() RETURNS void LANGUAGE plpgsql AS $f$ BEGIN\n'+body+
                    '\nUPDATE synthetic_gate_calls SET n=n+1; END; $f$;')
            # Missing helper must be denied before any delegated operation.
            sql("DO $$ BEGIN PERFORM public.new_gate(); RAISE EXCEPTION 'missing authority admitted'; EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;")
            checks.append('missing_helper_denied')
            sql("CREATE FUNCTION public.rosago_provider_session_current() RETURNS boolean LANGUAGE sql AS $$ SELECT NULLIF(current_setting('synthetic.current',true),'')::boolean $$;")
            for value in ('false',''):
                sql("SET synthetic.current='"+value+"'; DO $$ BEGIN PERFORM public.new_gate(); RAISE EXCEPTION 'unknown/denied authority admitted'; EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;")
                assert sql('SELECT n FROM synthetic_gate_calls;').strip()=='0'
                checks.append('false_denied_before_delegation' if value else 'null_denied_before_delegation')
            sql("SET synthetic.current=''; SELECT public.old_gate();")
            assert sql('SELECT n FROM synthetic_gate_calls;').strip()=='1'
            checks.append('old_null_fallthrough_reproduced')
            sql("SET synthetic.current='true'; SELECT public.new_gate();")
            assert sql('SELECT n FROM synthetic_gate_calls;').strip()=='2'
            checks.append('true_reaches_delegation_boundary')
        finally:
            if owned:command('rm','-f','-v',owned)
    result=dict(scope='Only extracted entry gate, native PostgreSQL17, synthetic helper/counter, network none; not full RPC or real provider qualification.',
        checks=checks,passed=len(checks),owned_fixture_removed=True,hosted_requests=0,
        sql_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (old,new)},
        full_rpc_requalified=False,auth_restore_replay_resolved=False,remote_deployment='NO-GO')
    write_new(ROOT/'local_catalog/catalog-authority-gate-local-results.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
