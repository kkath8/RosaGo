"""Catalog review/filtering and denied mutations through real Admin boundaries."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from admin_places_service import (
    AdminPlacesError, AdminPlacesFilterError, catalog_page, get_destination,
    DETAIL_PROJECTION, PROJECTION, TOURISM_FIELDS, validate_catalog_filters,
)
from normal_auth_coordinator import AuthenticatedContext
from places_service import parse_place_row
import test_admin_authorization as foundation
import test_registration
from test_admin_places import row
from test_public_layout import Document


def record(n=1, **changes):
    return row(slug=f'fixture-{n:03}', name=f'Fixture destination {n}') | dict(
        description='Catalog description <script>unsafe</script>', image_url=None,
        created_at='2026-10-19T04:00:00Z', tourism_type=None, tourism_category=None,
        tourism_opening_hours_raw=None, tourism_closing_hours_raw=None,
        tourism_hours_status=None, tourism_source=None, tourism_source_row=None) | changes


class CatalogReadTests(unittest.TestCase):
    def setUp(self):
        self.query = Mock()
        for key in ('select', 'order', 'range', 'retry', 'eq', 'limit'):
            getattr(self.query, key).return_value = self.query
        self.client = Mock(spec=['table'])
        self.client.table.return_value = self.query
        self.context = AuthenticatedContext('handle', 'user', 'private@example.invalid', self.client, realm='admin')

    def read(self, records, **filters):
        fields = (PROJECTION + ',tourism_type,tourism_category').split(',')
        if filters.get('sort') in ('newest', 'oldest'):
            fields.append('created_at')
        self.query.execute.return_value = SimpleNamespace(count=len(records),
            data=[{key: r[key] for key in fields} for r in records])
        return catalog_page(self.context, tourism_metadata_enabled=True, **filters)

    def test_filters_search_all_requested_fields_and_global_summary(self):
        rows = [record(1, status='published', category='attraction', tourism_type='Local',
                       tourism_category='Theme Park / Recreation', latitude=14.3, longitude=121.1),
                record(2, status='draft', category='dining', tourism_type='Common', address='Paseo fixture'),
                record(3, status='archived', category='heritage')]
        cases = [({'status': 'published'}, rows[:1]), ({'status': 'draft'}, rows[1:2]),
                 ({'status': 'archived'}, rows[2:]), ({'category': 'dining'}, rows[1:2]),
                 ({'tourism_type': 'Local'}, rows[:1]), ({'tourism_type': 'Common'}, rows[1:2]),
                 ({'tourism_type': 'unclassified'}, rows[2:]), ({'coordinates': 'with'}, rows[:1]),
                 ({'coordinates': 'missing'}, rows[1:]), ({'q': 'DESTINATION 1'}, rows[:1]),
                 ({'q': 'paseo'}, rows[1:2]), ({'q': 'heritage'}, rows[2:]),
                 ({'q': 'recreation'}, rows[:1]),
                 ({'status': 'draft', 'category': 'dining', 'tourism_type': 'Common', 'coordinates': 'missing'}, rows[1:2])]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                result = self.read(rows, **filters)
                self.assertEqual([p.slug for p in result.rows], [r['slug'] for r in expected])
                self.assertEqual(result.summary, dict(published=1, draft=1, archived=1, local=1, common=1, missing_coordinates=2))
                self.assertEqual(result.total, 3)
        self.assertEqual(self.read(rows, q='x),status.eq.published').matching, 0)
        self.query.select.assert_called_with(PROJECTION + ',tourism_type,tourism_category', count='exact')
        self.query.retry.assert_called_with(False)
        self.client.table.assert_called_with('places')

    def test_complete_pagination_and_display_pages(self):
        fields = (PROJECTION + ',tourism_type,tourism_category').split(',')
        rows = [{k: record(n)[k] for k in fields} for n in range(205)]
        self.query.execute.side_effect = [SimpleNamespace(count=205, data=rows[:200]),
                                          SimpleNamespace(count=205, data=rows[200:])]
        page = catalog_page(self.context, tourism_metadata_enabled=True, offset=25)
        self.assertEqual((page.total, page.matching, len(page.rows)), (205, 205, 25))
        self.assertEqual(page.rows[0].slug, 'fixture-025')

    def test_incomplete_duplicate_and_oversized_catalog_is_unavailable(self):
        fields = (PROJECTION + ',tourism_type,tourism_category').split(',')
        r = {k: record()[k] for k in fields}
        for count, rows in ((2, [r]), (2, [r, r]), (2001, []), (True, [])):
            self.query.execute.return_value = SimpleNamespace(count=count, data=rows)
            with self.assertRaises(AdminPlacesError):
                catalog_page(self.context, tourism_metadata_enabled=True)

    def test_filter_validation_before_catalog_read(self):
        for values in ({'category': 'invented'}, {'tourism_type': 'local'}, {'status': 'active'},
                       {'coordinates': 'nearby'}, {'q': 'x' * 151}, {'q': '\x00'}, {'offset': True},
                       {'tourism_type': 'Common', 'tourism_metadata_enabled': False}):
            with self.subTest(values=values), self.assertRaises(AdminPlacesFilterError):
                validate_catalog_filters(**({'tourism_metadata_enabled': True} | values))
        self.client.table.assert_not_called()

    def test_sorting_uses_creation_date_and_name_before_display_pagination(self):
        rows = [record(1, name='Zulu', created_at='2026-01-01T00:00:00Z'),
                record(2, name='alpha', created_at='2026-03-01T00:00:00Z'),
                record(3, name='Alpha', created_at='2026-03-01T00:00:00Z')]
        self.assertEqual([p.slug for p in self.read(rows, sort='newest').rows], ['fixture-002','fixture-003','fixture-001'])
        self.assertEqual([p.slug for p in self.read(rows, sort='oldest').rows], ['fixture-001','fixture-002','fixture-003'])
        self.assertEqual([p.slug for p in self.read(rows, sort='name').rows], ['fixture-002','fixture-003','fixture-001'])
        records = [record(n) for n in range(1,32)]
        first = self.read(records, page_size=10)
        second = self.read(records, page_size=10, offset=10)
        self.assertEqual((len(first.rows),len(second.rows),first.matching,first.total), (10,10,31,31))
        self.assertEqual(second.rows[0].slug, 'fixture-011')
        self.assertEqual(len(self.read(records, page_size=50).rows),31)

    def test_invalid_preferences_and_invalid_creation_dates_fail_closed(self):
        for values in ({'page_size':True},{'page_size':1000},{'page_size':'10'},{'sort':'name.desc'},{'sort':[]}):
            with self.subTest(values=values), self.assertRaises(AdminPlacesFilterError):
                validate_catalog_filters(**values)
        self.client.table.assert_not_called()
        for timestamp in ('bad',None,'2026-01-01T00:00:00'):
            with self.subTest(timestamp=timestamp), self.assertRaises(AdminPlacesError):
                self.read([record(created_at=timestamp)], sort='newest')

    def test_detail_validates_shared_metadata_and_coordinates_without_normalizing(self):
        r = record(1, tourism_type='Local', tourism_category='Original category',
                   tourism_opening_hours_raw=' 11:00 AM* ', tourism_closing_hours_raw='Verify',
                   tourism_hours_status='verify_required', tourism_source='City Tourism fixture', tourism_source_row=2)
        self.query.execute.return_value = SimpleNamespace(data=[r])
        p = get_destination(self.context, r['slug'], tourism_metadata_enabled=True)
        self.assertEqual(p.tourism_opening_hours_raw, ' 11:00 AM* ')
        self.assertEqual((p.tourism_type, p.tourism_source_row), ('Local', 2))
        self.query.select.assert_called_with(DETAIL_PROJECTION + ',' + ','.join(TOURISM_FIELDS))
        for changes in ({'tourism_type': 'common'}, {'tourism_hours_status': 'verified'},
                        {'tourism_source_row': True}, {'tourism_source_row': 1},
                        {'latitude': 91, 'longitude': 121}, {'latitude': 14, 'longitude': 181},
                        {'latitude': 14}, {'latitude': float('nan'), 'longitude': 121},
                        {'category': 'invented'}, {'status': 'deleted'}):
            with self.subTest(changes=changes):
                self.query.execute.return_value = SimpleNamespace(data=[r | changes])
                with self.assertRaises(AdminPlacesError):
                    get_destination(self.context, r['slug'], tourism_metadata_enabled=True)

    def test_public_and_admin_models_read_identical_catalog_values(self):
        r = record(1, status='published', tourism_type='Local', tourism_category='Theme Park / Recreation',
                   latitude=14.3, longitude=121.1, tourism_opening_hours_raw='11:00 AM*')
        self.query.execute.return_value = SimpleNamespace(data=[r])
        admin = get_destination(self.context, r['slug'], tourism_metadata_enabled=True)
        public = parse_place_row(r | {'id': '00000000-0000-0000-0000-000000000001'})
        for key in ('name', 'slug', 'description', 'category', 'address', 'latitude', 'longitude', *TOURISM_FIELDS):
            self.assertEqual(getattr(admin, key), getattr(public, key), key)


class DestinationReviewRoutes(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected

    def test_pagination_preferences_keep_filters_and_require_valid_admin_access(self):
        self.install_catalog()
        self.records = [record(n, status='draft') for n in range(1,32)]
        response = self.client.get('/admin/places?sort=newest&page_size=10&status=draft')
        self.protected(response,200)
        page = Document(response.get_data(as_text=True))
        table = page.find('tbody')[0]
        self.assertEqual(len([n for n in page.find('tr') if table in n.ancestors]),10)
        next_link = next(a.attrs['href'] for a in page.find('a') if a.text == 'Next page')
        for fragment in ('sort=newest','page_size=10','status=draft','offset=10'):
            self.assertIn(fragment,next_link)
        self.protected(self.client.get(next_link),200)
        for query in ('sort=bad','page_size=1000','page_size=010','page_size=10&page_size=50'):
            self.protected(self.client.get('/admin/places?'+query),400)
        self.value = False
        self.protected(self.client.get('/admin/places?sort=name&page_size=50'),403)

    def install_catalog(self):
        test_registration.seed_admin_session(self)
        self.value = True
        guard = patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='true')
        guard.start()
        self.addCleanup(guard.stop)
        self.records = [record(1, status='published', category='attraction', tourism_type='Local',
                               tourism_category='Theme Park / Recreation', tourism_hours_status='unverified',
                               tourism_opening_hours_raw='11:00 AM*', tourism_closing_hours_raw='8:00 PM*',
                               tourism_source='City Tourism fixture', tourism_source_row=2, latitude=14.3, longitude=121.1),
                        record(2, status='published', category='dining', tourism_type='Common',
                               tourism_category='Filipino Restaurant'), record(3, status='archived', category='heritage'),
                        record(4, status='draft', category='industrial')]

        def respond(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200, json=self.value)
            self.assertEqual(request.url.path, '/rest/v1/places')
            self.assertEqual(request.method, 'GET')
            self.assertNotIn('or', request.url.params)
            self.assertNotIn('q', request.url.params)
            rows = self.records
            slug = request.url.params.get('slug')
            if slug:
                rows = [r for r in rows if r['slug'] == slug.removeprefix('eq.')]
            fields = request.url.params['select'].split(',')
            offset = int(request.url.params.get('offset', 0))
            limit = int(request.url.params.get('limit', 200))
            return httpx.Response(200, json=[{k: r[k] for k in fields} for r in rows[offset:offset + limit]],
                                  headers={'Content-Range': f'*/{len(rows)}'})
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = factory

    def test_filter_routes_work_and_preserve_selected_values(self):
        self.install_catalog()
        for query, slug in (('status=published&category=dining', 'fixture-002'),
                            ('tourism_type=Local&coordinates=with', 'fixture-001'),
                            ('tourism_type=unclassified&status=archived', 'fixture-003'),
                            ('q=Filipino', 'fixture-002'), ('q=Industrial+Tourism', 'fixture-004')):
            response = self.client.get('/admin/places?' + query)
            self.protected(response, 200)
            page = Document(response.get_data(as_text=True))
            links = [a.attrs['href'] for a in page.find('a') if a.attrs.get('href', '').startswith('/admin/places/fixture-')]
            self.assertEqual(set(links), {f'/admin/places/{slug}', f'/admin/places/{slug}/edit'})
            self.assertEqual(page.stack, [])
        for query in ('status=invalid', 'category=invalid', 'tourism_type=common', 'coordinates=invalid',
                      'q=x&q=y', 'status=draft&status=published', 'q=' + 'x' * 151, 'role=admin'):
            self.requests.clear()
            self.protected(self.client.get('/admin/places?' + query), 400)
            self.assertFalse(any(r.url.path.endswith('/places') for r in self.requests))

    def test_pagination_preserves_combined_filters(self):
        self.install_catalog()
        self.records = [record(n, status='published', category='dining', tourism_type='Common') for n in range(30)]
        response = self.client.get('/admin/places?q=Fixture&status=published&category=dining&tourism_type=Common&coordinates=missing')
        page = Document(response.get_data(as_text=True))
        next_link = next(a for a in page.find('a') if a.text == 'Next page')
        self.assertIn('tourism_type=Common', next_link.attrs['href'])
        self.assertIn('coordinates=missing', next_link.attrs['href'])
        self.assertIn('offset=25', next_link.attrs['href'])
        self.protected(self.client.get(next_link.attrs['href']), 200)

    def test_detail_and_edit_show_metadata_unchanged_and_no_fake_write(self):
        self.install_catalog()
        for suffix in ('', '/edit'):
            response = self.client.get('/admin/places/fixture-001' + suffix)
            self.protected(response, 200)
            for text in (b'Local', b'Theme Park / Recreation', b'11:00 AM*', b'8:00 PM*'):
                self.assertIn(text, response.data)
            self.assertNotIn(b'<script>unsafe</script>', response.data)
            self.assertEqual(len(Document(response.get_data(as_text=True)).find('form')), 2 if suffix else 1)
        page = Document(self.client.get('/admin/places/fixture-001/edit').get_data(as_text=True))
        self.assertTrue(all('readonly' not in n.attrs for n in page.find('input') if n.attrs.get('type') != 'hidden'))
        self.assertTrue(all('disabled' not in n.attrs for n in page.find('select')
                            if n.attrs.get('id') != 'environment'))
        self.assertIn('disabled', page.find('select', id='environment')[0].attrs)
        self.assertIn(b'Coordinates not yet provided.', self.client.get('/admin/places/fixture-002').data)
        self.assertIn(b'Unknown', self.client.get('/admin/places/fixture-003').data)
        self.assertIn(b'Not classified', self.client.get('/admin/places/fixture-003').data)

    def test_only_published_located_rows_link_to_public_map(self):
        self.install_catalog()
        response = self.client.get('/admin/places/fixture-001')
        self.assertIn(b'/map?destination=fixture-001', response.data)
        response = self.client.get('/admin/places/fixture-003')
        self.assertNotIn(b'/map?destination=', response.data)

    def test_admin_and_nonadmin_cannot_mutate_unsupported_operations(self):
        self.install_catalog()
        for member in (True, False):
            self.value = member
            self.requests.clear()
            for path in ('/admin/places/new', '/admin/places/fixture-001/edit', '/admin/places/fixture-001'):
                for method in ('post', 'put', 'patch', 'delete'):
                    self.protected(getattr(self.client, method)(path, data={'name': 'forged', 'status': 'published'}), (403 if method == 'post' and path != '/admin/places/fixture-001' else 405))
            self.assertTrue(all(r.url.path.endswith('/rosago_is_admin') for r in self.requests))
        self.protected(self.client.get('/admin/places'), 403)
        self.protected(self.client.get('/admin/places/fixture-001/edit'), 403)

    def test_disabled_tourism_is_unavailable_and_filters_are_not_fake(self):
        self.install_catalog()
        with patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='false'):
            response = self.client.get('/admin/places')
            self.protected(response, 200)
            self.assertNotIn(b'id="catalog-tourism"', response.data)
            self.assertIn(b'Tourism metadata is not enabled', response.data)
            self.protected(self.client.get('/admin/places?tourism_type=unclassified'), 400)
