"""Qualify ONLY a disposable network-none PostgreSQL clone; never hosted I/O.

Positive full-98 cases use the seven EXISTING unapproved content proposals with
synthetic approval flags in memory. They do not approve or change review files.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import secrets
import tempfile
import time

from tools.prepare_owner_catalog98 import ROOT, OUTPUT, literal, original_hashes, digest
from tools.local_destination_catalog import read_json
from tools.prepare_catalog_from_preflight import validate, constraint_semantics
from tools.qualify_catalog_migrations_local import command


def run():
    preserved=original_hashes();checks=[];owned=None
    manifest=read_json(OUTPUT/'manifest.json')
    for entry in manifest['files']:assert digest(OUTPUT/entry['file'])==entry['sha256']
    plan=read_json(OUTPUT/'change-set.review.json')
    proposed=read_json(OUTPUT/'change-set.with-proposed-resolutions.review.json')
    schema=validate(read_json(ROOT/'local_catalog/production-catalog-latest-schema-preflight-corrected.json'))
    from pglast import parse_sql
    for path in OUTPUT.glob('*.sql'):parse_sql(path.read_text(encoding='utf-8'))
    checks.append('all_owner_sql_variants_parse')
    with tempfile.TemporaryDirectory(prefix='rosago-owner98-') as temp:
        env=Path(temp)/'postgres.env';env.write_text('POSTGRES_DB=rosago_owner98\nPOSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\n')
        try:
            owned=command('run','--pull=never','--detach','--network','none','--label','rosago.owner98.local=true',
                '--env-file',str(env),'postgres:17').stdout.strip()
            assert re.fullmatch('[a-f0-9]{64}',owned)
            def sql(statement,check=True):
                return command('exec','-i','-e','PGOPTIONS=-c statement_timeout=10000 -c lock_timeout=2000',owned,
                    'psql','-X','-q','-At','-U','postgres','-d','rosago_owner98','-v','ON_ERROR_STOP=1',input=statement,check=check)
            def scalar(statement):return sql(statement).stdout.strip()
            limit=time.monotonic()+30
            while sql('SELECT 1',False).returncode:
                if time.monotonic()>limit:raise RuntimeError('Owned PostgreSQL readiness timeout')
                time.sleep(.15)
            sql("""CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role BYPASSRLS;
                CREATE SCHEMA auth;CREATE SCHEMA extensions;CREATE EXTENSION pgcrypto SCHEMA extensions;
                CREATE TABLE auth.users(id uuid PRIMARY KEY,raw_user_meta_data jsonb DEFAULT '{}',email text,created_at timestamptz DEFAULT now());
                CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                  $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
                GRANT USAGE ON SCHEMA auth TO anon,authenticated;
                GRANT EXECUTE ON FUNCTION auth.uid() TO anon,authenticated;
            """)
            migrations=['0001_profiles.sql','0002_places.sql','0003_trips.sql','0004_itinerary_foundation.sql',
                '0005_itinerary_draft_lifecycle.sql','0006_itinerary_preference_extension.sql','0007_itinerary_preview_lifecycle.sql',
                '0008_admin_authorization.sql','0009_admin_places_read.sql','0010_itinerary_preview_adjustment.sql',
                '0011_places_tourism_metadata.sql','0012_admin_management.sql','0013_admin_destination_audit.sql']
            for name in migrations:sql((ROOT/'migrations'/name).read_text(encoding='utf-8'))
            sql((ROOT/'tools/admin_destination_photo_contract.sql').read_text(encoding='utf-8'))
            sql((ROOT/'migrations/0014_destination_environment.sql').read_text(encoding='utf-8'))
            for f in schema['functions']:
                identity=f['identity'];identity=identity if identity.startswith('public.') else 'public.'+identity
                sql(f['definition'].replace('\r','')+'; REVOKE ALL ON FUNCTION '+identity+' FROM PUBLIC,anon,authenticated,service_role;'+
                    ('GRANT EXECUTE ON FUNCTION '+identity+' TO authenticated;' if 'authenticated=X/' in f['acl'] else ''))
            names=scalar("SELECT string_agg(quote_ident(conname),',') FROM pg_constraint WHERE conrelid='public.places'::regclass AND contype='c'")
            for name in names.split(','):sql('ALTER TABLE public.places DROP CONSTRAINT '+name)
            for c in schema['constraints']:
                if c['definition'].startswith('CHECK'):sql('ALTER TABLE public.places ADD CONSTRAINT '+c['name']+' '+c['definition'])
            sql('INSERT INTO public.places SELECT * FROM jsonb_populate_recordset(NULL::public.places,'+literal(plan['baseline_rows'])+')')
            admin='11111111-1111-4111-8111-111111111111';user='22222222-2222-4222-8222-222222222222'
            for n,uid in enumerate((admin,user,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444')):
                sql(f"INSERT INTO auth.users(id,email) VALUES('{uid}','fixture{n}@example.invalid')")
            sql(f"INSERT INTO public.admin_memberships(user_id) VALUES('{admin}')")
            sql("INSERT INTO public.admin_destination_audit(actor_id,action,destination_id,summary) VALUES('"+
                admin+"','edit','"+plan['baseline_rows'][0]['id']+"','{\"fixture\":\"pre-existing audit\"}')")
            checkpoint_sql="""SELECT json_build_object('auth',(SELECT count(*) FROM auth.users),
                'profiles',(SELECT count(*) FROM public.profiles),'members',(SELECT count(*) FROM public.admin_memberships),
                'audit',(SELECT count(*) FROM public.admin_destination_audit))"""
            checkpoints=scalar(checkpoint_sql)
            audit_before=scalar("SELECT md5(jsonb_agg(to_jsonb(a) ORDER BY id)::text) FROM public.admin_destination_audit a")
            source=(OUTPUT/'schema.review.sql').read_text(encoding='utf-8')
            assert sql(source,False).returncode
            assert scalar("SELECT to_regclass('public.destination_categories') IS NULL")=='t'
            checks.append('schema_release_gate_rejects_without_side_effects')
            local=source.replace("DO $owner98_install_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_OWNER98_SCHEMA'; END $owner98_install_gate$;",'')
            roundtrips=[]
            for c in schema['constraints']:
                actual=scalar("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.places'::regclass AND conname='"+c['name']+"'")
                if actual!=c['definition']:
                    assert constraint_semantics(actual)==constraint_semantics(c['definition'])
                    local=local.replace(hashlib.md5(c['definition'].encode()).hexdigest(),hashlib.md5(actual.encode()).hexdigest())
                    roundtrips.append(c['name'])
            sql(local)
            checks.append('catalog_schema_preserves_mandatory_constraints_and_existing_admin_wrapper')
            assert scalar("SELECT to_regprocedure('public.rosago_provider_session_current()') IS NULL")=='t'
            checks.append('no_provider_helper_or_synthetic_provider_allow_stub_required')
            sql("CREATE SCHEMA storage;CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean);"
                "CREATE TABLE storage.objects(bucket_id text,name text,metadata jsonb,PRIMARY KEY(bucket_id,name));"
                "INSERT INTO storage.buckets VALUES('destination-images',true)")
            for variant in ('apply.review.sql','apply.with-proposed-resolutions.review.sql'):
                blocked=sql((OUTPUT/variant).read_text(encoding='utf-8'),False)
                assert blocked.returncode and 'UNAPPROVED_OWNER98_INSTALL' in blocked.stderr
                assert scalar("SELECT to_regnamespace('rosago_owner_catalog98') IS NULL")=='t'
            checks.append('both_apply_variants_gated_before_private_schema_creation')
            def installer(text):return text.replace("DO $owner98_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_OWNER98_INSTALL'; END $owner98_gate$;",'')
            sql(installer((OUTPUT/'apply.review.sql').read_text(encoding='utf-8')))
            call='BEGIN ISOLATION LEVEL SERIALIZABLE; SELECT rosago_owner_catalog98.apply(); COMMIT;'
            blocked=sql(call,False);assert blocked.returncode and 'Mandatory Draft fields unresolved' in blocked.stderr
            assert scalar('SELECT count(*) FROM public.places')=='50'
            assert scalar('SELECT count(*) FROM rosago_owner_catalog98.events')=='0'
            checks.append('as_received_all98_plan_rejects_seven_missing_mandatory_records_atomically')
            for role in ('anon','authenticated','service_role'):
                assert sql('SET ROLE '+role+';'+call,False).returncode
            assert sql(f"SET ROLE authenticated; SET request.jwt.claim.sub='{admin}';"+call,False).returncode
            checks.append('anon_authenticated_and_service_role_cannot_invoke_owner_batch')
            conditional=deepcopy(proposed)
            template=(ROOT/'tools/owner_catalog98/apply.sql.in').read_text(encoding='utf-8')
            definition=template[template.index('CREATE FUNCTION rosago_owner_catalog98.apply()'):template.index('ALTER FUNCTION rosago_owner_catalog98.apply()')]
            def replace_plan(candidate):
                sql(definition.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace('@PLAN@',literal(candidate)))
            replace_plan(conditional)
            blocked=sql(call,False);assert blocked.returncode and 'UNAPPROVED_OWNER98_PLAN' in blocked.stderr
            checks.append('proposed_descriptions_categories_do_not_imply_owner_approval')
            for key in ('approved','alias_mappings_approved','registry_approved','existing_auth_risk_acknowledged'):conditional[key]=True
            replace_plan(conditional)
            assert sql(call,False).returncode
            assert scalar('SELECT count(*) FROM public.places')=='50'
            checks.append('missing_storage_metadata_and_readback_receipts_reject_atomically')
            for image in conditional['images']:
                sql("INSERT INTO storage.objects VALUES('destination-images','"+image['object_name']+"',"+
                    literal(dict(size=image['bytes'],mimetype=image['mime_type']))+')')
            assert sql(call,False).returncode
            checks.append('storage_metadata_alone_cannot_substitute_for_upload_hash_receipts')
            for image in conditional['images']:
                sql("INSERT INTO rosago_owner_catalog98.upload_receipts(object_name,sha256,bytes,mime_type,verified_by) VALUES('"+
                    image['object_name']+"','"+image['expected_upload_sha256']+"',"+str(image['bytes'])+",'"+image['mime_type']+"','postgres')")
            changed=sql("BEGIN ISOLATION LEVEL SERIALIZABLE;UPDATE public.places SET address=address||' changed' WHERE id='"+
                plan['baseline_rows'][0]['id']+"'; SELECT rosago_owner_catalog98.apply(); COMMIT;",False)
            assert changed.returncode and 'baseline row drift' in changed.stderr
            checks.append('baseline_drift_is_rejected_before_catalog_changes')
            failure=sql("BEGIN ISOLATION LEVEL SERIALIZABLE;ALTER TABLE rosago_owner_catalog98.events ADD CONSTRAINT fixture_audit_failure CHECK(ordinal<25); SELECT rosago_owner_catalog98.apply(); COMMIT;",False)
            assert failure.returncode and 'fixture_audit_failure' in failure.stderr
            assert scalar('SELECT count(*) FROM public.places')=='50'
            assert scalar('SELECT count(*) FROM rosago_owner_catalog98.events')=='0'
            assert scalar("SELECT count(*) FROM pg_policies WHERE policyname LIKE 'places_owner98%'")=='0'
            checks.append('mid_batch_audit_failure_rolls_back_rows_policies_evidence_and_taxonomy')
            assert scalar('SELECT auth.uid() IS NULL')=='t'
            receipt=json.loads(sql(call).stdout)
            assert receipt['counts']==dict(total=120,published=65,draft=42,archived=13)
            checks.append('conditional_full98_success_without_fake_jwt_or_web_admin_session')
            assert scalar("SELECT count(*) FROM rosago_owner_catalog98.events WHERE csv_record IS NOT NULL")=='98'
            assert scalar('SELECT count(*) FROM rosago_owner_catalog98.events')=='105'
            assert scalar("SELECT count(*) FROM rosago_owner_catalog98.events WHERE operator_name<>'postgres'")=='0'
            assert scalar('SELECT count(*) FROM public.admin_destination_audit')=='1'
            assert scalar("SELECT md5(jsonb_agg(to_jsonb(a) ORDER BY id)::text) FROM public.admin_destination_audit a")==audit_before
            checks.append('truthful_operator_audit_has_105_events_and_preserves_admin_history')
            rows=json.loads(scalar('SELECT json_agg(p ORDER BY id) FROM public.places p'))
            by_id={r['id']:r for r in rows}
            for r in conditional['records']:
                actual=by_id[r['id']];assert actual['slug']==r['slug'] and actual['status']==r['status']
                assert all(actual[k]==v for k,v in r['values'].items())
            checks.append('all_98_exact_fields_ids_slugs_images_and_65_33_statuses_match')
            for old in plan['baseline_rows']:
                if old['status']!='published':assert {k:v for k,v in by_id[old['id']].items() if k!='operating_days_raw'}==old
            checks.append('all_13_archived_and_two_original_drafts_unchanged')
            for role,uid,count in [('anon',None,65),('authenticated',user,65),('authenticated',admin,120)]:
                prefix='SET ROLE '+role+';'+(f"SET request.jwt.claim.sub='{uid}';" if uid else '')
                assert scalar(prefix+'SELECT count(*) FROM public.places')==str(count)
                if uid!=admin:assert scalar(prefix+"SELECT count(*) FROM public.places WHERE status<>'published'")=='0'
            checks.append('all_33_csv_drafts_hidden_from_anon_and_ordinary_user_but_admin_sees_120')
            for role in ('anon','authenticated','service_role'):
                for table in ('events','batches','upload_receipts','verified_locations'):
                    assert sql('SET ROLE '+role+'; SELECT * FROM rosago_owner_catalog98.'+table,False).returncode
            checks.append('private_audit_backup_receipts_and_location_data_denied_to_api_roles')
            published=next(r for r in conditional['records'] if r['status']=='published')
            invalid=sql("UPDATE public.places SET latitude=latitude+0.001 WHERE id='"+published['id']+"'",False)
            assert invalid.returncode and 'places_owner98_verified_publication' in invalid.stderr
            checks.append('published_coordinate_mutation_cannot_reuse_stale_location_evidence')
            draft=next(r for r in conditional['records'] if r['status']=='draft' and r['values']['latitude'] is None)
            assert by_id[draft['id']]['longitude'] is None
            prefix=f"SET ROLE authenticated;SET request.jwt.claim.sub='{admin}';"
            values={k:draft['values'][k] for k in ('name','category','description','address','latitude','longitude')}
            # Edit in a rolled-back test transaction so containment evidence remains exact.
            edit=sql('BEGIN;'+prefix+"SELECT public.rosago_admin_mutate_destination('edit','"+draft['slug']+"','"+
                by_id[draft['id']]['updated_at']+"',"+literal({**values,'description':values['description']+' Reviewed.'})+");ROLLBACK;")
            assert edit.returncode==0
            checks.append('existing_audited_admin_edit_accepts_draft_with_missing_coordinates')
            promote=sql(prefix+"SELECT public.rosago_admin_mutate_destination('publish','"+draft['slug']+"','"+
                by_id[draft['id']]['updated_at']+"','{}')",False)
            assert promote.returncode and 'places_owner98_verified_publication' in promote.stderr
            checks.append('ordinary_admin_publish_cannot_promote_unverified_draft')
            duplicate=sql(call,False);assert duplicate.returncode and 'already recorded' in duplicate.stderr
            checks.append('repeat_owner_application_cannot_duplicate_destinations')
            bad=sql("INSERT INTO public.places(id,name,slug,category,description,address,status) SELECT gen_random_uuid(),name,'fixture-duplicate',category,description,address,'draft' FROM public.places LIMIT 1",False)
            assert bad.returncode and 'places_catalog_name_identity_unique' in bad.stderr
            checks.append('database_normalized_name_collision_rejected')
            for field in ('description','category'):
                assert sql("UPDATE public.places SET "+field+"=NULL WHERE id='"+draft['id']+"'",False).returncode
            checks.append('draft_not_null_description_and_category_constraints_remain_enforced')
            rollback=(OUTPUT/'rollback.review.sql').read_text(encoding='utf-8')
            assert sql(rollback,False).returncode
            sql(rollback.replace("DO $owner98_rollback_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_OWNER98_CONTAINMENT'; END $owner98_rollback_gate$;",''))
            for role in ('anon','authenticated','service_role'):
                assert sql('SET ROLE '+role+'; BEGIN ISOLATION LEVEL SERIALIZABLE; SELECT rosago_owner_catalog98.contain(); COMMIT;',False).returncode
            checks.append('containment_is_gated_and_owner_only')
            drift=sql("BEGIN ISOLATION LEVEL SERIALIZABLE;UPDATE public.places SET description=description||' changed' WHERE id='"+published['id']+"'; SELECT rosago_owner_catalog98.contain(); COMMIT;",False)
            assert drift.returncode and 'Post-publication drift' in drift.stderr
            assert scalar("SELECT count(*) FROM public.places WHERE status='published'")=='65'
            checks.append('containment_rejects_drift_without_partial_status_changes')
            stats=json.loads(scalar('BEGIN ISOLATION LEVEL SERIALIZABLE; SELECT rosago_owner_catalog98.contain(); COMMIT;'))
            assert stats==dict(published=0,draft=107,archived=13,total=120,deleted=0,images_deleted=0)
            assert scalar('SET ROLE anon;SELECT count(*) FROM public.places')=='0'
            assert scalar(f"SET ROLE authenticated;SET request.jwt.claim.sub='{admin}';SELECT count(*) FROM public.places")=='120'
            checks.append('containment_retains_all_120_rows_images_and_archives_while_hiding_all_publications')
            after=scalar(checkpoint_sql)
            assert json.loads(after)==json.loads(checkpoints)
            checks.append('synthetic_accounts_profiles_membership_and_existing_admin_audit_unchanged')
            assert json.loads(scalar((OUTPUT/'postflight.readonly.sql').read_text(encoding='utf-8')))['counts']['total']==120
            assert json.loads(scalar((OUTPUT/'preflight.readonly.sql').read_text(encoding='utf-8')))['transaction_read_only']=='on'
            checks.append('owner_preflight_and_postflight_helpers_execute_read_only')
        finally:
            if owned:
                info=json.loads(command('inspect',owned).stdout)[0]
                assert info['Id']==owned and info['Config']['Labels']['rosago.owner98.local']=='true'
                command('rm','-f','-v',owned)
    assert original_hashes()==preserved
    result=dict(checks_passed=checks,check_count=len(checks),original_package_preserved=True,
        scope='Owned network-none PostgreSQL17; production public-destination snapshot and captured schema; synthetic Auth identities and Storage metadata/receipts.',
        positive_full98_uses_unapproved_existing_seven_proposals=True,actual_content_decisions_approved=False,
        provider_helper_installed_or_stubbed=False,hosted_requests=0,live_signins=0,uploads=0,
        owned_container_removed=True,hosted_application_qualified=False,remote_deployment='NO-GO',
        local_constraint_roundtrip_names=roundtrips,review_sql_sha256={p.name:digest(p) for p in OUTPUT.glob('*.sql')})
    (OUTPUT/'qualification-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':run()
