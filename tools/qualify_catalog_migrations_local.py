"""Owned cached PostgreSQL container only, network disabled; synthetic qualification.

Never reads application credentials or connects to either Supabase project.
Draft baseline tokens are substituted only in memory using this synthetic DB.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / 'local_catalog/catalog_extension.review.sql'
GUARD = ROOT / 'local_catalog/mapped_publication_guard.review.sql'


def command(*args, input=None, check=True):
    result = subprocess.run(['docker', *args], input=input.encode('utf-8') if input is not None else None,
                            capture_output=True, timeout=40)
    result.stdout = result.stdout.decode('utf-8', errors='replace')
    result.stderr = result.stderr.decode('utf-8', errors='replace')
    if check and result.returncode:
        raise RuntimeError(result.stderr[-1200:])
    return result


def qualify(*, production_preflight=None, extension_path=None, guard_path=None, after_qualification=None):
    from pglast.parser import parse_sql_json, parse_plpgsql_json
    extension = (extension_path or EXTENSION).read_text(encoding='utf-8')
    selected_guard = guard_path or GUARD
    guard = selected_guard.read_text(encoding='utf-8')
    parse_sql_json(extension); parse_sql_json(guard)
    checks = ['both_review_sql_files_parse']
    clone_constraint_roundtrips=[]
    image = command('image', 'inspect', 'postgres:17', '--format', '{{.Id}}').stdout.strip()
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image)
    nonce = secrets.token_hex(6)
    name = 'rosago-catalog-qualification-' + nonce
    owned_container_id = None
    with tempfile.TemporaryDirectory(prefix='rosago-catalog-qualification-') as temporary:
        assert Path(temporary).resolve().parent == Path(tempfile.gettempdir()).resolve()
        envfile = Path(temporary) / 'postgres.env'
        envfile.write_text('POSTGRES_DB=rosago_catalog_lab\nPOSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n', encoding='utf-8')
        try:
            owned_container_id = command('run', '--pull=never', '--detach', '--name', name,
                '--network', 'none', '--label', 'rosago.catalog.qualification=' + nonce,
                '--env-file', str(envfile), image).stdout.strip()
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                pid_one = command('exec', name, 'cat', '/proc/1/comm', check=False)
                if pid_one.stdout.strip() == 'postgres' and command('exec', name, 'pg_isready', '-U', 'postgres', check=False).returncode == 0:
                    break
                time.sleep(.2)
            else:
                raise RuntimeError('Owned synthetic PostgreSQL did not start.')

            def sql(text, *, check=True):
                return command('exec', '-i', name, 'psql', '-U', 'postgres', '-d', 'rosago_catalog_lab',
                               '-v', 'ON_ERROR_STOP=1', '-X', '-q', '-A', '-t', input=text, check=check)

            def scalar(text):
                return sql(text).stdout.strip()

            bootstrap = """
                CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
                CREATE SCHEMA auth;
                CREATE TABLE auth.users(id uuid PRIMARY KEY,raw_user_meta_data jsonb DEFAULT '{}'::jsonb,email text,created_at timestamptz DEFAULT now());
                CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                $$ SELECT NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
                GRANT USAGE ON SCHEMA auth TO anon,authenticated;
                GRANT EXECUTE ON FUNCTION auth.uid() TO anon,authenticated;
            """
            if production_preflight:
                bootstrap += 'CREATE SCHEMA extensions; CREATE EXTENSION pgcrypto WITH SCHEMA extensions;\n'
                for migration in ('0001_profiles.sql','0002_places.sql','0003_trips.sql','0004_itinerary_foundation.sql',
                    '0005_itinerary_draft_lifecycle.sql','0006_itinerary_preference_extension.sql','0007_itinerary_preview_lifecycle.sql',
                    '0008_admin_authorization.sql','0009_admin_places_read.sql','0010_itinerary_preview_adjustment.sql',
                    '0011_places_tourism_metadata.sql','0012_admin_management.sql','0013_admin_destination_audit.sql'):
                    bootstrap += (ROOT/'migrations'/migration).read_text(encoding='utf-8')+'\n'
                bootstrap += (ROOT/'tools/admin_destination_photo_contract.sql').read_text(encoding='utf-8')+'\n'
                bootstrap += (ROOT/'migrations/0014_destination_environment.sql').read_text(encoding='utf-8')+'\n'
                sql(bootstrap)
                # Restore only checked definitions/constraints into this owned,
                # network-disabled clone. No production rows or credentials.
                from tools.prepare_catalog_from_preflight import function_body
                for function in production_preflight['functions']:
                    function_body(function)
                    function_identity=function['identity']
                    if not function_identity.startswith('public.'):function_identity='public.'+function_identity
                    sql(function['definition'].replace('\r','').rstrip()+';\n'+
                        'REVOKE ALL ON FUNCTION '+function_identity+' FROM PUBLIC,anon,authenticated,service_role;\n'+
                        ('GRANT EXECUTE ON FUNCTION '+function_identity+' TO authenticated;' if 'authenticated=X/' in function['acl'] else ''))
                names=scalar("SELECT string_agg(quote_ident(conname),',') FROM pg_constraint WHERE conrelid='public.places'::regclass AND contype='c';")
                for constraint in names.split(','):sql('ALTER TABLE public.places DROP CONSTRAINT '+constraint+';')
                for constraint in production_preflight['constraints']:
                    if constraint['definition'].startswith('CHECK'):
                        sql('ALTER TABLE public.places ADD CONSTRAINT "'+constraint['name']+'" '+constraint['definition']+';')
                checks.append('owner_export_function_definitions_acl_and_place_checks_reconstructed_locally')
            else:
                for migration in ('0002_places.sql','0011_places_tourism_metadata.sql','0008_admin_authorization.sql','0009_admin_places_read.sql',
                              '0012_admin_management.sql','0013_admin_destination_audit.sql'):
                    bootstrap += (ROOT / 'migrations' / migration).read_text(encoding='utf-8')
                bootstrap += 'ALTER TABLE public.places ADD COLUMN environment text;\n'
            baseline = (ROOT / 'migrations/0014_destination_environment.sql').read_text(encoding='utf-8')
            start = baseline.index('CREATE OR REPLACE FUNCTION public.rosago_admin_mutate_destination_unlogged(')
            end = baseline.index('$$;', baseline.index('AS $$', start)) + 3
            baseline = baseline[start:end].replace('BEGIN\n', "BEGIN\n    IF pg_catalog.current_setting('rosago.fixture_provider_valid',true)='false' THEN\n        RAISE EXCEPTION 'Synthetic provider validation rejected';\n    END IF;\n", 1)
            if not production_preflight:bootstrap += baseline
            interests = (ROOT / 'migrations/0004_itinerary_foundation.sql').read_text(encoding='utf-8')
            start = interests.index('CREATE FUNCTION public.rosago_itinerary_interests_valid(')
            end = interests.index('$$;', interests.index('AS $$', start)) + 3
            if not production_preflight:
                bootstrap += interests[start:end]
                sql(bootstrap)
            failure = sql(EXTENSION.read_text(encoding='utf-8'), check=False)
            assert failure.returncode and 'UNQUALIFIED' in failure.stderr
            assert scalar("SELECT to_regclass('public.destination_categories') IS NULL") == 't'
            checks.append('unqualified_draft_rejects_before_schema_changes')
            metadata = json.loads(scalar("""SELECT json_build_object(
                'mutation', (SELECT md5(replace(prosrc,chr(13),'')) FROM pg_proc WHERE oid='public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)'::regprocedure),
                'interests', (SELECT md5(replace(prosrc,chr(13),'')) FROM pg_proc WHERE oid='public.rosago_itinerary_interests_valid(text[])'::regprocedure),
                'constraint', (SELECT md5(pg_get_constraintdef(oid)) FROM pg_constraint WHERE conrelid='public.places'::regclass AND conname='places_category_check'))"""))
            qualified = extension
            if not production_preflight:
                for setting, key in [('expected_mutation_body_md5','mutation'), ('expected_interests_body_md5','interests'), ('expected_category_check_md5','constraint')]:
                    qualified, count = re.subn(r"(" + setting + r" constant text := )'UNQUALIFIED_CURRENT_PREFLIGHT_REQUIRED'", r"\g<1>'" + metadata[key] + "'", qualified)
                    assert count == 1
            if production_preflight:
                from tools.prepare_catalog_from_preflight import constraint_semantics
                for constraint in production_preflight['constraints']:
                    definition=scalar("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.places'::regclass AND conname='"+constraint['name']+"';")
                    if definition!=constraint['definition']:
                        if constraint_semantics(definition)!=constraint_semantics(constraint['definition']):
                            print(json.dumps(dict(clone_mismatch=constraint['name'],exported=constraint['definition'],local=definition)),flush=True)
                            raise AssertionError('Clone constraint meaning differs from owner export')
                        old=hashlib.md5(constraint['definition'].encode()).hexdigest();new=hashlib.md5(definition.encode()).hexdigest()
                        assert qualified.count("'"+old+"'")==1,'Unexpected guard fingerprint substitution scope'
                        qualified=qualified.replace("'"+old+"'","'"+new+"'",1)
                        clone_constraint_roundtrips.append(dict(name=constraint['name'],exported_hash=old,clone_hash=new,
                            reason='Equivalent AND association after PostgreSQL DDL roundtrip; local in-memory guard only, production SQL unchanged.'))
            # Only the in-memory local copy has synthetic baseline hashes.
            sql(qualified)
            checks.append('extension_executes_on_exact_synthetic_baseline')
            if not production_preflight:
                assert 'Synthetic provider validation rejected' in scalar("SELECT prosrc FROM pg_proc WHERE oid='public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)'::regprocedure")
                checks.append('existing_provider_entry_check_preserved')
            else:checks.append('actual_production_baseline_has_no_provider_guard_not_assumed_present')
            sql("BEGIN ISOLATION LEVEL SERIALIZABLE; INSERT INTO public.destination_categories VALUES ('specialty-coffee','Specialty Coffee','dining'); COMMIT;")
            cycle = sql("BEGIN ISOLATION LEVEL SERIALIZABLE; INSERT INTO public.destination_categories VALUES ('cycle-a','Cycle A',NULL),('cycle-b','Cycle B','cycle-a'); UPDATE public.destination_categories SET parent_key='cycle-b' WHERE key='cycle-a'; COMMIT;", check=False)
            assert cycle.returncode and 'cycle' in cycle.stderr.lower()
            checks.append('database_category_cycle_rejected_atomically')
            denied = sql("SET ROLE authenticated; INSERT INTO public.destination_categories VALUES ('bad','Bad',NULL);", check=False)
            assert denied.returncode
            checks.append('ordinary_roles_cannot_write_registry')

            failed_guard = sql(guard, check=False)
            assert failed_guard.returncode and 'UNQUALIFIED_HOSTED_PREFLIGHT' in failed_guard.stderr
            assert scalar("SELECT to_regnamespace('rosago_catalog_private') IS NULL") == 't'
            checks.append('unqualified_location_guard_rejects_without_side_effects')
            sql("INSERT INTO public.places(name,slug,description,category,address,latitude,longitude,status) VALUES ('Legacy Synthetic Published','legacy-unverified','Synthetic only','nature','Synthetic address',14.2,121.1,'published');")
            local_guard, count = re.subn(r'DO \$gate\$.*?\$gate\$;', '', guard, count=1, flags=re.S)
            assert count == 1
            sql(local_guard)
            checks.append('location_ledger_policy_and_rpc_execute_in_synthetic_database')
            admin = '11111111-1111-4111-8111-111111111111'
            normal = '22222222-2222-4222-8222-222222222222'
            sql(f"INSERT INTO auth.users VALUES ('{admin}'),('{normal}'); INSERT INTO public.admin_memberships(user_id) VALUES ('{admin}');")
            prefix = f"SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','{admin}',false);"
            values = "'{\"name\":\"Synthetic Coffee\",\"category\":\"specialty-coffee\",\"description\":\"Synthetic only\",\"address\":\"Synthetic address\",\"latitude\":14.25,\"longitude\":121.05,\"operating_days_raw\":\"Monday-Friday\",\"tourism_source\":\"synthetic.csv\",\"tourism_source_row\":2}'::jsonb"
            created = json.loads(scalar(prefix + "SELECT public.rosago_admin_mutate_destination('create',NULL,NULL," + values + ');').splitlines()[-1])
            slug = created['slug']
            def version():
                return scalar("SELECT updated_at::text FROM public.places WHERE slug='" + slug + "'")
            before = scalar("SELECT row_to_json(p) FROM public.places p WHERE slug='" + slug + "'")
            basic_values = "jsonb_build_object('name',name,'category',category,'description',description,'address',address,'latitude',latitude,'longitude',longitude)"
            payload = scalar("SELECT " + basic_values + " FROM public.places WHERE slug='" + slug + "'")
            payload_literal = "'" + payload.replace("'", "''") + "'::jsonb"
            unverified = sql(prefix + f"SELECT public.rosago_admin_mutate_destination('publish','{slug}','{version()}'::timestamptz,'{{}}'::jsonb);", check=False)
            assert unverified.returncode and 'places_verified_location_before_publication' in unverified.stderr
            checks.append('published_requires_approved_coordinate_evidence')
            missing = sql(prefix + f"SELECT public.rosago_admin_verify_destination_location('{slug}','{version()}'::timestamptz,{payload_literal},'Synthetic source');",check=False)
            assert missing.returncode and 'Provider-session authority unavailable' in missing.stderr
            checks.append('new_verification_rpc_fails_closed_when_provider_authority_missing')
            # Positive verification cases below require a synthetic authority.
            # This does not install or qualify a production provider mechanism.
            sql("CREATE FUNCTION public.rosago_provider_session_current() RETURNS boolean LANGUAGE sql STABLE SET search_path='' AS $$ SELECT CASE current_setting('rosago.fixture_provider_valid',true) WHEN 'unknown' THEN NULL WHEN 'false' THEN false ELSE true END $$; REVOKE ALL ON FUNCTION public.rosago_provider_session_current() FROM PUBLIC,anon,authenticated,service_role;")
            rejected = sql(prefix + "SELECT set_config('rosago.fixture_provider_valid','false',false);" +
                f"SELECT public.rosago_admin_verify_destination_location('{slug}','{version()}'::timestamptz,{payload_literal},'Synthetic verified source');", check=False)
            assert rejected.returncode and ('Synthetic provider validation rejected' in rejected.stderr or 'Current provider session required' in rejected.stderr)
            assert scalar('SELECT count(*) FROM rosago_catalog_private.location_verifications') == '0'
            checks.append('verification_delegates_fail_closed_provider_authority')
            if 'IS NOT TRUE THEN' in guard:
                before_unknown = scalar("SELECT row_to_json(p) FROM public.places p WHERE slug='" + slug + "'")
                rejected = sql(prefix + "SELECT set_config('rosago.fixture_provider_valid','unknown',false);" +
                    f"SELECT public.rosago_admin_verify_destination_location('{slug}','{version()}'::timestamptz,{payload_literal},'Synthetic unknown provider');", check=False)
                assert rejected.returncode and 'Current provider session required' in rejected.stderr
                assert scalar('SELECT count(*) FROM rosago_catalog_private.location_verifications') == '0'
                assert scalar("SELECT row_to_json(p) FROM public.places p WHERE slug='" + slug + "'") == before_unknown
                checks.append('full_verification_rpc_rejects_null_authority_without_edit_or_ledger_write')
            nonadmin_prefix = f"SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','{normal}',false);"
            rejected = sql(nonadmin_prefix + f"SELECT public.rosago_admin_verify_destination_location('{slug}','{version()}'::timestamptz,{payload_literal},'Synthetic source');", check=False)
            assert rejected.returncode and 'Admin access required' in rejected.stderr
            checks.append('ordinary_user_cannot_verify_a_destination')
            before_audit_failure = scalar("SELECT row_to_json(p) FROM public.places p WHERE slug='" + slug + "'")
            sql("ALTER TABLE public.admin_destination_audit ADD CONSTRAINT fixture_reject_verification CHECK (NOT(summary->'submitted_fields' ? 'coordinate_verification'));")
            rejected = sql(prefix + f"SELECT public.rosago_admin_verify_destination_location('{slug}','{version()}'::timestamptz,{payload_literal},'Synthetic verified source');", check=False)
            assert rejected.returncode and 'fixture_reject_verification' in rejected.stderr
            assert scalar('SELECT count(*) FROM rosago_catalog_private.location_verifications') == '0'
            assert scalar("SELECT row_to_json(p) FROM public.places p WHERE slug='" + slug + "'") == before_audit_failure
            sql('ALTER TABLE public.admin_destination_audit DROP CONSTRAINT fixture_reject_verification;')
            checks.append('audit_failure_rolls_back_verification_and_delegated_edit')
            sql(prefix + f"SELECT public.rosago_admin_verify_destination_location('{slug}','{version()}'::timestamptz,{payload_literal},'Synthetic verified source');")
            assert scalar("SELECT count(*) FROM public.admin_destination_audit WHERE summary->'submitted_fields' ? 'coordinate_verification'") == '1'
            checks.append('verification_is_recorded_in_existing_audit_history')
            assert scalar("SET ROLE anon; SELECT count(*) FROM public.places;") == '0'
            assert scalar(prefix + 'SELECT count(*) FROM public.places;').splitlines()[-1] == '2'
            checks.append('legacy_unverified_published_hidden_but_admin_visibility_preserved')
            checks.append('verified_draft_remains_hidden_from_public_readers')
            sql(prefix + f"SELECT public.rosago_admin_mutate_destination('publish','{slug}','{version()}'::timestamptz,'{{}}'::jsonb);")
            assert scalar("SET ROLE anon; SELECT count(*) FROM public.places;") == '1'
            assert scalar(nonadmin_prefix + 'SELECT count(*) FROM public.places;').splitlines()[-1] == '1'
            checks.append('verified_published_visible_to_anon_and_ordinary_user')
            denied = sql('SET ROLE authenticated; SELECT * FROM rosago_catalog_private.location_verifications;', check=False)
            assert denied.returncode
            denied = sql("SET ROLE anon; SELECT rosago_catalog_private.location_verified(gen_random_uuid(),'a','b',0,0);", check=False)
            assert denied.returncode
            checks.append('private_evidence_and_predicate_not_directly_accessible')
            moved = sql("UPDATE public.places SET latitude=14.26 WHERE slug='" + slug + "';", check=False)
            assert moved.returncode and 'places_verified_location_before_publication' in moved.stderr
            checks.append('published_coordinate_edits_cannot_reuse_stale_evidence')
            duplicate = sql("INSERT INTO public.places(name,slug,description,category,address) VALUES ('Synthetic   Coffee','duplicate-fixture','Synthetic','nature','Synthetic');", check=False)
            assert duplicate.returncode and 'places_catalog_name_identity_unique' in duplicate.stderr
            checks.append('database_normalized_name_collision_rejected')
            with ThreadPoolExecutor(max_workers=1) as executor:
                first = executor.submit(sql, "BEGIN; SET LOCAL application_name='catalog_duplicate_first'; INSERT INTO public.places(name,slug,description,category,address) VALUES ('Concurrent Fixture','concurrent-one','Synthetic','nature','Synthetic'); SELECT pg_sleep(1); COMMIT;")
                for _ in range(30):
                    if scalar("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='catalog_duplicate_first' AND wait_event='PgSleep')") == 't':
                        break
                    time.sleep(.02)
                else: raise AssertionError('Concurrent duplicate writer did not reach barrier')
                second = sql("INSERT INTO public.places(name,slug,description,category,address) VALUES ('Concurrent   Fixture','concurrent-two','Synthetic','nature','Synthetic');", check=False)
                first.result()
                assert second.returncode and 'places_catalog_name_identity_unique' in second.stderr
            checks.append('two_process_concurrent_duplicate_creation_rejected')
            # The database guard handles concurrent writes; full Python Unicode
            # matching is still mandatory in the operator review/import plan.
            sql("BEGIN ISOLATION LEVEL SERIALIZABLE; INSERT INTO public.destination_categories VALUES ('parallel-a','Parallel A',NULL),('parallel-b','Parallel B',NULL); COMMIT;")
            with ThreadPoolExecutor(max_workers=1) as executor:
                first = executor.submit(sql, "BEGIN ISOLATION LEVEL SERIALIZABLE; SET LOCAL application_name='catalog_cycle_first'; UPDATE public.destination_categories SET parent_key='parallel-b' WHERE key='parallel-a'; SELECT pg_sleep(1); COMMIT;", check=False)
                for _ in range(30):
                    if scalar("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='catalog_cycle_first' AND wait_event='PgSleep')") == 't': break
                    time.sleep(.02)
                else: raise AssertionError('Concurrent registry writer did not reach barrier')
                second = sql("BEGIN ISOLATION LEVEL SERIALIZABLE; UPDATE public.destination_categories SET parent_key='parallel-a' WHERE key='parallel-b'; COMMIT;", check=False)
                one = first.result()
                assert one.returncode or second.returncode
                assert scalar("SELECT NOT EXISTS(SELECT 1 FROM public.destination_categories a JOIN public.destination_categories b ON a.parent_key=b.key AND b.parent_key=a.key)") == 't'
            checks.append('serializable_concurrent_category_cycle_cannot_commit')
            sql(prefix + f"SELECT public.rosago_admin_mutate_destination('draft','{slug}','{version()}'::timestamptz,'{{}}'::jsonb);")
            sql("UPDATE public.places SET latitude=14.26 WHERE slug='" + slug + "';")
            stale = sql(prefix + f"SELECT public.rosago_admin_mutate_destination('publish','{slug}','{version()}'::timestamptz,'{{}}'::jsonb);", check=False)
            assert stale.returncode
            checks.append('draft_point_change_requires_new_verification')
            blocked_validation = sql('ALTER TABLE public.places VALIDATE CONSTRAINT places_verified_location_before_publication;', check=False)
            assert blocked_validation.returncode
            legacy_version = scalar("SELECT updated_at::text FROM public.places WHERE slug='legacy-unverified';")
            sql(prefix + f"SELECT public.rosago_admin_mutate_destination('draft','legacy-unverified','{legacy_version}'::timestamptz,'{{}}'::jsonb);")
            sql('ALTER TABLE public.places VALIDATE CONSTRAINT places_verified_location_before_publication;')
            checks.append('full_constraint_validation_requires_approved_legacy_cutover')
            if after_qualification is not None:after_qualification(sql,scalar,checks)
            qualified_hash = hashlib.sha256(qualified.encode()).hexdigest()
        finally:
            if owned_container_id:
                info = json.loads(command('inspect', name).stdout)[0]
                assert info['Id'] == owned_container_id and info['Config']['Labels']['rosago.catalog.qualification'] == nonce
                assert info['HostConfig']['NetworkMode'] == 'none' and not info['HostConfig']['PortBindings']
                command('rm', '--force', '--volumes', name)
    inputs=(EXTENSION,selected_guard,extension_path) if extension_path else (EXTENSION,selected_guard)
    return dict(scope='Owned cached PostgreSQL, network none, no exposed ports, synthetic Auth/roles; '+('public destination export used by added package tests.' if after_qualification else 'synthetic destinations only.'),
        owner_operated_preflight_validated=bool(production_preflight), hosted_migration_qualified=False, hosted_requests=0,
        owner_export_baseline_used=bool(production_preflight),
        synthetic_provider_stub_used_for_positive_verification_cases=True,
        clone_constraint_roundtrip_hash_substitutions=clone_constraint_roundtrips,
        checks_passed=checks, check_count=len(checks), local_sql_variant_sha256=qualified_hash,
        reviewed_draft_hashes={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='local_catalog/catalog-local-postgres-qualification-v4.json')
    parser.add_argument('--production-preflight',action='store_true')
    parser.add_argument('--guard',default=str(GUARD))
    parser.add_argument('--publication-package',action='store_true')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    assert output.parent == (ROOT / 'local_catalog').resolve() and output.name.endswith('.json')
    preflight=None
    if args.production_preflight:
        from tools.prepare_catalog_from_preflight import validate
        from tools.local_destination_catalog import read_json
        preflight=validate(read_json(ROOT/'local_catalog/production-catalog-schema-preflight.json'))
    callback=None
    if args.publication_package:
        from tools.qualify_publication_package import qualify_package
        callback=qualify_package
    result = qualify(production_preflight=preflight,
        extension_path=ROOT/'local_catalog/catalog_extension.production-bound-v2.review.sql' if preflight else None,
        guard_path=Path(args.guard).resolve(),after_qualification=callback)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result, indent=2))
