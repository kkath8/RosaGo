"""Presentation contracts using protected preview fixtures; no external I/O."""
from dataclasses import replace
import unittest
import test_itinerary_preview_routes as preview
from test_public_layout import Document


class PreviewLayoutTests(unittest.TestCase):
    setUp = preview.PreviewRouteTests.setUp
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview
    ready = preview.PreviewRouteTests.ready

    def test_primary_content_and_collapsed_support(self):
        self.ready()
        page = Document(self.client.get(preview.PREVIEW).get_data(as_text=True))
        actions = page.find('div', **{'class': 'preview-top-actions'})[0]
        self.assertIn('Edit Preferences', actions.text)
        self.assertTrue(any('data-open-save' in a.attrs
                            for a in page.find('a', href='#preview-save')))
        self.assertNotIn('open', page.find('details', id='preview-save')[0].attrs)
        self.assertNotIn('open', page.find('details', **{'class': 'preview-ai-about'})[0].attrs)
        self.assertIn('hidden', page.find('div', **{'class': 'preview-chat'})[0].attrs)
        self.assertEqual(len(page.find('section', id='preview-assistant')), 1)
        self.assertFalse(page.find('h2', id='preview-adjust-title'))
        self.assertEqual(page.stack, [])

    def test_card_metadata_reason_and_map_use_actual_destination(self):
        self.match = replace(self.match, tourism_type='Local', tourism_category='Heritage')
        self.catalog.list_published.return_value = (self.match,)
        self.ready()
        page = Document(self.client.get(preview.PREVIEW).get_data(as_text=True))
        card = page.find('article', **{'class': 'preview-stop'})[0]
        self.assertIn('Stop 1', card.text)
        self.assertIn('Recommended', card.text)
        self.assertIn('Attractions · Local', card.text)
        self.assertIn('Matches your Attractions interest.', card.text)
        self.assertNotIn('Matches your Heritage interest.', card.text)
        self.assertTrue(page.find('a', href='/map?destination=matched-place'))
        self.assertTrue(page.find('a', href='/places/matched-place'))
        self.assertLess(page.elements.index(page.find('h2', id='recommended-title')[0]),
                        page.elements.index(page.find('h2', id='preview-ai-title')[0]))

    def test_category_reason_is_absent_without_selected_interest_evidence(self):
        # A stored manual selection can include a category outside the interests.
        self.ready((self.other,))
        page = Document(self.client.get(preview.PREVIEW).get_data(as_text=True))
        card = page.find('article', **{'class': 'preview-stop'})[0]
        self.assertNotIn('Matches your', card.text)
        self.assertIn('Dining', card.text)
