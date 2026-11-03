"""Explore structure contracts; published-only service behavior is unchanged."""
import unittest
from dataclasses import replace
import test_places_routes as places
from test_public_layout import Document


class ExploreSaveUiTests(unittest.TestCase):
    setUp = places.PlacesRouteTests.setUp
    tearDown = places.PlacesRouteTests.tearDown
    get = places.PlacesRouteTests.get

    def test_filters_precede_full_width_results_without_sidebar(self):
        page = Document(self.get('/places').get_data(as_text=True))
        row = page.find('div', **{'class': 'explore-layout'})[0]
        filters=page.find('section', **{'class': 'explore-filters'})[0]
        self.assertIn(row, filters.ancestors)
        self.assertEqual(page.find('aside', **{'class': 'explore-filters'}), [])
        self.assertLess(page.elements.index(filters),page.elements.index(page.find('section', **{'class': 'explore-results'})[0]))
        self.assertIn(row, page.find('section', **{'class': 'explore-results'})[0].ancestors)
        self.assertLess(page.elements.index(page.find('p', **{'class': 'destination-result-count'})[0]),
                        page.elements.index(page.find('ul', **{'class': 'places-grid'})[0]))

    def test_card_actions_share_row_and_save_is_non_submitting_toggle(self):
        page = Document(self.get('/places').get_data(as_text=True))
        actions = page.find('div', **{'class': 'destination-card-actions'})[0]
        details = page.find('a', href='/places/synthetic-place')[0]
        save = page.find('button', **{'data-action': 'save'})[0]
        self.assertIn(actions, details.ancestors)
        self.assertIn(actions, save.ancestors)
        self.assertEqual(save.attrs['type'], 'button')
        self.assertEqual(save.attrs['aria-pressed'], 'false')
        self.assertFalse(any(node.tag == 'form' for node in save.ancestors))
        self.assertNotIn('data-open-dialog', save.attrs)
        self.assertEqual(save.attrs['data-id'], self.place.id)

    def test_category_search_fields_and_real_card_identity_remain(self):
        self.service.list_published.return_value = (replace(self.place, category='dining'),)
        page = Document(self.get('/places?category=dining&q=Synthetic').get_data(as_text=True))
        self.assertEqual(page.find('input', name='category')[0].attrs['value'], 'dining')
        self.assertEqual(page.find('input', name='q')[0].attrs['value'], 'Synthetic')
        nav = page.find('nav', **{'class': 'category-nav'})[0]
        self.assertEqual([node.text for node in page.find('a') if nav in node.ancestors
                          and 'aria-current' in node.attrs], ['Dining'])
        self.assertEqual(page.find('article', **{'class': 'place-card'})[0].attrs['data-place-id'], self.place.id)
