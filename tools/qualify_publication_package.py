"""Additional exact first-65 RPC tests inside the qualifier's disposable DB only."""
import json
import re

from tools.local_destination_catalog import read_json
from tools.prepare_production_publication import ROOT,literal


def qualify_package(sql,scalar,checks):
    folder=ROOT/'local_catalog/production-publication'
    plan=read_json(folder/'change-set.review.json')
    # Remove earlier synthetic test rows/ledger, retaining only synthetic Auth.
    sql("DROP FUNCTION public.rosago_admin_verify_destination_location(text,timestamptz,jsonb,text); DROP SCHEMA rosago_catalog_private CASCADE; DELETE FROM public.admin_destination_audit; DELETE FROM public.places;")
    legacy="'attraction','dining','shopping','nature','heritage','industrial','accommodation'"
    sql('BEGIN ISOLATION LEVEL SERIALIZABLE; DELETE FROM public.destination_categories WHERE key NOT IN ('+legacy+'); COMMIT;')
    sql('INSERT INTO public.places SELECT * FROM jsonb_populate_recordset(NULL::public.places,'+literal(plan['baseline_rows'])+');')
    sql("CREATE SCHEMA storage; CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean); CREATE TABLE storage.objects(bucket_id text,name text,metadata jsonb,PRIMARY KEY(bucket_id,name)); INSERT INTO storage.buckets VALUES('destination-images',true);")
    for image in plan['images']:
        sql("INSERT INTO storage.objects VALUES('destination-images','"+image['object_name']+"',"+
            literal(dict(size=image['bytes'],mimetype=image['mime_type']))+');')
    preparation=(folder/'prepare-cutover.review.sql').read_text(encoding='utf-8')
    blocked=sql(preparation,check=False)
    assert blocked.returncode and 'UNQUALIFIED_RELEASE' in blocked.stderr
    assert scalar("SELECT to_regnamespace('rosago_catalog_private') IS NULL;")=='t'
    checks.append('release_sql_guard_prevents_unapproved_hosted_style_application')
    def local_copy(text):
        result,count=re.subn(r'DO \$release_gate\$.*?\$release_gate\$;','',text,count=1,flags=re.S)
        assert count==1
        return result
    sql(local_copy(preparation))
    sql(local_copy((folder/'registry.review.sql').read_text(encoding='utf-8')))
    assert scalar("SET ROLE anon; SELECT count(*) FROM public.places;")=='35'
    checks.append('preparation_preserves_existing_public_visibility_until_atomic_cutover')
    admin='11111111-1111-4111-8111-111111111111';user='22222222-2222-4222-8222-222222222222'
    prefix="SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','"+admin+"',false);"
    call='SELECT public.rosago_admin_apply_first_catalog_batch();'
    denied=sql('SET ROLE anon;'+call,check=False);assert denied.returncode
    denied=sql("SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','"+user+"',false);"+call,check=False)
    assert denied.returncode and 'Admin access required' in denied.stderr
    assert scalar('SELECT count(*) FROM public.places')=='50'
    checks.append('first_batch_anon_and_ordinary_user_denied_without_changes')
    for state in ('false','unknown'):
        denied=sql(prefix+"SELECT set_config('rosago.fixture_provider_valid','"+state+"',false);"+call,check=False)
        assert denied.returncode and 'Current provider authority required' in denied.stderr
    checks.append('first_batch_false_and_null_provider_authority_denied')
    drift=sql("BEGIN; UPDATE public.places SET address=address||' changed' WHERE id='"+plan['baseline_rows'][0]['id']+"';"+prefix+call,check=False)
    assert drift.returncode and 'Catalog row drift' in drift.stderr
    checks.append('exact_baseline_drift_rejects_first_batch')
    missing=sql("BEGIN; DELETE FROM storage.objects WHERE name='"+plan['images'][0]['object_name']+"';"+prefix+call,check=False)
    assert missing.returncode and 'upload receipt/object missing' in missing.stderr
    checks.append('first_batch_rejects_missing_storage_receipt')
    failure=sql("BEGIN; ALTER TABLE public.admin_destination_audit ADD CONSTRAINT fixture_cutover_audit_failure CHECK(NOT(summary->'submitted_fields' ? 'coordinate_verification'));"+prefix+call,check=False)
    assert failure.returncode and 'fixture_cutover_audit_failure' in failure.stderr
    assert scalar('SELECT count(*) FROM public.places')=='50'
    assert scalar("SET ROLE anon; SELECT count(*) FROM public.places")=='35'
    assert scalar("SELECT count(*) FROM pg_constraint WHERE conname='places_verified_location_before_publication'")=='0'
    checks.append('mid_batch_failure_rolls_back_rows_audits_rls_and_public_visibility_atomically')
    receipt=json.loads(scalar(prefix+call).splitlines()[-1])
    assert len(receipt['records'])==65
    stats=json.loads(scalar("SELECT json_build_object('total',count(*),'published',count(*) FILTER(WHERE status='published'),'draft',count(*) FILTER(WHERE status='draft'),'archived',count(*) FILTER(WHERE status='archived')) FROM public.places;"))
    assert stats==dict(total=101,published=65,draft=23,archived=13)
    checks.append('exact_65_record_cutover_has_101_total_65_published_23_draft_13_archived')
    by_csv={r['csv_record']:r for r in receipt['records']}
    for row in plan['records']:
        actual=by_csv[row['csv_record']]
        if row['existing_id']:assert actual['id']==row['existing_id'] and actual['slug']==row['existing_slug']
        else:assert actual['slug'].startswith('destination-') and actual['id'] not in {r['id'] for r in plan['baseline_rows']}
        assert actual['image_url']==row['values']['image_url']
    checks.append('existing_14_ids_slugs_and_all_65_image_references_preserved_or_assigned_exactly')
    assert scalar("SET ROLE anon; SELECT count(*) FROM public.places")=='65'
    assert scalar("SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','"+user+"',false); SELECT count(*) FROM public.places;").splitlines()[-1]=='65'
    assert scalar(prefix+'SELECT count(*) FROM public.places;').splitlines()[-1]=='101'
    checks.append('published65_visible_to_user_and_anon_held_records_visible_only_to_admin')
    assert scalar("SELECT convalidated FROM pg_constraint WHERE conname='places_verified_location_before_publication'")=='t'
    assert scalar("SELECT count(*) FROM public.admin_destination_audit")=='295'
    checks.append('first_batch_validates_location_constraint_and_preserves_all_295_audit_events')
    denied=sql('SET ROLE authenticated; SELECT * FROM rosago_catalog_private.publication_batches;',check=False)
    assert denied.returncode
    duplicate=sql(prefix+call,check=False)
    assert duplicate.returncode and 'Batch already recorded' in duplicate.stderr
    assert scalar('SELECT count(*) FROM public.places')=='101'
    checks.append('private_receipt_denied_and_repeat_execution_cannot_duplicate_destinations')
    # Containment rollback uses the recorded live versions and never restores Auth.
    hold='SELECT public.rosago_admin_hold_first_catalog_batch();'
    denied=sql("SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','"+user+"',false);"+hold,check=False)
    assert denied.returncode and 'Admin access required' in denied.stderr
    denied=sql(prefix+"SELECT set_config('rosago.fixture_provider_valid','unknown',false);"+hold,check=False)
    assert denied.returncode and 'Current provider authority required' in denied.stderr
    first=receipt['records'][0]
    stale=sql("BEGIN; UPDATE public.places SET description=description||' changed' WHERE id='"+first['id']+"';"+prefix+hold,check=False)
    assert stale.returncode and 'Published record drift' in stale.stderr
    assert scalar("SELECT count(*) FROM public.places WHERE status='published'")=='65'
    checks.append('containment_rollback_rejects_nonadmin_unknown_authority_and_record_drift')
    held=json.loads(scalar(prefix+hold).splitlines()[-1]);assert held['held']==65 and held['deleted']==0
    assert scalar('SELECT count(*) FROM public.places')=='101'
    assert scalar("SET ROLE anon; SELECT count(*) FROM public.places")=='0'
    assert scalar("SELECT count(*) FROM public.places WHERE status='draft'")=='88'
    checks.append('containment_rollback_atomically_holds_65_without_deletes_or_auth_restore')
