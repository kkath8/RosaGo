"""Local preview rendering/access boundaries; real account/provider I/O forbidden."""
import socket
import sys
import os
import runpy
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_public_layout import Document
from catalog_preview import create_app,preview_image_path


class CatalogPreviewTests(unittest.TestCase):
    def setUp(self):
        for target,name in ((socket.socket,'connect'),(socket,'create_connection')):
            guard=patch.object(target,name,side_effect=AssertionError('Network prohibited'))
            guard.start();self.addCleanup(guard.stop)
        self.app=create_app({'ROSAGO_CATALOG_PREVIEW':'true'});self.app.testing=True
        self.client=self.app.test_client()

    def get(self,path,**kwargs):
        response=self.client.get(path,environ_base={'REMOTE_ADDR':'127.0.0.1'},**kwargs)
        self.assertNotIn('Set-Cookie',response.headers)
        self.addCleanup(response.close)
        return response

    def test_exact_98_cards_include_draft_labels_and_82_local_images(self):
        response=self.get('/places');self.assertEqual(response.status_code,200)
        page=Document(response.get_data(as_text=True))
        self.assertEqual(len(page.find('article',**{'class':'place-card'})),98)
        images=page.find('img',**{'data-destination-image':None})
        self.assertEqual(sum(i.attrs['src'].startswith('/preview/images/') for i in images),82)
        self.assertEqual(sum(i.attrs['src']=='/static/img/destination-placeholder.svg' for i in images),16)
        html=response.get_data(as_text=True)
        self.assertIn('Draft',html);self.assertIn('Proposed Published',html)
        self.assertNotIn('supabase.co',html);self.assertNotIn('data-add-to-trip',html)
        self.assertNotIn('/js/user-ui.js',html);self.assertNotIn('fonts.googleapis',html)

    def test_all_98_details_and_prepared_image_routes_preserve_holds(self):
        for place in self.app.extensions['rosago_catalog_preview']['places']:
            response=self.get('/places/'+place.slug)
            self.assertEqual(response.status_code,200)
            self.assertNotIn('Private Notes',response.get_data(as_text=True))
        for number in (1,3,22):
            response=self.get('/preview/images/'+str(number))
            self.assertEqual(response.status_code,200);self.assertIn(response.mimetype,('image/jpeg','image/png','image/webp'))
        for number in (56,58,65,999):self.assertEqual(self.get('/preview/images/'+str(number)).status_code,404)

    def test_search_category_and_simulation_are_functional_read_only_views(self):
        response=self.get('/places?q=Nuvali')
        self.assertGreater(len(Document(response.get_data(as_text=True)).find('article',**{'class':'place-card'})),0)
        self.assertEqual(self.get('/places?category=resort-swimming-pool').status_code,200)
        self.assertEqual(self.get('/places?category=not-registered').status_code,400)
        response=self.get('/user/planner?interest=attraction&stops=12')
        page=Document(response.get_data(as_text=True));cards=page.find('article',**{'class':'place-card'})
        self.assertLessEqual(len(cards),12);self.assertGreater(len(cards),0)
        details=self.app.extensions['rosago_catalog_preview']['details']
        selected={r['number'] for r in details.values() if r['first_batch']}
        self.assertTrue(all(int(c.attrs['data-place-id'].rsplit('-',1)[1]) in selected for c in cards))
        self.assertIn('Nothing is saved',response.get_data(as_text=True))
        self.assertEqual(self.get('/user/planner?stops=999').status_code,400)

    def test_auth_and_mutation_endpoints_are_not_present_in_preview(self):
        for path in ('/login','/admin','/api/places','/user/trips','/api/user/avatar','/api/route'):
            self.assertEqual(self.get(path).status_code,404)
            self.assertEqual(self.client.post(path,environ_base={'REMOTE_ADDR':'127.0.0.1'}).status_code,405)
        response=self.get('/places',headers={'Cookie':'rosago_session=do-not-use-this-account-cookie'})
        self.assertNotIn('do-not-use-this-account-cookie',response.get_data(as_text=True))
        self.assertIn("connect-src 'none'",response.headers['Content-Security-Policy'])

    def test_opt_in_production_remote_and_forwarded_requests_fail_closed(self):
        for env in ({},{'ROSAGO_CATALOG_PREVIEW':'false'},
                    {'ROSAGO_CATALOG_PREVIEW':'true','RENDER':'true'},
                    {'ROSAGO_CATALOG_PREVIEW':'true','ROSAGO_AUTH_MODE':'production'},
                    {'ROSAGO_CATALOG_PREVIEW':'true','FLASK_RUN_HOST':'0.0.0.0'}):
            with self.subTest(env=env),self.assertRaises(RuntimeError):create_app(env)
        self.assertEqual(self.client.get('/places',environ_base={'REMOTE_ADDR':'192.0.2.1'}).status_code,403)
        self.assertEqual(self.get('/places',headers={'Host':'example.invalid'}).status_code,403)
        self.assertEqual(self.get('/places',headers={'X-Forwarded-For':'127.0.0.1'}).status_code,403)

    def test_no_arbitrary_file_or_path_traversal_is_served(self):
        with self.assertRaises(RuntimeError):preview_image_path({'staged_file':'local_catalog/../.env'})
        for path in ('/static/../.env','/static/images/destinations/NuvaliSandCourts.jpg','/static/css/../../app.py'):
            self.assertEqual(self.get(path).status_code,404)

    def test_normal_launcher_rejects_production_preview_before_creating_provider_client(self):
        with patch.dict(os.environ,{'ROSAGO_CATALOG_PREVIEW':'true','ROSAGO_EVALUATION':'false','RENDER':'true'}),patch('dotenv.load_dotenv'),patch('supabase.create_client') as client:
            with self.assertRaisesRegex(RuntimeError,'local development mode'):
                runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'))
            client.assert_not_called()


if __name__=='__main__':unittest.main()
