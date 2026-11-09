"""Offline cover/placeholder rendering and review-only final mapping contracts."""
from dataclasses import replace
import unittest

from tools.local_destination_catalog import CatalogError
from tools.prepare_final_image_mapping import mapping_records
from test_public_layout import Document

PHOTO='https://example.supabase.co/storage/v1/object/public/destination-images/destinations/'+'a'*32+'.jpg'
PLACEHOLDER='/static/img/destination-placeholder.svg'


class DestinationImageViews(unittest.TestCase):
    def fixture(self,case):
        self.addCleanup(case.doCleanups)
        case.setUp()
        self.addCleanup(case.tearDown)
        return case

    def assert_cover(self,response,url):
        self.assertEqual(response.status_code,200)
        images=Document(response.get_data(as_text=True)).find('img',**{'data-destination-image':None})
        self.assertTrue(images)
        self.assertTrue(all(img.attrs['src']==url for img in images))
        if url==PLACEHOLDER:
            self.assertTrue(all('destination-photo-placeholder' in img.attrs.get('class','') for img in images))
        else:
            self.assertTrue(all(img.attrs.get('referrerpolicy')=='no-referrer' for img in images))

    def test_user_cards_and_detail_show_recorded_image_or_shared_placeholder(self):
        from test_places_routes import PlacesRouteTests
        case=self.fixture(PlacesRouteTests('test_logged_out_list_and_exact_template_boundary'))
        for url in (PHOTO,None):
            place=replace(case.place,image_url=url)
            case.service.list_published.return_value=(place,)
            case.service.get_published_by_slug.return_value=place
            for path in ('/places','/places/synthetic-place'):
                self.assert_cover(case.get(path),url or PLACEHOLDER)
        asset=case.client.get(PLACEHOLDER)
        self.assertEqual(asset.status_code,200)
        self.assertIn('image/svg+xml',asset.content_type)
        self.assertIn(b'Photo unavailable',asset.data)
        self.assertNotIn(b'<script',asset.data)

    def test_recommendations_display_recorded_image_and_null_photo_placeholder(self):
        from test_itinerary_recommendations import RecommendationRouteTests
        case=self.fixture(RecommendationRouteTests('test_owned_shortlist_real_engine_and_presentation'))
        for url in (PHOTO,None):
            case.match=replace(case.match,image_url=url)
            case.catalog.list_published.return_value=(case.match,)
            response=case.post(headers={'Origin':'http://localhost'})
            self.assert_cover(response,url or PLACEHOLDER)
        case.drafts['create_itinerary_draft'].assert_not_called()
        case.drafts['update_itinerary_draft_preferences'].assert_not_called()

    def test_itinerary_preview_shows_recorded_cover_then_placeholder(self):
        from test_itinerary_preview_routes import PreviewRouteTests,PREVIEW
        case=self.fixture(PreviewRouteTests('test_mutation_csrf_origin_exact_fields_and_revisions'))
        for url in (PHOTO,None):
            case.match=replace(case.match,image_url=url)
            case.catalog.list_published.return_value=(case.match,)
            case.ready()
            self.assert_cover(case.client.get(PREVIEW),url or PLACEHOLDER)

    def test_admin_create_edit_controls_and_empty_preview_use_the_real_multipart_flow(self):
        from test_admin_photos import PhotoRouteTests
        case=self.fixture(PhotoRouteTests('test_upload_replace_unrelated_edit_remove_and_admin_rendering'))
        case.install()
        page=Document(case.client.get('/admin/places/new').get_data(as_text=True))
        self.assertTrue(page.find('form',enctype='multipart/form-data'))
        control=page.find('input',name='photo')[0]
        self.assertEqual(control.attrs['type'],'file')
        self.assertEqual(control.attrs['accept'],'image/jpeg,image/png,image/webp')
        empty=page.find('img',**{'data-photo-preview':None})[0]
        self.assertEqual(empty.attrs['src'],PLACEHOLDER)
        self.assertNotIn('hidden',empty.attrs)
        case.protected(case.save(),303)  # SDK mock transport, never a real upload.
        saved=case.records[0]['image_url']
        page=Document(case.client.get('/admin/places/fixture-destination/edit').get_data(as_text=True))
        preview=page.find('img',**{'data-photo-preview':None})[0]
        self.assertEqual(preview.attrs['src'],saved)
        self.assertEqual(preview.attrs['data-saved-src'],saved)
        self.assertTrue(page.find('input',name='remove_photo'))
        case.protected(case.save(edit=True,file=False),303)
        self.assertEqual(case.records[0]['image_url'],saved)
        self.assertNotIn('image_url',case.operations[-1]['p_values'])


class FinalImageMappingTests(unittest.TestCase):
    def fixture(self):
        missing={65,66,67,70,71,72,73,74,75,76,77,78,80,81}
        rows=[];payloads=[]
        for number in range(1,99):
            candidate=None if number in missing else dict(staged_file=f'synthetic/{number}.jpg')
            if candidate:payloads.append(candidate|dict(expected_upload_content_sha256='synthetic-hash'))
            rows.append(dict(csv_record=number,name=f'Synthetic {number}',existing_id=None,
                existing_image_url=PHOTO if number in (1,21,52) else None,candidate=candidate))
        return dict(records=rows),dict(payloads=payloads)

    def test_exact_dispositions_preserve_hosted_and_never_assign_bad_court_image(self):
        images,payloads=self.fixture();rows=mapping_records(images,payloads)
        self.assertEqual(sum(r['action']=='preserve_existing_hosted_image' for r in rows),3)
        self.assertEqual(sum(r['action']=='proposed_attachment_requires_approval' for r in rows),79)
        self.assertEqual(sum(r['action'].startswith('placeholder_') for r in rows),16)
        self.assertIsNone(rows[55]['selected_local_candidate'])
        self.assertIsNone(rows[55]['proposed_database_image_url'])
        self.assertIsNone(rows[57]['selected_local_candidate'])
        self.assertTrue(all(not r['approved_for_upload'] and not r['publishing_authorized'] for r in rows))
        self.assertTrue(all(r['proposed_database_image_url'] is None or r['proposed_database_image_url']==PHOTO for r in rows))

    def test_missing_completed_payload_evidence_rejects_the_mapping(self):
        images,payloads=self.fixture();payloads['payloads']=[]
        with self.assertRaises(CatalogError):mapping_records(images,payloads)


if __name__=='__main__':unittest.main()
