"""Synthetic offline schema-evidence and derived-image safety checks."""
from copy import deepcopy
import hashlib
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import FileStorage
from admin_photo_service import prepare_photo
from tools.local_destination_catalog import CatalogError, FIELDS
from tools.prepare_catalog_from_preflight import validate, function_body, bind_extension, constraint_semantics
from tools.prepare_destination_images import sanitize


def function(name, args, *, definer=False, acl='{postgres=X/postgres}'):
    body="SELECT '{}'::jsonb;" if name!='rosago_itinerary_interests_valid' else 'SELECT true;'
    returns='jsonb' if name!='rosago_itinerary_interests_valid' else 'boolean'
    definition=f"CREATE OR REPLACE FUNCTION public.{name}({args}) RETURNS {returns} LANGUAGE sql "+('SECURITY DEFINER ' if definer else '')+f"SET search_path='' AS $fixture${body}$fixture$;"
    # Only type identity is relevant; parameter names are omitted in this fixture.
    return dict(identity=name+'('+args+')',definition=definition,body_md5=hashlib.md5(body.encode()).hexdigest(),
                owner='postgres',security_definer=definer,config=['search_path=""'],acl=acl)


def document():
    functions=[function('rosago_admin_mutate_destination_unlogged','text,text,timestamptz,jsonb',definer=True),
               function('rosago_admin_mutate_destination','text,text,timestamptz,jsonb',definer=True,acl='{postgres=X/postgres,authenticated=X/postgres}'),
               function('rosago_itinerary_interests_valid','text[]')]
    return dict(export_format='rosago_catalog_schema_preflight_v1',owner_selected_project_ref='brnkigrrqdrywahvcbvc',
        project_identity_requires_dashboard_confirmation=True,database_role='postgres',transaction_read_only='on',
        exported_at='2026-11-08T01:00:00Z',migration_history_relation_present=False,functions=functions,
        columns=[dict(name=name) for name in FIELDS],
        table_security=[dict(table=name,owner='postgres',rls_enabled=True,force_rls=False)
                        for name in ('places','itinerary_drafts','admin_destination_audit')],
        constraints=[dict(name='places_category_check',definition="CHECK(category IN ('nature','dining'))")],
        table_grants=[dict(table_name='places',privilege_type='SELECT',grantee='anon')],
        policies=[dict(tablename=table,policyname=name) for table,name in (
            ('places','places_select_published'),('places','places_select_admin'),
            ('itinerary_drafts','itinerary_drafts_select_own'),('admin_destination_audit','admin_destination_audit_select'))],indexes=[])


class SchemaEvidenceTests(unittest.TestCase):
    def test_local_ddl_roundtrip_allows_only_and_association_not_weaker_checks(self):
        nested="CHECK (((char_length(name)>=1 AND char_length(name)<=150) AND name<>''))"
        flat="CHECK (char_length(name)>=1 AND char_length(name)<=150 AND name<>'')"
        self.assertEqual(constraint_semantics(nested),constraint_semantics(flat))
        self.assertNotEqual(constraint_semantics(nested),constraint_semantics(flat.replace('>=1','>=0')))
        self.assertNotEqual(constraint_semantics(nested),constraint_semantics(flat.replace(' AND ',' OR ',1)))
        nested_array="CHECK ((latitude IS NULL) OR ((latitude>=-90 AND latitude<=90) AND latitude<>ALL(ARRAY['NaN'::double precision,'Infinity'::double precision])))"
        flat_array="CHECK ((latitude IS NULL) OR (latitude>=-90 AND latitude<=90 AND latitude<>ALL(ARRAY['NaN'::double precision,'Infinity'::double precision])))"
        self.assertEqual(constraint_semantics(nested_array),constraint_semantics(flat_array))
    def test_readonly_target_hash_and_raw_execution_permissions(self):
        doc=document();expected={f['identity'].split('(')[0]:f['body_md5'] for f in doc['functions']}
        with patch('tools.prepare_catalog_from_preflight.TARGETS',expected):
            self.assertEqual(validate(doc),doc)
            for changes in [dict(transaction_read_only='off'),dict(owner_selected_project_ref='jfaufpfzfhysqkhcdsrs')]:
                with self.assertRaises(CatalogError):validate(doc|changes)
            bad=deepcopy(doc);bad['functions'][0]['acl']='{=X/postgres,postgres=X/postgres}'
            with self.assertRaises(CatalogError):validate(bad)

    def test_source_tampering_security_mismatch_and_signature_mismatch_rejected(self):
        base=document()['functions'][0]
        for bad in [base|dict(body_md5='0'*32),base|dict(security_definer=False),
                    base|dict(identity='rosago_admin_mutate_destination_unlogged(integer)')]:
            with self.assertRaises(CatalogError):function_body(bad)

    def test_unsafe_table_write_grant_or_extra_statement_rejected(self):
        doc=document();expected={f['identity'].split('(')[0]:f['body_md5'] for f in doc['functions']}
        with patch('tools.prepare_catalog_from_preflight.TARGETS',expected):
            bad=deepcopy(doc);bad['table_grants'][0]['privilege_type']='UPDATE'
            with self.assertRaises(CatalogError):validate(bad)
            bad=deepcopy(doc);bad['constraints'][0]['definition']+='; DROP TABLE public.places'
            with self.assertRaises(CatalogError):validate(bad)

    def test_bound_sql_pins_definitions_owners_acl_and_constraint_drift(self):
        doc=document()
        draft="BEGIN;\n"+'\n'.join(name+" constant text := 'UNQUALIFIED_CURRENT_PREFLIGHT_REQUIRED';"
            for name in ('expected_mutation_body_md5','expected_interests_body_md5','expected_category_check_md5'))
        sql=bind_extension(doc,draft)
        self.assertNotIn('UNQUALIFIED_CURRENT_PREFLIGHT_REQUIRED',sql)
        self.assertIn("p.proacl::text='{postgres=X/postgres}'",sql)
        self.assertIn("pg_catalog.pg_get_userbyid(p.proowner)='postgres'",sql)
        self.assertIn('Destination constraint inventory changed',sql)


class ImageStagingTests(unittest.TestCase):
    @staticmethod
    def pixels(fmt='JPEG',size=(16,12)):
        out=BytesIO();Image.new('RGB',size,(128,0,32)).save(out,format=fmt)
        return out.getvalue()

    def test_detects_actual_format_and_preserves_original_bytes(self):
        raw=self.pixels();before=hashlib.sha256(raw).hexdigest()
        content,extension,mimetype,size=sanitize(raw)
        self.assertEqual((extension,mimetype,size),('jpg','image/jpeg',(16,12)))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),before)
        self.assertLessEqual(len(content),5*1024*1024)

    def test_staged_photo_passes_existing_unweakened_admin_upload_validation(self):
        for fmt in ('JPEG','PNG','WEBP'):
            content,extension,mimetype,_=sanitize(self.pixels(fmt))
            prepared=prepare_photo(FileStorage(stream=BytesIO(content),filename='reviewed.'+extension,content_type=mimetype))
            self.assertEqual(prepared.content_type,mimetype)
            self.assertLessEqual(len(prepared.content),5*1024*1024)

    def test_malformed_and_oversized_dimensions_are_rejected_without_source_changes(self):
        with self.assertRaises(Exception):sanitize(b'<html>not an image</html>')
        with self.assertRaises(CatalogError):sanitize(self.pixels('PNG',(8193,1)))

    def test_metadata_is_removed_from_staged_copy(self):
        out=BytesIO();image=Image.new('RGB',(16,12),'red');exif=Image.Exif();exif[270]='Synthetic private metadata'
        image.save(out,format='JPEG',exif=exif)
        content,_,_,_=sanitize(out.getvalue())
        with Image.open(BytesIO(content)) as clean:self.assertFalse(clean.getexif())


if __name__=='__main__':unittest.main()
