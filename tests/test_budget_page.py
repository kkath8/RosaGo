"""Budget direct-entry scope and script contracts over existing route fixtures."""
import unittest
import test_user_features as features
from test_public_layout import Document,assert_shared_scripts

class BudgetPageTests(unittest.TestCase):
 setUp=features.UserFeatureTests.setUp
 tearDown=features.UserFeatureTests.tearDown
 seed=features.UserFeatureTests.seed
 def test_authenticated_direct_entry_has_verified_scope(self):
  response=self.client.get('/budget')
  self.assertEqual(response.headers['Cache-Control'],'private, no-store')
  page=Document(response.get_data(as_text=True))
  body=page.find('body')[0]
  self.assertEqual(body.attrs['data-authenticated'],'true')
  self.assertRegex(body.attrs['data-ui-scope'],r'^[a-f0-9]{24}$')
  assert_shared_scripts(self,page)
  for service in self.services.values():service.assert_not_called()
 def test_guest_keeps_personal_planning_and_own_scope(self):
  with self.client.session_transaction() as session:session.clear()
  page=Document(self.client.get('/budget').get_data(as_text=True))
  self.assertEqual(page.find('body')[0].attrs['data-ui-scope'],'guest')
  self.assertTrue(page.find('form',id='budget-plan-form'))
