"""Offline quiz flow with real authentication scopes and guarded network access."""
from dataclasses import replace
from datetime import datetime, timezone
import io
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

import test_trip_routes as trips
from test_itinerary_quiz_form import form
from itinerary_quiz_form import parse_quiz_form
from itinerary_draft_service import (
    ItineraryDraft, DraftResult, DraftValidationError, DraftRejectedError,
    DraftUnavailableError, DraftConsistencyError,
)
from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable

START = '/user/itinerary/start'
QUIZ = '/user/itinerary/' + trips.TRIP + '/preferences'
REVIEW = '/user/itinerary/' + trips.TRIP + '/review'
ROUTES = [('POST', START), ('GET', QUIZ), ('POST', QUIZ), ('GET', REVIEW)]


class QuizRouteTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    protected = trips.TripRouteTests.protected

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.draft = ItineraryDraft(trips.TRIP, 'editing', 2, parse_quiz_form(form())[1],
                                    datetime(2099, 1, 1, tzinfo=timezone.utc))
        self.drafts = {}
        for name, result in {
            'get_itinerary_draft': self.draft,
            'create_itinerary_draft': DraftResult(trips.TRIP, 'editing', 1),
            'update_itinerary_draft_preferences': DraftResult(trips.TRIP, 'editing', 3),
        }.items():
            def operation(context, *args, result=result):
                self.assertIs(context, g.auth)
                self.assertIs(context.client, self.owned[-1])
                self.assertEqual(context.user_id, trips.OWNER)
                return result
            self.drafts[name] = Mock(side_effect=operation)
        namespace = self.app.view_functions['itinerary_start'].__wrapped__.__globals__
        guard = patch.dict(namespace, self.drafts)
        guard.start()
        self.addCleanup(guard.stop)

    def tearDown(self):
        trips.TripRouteTests.tearDown(self)
        for service in self.services.values():
            service.assert_not_called()

    def payload(self, **changes):
        return form(csrf_token=self.csrf, expected_revision='2', **changes)

    def test_planner_start_quiz_save_review(self):
        planner = self.client.get('/user/trips/new')
        self.assertIn(b'action="/user/itinerary/start"', planner.data)
        response = self.client.post(START, data={'csrf_token': self.csrf})
        self.assertEqual((response.status_code, response.location), (303, QUIZ))
        self.drafts['create_itinerary_draft'].assert_called_once()
        self.assertEqual(len(self.drafts['create_itinerary_draft'].call_args.args), 1)
        response = self.client.get(QUIZ)
        self.assertIn(b'name="expected_revision" value="2"', response.data)
        self.assertIn(b'value="08:00"', response.data)
        self.assertIn(b'aria-current="true">Planner', response.data)
        response = self.client.post(QUIZ, data=self.payload(), headers={'Origin': 'http://localhost'})
        self.assertEqual((response.status_code, response.location), (303, REVIEW))
        self.protected(response)
        update = self.drafts['update_itinerary_draft_preferences']
        update.assert_called_once()
        self.assertEqual(update.call_args.args[1:], (trips.TRIP, 2, self.draft.preferences))
        response = self.client.get(REVIEW + '?budget=999&preview=forged')
        self.assertIn('₱5,000.50', response.get_data(as_text=True))
        self.assertNotIn(b'forged', response.data)
        self.assertIn(b'No trip has been created.', response.data)
        self.protected(response)

    def test_auth_required_and_auth_unavailability(self):
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                for method, path in ROUTES:
                    response = self.client.open(path, method=method, data=self.payload())
                    self.assertEqual(response.status_code, 503)
                    self.protected(response)
        for state in ({}, {'user_id': trips.OWNER}, {'password_recovery_id': 'grant'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            for method, path in ROUTES:
                response = self.client.open(path, method=method, data=self.payload())
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/login?login_required=1')
                self.protected(response)
        for service in self.drafts.values():
            service.assert_not_called()

    def test_mutation_security_before_service_access(self):
        for path, valid in ((START, MultiDict({'csrf_token': self.csrf})), (QUIZ, self.payload())):
            cases = []
            for field in valid:
                if field in ('interests', 'activity_preferences'):
                    continue
                missing = valid.copy(); del missing[field]
                duplicate = valid.copy(); duplicate.add(field, valid[field])
                status = 403 if field == 'csrf_token' else 400
                cases.extend([(missing, {}, status), (duplicate, {}, status)])
            for field in ('user_id', 'state', 'timezone', 'preview', 'save', 'saved_trip_id', 'revision'):
                data = valid.copy(); data[field] = 'forged'
                cases.append((data, {}, 400))
            data = valid.copy(); data['upload'] = (io.BytesIO(b'file'), 'file.txt')
            cases.append((data, {}, 400))
            data = valid.copy(); data['csrf_token'] = 'wrong'
            cases.append((data, {}, 403))
            for origin in ('null', '', 'https://foreign.invalid', 'http://localhost.evil'):
                cases.append((valid, {'Origin': origin}, 403))
            for data, headers, status in cases:
                with self.subTest(path=path, fields=list(data), headers=headers):
                    response = self.client.post(path, data=data, headers=headers)
                    self.assertEqual(response.status_code, status)
                    self.protected(response)
        for service in self.drafts.values():
            service.assert_not_called()

    def test_validation_keeps_submitted_revision_and_no_write(self):
        response = self.client.post(QUIZ, data=self.payload(budget='NaN'))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'name="expected_revision" value="2"', response.data)
        self.protected(response)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()

    def test_legacy_review_and_edit_require_explicit_new_choices(self):
        from itinerary_draft_service import EXTENSION_FIELDS
        from test_public_layout import Document
        legacy = {key: value for key, value in self.draft.preferences.items() if key not in EXTENSION_FIELDS}
        read = self.drafts['get_itinerary_draft']
        read.side_effect = None
        read.return_value = replace(self.draft, preferences=legacy)
        response = self.client.get(REVIEW)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'Not selected'), 3)
        self.assertIn('₱5,000.50', response.get_data(as_text=True))
        page = Document(self.client.get(QUIZ).get_data(as_text=True))
        for field in ('trip_pace', 'environment_preference'):
            options = page.find('input', name=field, type='radio')
            self.assertEqual(len(options), 3)
            self.assertTrue(all('required' in node.attrs for node in options))
            self.assertFalse(any('checked' in node.attrs for node in options))
        self.assertFalse(any('checked' in node.attrs for node in page.find('input', name='activity_preferences')))
        for field in ('trip_pace', 'environment_preference', 'activity_preferences'):
            data = self.payload(); del data[field]
            self.assertEqual(self.client.post(QUIZ, data=data).status_code, 400)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()
        self.assertEqual(self.client.post(QUIZ, data=self.payload()).status_code, 303)
        self.drafts['update_itinerary_draft_preferences'].assert_called_once()

    def test_literal_text_escaped_in_review_form_and_error_page(self):
        literal = '<script>alert(1)</script>'
        read = self.drafts['get_itinerary_draft']
        read.side_effect = None
        read.return_value = replace(self.draft, preferences=self.draft.preferences | {
            'other_interests': literal, 'additional_preferences': literal})
        for response in (self.client.get(QUIZ), self.client.get(REVIEW),
                         self.client.post(QUIZ, data=self.payload(budget='NaN', other_interests=literal,
                                                                 additional_preferences=literal))):
            self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;', response.data)
            self.assertNotIn(literal.encode(), response.data)
            self.protected(response)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()
        response = self.client.post(QUIZ, data=self.payload(other_interests='  ' + literal + '  ',
                                                           additional_preferences=literal))
        self.assertEqual(response.status_code, 303)
        stored = self.drafts['update_itinerary_draft_preferences'].call_args.args[3]
        self.assertEqual(stored['other_interests'], literal)
        self.assertEqual(stored['additional_preferences'], literal)

    def test_stale_revision_is_passed_unchanged_and_never_retried(self):
        update = self.drafts['update_itinerary_draft_preferences']
        update.side_effect = DraftRejectedError()
        data = self.payload(); data['expected_revision'] = '1'
        response = self.client.post(QUIZ, data=data)
        self.assertEqual(response.status_code, 409)
        update.assert_called_once()
        self.assertEqual(update.call_args.args[2], 1)

    def test_quiz_native_controls_exact_fields_and_selected_form_roundtrip(self):
        from test_public_layout import Document
        from itinerary_quiz_form import FORM_FIELDS
        from itinerary_draft_service import TRANSPORTATION, ACTIVITIES, TRIP_PACES, ENVIRONMENTS
        page = Document(self.client.get(QUIZ).get_data(as_text=True))
        self.assertEqual(page.find('h1')[0].text, 'Plan Your Perfect Santa Rosa Trip')
        forms = page.find('form')
        self.assertEqual(len(forms), 1)
        self.assertEqual((forms[0].attrs['method'], forms[0].attrs['action']), ('post', QUIZ))
        inputs = [node for node in page.elements if node.tag in ('input', 'textarea') and forms[0] in node.ancestors]
        self.assertEqual({node.attrs['name'] for node in inputs}, FORM_FIELDS)
        payload = MultiDict()
        for node in inputs:
            kind = node.attrs.get('type')
            if kind not in ('radio', 'checkbox') or 'checked' in node.attrs:
                payload.add(node.attrs['name'], node.text if node.tag == 'textarea' else node.attrs['value'])
        self.assertEqual(parse_quiz_form(payload), (2, self.draft.preferences))
        for field, options, kind in (('transportation', TRANSPORTATION, 'radio'),
                                      ('trip_pace', TRIP_PACES, 'radio'),
                                      ('environment_preference', ENVIRONMENTS, 'radio'),
                                      ('activity_preferences', ACTIVITIES, 'checkbox')):
            controls = page.find('input', name=field, type=kind)
            self.assertEqual([node.attrs['value'] for node in controls], list(options))
            for node in controls:
                self.assertEqual(node.ancestors[-1].tag, 'label')
                self.assertTrue(any(parent.tag == 'fieldset' for parent in node.ancestors))
                self.assertEqual('required' in node.attrs, kind == 'radio')
        self.assertEqual(page.find('input', name='other_interests')[0].attrs['maxlength'], '200')
        self.assertEqual(page.find('textarea', name='additional_preferences')[0].attrs['maxlength'], '500')
        self.assertNotIn('required', page.find('input', name='budget')[0].attrs)
        for field in ('daily_start_time', 'daily_end_time'):
            self.assertEqual(page.find('input', name=field)[0].attrs['step'], '60')
        self.assertEqual(page.find('script'), [])
        self.assertEqual(page.stack, [])
        self.assertEqual(page.find('button', type='submit')[0].text.strip(), 'Review My Trip →')

    def test_review_display_formats_real_values_and_disables_generation(self):
        from test_public_layout import Document
        read = self.drafts['get_itinerary_draft']
        read.side_effect = None
        for transport, label in (('motorcycle', 'Motorcycle'), ('public_transport', 'Public Transport'),
                                 ('ride_hailing', 'Ride-Hailing / Taxi'), ('mixed_transport', 'Mixed Transport'),
                                 ('bicycle', 'Bicycle'), ('walking', 'Walking'), ('private_car', 'Private Car')):
            read.return_value = replace(self.draft, preferences=self.draft.preferences | {
                'transportation': transport, 'daily_start_time': '00:00:00', 'daily_end_time': '12:01:30',
                'activity_preferences': ['food_trip', 'outdoor_activities', 'culture_heritage']})
            page = Document(self.client.get(REVIEW).get_data(as_text=True))
            main = page.find('main')[0].text
            for expected in (label, 'Food Trip', 'Outdoor Activities', 'Culture & Heritage',
                             'Mix of Both', 'Attractions', 'Balanced', 'Feb 29, 2020', 'Mar 6, 2020',
                             '12:00 AM', '12:01:30 PM', '₱5,000.50'):
                self.assertIn(expected, main)
            self.assertEqual(page.find('h1')[0].text, 'Review Your Trip')
            button = page.find('button')[0]
            self.assertEqual(button.attrs['type'], 'button')
            self.assertIn('disabled', button.attrs)
            self.assertEqual(page.find('form'), [])
            self.assertTrue(page.find('a', href=QUIZ))
            self.assertTrue(page.find('a', href='/user/trips/new'))
            self.assertEqual(page.find('script'), [])
            self.assertEqual(page.stack, [])
        for amount, display in ((None, 'Not provided'), (0, '₱0'), (10000000, '₱100,000'), (1, '₱0.01')):
            read.return_value = replace(self.draft, preferences=self.draft.preferences | {
                'budget_centavos': amount, 'end_date': self.draft.preferences['start_date']})
            page = Document(self.client.get(REVIEW).get_data(as_text=True))
            self.assertIn(display, page.find('main')[0].text)
            self.assertEqual(len(page.find('time', datetime='2020-02-29')), 1)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()

    def test_validation_notice_is_accessible_and_preserves_selection(self):
        from test_public_layout import Document
        response = self.client.post(QUIZ, data=self.payload(budget='100000.01'))
        self.assertEqual(response.status_code, 400)
        page = Document(response.get_data(as_text=True))
        alert = page.find('div', role='alert', id='quiz-error')[0]
        self.assertIn('Check all fields', alert.text)
        self.assertEqual(page.find('form')[0].attrs['aria-describedby'], 'quiz-error')
        self.assertEqual(page.find('input', name='budget')[0].attrs['value'], '100000.01')
        self.assertIn('checked', page.find('input', name='trip_pace', value='balanced')[0].attrs)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()

    def test_missing_foreign_noneditable_and_empty_drafts(self):
        read = self.drafts['get_itinerary_draft']
        read.side_effect = None
        read.return_value = None
        for draft_id in (trips.TRIP, trips.OWNER):
            for method, path in ROUTES[1:]:
                response = self.client.open(path.replace(trips.TRIP, draft_id), method=method, data=self.payload())
                self.assertEqual((response.status_code, response.data), (404, b'Draft not found.'))
        for draft in [replace(self.draft, state=state) for state in
                      ('generating', 'preview_ready', 'failed', 'saved', 'expired')] + [
                          replace(self.draft, expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))]:
            read.return_value = draft
            for method, path in ROUTES[1:]:
                self.assertEqual(self.client.open(path, method=method, data=self.payload()).status_code, 409)
        read.return_value = replace(self.draft, preferences=None)
        response = self.client.get(REVIEW)
        self.assertEqual((response.status_code, response.location), (303, QUIZ))
        self.assertEqual(self.client.get(QUIZ).status_code, 200)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()

    def test_sanitized_errors_and_single_mutation_attempt(self):
        for name, method, path in [('create_itinerary_draft', 'POST', START),
                                   ('update_itinerary_draft_preferences', 'POST', QUIZ),
                                   ('get_itinerary_draft', 'GET', REVIEW)]:
            service = self.drafts[name]
            original = service.side_effect
            for error_type, status in ((DraftValidationError, 400), (DraftRejectedError, 409),
                                       (DraftUnavailableError, 503), (DraftConsistencyError, 500)):
                error = error_type(); error.args = ('private-provider-message',)
                service.side_effect = error; service.reset_mock()
                data = {'csrf_token': self.csrf} if path == START else self.payload()
                response = self.client.open(path, method=method, data=data)
                self.assertEqual(response.status_code, status)
                self.assertNotIn(b'private-provider-message', response.data)
                self.protected(response)
                service.assert_called_once()
            service.side_effect = original

    def test_template_authority_isolation_and_read_only_gets(self):
        seen = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            for value in context.values():
                self.assertNotIsInstance(value, AuthenticatedContext)
                self.assertTrue(all(value is not client for client in self.owned))
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            for path in (QUIZ, REVIEW):
                response = self.client.get(path)
                for secret in (trips.OWNER, self.handle, 'private-access', 'private-refresh', 'private-provider-session'):
                    self.assertNotIn(secret.encode(), response.data)
            self.client.post(QUIZ, data=self.payload(budget='<script>'))
        self.assertEqual(seen, ['itinerary/preferences.html', 'itinerary/review.html', 'itinerary/preferences.html'])
        self.assertEqual(self.client.get(START).status_code, 405)
        self.drafts['create_itinerary_draft'].assert_not_called()
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
