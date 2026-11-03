"""AI routes with verified auth fixtures; Gemini and all network access mocked."""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import Mock
import unittest

import httpx
from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

from gemini_service import GeminiService
from normal_auth_coordinator import AuthenticatedContext
from assistant_store import MAX_HISTORY_CHARS, MAX_MESSAGES
from places_service import PlacesUnavailableError
from test_public_layout import Document, assert_shared_scripts
from test_recommendation_engine import place
import test_trip_routes as trips
import test_itinerary_recommendations as recommendations
import test_itinerary_preview_routes as preview


def mocked_gemini(output=None, *, error=None, status=200):
    def handle(request):
        if error:
            raise error
        return httpx.Response(status, json={'candidates': [{'finishReason': 'STOP',
            'content': {'parts': [{'text': json.dumps(output)}]}}]})
    return GeminiService('private-gemini-fixture-key',
        http_factory=lambda **options: httpx.Client(transport=httpx.MockTransport(handle), **options))


class PreviewAIExplanationTests(unittest.TestCase):
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview
    ready = preview.PreviewRouteTests.ready

    def setUp(self):
        preview.PreviewRouteTests.setUp(self)
        self.ready()
        self.path = preview.PREVIEW + '/explain'
        self.provider = Mock(configured=True)
        self.provider.explain.return_value = dict(summary='Existing selections explained.', explanations=[
            dict(place_id=self.match.id, name=self.match.name, reason='Matches your attraction interest.')])
        self.app.extensions['rosago_gemini'] = self.provider

    def explain(self, data=None, headers=preview.ORIGIN):
        return self.client.post(self.path, headers=headers, data=data if data is not None else
            {'csrf_token': self.csrf, 'expected_revision': '3'})

    def test_preview_action_and_stored_selection_order_only_without_mutation(self):
        later = replace(place(8, 'attraction'), name='Later selected', slug='later-selected')
        self.ready((later, self.match))
        self.catalog.list_published.return_value = (self.other, self.match, later)
        before = deepcopy(self.current)
        page = self.client.get(preview.PREVIEW)
        self.assertIn(self.path.encode(), page.data)
        self.assertIn(b'Why these places?', page.data)
        self.provider.explain.assert_not_called()
        response = self.explain()
        self.assertEqual(response.status_code, 200)
        context = self.provider.explain.call_args.args[0]
        self.assertEqual([p['place_id'] for p in context['candidates']], [later.id, self.match.id])
        self.assertEqual(context['interests'], self.current.preferences['interests'])
        self.assertIn('not evaluated', context['selection_method'])
        self.assertNotIn(self.other.id, str(context))
        self.assertIn(b'Matches your attraction interest.', response.data)
        self.assertNotIn(b'Existing selections explained.', response.data)
        self.provider.explain.assert_called_once_with(context, per_destination=True)
        cards = Document(response.get_data(as_text=True)).find('article', **{'class': 'preview-stop'})
        self.assertEqual(len(cards), 2)
        chat = Document(response.get_data(as_text=True)).find('div', **{'class': 'preview-chat'})[0]
        self.assertIn('unavailable for this destination', chat.text)
        self.assertNotIn('Matches your attraction interest.', cards[0].text)
        self.assertIn('Matches your attraction interest.', chat.text)
        self.assertLess(response.data.index(b'preview-days'), response.data.index(b'id="preview-assistant"'))
        self.assertEqual(self.current, before)
        self.engine.assert_not_called(); self.adapter.assert_not_called()
        self.store.assert_not_called(); self.edit.assert_not_called()
        self.assertTrue(any(n.text.strip() == 'Planner' and n.attrs.get('aria-current') == 'true'
                            for n in Document(response.get_data(as_text=True)).find('a')))

    def test_authentication_origin_csrf_and_exact_bounded_form(self):
        self.assertEqual(self.client.get(self.path).status_code, 405)
        for data, headers, status in [({}, preview.ORIGIN, 403),
            ({'csrf_token': 'bad', 'expected_revision': '3'}, preview.ORIGIN, 403),
            ({'csrf_token': self.csrf, 'expected_revision': '3'}, {}, 403),
            ({'csrf_token': self.csrf, 'expected_revision': '3'}, {'Origin': 'https://foreign.invalid'}, 403),
            ({'csrf_token': self.csrf, 'expected_revision': '3', 'selected_place_ids': self.other.id}, preview.ORIGIN, 400),
            ({'csrf_token': self.csrf, 'expected_revision': 'bad'}, preview.ORIGIN, 400),
            (MultiDict([('csrf_token', self.csrf), ('expected_revision', '3'), ('expected_revision', '3')]), preview.ORIGIN, 400)]:
            self.assertEqual(self.explain(data, headers).status_code, status)
        self.assertEqual(self.explain({'csrf_token': self.csrf, 'expected_revision': '3', 'extra': 'x'*5000}).status_code, 413)
        self.provider.explain.assert_not_called()
        self.preview_read.assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.explain().status_code, 302)

    def test_revision_mismatch_preserves_current_preview_without_provider_call(self):
        before = deepcopy(self.current)
        response = self.explain({'csrf_token': self.csrf, 'expected_revision': '2'})
        self.assertEqual(response.status_code, 409)
        self.assertIn(b'Your preview changed.', response.data)
        self.assertIn(b'Matched &lt;Place&gt;', response.data)
        self.provider.explain.assert_not_called()
        self.assertEqual(self.current, before)

    def test_missing_expired_and_wrong_lifecycle_drafts_are_rejected(self):
        foreign = self.client.post(self.path.replace(trips.TRIP, trips.OWNER),
            headers=preview.ORIGIN, data={'csrf_token': self.csrf, 'expected_revision': '3'})
        self.assertEqual(foreign.status_code, 404)
        self.assertIn(b'Draft not found.', foreign.data)
        original = self.current
        for state in ('editing', 'generating', 'failed', 'saved', 'expired'):
            self.current = replace(original, state=state)
            self.assertEqual(self.explain().status_code, 409)
        self.current = replace(original, expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(self.explain().status_code, 409)
        self.preview_read.side_effect = None
        self.preview_read.return_value = None
        self.assertEqual(self.explain().status_code, 404)
        self.provider.explain.assert_not_called()

    def test_changed_missing_and_unavailable_catalog_never_calls_provider_or_writes(self):
        before = deepcopy(self.current)
        for catalog in [(), (self.other,), (replace(self.match, name='Changed'),),
                        (replace(self.match, category='dining'),)]:
            self.catalog.list_published.return_value = catalog
            self.assertEqual(self.explain().status_code, 409)
        self.catalog.list_published.side_effect = PlacesUnavailableError()
        self.assertEqual(self.explain().status_code, 503)
        self.provider.explain.assert_not_called()
        self.assertEqual(self.current, before)
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_unconfigured_and_provider_failures_leave_itinerary_visible_and_unchanged(self):
        before = deepcopy(self.current)
        for provider in [GeminiService(), mocked_gemini(error=httpx.ReadTimeout('private-key')),
                         mocked_gemini(status=429), mocked_gemini(output={'bad': True}),
                         mocked_gemini(output={'summary':'Unknown', 'explanations':[
                             {'place_id':'unknown','matched_interest':'attraction','reason':'Invented'}]})]:
            self.app.extensions['rosago_gemini'] = provider
            response = self.explain()
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Your itinerary remains unchanged and usable.', response.data)
            self.assertIn(b'Matched &lt;Place&gt;', response.data)
            self.assertNotIn(b'private-key', response.data)
            self.assertEqual(self.current, before)
        self.app.extensions['rosago_gemini'] = GeminiService()
        page = self.client.get(preview.PREVIEW)
        self.assertNotIn(self.path.encode(), page.data)
        self.assertIn(b'Your itinerary remains usable.', page.data)
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_ai_output_is_escaped_on_preview_and_not_persisted(self):
        self.provider.explain.return_value = dict(summary='<script>unsafe summary</script>', explanations=[
            dict(place_id=self.match.id, name=self.match.name, reason='<img src=x onerror=alert(1)>')])
        before = deepcopy(self.current)
        response = self.explain()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'unsafe summary', response.data)
        self.assertIn(b'&lt;img src=x onerror=alert(1)&gt;', response.data)
        page = Document(response.get_data(as_text=True))
        assert_shared_scripts(self,page)
        self.assertEqual(page.find('img'), [])
        self.assertEqual(self.current, before)
        self.assertNotIn(b'unsafe summary', self.client.get(preview.PREVIEW).data)

    def test_structured_multi_place_response_maps_to_cards_without_reordering(self):
        later = replace(place(8, 'attraction'), name='Later selected', slug='later-selected')
        self.ready((later, self.match))
        self.catalog.list_published.return_value = (self.other, self.match, later)
        before = deepcopy(self.current)
        self.app.extensions['rosago_gemini'] = mocked_gemini(output={'explanations': [
            dict(place_id=self.match.id, matched_interest='attraction', reason='Reason for matched place.'),
            dict(place_id=later.id, matched_interest='attraction', reason='Reason for later place.')]})
        response = self.explain()
        self.assertEqual(response.status_code, 200)
        cards = Document(response.get_data(as_text=True)).find('article', **{'class': 'preview-stop'})
        self.assertIn('Later selected', cards[0].text)
        chat = Document(response.get_data(as_text=True)).find('div', **{'class': 'preview-chat'})[0]
        self.assertIn('Reason for later place.', chat.text)
        self.assertNotIn('Reason for matched place.', cards[0].text)
        self.assertIn('Reason for matched place.', chat.text)
        self.assertLess(chat.text.index('Reason for later place.'), chat.text.index('Reason for matched place.'))
        for card in cards:
            self.assertIn('Why it fits your trip:', card.text)
            self.assertNotIn('Reason for', card.text)
        self.assertEqual(self.current, before)
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_partial_and_invalid_rows_only_affect_their_explanation(self):
        later = replace(place(8, 'attraction'), name='Later selected', slug='later-selected')
        self.ready((later, self.match))
        self.catalog.list_published.return_value = (self.other, self.match, later)
        valid = dict(place_id=later.id, matched_interest='attraction', reason='Valid later reason.')
        for bad in ([], [None], [dict(place_id=self.other.id, matched_interest='dining', reason='Foreign reason.')],
                    [dict(place_id=self.match.id, matched_interest='attraction', reason=42)]):
            self.app.extensions['rosago_gemini'] = mocked_gemini(output={'explanations': [valid] + bad})
            response = self.explain()
            self.assertEqual(response.status_code, 200)
            cards = Document(response.get_data(as_text=True)).find('article', **{'class': 'preview-stop'})
            self.assertEqual(len(cards), 2)
            chat = Document(response.get_data(as_text=True)).find('div', **{'class': 'preview-chat'})[0]
            self.assertIn('Valid later reason.', chat.text)
            self.assertIn('unavailable for this destination', chat.text)
            self.assertNotIn(b'Foreign reason.', response.data)

    def test_request_limit_keeps_every_selected_card_visible(self):
        selected = tuple(replace(place(n, 'attraction'), name=f'Selected {n}') for n in range(20, 33))
        self.ready(selected)
        self.catalog.list_published.return_value = selected
        response = self.explain()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.provider.explain.call_args.args[0]['candidates']), 12)
        self.assertEqual(len(Document(response.get_data(as_text=True)).find(
            'article', **{'class': 'preview-stop'})), 13)
        self.assertIn(b'Selected 32', response.data)


class AIRecommendationRouteTests(unittest.TestCase):
    tearDown = recommendations.RecommendationRouteTests.tearDown
    seed = trips.TripRouteTests.seed

    def setUp(self):
        recommendations.RecommendationRouteTests.setUp(self)
        self.provider = Mock(configured=True)
        self.provider.explain.return_value = dict(summary='A useful category match.', explanations=[
            dict(place_id=self.match.id, name=self.match.name, reason='Matches the chosen category.')])
        self.app.extensions['rosago_gemini'] = self.provider
        self.path = recommendations.ROUTE + '/explain'

    def explain(self, **kwargs):
        return self.client.post(self.path, data={'csrf_token': self.csrf, 'expected_revision': '2'}, **kwargs)

    def test_explicit_explanation_preserves_deterministic_candidates_and_ranking(self):
        self.assertEqual(self.client.get(recommendations.ROUTE).status_code, 200)
        self.provider.explain.assert_not_called()
        self.engine.reset_mock()
        response = self.explain()
        self.assertEqual(response.status_code, 200)
        self.engine.assert_called_once_with(self.draft.preferences, (self.other, self.match))
        context = self.provider.explain.call_args.args[0]
        self.assertEqual([p['place_id'] for p in context['candidates']], [self.match.id])
        self.assertNotIn('companion_type', context)
        self.assertNotIn(b'A useful category match.', response.data)
        self.assertNotIn(b'Optional AI explanation',response.data)
        self.assertIn(b'Matched &lt;Place&gt;', response.data)
        self.assertNotIn(b'Unmatched dining', response.data)
        page = Document(response.get_data(as_text=True))
        self.assertEqual([n.attrs['value'] for n in page.find('input', type='checkbox', name='selected_place_ids')], [self.match.id])

    def test_no_key_timeout_quota_malformed_and_unknown_ids_keep_recommendations(self):
        unknown = dict(summary='Invented answer', explanations=[dict(place_id='unknown',
            matched_interest='attraction', reason='Unsupported destination.')])
        for provider in (GeminiService(), mocked_gemini(error=httpx.ReadTimeout('private-key')),
                         mocked_gemini(status=429), mocked_gemini(output={'bad': True}), mocked_gemini(output=unknown)):
            self.app.extensions['rosago_gemini'] = provider
            response = self.explain()
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Personalized recommendations', response.data)
            self.assertIn(b'Matched &lt;Place&gt;', response.data)
            self.assertNotIn(b'Unsupported destination.', response.data)
            self.assertNotIn(b'private-key', response.data)

    def test_explanation_auth_csrf_origin_fields_and_revision_checks(self):
        self.assertEqual(self.client.get(self.path).status_code, 405)
        for data, headers, status in [({}, {}, 403),
            ({'csrf_token': 'bad', 'expected_revision': '2'}, {}, 403),
            ({'csrf_token': self.csrf, 'expected_revision': '2'}, {'Origin': 'https://foreign.invalid'}, 403),
            ({'csrf_token': self.csrf, 'expected_revision': '2', 'extra': 'value'}, {}, 400),
            ({'csrf_token': self.csrf, 'expected_revision': 'bad'}, {}, 400),
            ({'csrf_token': self.csrf, 'expected_revision': '1'}, {}, 409)]:
            response = self.client.post(self.path, data=data, headers=headers)
            self.assertEqual(response.status_code, status)
        self.provider.explain.assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.explain().status_code, 302)

    def test_ai_text_is_escaped(self):
        self.provider.explain.return_value['summary'] = '<script>unsafe summary</script>'
        self.provider.explain.return_value['explanations'][0]['reason'] = '<img src=x onerror=alert(1)>'
        html = self.explain().get_data(as_text=True)
        self.assertNotIn('unsafe summary', html)
        self.assertNotIn('<img src=x onerror=alert(1)>',html)
        assert_shared_scripts(self,Document(html))
        self.assertEqual(Document(html).find('img'), [])


class AssistantRouteTests(unittest.TestCase):
    tearDown = trips.TripRouteTests.tearDown
    seed = trips.TripRouteTests.seed

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.provider = Mock(configured=True)
        self.provider.chat.return_value = dict(answer='Open Explore to review catalog places.', destination_ids=[])
        self.app.extensions['rosago_gemini'] = self.provider
        self.catalog = Mock(list_published=Mock(return_value=(place(1, 'heritage'),)))
        self.weather = Mock(get_weather=Mock(return_value=None))
        self.routing = Mock(label='OSRM', modes=('driving',))
        self.app.extensions['rosago_places'] = self.catalog
        self.app.extensions['rosago_weather'] = self.weather
        self.app.extensions['rosago_routing'] = self.routing

    def post(self, message='How do I plan a trip?', **kwargs):
        return self.client.post('/user/assistant', data={'csrf_token': self.csrf, 'message': message}, **kwargs)

    def test_get_is_private_and_does_not_call_gemini_or_catalog(self):
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(any(isinstance(value, AuthenticatedContext) for value in context.values()))
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get('/user/assistant')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
        page = Document(response.get_data(as_text=True))
        self.assertEqual(len(page.find('h1')), 1)
        self.assertEqual(page.stack, [])
        self.assertTrue(page.find('a', href='/user/assistant', **{'aria-current': 'page'}))
        self.provider.chat.assert_not_called()
        self.catalog.list_published.assert_not_called()
        self.weather.get_weather.assert_not_called()

    def test_anonymous_access_is_rejected_before_ai_context_reads(self):
        for state in ({}, {'user_id': trips.OWNER}, {'auth_session_id': 'stale'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            self.assertEqual(self.client.get('/user/assistant').status_code, 302)
            self.assertEqual(self.post().status_code, 302)
            self.assertEqual(self.client.post('/user/assistant/clear', data={'csrf_token': self.csrf}).status_code, 302)
        self.provider.chat.assert_not_called()
        self.catalog.list_published.assert_not_called()

    def test_valid_post_grounding_and_redirect_without_prompt_in_cookie(self):
        response = self.post(headers={'Origin': 'http://localhost'})
        self.assertEqual((response.status_code, response.location), (303, '/user/assistant'))
        context = self.provider.chat.call_args.args[0]
        self.assertEqual(context['catalog'][0]['place_id'], self.catalog.list_published.return_value[0].id)
        self.assertEqual(context['transport']['supported_modes'], ['driving'])
        self.assertIsNone(context['transport']['calculated_route'])
        self.assertNotIn('private-access', json.dumps(context))
        self.assertNotIn('fixture@example.invalid', json.dumps(context))
        self.weather.get_weather.assert_not_called()
        self.routing.route.assert_not_called()
        html = self.client.get('/user/assistant').get_data(as_text=True)
        self.assertIn('Open Explore to review catalog places.', html)
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {'auth_session_id'})

    def test_csrf_origin_blank_oversized_duplicate_and_invalid_input(self):
        for data, headers, status in [({}, {}, 403),
            ({'csrf_token': 'wrong', 'message': 'hello'}, {}, 403),
            ({'csrf_token': self.csrf, 'message': 'hello'}, {'Origin': 'null'}, 403),
            ({'csrf_token': self.csrf, 'message': 'hello'}, {'Origin': 'https://foreign.invalid'}, 403),
            ({'csrf_token': self.csrf, 'message': ''}, {}, 400),
            ({'csrf_token': self.csrf, 'message': ' '}, {}, 400),
            ({'csrf_token': self.csrf, 'message': 'x' * 1001}, {}, 400),
            (MultiDict([('csrf_token', self.csrf), ('message', 'one'), ('message', 'two')]), {}, 400),
            ({'csrf_token': self.csrf, 'message': 'hello', 'user_id': 'other'}, {}, 400)]:
            response = self.client.post('/user/assistant', data=data, headers=headers)
            self.assertEqual(response.status_code, status)
        response = self.client.post('/user/assistant', data='x' * 17000,
                                    content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 400)
        self.provider.chat.assert_not_called()
        self.catalog.list_published.assert_not_called()

    def test_missing_configuration_timeout_failure_and_unknown_output_do_not_crash(self):
        for provider in (GeminiService(), mocked_gemini(error=httpx.ReadTimeout('private-key')),
                         mocked_gemini(status=500), mocked_gemini(output={}),
                         mocked_gemini(output=dict(in_scope=True, answer='Unknown place', destination_ids=['unknown']))):
            self.app.extensions['rosago_gemini'] = provider
            response = self.post()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'private-key', response.data)
        key = (trips.OWNER, self.handle)
        self.assertEqual(self.app.extensions['rosago_assistant'].snapshot(key), ())

    def test_weather_unavailable_is_explicit_context_and_reuses_weather_service(self):
        response = self.post('Will it rain in Santa Rosa?')
        self.assertEqual(response.status_code, 303)
        self.weather.get_weather.assert_called_once()
        self.assertFalse(self.provider.chat.call_args.args[0]['weather']['available'])
        self.routing.route.assert_not_called()

    def test_plain_escaped_output_and_catalog_references(self):
        catalog_place = self.catalog.list_published.return_value[0]
        self.provider.chat.return_value = dict(answer='<script>alert(1)</script>', destination_ids=[catalog_place.id])
        response = self.post('<img src=x onerror=alert(1)>')
        self.assertEqual(response.status_code, 303)
        html = self.client.get('/user/assistant').get_data(as_text=True)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', html)
        page = Document(html)
        assert_shared_scripts(self,page)
        self.assertEqual(page.find('img'), [])
        self.assertTrue(page.find('a', href='/places/' + catalog_place.slug))

    def test_history_bounds_clear_and_session_isolation(self):
        self.provider.chat.return_value['answer'] = 'a' * 2000
        for _ in range(10):
            self.assertEqual(self.post('q' * 1000).status_code, 303)
        store = self.app.extensions['rosago_assistant']
        history = store.snapshot((trips.OWNER, self.handle))
        self.assertLessEqual(len(history), MAX_MESSAGES)
        self.assertLessEqual(sum(len(item['text']) for item in history), MAX_HISTORY_CHARS)
        previous_handle = self.handle
        self.handle = self.seed()
        self.assertEqual(store.snapshot((trips.OWNER, self.handle)), ())
        self.assertNotIn('q' * 1000, self.client.get('/user/assistant').get_data(as_text=True))
        self.assertEqual(self.client.post('/user/assistant/clear', data={'csrf_token': 'wrong'}).status_code, 403)
        self.csrf = self.dependencies.store.resolve(self.handle).csrf
        self.assertEqual(self.client.post('/user/assistant/clear', data={'csrf_token': self.csrf}).status_code, 303)
        self.assertTrue(store.snapshot((trips.OWNER, previous_handle)))

    def test_catalog_failure_is_truthful_and_no_model_request_is_sent(self):
        self.catalog.list_published.side_effect = PlacesUnavailableError()
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertIn(b'destination catalog is temporarily unavailable', response.data)
        self.provider.chat.assert_not_called()
