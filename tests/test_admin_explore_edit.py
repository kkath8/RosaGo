"""Existing-row editing through Flask/SDKs with isolated Auth/DB/Storage doubles.

No live sign-in, database, email or Storage request is permitted by the fixtures.
"""
from copy import deepcopy
from io import BytesIO
import os
import unittest
from unittest.mock import patch

import httpx
from werkzeug.datastructures import MultiDict

import test_admin_management as management
import test_admin_photos as photos
import test_registration
from admin_management_service import validate_destination
from places_client import PublicPlacesClient
from places_service import PlacesService
from test_public_layout import Document


class ExistingExploreEditTests(unittest.TestCase):
    setUp = management.ManagementRouteTests.setUp
    tearDown = management.ManagementRouteTests.tearDown
    protected = management.ManagementRouteTests.protected
    slug = 'existing-garden'
    path = '/admin/places/existing-garden/edit'

    def install(self):
        photos.PhotoRouteTests.install(self)
        patch.dict(os.environ, ROSAGO_DESTINATION_ENVIRONMENT_ENABLED='true').start()
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(self.respond), **kwargs)
            self.clients.append(client)
            return client
        public = PublicPlacesClient('https://example.supabase.co', 'sb_publishable_fixture', http_factory=factory)
        self.app.extensions['rosago_places'] = PlacesService(public.database_client,
            tourism_metadata_enabled=True, environment_enabled=True)
        # Arrange two existing rows directly, never through the create endpoint.
        for index, slug in enumerate(('another-museum', self.slug), 1):
            self.records.append(validate_destination(management.BASE | dict(
                name='Unrelated Museum' if index == 1 else 'Existing Garden',
                category='heritage' if index == 1 else 'nature',
                description='Saved description\nSecond line.', address='Saved address',
                latitude='14.3', longitude='121.1', tourism_type='Local',
                tourism_category='Saved Tourism category', tourism_opening_hours_raw='8:00 AM*',
                tourism_closing_hours_raw='6:00 PM*', tourism_hours_status='unverified'),
                tourism_enabled=True) | dict(
                    id=f'11111111-1111-4111-8111-{index:012}', slug=slug,
                    status='published', environment='Indoor',
                    image_url='https://example.supabase.co/storage/v1/object/public/destination-images/destinations/' + str(index) * 32 + '.png',
                    created_at='2026-10-01T00:00:00+00:00', updated_at='2026-11-01T00:00:00+00:00',
                    tourism_source='Isolated fixture', tourism_source_row=index + 1))
        self.target = self.records[1]
        self.unrelated = deepcopy(self.records[0])

    def form(self, response=None, *, status=200):
        response = response or self.client.get(self.path)
        self.protected(response, status)
        page = Document(response.get_data(as_text=True))
        form = page.find('form', enctype='multipart/form-data')[0]
        values = MultiDict()
        for node in page.elements:
            if form not in node.ancestors or 'name' not in node.attrs or 'disabled' in node.attrs:
                continue
            name = node.attrs['name']
            if node.tag == 'input':
                kind = node.attrs.get('type', 'text')
                if kind in ('file', 'submit') or (kind == 'checkbox' and 'checked' not in node.attrs):
                    continue
                values.add(name, node.attrs.get('value', ''))
            elif node.tag == 'textarea':
                values.add(name, node.text)
            elif node.tag == 'select':
                options = [o for o in page.find('option') if node in o.ancestors]
                selected = next((o for o in options if 'selected' in o.attrs), options[0])
                values.add(name, selected.attrs.get('value', selected.text))
        self.assertEqual(set(values), set(management.BASE) | {
            'csrf_token', 'environment', 'expected_updated_at'} | (
                {'remove_photo'} if 'remove_photo' in values else set()))
        return values

    def submit(self, values):
        return self.client.post(self.path, data=values, headers=management.ORIGIN,
                                content_type='multipart/form-data')

    def unchanged_other(self):
        self.assertEqual(len(self.records), 2)
        self.assertEqual(self.records[0], self.unrelated)

    def test_catalog_and_details_edit_links_load_exact_saved_row(self):
        self.install()
        for path in ('/admin/places', '/admin/places/' + self.slug):
            response = self.client.get(path)
            self.protected(response, 200)
            self.assertTrue(Document(response.get_data(as_text=True)).find('a', href=self.path))
        values = self.form()
        for key in management.BASE:
            expected = self.target[key]
            if key in ('latitude', 'longitude'):
                self.assertEqual(float(values[key]), expected)
            else:
                self.assertEqual(values[key], expected or '', key)
        self.assertEqual(values['environment'], 'Indoor')
        self.assertEqual(values['expected_updated_at'], self.target['updated_at'])
        page = self.client.get(self.path).data
        self.assertIn(self.target['image_url'].encode(), page)
        self.assertNotIn(self.unrelated['image_url'].encode(), page)
        self.assertEqual(self.operations, [])
        self.assertEqual(self.storage_requests, [])

    def test_edit_updates_existing_identity_and_public_explore_only(self):
        self.install()
        original = deepcopy(self.target)
        values = self.form()
        for key, value in dict(name='Edited Garden', description='Edited description.',
            category='attraction', address='Edited address', latitude='14.31', longitude='121.12',
            environment='Outdoor').items():
            values[key] = value
        response = self.submit(values)
        self.protected(response, 303)
        self.assertEqual(response.location, '/admin/places/' + self.slug)
        for key in ('id', 'slug', 'created_at', 'status', 'image_url', 'tourism_source', 'tourism_source_row'):
            self.assertEqual(self.target[key], original[key], key)
        self.unchanged_other()
        self.assertEqual([op['p_action'] for op in self.operations], ['edit'])
        self.assertEqual(self.operations[0]['p_slug'], self.slug)
        self.assertNotIn('image_url', self.operations[0]['p_values'])
        self.assertNotEqual(self.target['updated_at'], original['updated_at'])
        saved = self.form()
        for key in ('name', 'description', 'category', 'address', 'environment'):
            self.assertEqual(saved[key], values[key])
        for path in ('/places', '/places/' + self.slug):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Edited Garden', response.data)
            self.assertNotIn(b'Existing Garden', response.data)
        rows = self.client.get('/api/places').json['places']
        target = next(row for row in rows if row['slug'] == self.slug)
        for key in ('name', 'description', 'category', 'address', 'environment', 'image_url'):
            self.assertEqual(target[key], self.target[key], key)
        public_place = self.app.extensions['rosago_places'].get_published_by_slug(self.slug)
        self.assertEqual((public_place.latitude, public_place.longitude), (14.31, 121.12))
        self.assertEqual(len(rows), 2)
        # Replaying the original browser form cannot create a duplicate or overwrite newer state.
        after = deepcopy(self.records)
        self.protected(self.submit(values), 503)
        self.assertEqual(self.records, after)
        self.assertTrue(all(op['p_action'] == 'edit' for op in self.operations))

    def test_description_only_save_and_restore_preserve_photo_and_other_fields(self):
        self.install()
        original = deepcopy(self.target)
        for description in (original['description'] + ' [RosaGo edit check]', original['description']):
            values = self.form()
            values['description'] = description
            self.protected(self.submit(values), 303)
            self.assertEqual(self.target['description'], description)
            for key, value in original.items():
                if key not in ('description', 'updated_at'):
                    self.assertEqual(self.target[key], value, key)
            self.assertNotIn('image_url', self.operations[-1]['p_values'])
            self.assertEqual(self.storage_requests, [])
            self.unchanged_other()
            public = self.app.extensions['rosago_places'].get_published_by_slug(self.slug)
            self.assertEqual(public.description, description)
            self.assertEqual(public.image_url, original['image_url'])
        self.assertEqual(len(self.operations), 2)
        self.assertTrue(all(op['p_action'] == 'edit' for op in self.operations))

    def test_invalid_fields_and_identity_injection_never_mutate(self):
        self.install()
        original = deepcopy(self.records)
        for change, status in (({'name': ''}, 400), ({'category': 'invented'}, 400),
                ({'latitude': 'nan'}, 400), ({'longitude': ''}, 400),
                ({'latitude': '91'}, 400), ({'environment': 'covered'}, 400),
                ({'id': self.unrelated['id']}, 403), ({'slug': 'another-museum'}, 403),
                ({'status': 'archived'}, 403)):
            with self.subTest(fields=tuple(change)):
                values = self.form()
                for key, value in change.items():
                    values[key] = value
                self.protected(self.submit(values), status)
                self.assertEqual(self.records, original)
        self.assertEqual(self.operations, [])
        self.assertEqual(self.storage_requests, [])
        self.protected(self.client.get(self.path + '?slug=another-museum'), 400)
        self.protected(self.client.get('/admin/places/missing-place/edit'), 404)

    def test_archived_edit_stays_hidden_and_restore_requires_confirmation(self):
        self.install()
        self.target['status'] = 'archived'
        original_id = self.target['id']
        values = self.form()
        values['name'] = 'Edited Archived Garden'
        self.protected(self.submit(values), 303)
        self.assertEqual(self.target['status'], 'archived')
        self.assertEqual(self.client.get('/places/' + self.slug).status_code, 404)
        self.assertNotIn(b'Edited Archived Garden', self.client.get('/places').data)
        self.assertEqual(len(self.client.get('/api/places').json['places']), 1)
        path = '/admin/places/' + self.slug + '/publication/restore'
        self.protected(self.client.get(path), 200)
        self.assertEqual(self.target['status'], 'archived')
        self.protected(self.client.post(path, data=dict(csrf_token=self.csrf,
            expected_updated_at=self.target['updated_at']), headers=management.ORIGIN), 303)
        self.assertEqual(self.target['status'], 'draft')
        self.assertEqual(self.target['id'], original_id)
        self.assertEqual(self.client.get('/places/' + self.slug).status_code, 404)
        self.unchanged_other()

    def test_existing_photo_replacement_and_removal_use_mock_storage(self):
        self.install()
        old_url = self.target['image_url']
        values = self.form()
        values.add('photo', (BytesIO(photos.image_bytes()), 'replacement.png', 'image/png'))
        self.protected(self.submit(values), 303)
        new_url = self.target['image_url']
        self.assertNotEqual(new_url, old_url)
        self.assertIn('/storage/v1/object/public/destination-images/destinations/', new_url)
        self.assertEqual(len(self.storage_requests), 1)
        self.assertEqual(self.storage_requests[0].method, 'POST')
        self.assertIn(new_url.encode(), self.client.get('/places/' + self.slug).data)
        self.unchanged_other()
        values = self.form()
        values['remove_photo'] = '1'
        self.protected(self.submit(values), 303)
        self.assertIsNone(self.target['image_url'])
        self.assertNotIn(new_url.encode(), self.client.get('/places/' + self.slug).data)
        self.assertEqual(len(self.storage_requests), 1)  # Detach only; no object deletion.
        self.unchanged_other()

    def test_failed_validation_preserves_explicit_photo_removal_for_correction(self):
        self.install()
        original = deepcopy(self.records)
        values = self.form()
        values['name'] = ''
        values['remove_photo'] = '1'
        response = self.submit(values)
        self.protected(response, 400)
        self.assertEqual(self.records, original)
        self.assertEqual(self.operations, [])
        # Serialize the returned browser controls, then correct only the text error.
        corrected = self.form(response, status=400)
        self.assertEqual(corrected.get('remove_photo'), '1')
        corrected['name'] = 'Corrected Garden'
        self.protected(self.submit(corrected), 303)
        self.assertIsNone(self.target['image_url'])
        self.assertEqual(self.storage_requests, [])
        self.unchanged_other()

    def test_non_admin_and_user_only_sessions_cannot_read_or_save(self):
        self.install()
        values = self.form()
        self.value = False
        self.protected(self.client.get(self.path), 403)
        self.protected(self.submit(values), 403)
        self.value = None
        self.protected(self.submit(values), 503)
        with self.client.session_transaction(path='/admin') as state:
            state.clear()
        test_registration.seed_normal_session(self)
        self.protected(self.client.get(self.path), 302)
        self.protected(self.submit(values), 302)
        self.assertEqual(self.operations, [])
        self.assertEqual(self.storage_requests, [])
        self.unchanged_other()


if __name__ == '__main__':
    unittest.main()
