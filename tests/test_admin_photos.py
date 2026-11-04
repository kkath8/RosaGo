"""Photo security and Admin-to-User flow using real SDKs and isolated transports."""
from io import BytesIO
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from PIL import Image, PngImagePlugin
from werkzeug.datastructures import FileStorage, MultiDict

from admin_photo_service import prepare_photo, PhotoValidationError, MAX_PHOTO_BYTES
from admin_management_service import validate_destination, DestinationValidationError
from places_client import PublicPlacesClient
from places_service import PlacesService
import test_admin_management as management
import test_registration
from test_public_layout import Document


def image_bytes(fmt='PNG', size=(8, 8)):
    result = BytesIO()
    Image.new('RGB', size, 'red').save(result, format=fmt)
    return result.getvalue()


class PhotoValidationTests(unittest.TestCase):
    def test_actual_formats_and_metadata_are_validated_not_just_filename(self):
        for fmt, ext, mime in [('JPEG', 'jpg', 'image/jpeg'), ('PNG', 'png', 'image/png'), ('WEBP', 'webp', 'image/webp')]:
            result = prepare_photo(FileStorage(BytesIO(image_bytes(fmt)), filename='../../unsafe.' + ext, content_type=mime))
            self.assertEqual(result.content_type, mime)
            self.assertEqual(result.extension, ext)
            self.assertLess(len(result.content), MAX_PHOTO_BYTES)
        metadata = PngImagePlugin.PngInfo(); metadata.add_text('private', 'private-metadata-marker')
        source = BytesIO(); Image.new('RGB', (8, 8)).save(source, format='PNG', pnginfo=metadata)
        result = prepare_photo(FileStorage(BytesIO(source.getvalue()), filename='photo.png', content_type='image/png'))
        self.assertNotIn(b'private-metadata-marker', result.content)
        with self.assertRaises(PhotoValidationError):
            prepare_photo(FileStorage(BytesIO(image_bytes('PNG')), filename='fake.jpg', content_type='image/jpeg'))

    def test_empty_oversized_svg_truncated_oversized_dimensions_and_animation_rejected(self):
        animated = BytesIO()
        Image.new('RGB', (4, 4), 'red').save(animated, format='WEBP', save_all=True,
            append_images=[Image.new('RGB', (4, 4), 'blue')], duration=100, loop=0)
        for content, filename, mime in [(b'', 'empty.png', 'image/png'),
            (b'x' * (MAX_PHOTO_BYTES + 1), 'large.png', 'image/png'),
            (b'<svg onload="alert(1)"></svg>', 'fake.png', 'image/png'),
            (image_bytes()[:30], 'truncated.png', 'image/png'),
            (image_bytes(size=(8193, 1)), 'wide.png', 'image/png'),
            (animated.getvalue(), 'animated.webp', 'image/webp')]:
            with self.subTest(filename=filename), self.assertRaises(PhotoValidationError):
                prepare_photo(FileStorage(BytesIO(content), filename=filename, content_type=mime))

    def test_optional_mutation_field_preserves_replaces_or_removes_and_rejects_foreign_urls(self):
        with patch.dict(os.environ, SUPABASE_URL='https://example.supabase.co', SUPABASE_STORAGE_BUCKET='destination-images'):
            self.assertNotIn('image_url', validate_destination(management.BASE, tourism_enabled=True))
            self.assertIsNone(validate_destination(management.BASE | {'image_url': None}, tourism_enabled=True)['image_url'])
            url = 'https://example.supabase.co/storage/v1/object/public/destination-images/destinations/' + 'a' * 32 + '.png'
            self.assertEqual(validate_destination(management.BASE | {'image_url': url}, tourism_enabled=True)['image_url'], url)
            for bad in ('javascript:alert(1)', 'https://foreign.invalid/photo.png', url + '?token=secret', url.replace('destinations/', '../')):
                with self.assertRaises(DestinationValidationError):
                    validate_destination(management.BASE | {'image_url': bad}, tourism_enabled=True)


class PhotoRouteTests(unittest.TestCase):
    setUp = management.ManagementRouteTests.setUp
    tearDown = management.ManagementRouteTests.tearDown
    protected = management.ManagementRouteTests.protected
    version = management.ManagementRouteTests.version
    transition = management.ManagementRouteTests.transition

    def install(self):
        management.ManagementRouteTests.install(self)
        patch.dict(os.environ, SUPABASE_STORAGE_SECRET_KEY='sb_secret_photo_test_only',
                   SUPABASE_STORAGE_BUCKET='destination-images', SUPABASE_URL='https://example.supabase.co').start()
        self.storage_requests = []
        self.storage_status = 200
        self.storage_timeout = False
        def respond(request):
            self.storage_requests.append(request)
            self.assertEqual(request.headers['apikey'], 'sb_secret_photo_test_only')
            self.assertNotIn('authorization', request.headers)
            self.assertEqual(request.headers['x-upsert'], 'false')
            self.assertEqual(request.method, 'POST')
            self.assertRegex(request.url.path, r'^/storage/v1/object/destination-images/destinations/[0-9a-f]{32}\.(png|jpg|webp)$')
            if self.storage_timeout:
                raise httpx.ReadTimeout('private-provider-detail')
            if self.storage_status != 200:
                return httpx.Response(self.storage_status, json=dict(statusCode=self.storage_status,
                    error='StorageError', message='private-provider-detail'))
            return httpx.Response(200, json={'Key': request.url.path.split('/object/', 1)[1]})
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        patch('admin_photo_service._http_client', side_effect=factory).start()

    def save(self, *, edit=False, file=True, **changes):
        values = management.BASE | dict(csrf_token=self.csrf) | changes
        if edit: values['expected_updated_at'] = self.version()
        if file: values['photo'] = (BytesIO(image_bytes()), '../../untrusted.png', 'image/png')
        return self.client.post('/admin/places/fixture-destination/edit' if edit else '/admin/places/new',
            data=values, headers=management.ORIGIN)

    def test_upload_replace_unrelated_edit_remove_and_admin_rendering(self):
        self.install()
        self.protected(self.save(), 303)
        first = self.records[0]['image_url']
        self.assertIn(first.encode(), self.client.get('/admin/places/fixture-destination').data)
        self.assertIn(first.encode(), self.client.get('/admin/places/fixture-destination/edit').data)
        self.protected(self.save(edit=True, file=False, name='Renamed only'), 303)
        self.assertEqual(self.records[0]['image_url'], first)
        self.assertNotIn('image_url', self.operations[-1]['p_values'])
        self.protected(self.save(edit=True), 303)
        second = self.records[0]['image_url']
        self.assertNotEqual(first, second)
        self.protected(self.save(edit=True, file=False, remove_photo='1'), 303)
        self.assertIsNone(self.records[0]['image_url'])
        self.assertIsNone(self.operations[-1]['p_values']['image_url'])
        self.assertEqual(len(self.storage_requests), 2)
        self.assertTrue(all(r.method == 'POST' for r in self.storage_requests))
        self.assertFalse(any('storage' in r.url.path for r in self.requests))

    def test_invalid_files_and_invalid_destination_fields_never_upload(self):
        self.install()
        for raw, name, mime in [(b'not an image', 'bad.png', 'image/png'),
                (image_bytes(), 'fake.svg', 'image/svg+xml'), (b'x' * (MAX_PHOTO_BYTES + 1), 'large.png', 'image/png')]:
            values = management.BASE | dict(csrf_token=self.csrf, photo=(BytesIO(raw), name, mime))
            response = self.client.post('/admin/places/new', data=values, headers=management.ORIGIN)
            self.protected(response, 400)
            response.request.close()
            response.request.input_stream.close()
        self.protected(self.save(name=''), 400)
        self.assertEqual(self.storage_requests, [])
        self.assertEqual(self.operations, [])

    def test_body_limit_is_clear_and_rejects_before_storage(self):
        self.install()
        response = self.client.post('/admin/places/new', data=management.BASE | dict(csrf_token=self.csrf,
            photo=(BytesIO(b'x' * (MAX_PHOTO_BYTES + 200000)), 'too-large.png', 'image/png')), headers=management.ORIGIN)
        self.protected(response, 413)
        self.assertIn(b'no larger than 5 MB', response.data)
        self.assertEqual(self.storage_requests, [])
        response.request.close()
        response.request.input_stream.close()

    def test_permissions_csrf_origin_and_fresh_upload_membership(self):
        self.install()
        self.value = False
        self.protected(self.save(), 403)
        self.value = True
        self.protected(self.save(csrf_token='wrong'), 403)
        with patch('admin_photo_service.is_current_admin', return_value=False):
            self.protected(self.save(), 403)
        self.assertEqual(self.storage_requests, [])
        self.assertEqual(self.operations, [])
        with self.client.session_transaction() as session: session.clear()
        self.protected(self.save(), 302)

    def test_browser_origin_rendered_edit_form_accepts_multipart_photo(self):
        self.install(); self.protected(self.save(), 303)
        self.records[0]['slug'] = 'enchanted-kingdom'
        # Exercise the browser's exact host, with a host-scoped session cookie.
        cookie_name = self.app.config['SESSION_COOKIE_NAME']
        cookie = self.client.get_cookie(cookie_name)
        self.client.set_cookie(cookie_name, cookie.value, domain='127.0.0.1')
        base = 'http://127.0.0.1:5000'
        path = '/admin/places/enchanted-kingdom/edit'
        writes = len(self.operations)
        response = self.client.get(path, base_url=base)
        self.protected(response, 200)
        self.assertEqual(len(self.operations), writes)
        page = Document(response.get_data(as_text=True))
        form = page.find('form', enctype='multipart/form-data')[0]
        values = MultiDict()
        for node in page.elements:
            if form not in node.ancestors or 'name' not in node.attrs:
                continue
            name = node.attrs['name']
            if node.tag == 'input' and node.attrs.get('type') not in ('file', 'checkbox', 'submit'):
                values.add(name, node.attrs.get('value', ''))
            elif node.tag == 'textarea':
                values.add(name, node.text)
            elif node.tag == 'select':
                options = [o for o in page.find('option') if node in o.ancestors]
                selected = next((o for o in options if 'selected' in o.attrs), options[0])
                values.add(name, selected.attrs.get('value', selected.text))
        values.add('photo', (BytesIO(image_bytes()), 'replacement.png', 'image/png'))
        with self.assertNoLogs(self.app.logger, level='WARNING'):
            response = self.client.post(path, base_url=base, data=values,
                content_type='multipart/form-data', headers={'Origin': base, 'Referer': base + path})
        self.protected(response, 303)
        self.assertEqual(len(self.storage_requests), 2)
        self.assertEqual(self.operations[-1]['p_slug'], 'enchanted-kingdom')
        self.assertIn('image_url', self.operations[-1]['p_values'])

    def test_invalid_form_structure_is_rejected_before_upload_or_mutation(self):
        self.install()
        base = list(management.BASE.items()) + [('csrf_token', self.csrf)]
        cases = [
            ('origin_mismatch', base, {'Origin': 'https://private-marker.invalid'}),
            ('missing_form_fields', [(k, v) for k, v in base if k != 'name'], management.ORIGIN),
            ('unexpected_form_fields', base + [('private-field-marker', 'private-value-marker')], management.ORIGIN),
            ('duplicate_form_fields', base + [('csrf_token', self.csrf)], management.ORIGIN),
            ('unexpected_file_fields', base + [('private-file-marker',
                (BytesIO(image_bytes()), 'private-name-marker.png', 'image/png'))], management.ORIGIN),
            ('duplicate_file_fields', base + [('photo', (BytesIO(image_bytes()), 'one.png', 'image/png')),
                ('photo', (BytesIO(image_bytes()), 'two.png', 'image/png'))], management.ORIGIN),
            ('invalid_removal_flag', base + [('remove_photo', 'private-value-marker')], management.ORIGIN),
            ('csrf_session_mismatch', [(k, 'private-token-marker' if k == 'csrf_token' else v)
                for k, v in base], management.ORIGIN),
        ]
        for reason, fields, headers in cases:
            with self.subTest(reason=reason):
                response = self.client.post('/admin/places/new', data=MultiDict(fields),
                    content_type='multipart/form-data', headers=headers)
                self.protected(response, 403)
        self.assertEqual(self.storage_requests, [])
        self.assertEqual(self.operations, [])
        self.assertFalse(any(r.url.path.endswith('/places') for r in self.requests))

    def test_csrf_is_bound_to_current_session_even_when_token_is_present(self):
        self.install()
        previous_csrf = self.csrf
        handle = test_registration.seed_normal_session(self)
        current_csrf = self.dependencies.store.resolve(handle).csrf
        self.assertNotEqual(previous_csrf, current_csrf)
        self.protected(self.save(csrf_token=previous_csrf), 403)
        self.assertEqual(self.storage_requests, [])
        self.assertEqual(self.operations, [])
        self.protected(self.save(csrf_token=current_csrf), 303)

    def test_edit_multipart_success_and_authorization_failures(self):
        self.install(); self.protected(self.save(file=False), 303)
        path = '/admin/places/fixture-destination/edit'

        def submit(*, photo=True, csrf=None):
            data = management.BASE | dict(csrf_token=self.csrf if csrf is None else csrf,
                expected_updated_at=self.version(), photo=(BytesIO(image_bytes() if photo else b''),
                    'cover.png' if photo else '', 'image/png' if photo else 'application/octet-stream'))
            return self.client.post(path, data=data, content_type='multipart/form-data',
                headers=management.ORIGIN | {'Referer': 'http://localhost' + path})

        response = submit(photo=False)
        self.protected(response, 303)
        self.assertEqual(len(self.storage_requests), 0)

        response = submit()
        self.protected(response, 303)
        self.assertEqual(len(self.storage_requests), 1)
        writes = len(self.operations)
        reads = sum(r.url.path.endswith('/places') for r in self.requests)

        response = submit(csrf='private-invalid-token')
        self.protected(response, 403)
        self.assertIn(b'Please reload this page and try again.', response.data)
        self.assertEqual(sum(r.url.path.endswith('/places') for r in self.requests), reads)

        self.value = False
        response = submit()
        self.protected(response, 403)
        self.assertIn(b'Admin access required.', response.data)
        self.value = True

        with patch('admin_photo_service.is_current_admin', return_value=False):
            response = submit()
        self.protected(response, 403)
        self.assertNotIn(b'Please reload this page and try again.', response.data)

        with self.client.session_transaction() as session:
            session['auth_session_id'] = 'missing-fixture-session'
        response = submit()
        self.protected(response, 302)
        self.assertTrue(response.location.startswith('/admin/login'))

        handle = test_registration.seed_normal_session(self)
        record = self.dependencies.store.resolve(handle)
        self.csrf = record.csrf
        with patch.object(self.dependencies.store, '_clock', return_value=record.last_activity_at + 1801):
            response = submit()
        self.protected(response, 302)
        self.assertEqual(len(self.storage_requests), 1)
        self.assertEqual(len(self.operations), writes)

    def test_storage_error_and_timeout_do_not_save_or_expose_credentials(self):
        self.install()
        for timeout in (False, True):
            self.storage_status = 503
            self.storage_timeout = timeout
            response = self.save()
            self.protected(response, 503)
            self.assertIn(b'photo could not be uploaded', response.data)
            self.assertNotIn(b'sb_secret_photo_test_only', response.data)
            self.assertNotIn(b'private-provider-detail', response.data)
        self.assertEqual(self.operations, [])

    def test_duplicate_files_and_forged_image_urls_are_rejected(self):
        self.install()
        values = MultiDict(list(management.BASE.items()) + [('csrf_token', self.csrf),
            ('photo', (BytesIO(image_bytes()), 'one.png', 'image/png')),
            ('photo', (BytesIO(image_bytes()), 'two.png', 'image/png'))])
        self.protected(self.client.post('/admin/places/new', data=values, headers=management.ORIGIN), 403)
        self.protected(self.save(image_url='https://foreign.invalid/forged.png'), 403)
        self.assertEqual(self.storage_requests, [])
        self.assertEqual(self.operations, [])

    def test_replacement_and_removal_cannot_be_submitted_together(self):
        self.install(); self.protected(self.save(), 303)
        original = self.records[0]['image_url']
        self.protected(self.save(edit=True, remove_photo='1'), 400)
        self.assertEqual(len(self.storage_requests), 1)
        self.assertEqual(self.records[0]['image_url'], original)
        with patch.dict(os.environ, SUPABASE_STORAGE_SECRET_KEY=''):
            self.protected(self.save(edit=True, file=False, remove_photo='1'), 303)
        self.assertIsNone(self.records[0]['image_url'])

    def test_database_failure_keeps_old_image_and_does_not_delete_uncertain_upload(self):
        self.install(); self.protected(self.save(), 303)
        saved = self.records[0]['image_url']
        self.failure = True
        response = self.save(edit=True)
        self.protected(response, 503)
        self.assertIn(b'destination save could not be confirmed', response.data)
        self.assertEqual(self.records[0]['image_url'], saved)
        self.assertTrue(all(r.method == 'POST' for r in self.storage_requests))
        self.assertNotIn(b'Destination changes saved.', response.data)

    def test_user_cards_and_details_share_updated_url_and_publication_rules(self):
        self.install(); self.protected(self.save(), 303)
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(self.respond), **kwargs)
            self.clients.append(client); return client
        public = PublicPlacesClient('https://example.supabase.co', 'sb_publishable_fixture', http_factory=factory)
        self.app.extensions['rosago_places'] = PlacesService(public.database_client, tourism_metadata_enabled=True)
        self.assertEqual(self.client.get('/places/fixture-destination').status_code, 404)
        self.protected(self.transition('publish'), 303)
        for replacement in (False, True):
            if replacement: self.protected(self.save(edit=True), 303)
            url = self.records[0]['image_url']
            for route in ('/places', '/places/fixture-destination'):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(('src="' + url + '"').encode(), response.data)
                self.assertNotIn(b'sb_secret_photo_test_only', response.data)
        self.protected(self.save(edit=True, file=False, remove_photo='1'), 303)
        response = self.client.get('/places/fixture-destination')
        self.assertNotIn(url.encode(), response.data)
        self.assertIn(b'<svg viewBox="0 0 200 100"', response.data)
        self.protected(self.transition('archive'), 303)
        self.assertEqual(self.client.get('/places/fixture-destination').status_code, 404)
        self.assertNotIn(b'RosaGo Admin Verification Test', self.client.get('/places').data)

    def test_review_sql_preserves_existing_wrapper_and_only_updates_present_image_field(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / 'tools/admin_destination_photo_contract.sql').read_text()
        baseline = (root / 'migrations/0012_admin_management.sql').read_text()
        start = baseline.index('AS $$') + len('AS $$')
        original = baseline[start:baseline.index('$$;', start)].replace('\r', '')
        self.assertIn(hashlib.md5(original.encode()).hexdigest(), sql)
        self.assertIn('differs from the reviewed baseline', sql)
        self.assertIn('CREATE OR REPLACE FUNCTION public.rosago_admin_mutate_destination_unlogged(', sql)
        self.assertIn("IF p_values ? 'image_url' THEN", sql)
        self.assertIn("SET image_url=p_values->>'image_url'", sql)
        self.assertIn('WHERE m.user_id = (SELECT auth.uid()) FOR SHARE', sql)
        self.assertIn('destination.updated_at <> p_expected_updated_at', sql)
        self.assertNotIn('CREATE TABLE', sql)
        self.assertNotIn('CREATE POLICY', sql)
