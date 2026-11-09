"""Normal Flask integration with synthetic SDK; never signs in or contacts Supabase."""
import os
from pathlib import Path
import runpy
import socket
import sys
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_public_layout import Document
from catalog_preview import install_catalog_preview

ROOT=Path(__file__).resolve().parents[1]


def normal_app(preview=True):
    sdk=Mock()
    with patch.dict(os.environ,{'ROSAGO_CATALOG_PREVIEW':'true' if preview else 'false',
            'ROSAGO_EVALUATION':'false','ROSAGO_AUTH_MODE':'development',
            'SUPABASE_URL':'https://fixture.invalid','SUPABASE_KEY':'sb_publishable_synthetic_preview',
            'FLASK_SECRET_KEY':'synthetic-integrated-preview-only'},clear=True),\
            patch('dotenv.load_dotenv'),patch('supabase.create_client',return_value=sdk):
        app=runpy.run_path(str(ROOT/'app.py'))['app']
    app.testing=True
    return app,sdk


class IntegratedCatalogPreviewTests(unittest.TestCase):
    def setUp(self):
        for target,name in ((socket.socket,'connect'),(socket,'create_connection')):
            guard=patch.object(target,name,side_effect=AssertionError('Network prohibited'))
            guard.start();self.addCleanup(guard.stop)
        self.app,self.sdk=normal_app();self.client=self.app.test_client()
        self.original_service=self.app.extensions['rosago_places']
        self.guard=patch.object(self.original_service,'list_published',side_effect=AssertionError('Preview must not read hosted catalog'))
        self.guard.start();self.addCleanup(self.guard.stop)
        self.addCleanup(lambda:self.assertEqual(self.sdk.mock_calls,[]))

    def get(self,path,**kwargs):
        response=self.client.get(path,**kwargs);self.addCleanup(response.close);return response

    def test_normal_explore_and_detail_render_prepared_catalog_without_replacing_service(self):
        response=self.get('/places');self.assertEqual(response.status_code,200)
        page=Document(response.get_data(as_text=True))
        self.assertEqual(len(page.find('article',**{'class':'place-card'})),98)
        self.assertEqual(sum(n.attrs['src'].startswith('/preview/images/') for n in page.find('img')),82)
        self.assertIs(self.app.extensions['rosago_places'],self.original_service)
        for path in ('/places/nuvali','/places/nuvali-sand-courts','/preview/images/1'):
            self.assertEqual(self.get(path).status_code,200)
        self.assertEqual(self.get('/preview/images/56').status_code,404)
        self.assertIn('/preview/planner',response.get_data(as_text=True))
        self.assertIn('/admin',response.get_data(as_text=True))

    def test_real_planner_and_admin_remain_protected_simulation_is_distinct(self):
        for path in ('/user/planner','/user/trips','/admin','/admin/places'):
            response=self.get(path)
            self.assertIn(response.status_code,(302,303))
            self.assertIn('login',response.headers['Location'])
        response=self.get('/preview/planner?interest=dining&stops=3')
        self.assertEqual(response.status_code,200)
        self.assertIn('Planner simulation',response.get_data(as_text=True))
        self.assertEqual(len(Document(response.get_data(as_text=True)).find('article',**{'class':'place-card'})),3)

    def test_data_writes_and_signin_fail_before_any_original_handler_runs(self):
        for path in ('/user/trips','/user/itinerary/start','/admin/places/new','/login','/api/route','/user/bag'):
            response=self.client.post(path)
            self.assertEqual(response.status_code,403)
            self.assertIn(b'read-only',response.data)

    def test_logout_reaches_existing_auth_checks_and_invalid_sessions_are_not_bypassed(self):
        # No identity/login fixture is installed. The original protected logout
        # redirects a guest instead of the read-only guard granting authority.
        response=self.client.post('/admin/logout')
        self.assertIn(response.status_code,(302,303));self.assertIn('login',response.headers['Location'])
        # Existing Admin realm rejects its invalid cookie on its own protected path.
        self.client.set_cookie(self.app.session_interface.cookie_name,'invalid',path='/admin')
        response=self.get('/admin')
        self.assertEqual(response.status_code,403)

    def test_remote_preview_and_proxy_requests_are_denied(self):
        self.assertEqual(self.get('/places',headers={'Host':'example.invalid'}).status_code,403)
        self.assertEqual(self.get('/places',headers={'X-Forwarded-For':'127.0.0.1'}).status_code,403)
        self.assertEqual(self.client.get('/places',environ_base={'REMOTE_ADDR':'192.0.2.9'}).status_code,403)

    def test_off_mode_keeps_routes_and_services_and_does_not_load_local_inputs(self):
        with patch('catalog_preview.load_preview',side_effect=AssertionError('Disabled preview loaded')):
            normal,_=normal_app(preview=False)
        self.assertNotIn('rosago_catalog_preview',normal.extensions)
        normal_rules={r.rule for r in normal.url_map.iter_rules()}
        active_rules={r.rule for r in self.app.url_map.iter_rules()}
        self.assertTrue(normal_rules<=active_rules)
        self.assertEqual(active_rules-normal_rules,{'/preview/planner','/preview/images/<int:number>'})
        service=Mock();service.list_published.return_value=()
        normal.extensions['rosago_places']=service
        response=normal.test_client().get('/places')
        self.assertEqual(response.status_code,200);service.list_published.assert_called()
        self.assertNotIn('Local catalog preview',response.get_data(as_text=True))


if __name__=='__main__':unittest.main()
