"""Bounded grounding and chat isolation; no live provider/database requests."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from assistant_context import (chat_context, recommendation_context, validate_message,
                               weather_requested, MAX_CONTEXT_BYTES)
from assistant_store import (AssistantStore, ChatBusy, MAX_MESSAGES, MAX_HISTORY_CHARS,
                             MAX_CONVERSATIONS, IDLE_SECONDS)
from test_recommendation_engine import place


class AssistantContextTests(unittest.TestCase):
    def test_relevant_subset_and_fields_never_contain_credentials_or_coordinates(self):
        places = tuple(replace(place(index, 'heritage'), name=f'Place {index}', slug=f'place-{index}')
                       for index in range(1, 29))
        places = places[:-1] + (replace(places[-1], name='Nuvali'),)
        routing = SimpleNamespace(label='OSRM', modes=('driving',))
        result = chat_context('Tell me about Nuvali', (), places, routing)
        self.assertEqual(len(result['catalog']), 8)
        self.assertEqual(result['catalog'][0]['name'], 'Nuvali')
        self.assertFalse(result['catalog_is_complete'])
        self.assertEqual(result['transport']['supported_modes'], ['driving'])
        self.assertIsNone(result['transport']['calculated_route'])
        for field in ('image_url', 'latitude', 'longitude', 'created_at', 'user_id', 'token'):
            self.assertNotIn(field, result['catalog'][0])

    def test_recommendations_send_only_supported_interest_signals(self):
        cards = tuple(dict(place=place(index, 'heritage')) for index in range(1, 20))
        result = recommendation_context({'interests': ['heritage'], 'other_interests': 'private note',
                                         'budget_centavos': 100}, cards)
        self.assertEqual(len(result['candidates']), 12)
        self.assertTrue(result['explanation_subset'])
        self.assertNotIn('private note', json.dumps(result))
        self.assertNotIn('budget_centavos', result)

    def test_weather_relevance_unavailability_and_total_context_bound(self):
        routing = SimpleNamespace(label='OSRM', modes=('driving',))
        self.assertTrue(weather_requested('Will it rain?', ()))
        self.assertTrue(weather_requested('Tomorrow?', ({'role': 'user', 'text': 'weather today'},)))
        self.assertFalse(weather_requested('How do I save a trip?', ()))
        history = tuple(dict(role='user' if i % 2 == 0 else 'assistant', text='😀' * 2000) for i in range(12))
        result = chat_context('Weather?', history, (), routing, include_weather=True)
        self.assertFalse(result['weather']['available'])
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode()), MAX_CONTEXT_BYTES)
        self.assertLess(len(result['history']), len(history))

    def test_message_type_blank_length_and_controls(self):
        self.assertEqual(validate_message('  Hello\r\nRosaGo '), 'Hello\nRosaGo')
        for message in (None, True, [], '', '   ', 'a' * 1001, 'bad\x00text', '\ud800'):
            with self.subTest(message=repr(message)[:30]), self.assertRaises(ValueError):
                validate_message(message)


class AssistantStoreTests(unittest.TestCase):
    def test_isolation_and_expiry(self):
        tick = [0]
        store = AssistantStore(clock=lambda: tick[0])
        key = ('owner', 'session-a')
        token, history = store.begin(key)
        self.assertEqual(history, ())
        store.complete(key, token, 'My question', 'My answer')
        self.assertEqual(len(store.snapshot(key)), 2)
        self.assertEqual(store.snapshot(('other', 'session-a')), ())
        self.assertEqual(store.snapshot(('owner', 'session-b')), ())
        self.assertNotIn('My question', repr(store))
        tick[0] = IDLE_SECONDS
        self.assertEqual(store.snapshot(key), ())

    def test_message_count_characters_busy_and_clear_do_not_replay_old_reply(self):
        store, key = AssistantStore(), ('owner', 'session')
        for _ in range(10):
            token, _ = store.begin(key)
            store.complete(key, token, 'q' * 1000, 'a' * 2000)
        messages = store.snapshot(key)
        self.assertLessEqual(len(messages), MAX_MESSAGES)
        self.assertLessEqual(sum(len(item['text']) for item in messages), MAX_HISTORY_CHARS)
        self.assertEqual([item['role'] for item in messages], ['user', 'assistant'] * (len(messages) // 2))
        token, _ = store.begin(key)
        with self.assertRaises(ChatBusy):
            store.begin(key)
        store.clear(key)
        new_token, _ = store.begin(key)
        store.complete(key, token, 'old question', 'old answer')
        self.assertEqual(store.snapshot(key), ())
        store.complete(key, new_token, 'new question', 'new answer')
        self.assertEqual(store.snapshot(key)[0]['text'], 'new question')

    def test_global_storage_capacity_is_bounded_and_failed_turn_is_cancelled(self):
        store = AssistantStore()
        for i in range(MAX_CONVERSATIONS + 1):
            token, _ = store.begin(('owner', str(i)))
            store.cancel(('owner', str(i)), token)
        self.assertEqual(len(store._entries), MAX_CONVERSATIONS)
        self.assertNotIn(('owner', '0'), store._entries)
