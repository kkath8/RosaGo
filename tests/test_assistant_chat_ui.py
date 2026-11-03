"""Presentation contracts over existing authenticated assistant fixtures."""
import unittest
import test_ai_routes as ai
from test_public_layout import Document, assert_shared_scripts


class AssistantChatUiTests(unittest.TestCase):
    setUp = ai.AssistantRouteTests.setUp
    tearDown = ai.AssistantRouteTests.tearDown
    seed = ai.AssistantRouteTests.seed
    post = ai.AssistantRouteTests.post

    def test_one_panel_empty_history_and_separate_live_announcer(self):
        page = Document(self.client.get('/user/assistant').get_data(as_text=True))
        panel = page.find('section', **{'class':'conversation-panel'})[0]
        history = page.find('ol', **{'class':'chat-history'})[0]
        self.assertIn(panel, history.ancestors)
        self.assertEqual(panel.attrs['tabindex'], '0')
        self.assertNotIn('aria-live', history.attrs)
        announcer = page.find('p', **{'aria-live':'polite'})[0]
        self.assertNotIn(panel, announcer.ancestors)
        self.assertEqual(announcer.attrs['aria-atomic'], 'true')
        self.assertTrue(any('data-chat-empty' in node.attrs for node in page.find('p')))
        assert_shared_scripts(self, page)
        self.assertEqual(page.stack, [])

    def test_existing_forms_endpoints_and_composer_contract_are_preserved(self):
        page = Document(self.client.get('/user/assistant').get_data(as_text=True))
        send = page.find('form', action='/user/assistant')[0]
        clear = page.find('form', action='/user/assistant/clear')[0]
        for form in (send, clear):
            self.assertEqual(form.attrs['method'], 'post')
            self.assertEqual([node.attrs['value'] for node in page.find('input',name='csrf_token')
                              if form in node.ancestors], [self.csrf])
        self.assertEqual(page.find('textarea',id='assistant-message')[0].attrs['maxlength'],'1000')
        self.assertIn('data-chat-send',send.attrs)
        self.assertIn('data-chat-clear',clear.attrs)

    def test_reply_is_server_escaped_and_keeps_bounded_history(self):
        self.provider.chat.return_value = dict(answer='<script>unsafe reply</script>',destination_ids=[])
        self.assertEqual(self.post('<img src=x>').status_code,303)
        response = self.client.get('/user/assistant')
        self.assertIn(b'&lt;script&gt;unsafe reply&lt;/script&gt;',response.data)
        self.assertNotIn(b'<script>unsafe reply</script>',response.data)
        page=Document(response.get_data(as_text=True))
        self.assertEqual(len(page.find('li',**{'class':'chat-message chat-assistant'})),1)
        self.assertEqual(len(page.find('li',**{'class':'chat-message chat-user'})),1)
        self.assertEqual(page.find('img'),[])

    def test_unconfigured_send_stays_disabled_and_error_is_inside_panel(self):
        self.provider.configured=False
        page=Document(self.client.get('/user/assistant').get_data(as_text=True))
        send=page.find('form',action='/user/assistant')[0]
        self.assertTrue(any('disabled' in node.attrs for node in page.find('button') if send in node.ancestors))
        response=self.post()
        self.assertEqual(response.status_code,503)
        page=Document(response.get_data(as_text=True))
        error=[node for node in page.find('p') if 'data-chat-server-error' in node.attrs][0]
        self.assertIn(page.find('section',**{'class':'conversation-panel'})[0],error.ancestors)
