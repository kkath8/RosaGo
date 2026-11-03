"""All Gemini calls use MockTransport. Never consumes live Gemini quota."""
from copy import deepcopy
import json
import unittest

import httpx

from gemini_service import GeminiService, SYSTEM_INSTRUCTION, SCOPE_REPLY

FIRST = '00000000-0000-0000-0000-000000000001'
SECOND = '00000000-0000-0000-0000-000000000002'


def context():
    return dict(interests=['heritage'], candidates=[
        dict(place_id=FIRST, name='First catalog place', category='heritage'),
        dict(place_id=SECOND, name='Second catalog place', category='heritage')])


def explanation():
    return dict(summary='These catalog choices match your heritage interest.', explanations=[
        dict(place_id=FIRST, matched_interest='heritage', reason='Matches the selected heritage category.')])


class GeminiServiceTests(unittest.TestCase):
    def service(self, output=None, *, status=200, error=None, envelope=None, raw=None):
        self.calls, self.clients = [], []
        def handle(request):
            self.calls.append(request)
            if error:
                raise error
            if raw is not None:
                return httpx.Response(status, content=raw)
            body = envelope if envelope is not None else {'candidates': [
                {'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(output)}]}}]}
            return httpx.Response(status, json=body)
        def factory(**options):
            self.assertEqual(options, dict(timeout=12, follow_redirects=False, trust_env=False))
            client = httpx.Client(transport=httpx.MockTransport(handle), **options)
            self.clients.append(client)
            return client
        return GeminiService('private-gemini-fixture-key', http_factory=factory)

    def test_valid_explanation_structured_protocol_and_server_only_key(self):
        service = self.service(explanation())
        result = service.explain(context())
        self.assertEqual(result['explanations'][0]['name'], 'First catalog place')
        request = self.calls[0]
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.url.host, 'generativelanguage.googleapis.com')
        self.assertTrue(request.url.path.endswith(':generateContent'))
        self.assertEqual(request.url.query, b'')
        self.assertEqual(request.headers['x-goog-api-key'], 'private-gemini-fixture-key')
        payload = json.loads(request.content)
        self.assertEqual(payload['systemInstruction']['parts'][0]['text'], SYSTEM_INSTRUCTION)
        self.assertEqual(payload['generationConfig']['responseMimeType'], 'application/json')
        self.assertIn('responseJsonSchema', payload['generationConfig'])
        self.assertNotIn('tools', payload)
        self.assertNotIn('private-gemini-fixture-key', json.dumps(result) + repr(service) + request.content.decode())
        self.assertTrue(self.clients[0].is_closed)

    def test_missing_key_bad_key_and_model_cannot_make_requests(self):
        for key, model in [(None, 'gemini-3.5-flash-lite'), ('bad\nkey', 'gemini-3.5-flash-lite'),
                           ('private-gemini-fixture-key', '../other?key=secret')]:
            service = GeminiService(key, model, http_factory=lambda **_: self.fail('Network forbidden'))
            self.assertFalse(service.configured)
            self.assertIsNone(service.explain(context()))

    def test_opaque_key_rejects_missing_empty_whitespace_controls_and_non_header_text(self):
        values = [None, '', False, 123, ' ', ' fixture', 'fixture ', 'fixture key',
                  'fixture\tkey', 'fixture\rkey', 'fixture\nkey', 'fixture\u00a0key',
                  'fixture\u2003key', 'fixture\u00e9key', 'fixture\ud800key']
        values += ['fixture' + chr(code) + 'key' for code in list(range(32)) + [127]]
        for index, key in enumerate(values):
            with self.subTest(case=index):
                service = GeminiService(key, http_factory=lambda **_: self.fail('Network forbidden'))
                self.assertFalse(service.configured)
                self.assertIsNone(service.explain(context()))

    def test_opaque_punctuation_short_and_long_keys_are_passed_unchanged_server_side(self):
        for index, key in enumerate(['x', 'opaque.fixture:/+token=!?@#$%&*()[]{}',
                                     'synthetic.' + 'a' * 1024 + '=']):
            with self.subTest(case=index):
                calls = []
                def handle(request):
                    calls.append(request)
                    return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP',
                        'content': {'parts': [{'text': json.dumps(explanation())}]}}]})
                def factory(**options):
                    return httpx.Client(transport=httpx.MockTransport(handle), **options)
                service = GeminiService(key, http_factory=factory)
                self.assertTrue(service.configured)
                self.assertIsNotNone(service.explain(context()))
                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0].headers['x-goog-api-key'] == key)
                if index:
                    self.assertTrue(key not in str(calls[0].url))
                    self.assertTrue(key not in calls[0].content.decode())
                self.assertEqual(repr(service), '<GeminiService redacted>')

    def test_opaque_key_does_not_relax_model_validation(self):
        for model in [None, '', ' gemini-model', 'gemini-model ', '../model',
                      'gemini-a/b', 'gemini-a?key=value', 'gemini-a\n',
                      'gemini-A', 'gemini-' + 'a' * 72]:
            service = GeminiService('synthetic.opaque=fixture', model,
                                    http_factory=lambda **_: self.fail('Network forbidden'))
            self.assertFalse(service.configured)
            self.assertIsNone(service.explain(context()))
        for model in ['gemini-3.5-flash-lite', 'gemini-test-1.0']:
            self.assertTrue(GeminiService('synthetic.opaque=fixture', model).configured)

    def test_provider_errors_cannot_return_opaque_credential_to_callers(self):
        key = 'synthetic.opaque=fixture'
        for failure in ['response', 'exception']:
            def handle(request):
                if failure == 'exception':
                    raise httpx.ReadTimeout(key, request=request)
                return httpx.Response(401, json={'error': {'message': key}})
            def factory(**options):
                return httpx.Client(transport=httpx.MockTransport(handle), **options)
            service = GeminiService(key, http_factory=factory)
            self.assertIsNone(service.explain(context()))
            self.assertEqual(repr(service), '<GeminiService redacted>')

    def test_unknown_identifiers_and_unsupported_interest_rejected(self):
        for changes in ({'place_id': 'unknown'}, {'matched_interest': 'dining'},
                        {'place_id': 1}, {'reason': ''}, {'extra': 'untrusted'}):
            output = explanation()
            output['explanations'][0].update(changes)
            self.assertIsNone(self.service(output).explain(context()))

    def test_duplicates_are_deduplicated_and_catalog_order_is_preserved(self):
        output = explanation()
        output['explanations'] *= 2
        result = self.service(output).explain(context())
        self.assertEqual(len(result['explanations']), 1)
        output['explanations'] = [dict(place_id=SECOND, matched_interest='heritage', reason='Second match.'),
                                  dict(place_id=FIRST, matched_interest='heritage', reason='First match.')]
        result = self.service(output).explain(context())
        self.assertEqual([item['place_id'] for item in result['explanations']], [FIRST, SECOND])

    def test_preview_multiple_destinations_use_one_request_and_validated_id_schema(self):
        output = {'explanations': [
            dict(place_id=SECOND, matched_interest='heritage', reason='Second reason.'),
            dict(place_id=FIRST, matched_interest='heritage', reason='First reason.')]}
        result = self.service(output).explain(context(), per_destination=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual([item['place_id'] for item in result['explanations']], [FIRST, SECOND])
        self.assertEqual([item['reason'] for item in result['explanations']], ['First reason.', 'Second reason.'])
        schema = json.loads(self.calls[0].content)['generationConfig']['responseJsonSchema']
        self.assertEqual(schema['required'], ['explanations'])
        self.assertEqual(schema['properties']['explanations']['items']['properties']['place_id']['enum'], [FIRST, SECOND])

    def test_preview_rejects_unknown_invalid_and_duplicate_entries_without_losing_valid_rows(self):
        valid = explanation()['explanations'][0]
        for bad in (None, {}, valid | {'place_id': 'unknown'}, valid | {'place_id': SECOND, 'reason': ''},
                    valid | {'place_id': SECOND, 'matched_interest': 'dining'}):
            result = self.service({'explanations': [bad, valid]}).explain(context(), per_destination=True)
            self.assertEqual([item['place_id'] for item in result['explanations']], [FIRST])
        result = self.service({'explanations': [valid, valid]}).explain(context(), per_destination=True)
        self.assertEqual(result['explanations'], [])
        for output in (None, [], {}, {'explanations': 'bad'}, {'explanations': []},
                       {'explanations': [valid] * 3}):
            self.assertIsNone(self.service(output).explain(context(), per_destination=True))

    def test_timeout_quota_network_http_refusal_and_malformed_output_fallback(self):
        for error in (httpx.ReadTimeout('private-gemini-fixture-key'), httpx.ConnectError('private-provider-body')):
            self.assertIsNone(self.service(error=error).explain(context()))
            self.assertTrue(self.clients[0].is_closed)
        for status in (301, 400, 401, 429, 500, 503):
            self.assertIsNone(self.service(status=status).explain(context()))
        for envelope in ({}, {'promptFeedback': {'blockReason': 'SAFETY'}},
                         {'candidates': [{'finishReason': 'SAFETY'}]},
                         {'candidates': [{'finishReason': 'MAX_TOKENS'}]},
                         {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'functionCall': {}}]}}]}):
            self.assertIsNone(self.service(envelope=envelope).explain(context()))
        for output in (None, '', [], {}, {'summary': ' '}, explanation() | {'new_ids': ['unknown']}):
            self.assertIsNone(self.service(output).explain(context()))
        for raw in (b'not-json', b'[]', b'x' * 256001):
            self.assertIsNone(self.service(raw=raw).explain(context()))

    def test_chat_validates_references_and_handles_out_of_scope(self):
        chat_context = {'catalog': context()['candidates'], 'message': 'Tell me about heritage'}
        output = dict(in_scope=True, answer='You can compare the supplied heritage entries.', destination_ids=[FIRST])
        result = self.service(output).chat(chat_context)
        self.assertEqual(result, dict(answer=output['answer'], destination_ids=[FIRST]))
        for output in (output | {'destination_ids': ['unknown']}, output | {'answer': ''},
                       output | {'in_scope': 'true'}, output | {'answer': 'a' * 2001}):
            self.assertIsNone(self.service(output).chat(chat_context))
        output = dict(in_scope=False, answer='Unrelated answer', destination_ids=[])
        self.assertEqual(self.service(output).chat(chat_context)['answer'], SCOPE_REPLY)

    def test_rate_limit_does_not_retry_or_call_provider_automatically(self):
        service = self.service(explanation())
        service._clock = lambda: 1
        self.assertIsNotNone(service.explain(context()))
        self.assertIsNone(service.explain(context()))
        self.assertEqual(len(self.calls), 1)

    def test_thought_metadata_is_not_displayed_as_advisory_output(self):
        body = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'thought': True, 'text': 'Internal model reasoning is not an answer.'},
            {'thought': False, 'thoughtSignature': 'opaque-metadata', 'text': json.dumps(explanation())}]}}]}
        result = self.service(envelope=body).explain(context())
        self.assertIsNotNone(result)
        self.assertNotIn('Internal model reasoning', json.dumps(result))
        self.assertNotIn('opaque-metadata', json.dumps(result))
