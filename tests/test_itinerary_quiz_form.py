"""Offline form parsing contracts, including exact integer money conversion."""
import unittest
from werkzeug.datastructures import MultiDict

from itinerary_quiz_form import parse_quiz_form, form_values
from itinerary_draft_service import DraftValidationError


def form(**changes):
    data = dict(csrf_token='fixture', expected_revision='1', interests=['attraction', 'nature'],
                companion_type='friends', budget='5000.50', start_date='2020-02-29',
                end_date='2020-03-06', daily_start_time='08:00', daily_end_time='17:00',
                transportation='public_transport')
    return MultiDict(data | changes)


class QuizFormTests(unittest.TestCase):
    def test_canonical_snapshot_and_no_future_date_rule(self):
        revision, prefs = parse_quiz_form(form())
        self.assertEqual(revision, 1)
        self.assertEqual(prefs, dict(interests=['attraction', 'nature'], companion_type='friends',
            budget_centavos=500050, start_date='2020-02-29', end_date='2020-03-06',
            daily_start_time='08:00:00', daily_end_time='17:00:00',
            transportation='public_transport', timezone='Asia/Manila'))

    def test_budget_boundaries_and_roundtrip(self):
        for value, amount in (('', None), ('0', 0), ('5000', 500000), ('5000.50', 500050),
                              ('0.01', 1), ('100000.00', 10000000)):
            with self.subTest(value=value):
                _, prefs = parse_quiz_form(form(budget=value))
                self.assertEqual(prefs['budget_centavos'], amount)
                values = form_values(prefs)
                for key in ('daily_start_time', 'daily_end_time'):
                    values[key] = values[key][:5]
                self.assertEqual(parse_quiz_form(form(**values))[1], prefs)

    def test_valid_interest_and_time_boundaries(self):
        for interests in (['nature'], ['attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage']):
            _, prefs = parse_quiz_form(form(interests=interests, daily_start_time='00:00', daily_end_time='23:59'))
            self.assertEqual(prefs['interests'], interests)
            self.assertEqual(prefs['daily_start_time'], '00:00:00')
            self.assertEqual(prefs['daily_end_time'], '23:59:00')

    def test_invalid_fields_and_values(self):
        cases = []
        for key, values in {
            'interests': [[], ['nature', 'nature'], ['other'], ['nature'] * 7],
            'companion_type': ['', 'unknown', 'Friends'],
            'budget': [' ', '-1', '+1', '100000.01', '100001', '1.001', '1e3', 'NaN', 'Infinity', '1,000', '.50', '5.'],
            'start_date': ['2020-2-29', '2021-02-29', '0000-01-01', '2020-02-29\n'],
            'end_date': ['2020-02-28', '2020-03-07'],
            'daily_start_time': ['24:00', '24:00:00', '08:60', '8:00', '08:00:00'],
            'daily_end_time': ['08:00', '07:59', '24:00', '24:00:00', '17:00:60', '23:59:59'],
            'transportation': ['', 'bus'],
            'expected_revision': ['', '0', '-1', '01', '1.0', '1e0', ' 1', '9223372036854775807'],
        }.items():
            cases.extend(form(**{key: value}) for value in values)
        for key in ('user_id', 'state', 'revision', 'timezone', 'preview', 'saved_trip_id'):
            cases.append(form(**{key: 'bad'}))
        for key in form().keys():
            missing = form(); del missing[key]; cases.append(missing)
            if key != 'interests':
                duplicate = form(); duplicate.add(key, duplicate[key]); cases.append(duplicate)
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(DraftValidationError):
                    parse_quiz_form(data)


if __name__ == '__main__':
    unittest.main()
