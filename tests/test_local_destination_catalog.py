"""Synthetic offline identity/planning checks. Never connect or execute SQL."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import csv
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from tools import local_destination_catalog as catalog

NOW = datetime(2026,11,8,1,tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def row(index=1, **changes):
    return dict(id=f'11111111-1111-4111-8111-{index:012d}',slug=f'fixture-{index}',
        name=f'Synthetic destination {index}',description='Offline fixture only.',category='nature',
        address='Synthetic address',latitude=None,longitude=None,image_url=None,status='draft',
        created_at='2026-01-01T00:00:00Z',updated_at='2026-11-08T00:00:00Z',
        tourism_type=None,tourism_category=None,tourism_opening_hours_raw=None,
        tourism_closing_hours_raw=None,tourism_hours_status=None,tourism_source=None,
        tourism_source_row=None,environment=None) | changes


def snapshot(rows=None):
    rows = rows if rows is not None else [row(1,status='published'),row(2),row(3,status='archived')]
    return dict(schema_version=1,project_ref=catalog.PROJECT,table='public.places',
        scope='all_publication_statuses',all_statuses_verified=True,authorization_ref='synthetic-offline-test-only',
        exported_at=NOW.isoformat(),row_count=len(rows),
        status_counts={s:sum(r['status']==s for r in rows) for s in catalog.STATUSES},
        rows_sha256=catalog.rows_hash(rows),rows=rows)


class LocalCatalogTests(unittest.TestCase):
    def setUp(self):
        for target,name in ((socket,'create_connection'),(socket.socket,'connect')):
            guard=patch.object(target,name,side_effect=AssertionError('Network forbidden.'))
            mock=guard.start();self.addCleanup(guard.stop);self.addCleanup(mock.assert_not_called)

    def test_initialization_retains_all_statuses_and_full_records(self):
        source=snapshot();before=deepcopy(source)
        result=catalog.initialize(source,now=NOW)
        self.assertEqual(result['records'],source['rows'])
        self.assertEqual(result['new_records'],[])
        self.assertEqual(source,before)
        result['records'][0]['name']='Edited fixture'
        self.assertEqual(source,before)

    def test_matching_uuid_is_update_with_version_and_never_creation(self):
        source=snapshot();desired=catalog.initialize(source,now=NOW)
        desired['records'][0]['description']='Updated local draft description.'
        result=catalog.plan_changes(source,desired,now=NOW)
        self.assertEqual(len(result['updates']),1)
        self.assertEqual(result['updates'][0]['id'],source['rows'][0]['id'])
        self.assertEqual(result['updates'][0]['expected_updated_at'],source['rows'][0]['updated_at'])
        self.assertEqual(result['proposed_new_drafts'],[])
        self.assertFalse(result['executable']);self.assertEqual(result['hosted_changes'],0)

    def test_omissions_preserve_rows_and_still_participate_in_duplicate_checks(self):
        source=snapshot();desired=catalog.initialize(source,now=NOW)
        desired['records']=[]
        result=catalog.plan_changes(source,desired,now=NOW)
        self.assertEqual(len(result['omitted_records_preserved']),3)
        self.assertEqual(result['automatic_deletes'],[]);self.assertEqual(result['automatic_archives'],[])
        new={k:v for k,v in row(9,name='SYNTHETIC destination 2').items() if k in catalog.NEW_FIELDS}
        desired['new_records']=[new]
        with self.assertRaises(catalog.CatalogError):catalog.plan_changes(source,desired,now=NOW)

    def test_slug_and_normalized_name_collisions_are_blocked(self):
        self.assertEqual(catalog.normalized_name("People's Caf\u00e9 & Park"),catalog.normalized_name('PEOPLES CAFE and PARK'))
        source=snapshot()
        for changes in ({'slug':'fixture-2'},{'name':'Synthetic--destination 2'}):
            desired=catalog.initialize(source,now=NOW)
            desired['new_records']=[{k:v for k,v in row(9,**changes).items() if k in catalog.NEW_FIELDS}]
            with self.subTest(changes=changes),self.assertRaises(catalog.CatalogError):catalog.plan_changes(source,desired,now=NOW)
        for changes in ({'id':row(1)['id']},{'slug':'fixture-1'},{'name':'SYNTHETIC DESTINATION 1'}):
            with self.subTest(changes=changes),self.assertRaises(catalog.CatalogError):
                catalog.initialize(snapshot([row(1),row(2,**changes)]),now=NOW)

    def test_unknown_uuid_identity_and_baseline_changes_never_become_new_records(self):
        source=snapshot()
        for field,value in (('id',row(99)['id']),('slug','renamed-identity'),('created_at',NOW.isoformat()),
                            ('updated_at',NOW.isoformat())):
            desired=catalog.initialize(source,now=NOW);desired['records'][0][field]=value
            with self.subTest(field=field),self.assertRaises(catalog.CatalogError):catalog.plan_changes(source,desired,now=NOW)
        desired=catalog.initialize(source,now=NOW);desired['snapshot_rows_sha256']='0'*64
        with self.assertRaises(catalog.CatalogError):catalog.plan_changes(source,desired,now=NOW)

    def test_new_drafts_are_explicit_and_collisions_between_new_rows_stop(self):
        source=snapshot();desired=catalog.initialize(source,now=NOW)
        new={k:v for k,v in row(9).items() if k in catalog.NEW_FIELDS}
        desired['new_records']=[new]
        result=catalog.plan_changes(source,desired,now=NOW)
        self.assertEqual(result['updates'],[])
        self.assertTrue(result['proposed_new_drafts'][0]['requires_server_assigned_identity'])
        desired['new_records'].append(deepcopy(new))
        with self.assertRaises(catalog.CatalogError):catalog.plan_changes(source,desired,now=NOW)
        desired['new_records']=[new|{'status':'published'}]
        with self.assertRaises(catalog.CatalogError):catalog.plan_changes(source,desired,now=NOW)

    def test_metadata_counts_hash_freshness_and_target_fail_closed(self):
        for changes in ({'project_ref':'brnkigrrqdrywahvcbvc'},{'table':'auth.users'},
                        {'scope':'published_only'},{'all_statuses_verified':False},{'authorization_ref':''},
                        {'row_count':True},{'row_count':2},{'rows_sha256':'0'*64},
                        {'status_counts':{'published':1,'draft':1,'archived':False}},
                        {'exported_at':(NOW-timedelta(days=2)).isoformat()},
                        {'exported_at':(NOW+timedelta(hours=1)).isoformat()}):
            with self.subTest(changes=changes),self.assertRaises(catalog.CatalogError):
                catalog.initialize(snapshot()|changes,now=NOW)
        source=snapshot();source['rows'][0]['description']='Modified without rehashing'
        with self.assertRaises(catalog.CatalogError):catalog.initialize(source,now=NOW)

    def test_optional_values_json_keys_and_output_overwrites_fail_closed(self):
        for changes in ({'latitude':True,'longitude':1},{'image_url':'https://fixture.invalid/photo?token=secret'},
                        {'environment':'invented'},{'access_token':'not-a-destination-field'}):
            with self.subTest(changes=changes),self.assertRaises(catalog.CatalogError):
                catalog.initialize(snapshot([row(**changes)]),now=NOW)
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as temp:
            path=Path(temp)/'review.json'
            catalog.write_new(path,{'review_only':True})
            previous=path.read_bytes()
            with self.assertRaises(FileExistsError):catalog.write_new(path,{'overwrite':True})
            self.assertEqual(previous,path.read_bytes())
            duplicate=Path(temp)/'duplicate.json';duplicate.write_text('{"id":1,"id":2}',encoding='utf-8')
            with self.assertRaises(catalog.CatalogError):catalog.read_json(duplicate)

    def test_cli_init_without_snapshot_stops_and_does_not_create_catalog(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as temp:
            directory=Path(temp)
            catalog.write_new(directory/'manifest.json',{'project_ref':catalog.PROJECT,'hosted_writes_enabled':False})
            with patch.object(catalog,'DIRECTORY',directory),patch('sys.argv',['local_destination_catalog.py','init']),patch('sys.stderr',new_callable=io.StringIO):
                self.assertEqual(catalog.main(),1)
            self.assertFalse((directory/'catalog.json').exists())

    def test_archived_files_are_intact_and_weather_runtime_path_stays_active(self):
        from destination_weather_metadata import METADATA_PATH,load_weather_catalog
        archive=ROOT/'data/santa_rosa_places/archive'
        manifest=json.loads((archive/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['files']),5)
        for entry in manifest['files']:
            self.assertEqual(hashlib.sha256((ROOT/entry['archived']).read_bytes()).hexdigest(),entry['sha256'])
        self.assertEqual(METADATA_PATH,ROOT/'data/santa_rosa_places/weather_metadata.json')
        self.assertTrue(load_weather_catalog().available)

    def csv_document(self, rows, directory):
        path=Path(directory)/'source.csv'
        with path.open('w',encoding='utf-8',newline='') as output:
            writer=csv.writer(output);writer.writerow(catalog.CSV_COLUMNS)
            writer.writerows(rows)
        return path

    def csv_row(self, **changes):
        values=dict(zip(catalog.CSV_COLUMNS,['Synthetic destination 2','Local','Garden / Recreation','Outdoor',
            '14.25\u00b0 N','121.05\u00b0 E','Monday-Sunday','09:00am','05:00pm',
            'Synthetic description','Synthetic address','https://share.google/offline-fixture','']))
        values.update(changes)
        return [values[key] for key in catalog.CSV_COLUMNS]

    def test_csv_inspection_preserves_source_and_does_not_fabricate_identity_or_status(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as directory:
            path=self.csv_document([self.csv_row(**{'Opening Hours':'09:00am\n10:00am'})],directory)
            before=path.read_bytes();result=catalog.inspect_csv(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(result['source_sha256'],hashlib.sha256(before).hexdigest())
            self.assertEqual(result['record_count'],1)
            self.assertGreater(result['records'][0]['csv_line_end'],2)
            self.assertFalse(result['import_ready']);self.assertEqual(result['hosted_changes'],0)
            entry=result['records'][0]
            self.assertEqual(entry['identity_review']['state'],'pending_authorized_all_status_snapshot')
            self.assertNotIn('id',entry);self.assertNotIn('status',entry)
            self.assertEqual(entry['photo_review'],'external_link_requires_review')

    def test_csv_coordinate_errors_and_missing_descriptions_stop_automatic_staging(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as directory:
            path=self.csv_document([self.csv_row(Latitude='121.05\u00b0 E',Description='')],directory)
            result=catalog.inspect_csv(path)
            self.assertIn('latitude_hemisphere_mismatch',result['records'][0]['errors'])
            self.assertIn('missing_required:Description',result['records'][0]['errors'])
            self.assertNotIn('latitude',result['records'][0]['proposed_coordinates'])
            self.assertEqual(result['records_with_errors'],1)
        self.assertEqual(catalog.csv_coordinate('14.25 S','latitude'),-14.25)
        with self.assertRaises(catalog.CatalogError):catalog.csv_coordinate('91','latitude')
        with self.assertRaises(catalog.CatalogError):catalog.csv_coordinate('-14.25 N','latitude')

    def test_csv_duplicate_names_block_review_and_exact_matches_are_only_candidates(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as directory:
            path=self.csv_document([self.csv_row(),self.csv_row(**{'Place Name':'SYNTHETIC--destination 2'})],directory)
            result=catalog.inspect_csv(path,snapshot=snapshot(),now=NOW)
            self.assertEqual(len(result['duplicate_normalized_names']),1)
            self.assertEqual(result['records'][0]['identity_review']['state'],'blocked_duplicate_source_name')
            self.assertEqual(result['records'][0]['identity_review']['candidates'][0]['id'],row(2)['id'])
            self.assertFalse(result['import_ready'])
            path.unlink()
            path=self.csv_document([self.csv_row(**{'Place Name':'An alias requiring review'})],directory)
            result=catalog.inspect_csv(path,snapshot=snapshot(),now=NOW)
            self.assertEqual(result['records'][0]['identity_review']['state'],'unmatched_requires_alias_and_identity_review')
            self.assertEqual(result['records'][0]['identity_review']['candidates'],[])

    def test_csv_bad_column_shape_and_unsafe_links_are_reported_without_network(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as directory:
            path=self.csv_document([self.csv_row(**{'Picture / Photo Link':'https://fixture.invalid/photo?token=secret'}),['short']],directory)
            result=catalog.inspect_csv(path)
            self.assertIn('invalid_or_credential_bearing_photo_link',result['records'][0]['errors'])
            self.assertEqual(result['records'][1]['errors'],['column_count_mismatch'])

    def test_csv_na_photos_remain_optional_missing_values(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT/'local_catalog') as directory:
            path=self.csv_document([self.csv_row(**{'Picture / Photo Link':'N/A'})],directory)
            result=catalog.inspect_csv(path)
            self.assertEqual(result['records_with_errors'],0)
            self.assertEqual(result['records'][0]['photo_review'],'not_supplied')
            self.assertIn('photo_placeholder_not_supplied',result['records'][0]['warnings'])


if __name__=='__main__':unittest.main()
