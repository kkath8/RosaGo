"""Synthetic curated metadata only. No destination research values or live I/O."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from destination_weather_metadata import (
    WeatherMetadata, load_weather_catalog, validate_weather_catalog, EXPOSURES,
)
from itinerary_weather import forecast_review
from weather_proposal import build_weather_proposal
from test_public_layout import Document
from test_recommendation_engine import place
import test_itinerary_weather as weather_tests
import test_itinerary_preview_routes as preview
import test_itinerary_adjustment as adjustment
from test_tourism_weather_identity import current_catalog_rows

NOW = weather_tests.NOW


def metadata_document(places, exposures=None):
    exposures = exposures or {}
    rows = []
    for item in places:
        exposure = exposures.get(item.id, 'unknown')
        rows.append(dict(slug=item.slug, name=item.name, category=item.category, address=item.address, exposure=exposure,
            source_url='https://fixture.invalid/evidence' if exposure != 'unknown' else None,
            source_note='Synthetic test evidence only.' if exposure != 'unknown' else None,
            verified_on='2026-10-22' if exposure != 'unknown' else None))
    return dict(schema_version=1, destinations=rows)


class MetadataTests(unittest.TestCase):
    def test_approved_curation_only_three_records_and_all_other_records_unknown(self):
        folder = Path(__file__).resolve().parents[1]/'data/santa_rosa_places'
        places = json.loads((folder/'archive/places.json').read_text(encoding='utf-8'))
        document = json.loads((folder/'weather_metadata.json').read_text(encoding='utf-8'))
        metadata = validate_weather_catalog(document)
        expected = {
            'enchanted-kingdom': ('Enchanted Kingdom', 'attraction', 'mixed', 'https://www.enchantedkingdom.ph/faq/'),
            'sm-city-santa-rosa': ('SM City Santa Rosa', 'shopping', 'indoor', 'https://www.smsupermalls.com/maps/sm-city-santa-rosa/'),
            'robinson-s-santa-rosa': ('Robinsons Sta. Rosa', 'shopping', 'indoor', 'https://robinsonsmalls.com/mall-info/robinsons-sta-rosa'),
        }
        catalog = {row['slug']: row for row in places}
        # Unknown metadata rows keep their prior state; only three curated
        # bindings are reconciled to the applied Tourism catalog in this phase.
        catalog.update({row['slug']: row for row in current_catalog_rows() if row['slug'] in expected})
        curated = set()
        for row in document['destinations']:
            for key in ('slug', 'name', 'category', 'address'):
                self.assertEqual(row[key], catalog[row['slug']][key])
            if row['slug'] in expected:
                curated.add(row['slug'])
                self.assertEqual(tuple(row[key] for key in ('name', 'category', 'exposure', 'source_url')),
                                 expected[row['slug']])
                self.assertEqual(row['verified_on'], '2026-10-26')
                self.assertIn('RosaGo-curated', row['source_note'])
                self.assertTrue(row['source_note'])
            else:
                self.assertEqual(row['exposure'], 'unknown')
                self.assertIsNone(row['source_url'])
                self.assertIsNone(row['source_note'])
                self.assertIsNone(row['verified_on'])
        self.assertEqual(curated, set(expected))
        self.assertEqual(len(metadata.records), 28)
        enchanted = next(row for row in document['destinations'] if row['slug'] == 'enchanted-kingdom')
        self.assertIn('https://www.enchantedkingdom.ph/rides-and-attractions/', enchanted['source_note'])

    def test_curated_real_catalog_allows_only_eligible_cross_interest_rain_proposals(self):
        from datetime import date
        from places_service import parse_place_row
        from test_recommendation_engine import preferences
        from itinerary_weather import ForecastConcern, ForecastReview
        folder = Path(__file__).resolve().parents[1]/'data/santa_rosa_places'
        rows = [row for row in current_catalog_rows() if row.get('status', 'published') == 'published']
        catalog = tuple(parse_place_row(dict(image_url=None) | row | dict(id=f'00000000-0000-0000-0000-{index:012x}',
            created_at='2026-10-26T00:00:00Z', updated_at='2026-10-26T00:00:00Z'))
            for index, row in enumerate(rows, 1))
        by_slug = {item.slug: item for item in catalog}
        enchanted = by_slug['enchanted-kingdom']
        sm = by_slug['sm-city-santa-rosa']
        robinsons = by_slug['robinson-s-santa-rosa']
        day = date(2026, 10, 27)
        review = ForecastReview(concerns=(ForecastConcern(day, 'caution', 'Light drizzle', 51, 63),))
        days = (dict(date=day, stops=(dict(order=1, place=enchanted),)),)
        metadata = load_weather_catalog()
        # Neither mall is selected; both are eligible only when shopping is a current interest.
        for ordered_catalog in (catalog, tuple(reversed(catalog))):
            proposal = build_weather_proposal(preferences(interests=['attraction', 'shopping']),
                days, ordered_catalog, review, metadata)
            self.assertEqual(len(proposal.replacements), 1)
            self.assertIn(proposal.places[0].id, (sm.id, robinsons.id))
            self.assertEqual(proposal.places[0].id, min(sm.id, robinsons.id))
        proposal = build_weather_proposal(preferences(interests=['attraction']), days, catalog, review, metadata)
        self.assertEqual(proposal.replacements, ())
        self.assertEqual(proposal.places, (enchanted,))
        self.assertTrue(any('no verified less-exposed alternative' in note for note in proposal.notices))
        all_selected = (dict(date=day, stops=tuple(dict(order=index, place=item)
            for index, item in enumerate((enchanted, sm, robinsons), 1))),)
        proposal = build_weather_proposal(preferences(interests=['attraction', 'shopping']),
            all_selected, catalog, review, metadata)
        self.assertEqual(proposal.replacements, ())

    def test_enum_and_provenance_validation(self):
        self.assertEqual(WeatherMetadata().exposure, 'unknown')
        for exposure in EXPOSURES[:-1]:
            self.assertEqual(WeatherMetadata(exposure, 'https://fixture.invalid/source',
                'Synthetic evidence.', '2026-10-22').exposure, exposure)
        for args in [('inside',), (True,), ('indoor',), ('unknown', 'https://fixture.invalid', None, None),
                     ('covered', 'javascript:alert(1)', 'Evidence', '2026-10-22'),
                     ('outdoor', 'https://user:password@fixture.invalid', 'Evidence', '2026-10-22'),
                     ('mixed', 'https://fixture.invalid', 'Evidence', '2026-1-1')]:
            with self.assertRaises(ValueError):
                WeatherMetadata(*args)

    def test_manifest_unknown_identity_binding_and_duplicate_validation(self):
        item = place(1)
        document = metadata_document((item,), {item.id: 'outdoor'})
        metadata = validate_weather_catalog(document)
        self.assertEqual(metadata.for_place(item).exposure, 'outdoor')
        for changed in (replace(item, slug='changed'), replace(item, name='Changed'),
                        replace(item, category='shopping'), replace(item, address='Changed address')):
            self.assertEqual(metadata.for_place(changed).exposure, 'unknown')
        bad = deepcopy(document)
        bad['destinations'] *= 2
        with self.assertRaises(ValueError):
            validate_weather_catalog(bad)
        with self.assertRaises(ValueError):
            validate_weather_catalog(document | {'arbitrary_ids': ['foreign']})

    def test_bad_missing_oversized_and_duplicate_key_files_fail_closed(self):
        path = Mock()
        path.open.side_effect = OSError('Unavailable file')
        self.assertFalse(load_weather_catalog(path).available)
        for raw in ('not JSON', '{}', 'x'*64001, '['*1100+'0'+']'*1100,
                    '{"schema_version":1,"schema_version":1,"destinations":[]}'):
            path.open.side_effect = lambda *args: io.BytesIO(raw.encode('utf-8'))
            metadata = load_weather_catalog(path)
            self.assertFalse(metadata.available)
            self.assertEqual(metadata.for_place(place(1)).exposure, 'unknown')

    def test_all_28_real_catalog_records_have_explicit_valid_metadata_and_provenance(self):
        folder = Path(__file__).resolve().parents[1]/'data/santa_rosa_places'
        places = json.loads((folder/'archive/places.json').read_text(encoding='utf-8'))
        document = json.loads((folder/'weather_metadata.json').read_text(encoding='utf-8'))
        self.assertEqual({row['slug'] for row in document['destinations']}, {row['slug'] for row in places})
        self.assertEqual(len(document['destinations']), 28)
        for row in document['destinations']:
            WeatherMetadata(row['exposure'], row['source_url'], row['source_note'], row['verified_on'])
        self.assertTrue(load_weather_catalog().available)


class WeatherProposalRoutes(unittest.TestCase):
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview
    ready = preview.PreviewRouteTests.ready
    save = adjustment.AdjustmentRoutes.save
    post = adjustment.AdjustmentRoutes.post

    def setUp(self):
        weather_tests.PreviewWeatherTests.setUp(self)
        self.places = tuple(replace(item, name=f'Synthetic place {index}', slug=f'synthetic-{index}')
                            for index, item in enumerate(self.places))
        self.catalog.list_published.return_value = self.places
        self.ready(self.places[:4])
        self.exposures = {self.places[0].id: 'outdoor', self.places[1].id: 'indoor',
                          self.places[4].id: 'indoor', self.places[5].id: 'covered'}
        self.metadata = validate_weather_catalog(metadata_document(self.places, self.exposures))
        guard = patch.dict(self.namespace, load_weather_catalog=lambda: self.metadata)
        guard.start(); self.addCleanup(guard.stop)
        self.weather_path = preview.PREVIEW+'/weather'

    def token(self):
        response = self.client.get(preview.PREVIEW)
        self.assertEqual(response.status_code, 200)
        tokens = Document(response.get_data(as_text=True)).find('input', name='proposal_token')
        self.assertEqual(len(tokens), 1)
        return tokens[0].attrs['value']

    def decide(self, token, decision='accept', **changes):
        return self.client.post(self.weather_path, headers=preview.ORIGIN, data=dict(
            csrf_token=self.csrf, expected_revision=str(self.current.revision),
            proposal_token=token, decision=decision) | changes)

    def proposal(self, catalog=None, review=None, metadata=None):
        selected = {item.id: item for item in self.places}
        days = tuple(dict(date=day.date, stops=tuple(dict(order=stop.order, place=selected[stop.place_id])
            for stop in day.stops)) for day in self.current.preview.plan.days)
        return build_weather_proposal(self.current.preferences, days,
            self.places if catalog is None else catalog,
            forecast_review(self.weather.get_weather.return_value, tuple(day['date'] for day in days), now=NOW)
                if review is None else review, self.metadata if metadata is None else metadata)

    def test_rain_deterministic_same_category_replacement_order_count_and_no_duplicates(self):
        expected = (self.places[4].id, self.places[1].id, self.places[2].id, self.places[3].id)
        for catalog in (self.places, tuple(reversed(self.places))):
            proposal = self.proposal(catalog=catalog)
            self.assertEqual(tuple(item.id for item in proposal.places), expected)
            self.assertEqual(len({item.id for item in proposal.places}), 4)
            self.assertEqual(len(proposal.replacements), 1)
            self.assertEqual(proposal.replacements[0].proposed.category, 'attraction')

    def test_unknown_selection_and_candidate_are_not_inferred(self):
        unknown = validate_weather_catalog(metadata_document(self.places))
        proposal = self.proposal(metadata=unknown)
        self.assertEqual(proposal.replacements, ())
        self.assertEqual(proposal.places, self.places[:4])
        self.assertIn('exposure is unknown', proposal.notices[0])
        metadata = validate_weather_catalog(metadata_document(self.places, {self.places[0].id: 'outdoor'}))
        proposal = self.proposal(metadata=metadata)
        self.assertEqual(proposal.replacements, ())
        self.assertTrue(any('no verified less-exposed alternative' in item for item in proposal.notices))

    def test_mixed_is_conservatively_exposed_and_wrong_interest_not_used(self):
        metadata = validate_weather_catalog(metadata_document(self.places, self.exposures | {self.places[0].id: 'mixed'}))
        self.assertEqual(len(self.proposal(metadata=metadata).replacements), 1)
        changed = self.places[:4] + tuple(replace(item, category='shopping') for item in self.places[4:])
        metadata = validate_weather_catalog(metadata_document(changed, self.exposures))
        self.assertEqual(self.proposal(catalog=changed, metadata=metadata).replacements, ())

    def test_unpublished_or_missing_alternatives_cannot_be_selected(self):
        proposal = self.proposal(catalog=self.places[:4])
        self.assertEqual(proposal.replacements, ())
        with self.assertRaises(ValueError):
            self.proposal(catalog=self.places[1:])

    def test_no_concern_no_proposal_and_provider_failure_is_review_only(self):
        snapshot = self.weather.get_weather.return_value
        self.weather.get_weather.return_value = replace(snapshot, forecast=tuple(
            replace(day, weather_code=0, precipitation_probability=0) for day in snapshot.forecast))
        self.assertIsNone(self.proposal())
        self.assertNotIn(b'proposal_token', self.client.get(preview.PREVIEW).data)
        self.weather.get_weather.return_value = None
        response = self.client.get(preview.PREVIEW)
        self.assertNotIn(b'proposal_token', response.data)
        self.assertIn(b'Weather is temporarily unavailable', response.data)
        self.mutate.assert_not_called()

    def test_strong_weather_produces_review_only_without_safety_guarantees(self):
        snapshot = self.weather.get_weather.return_value
        self.weather.get_weather.return_value = replace(snapshot, forecast=tuple(
            replace(day, weather_code=95) for day in snapshot.forecast))
        response = self.client.get(preview.PREVIEW)
        self.assertIn(b'Severe weather may affect', response.data)
        self.assertNotIn(b'proposal_token', response.data)
        self.assertIn(b'does not propose replacements for severe weather', response.data)

    def test_page_comparison_and_keep_never_write_or_call_gemini(self):
        before = deepcopy(self.current)
        response = self.client.get(preview.PREVIEW)
        for phrase in (b'Your Personalized Itinerary', b'Suggested adjustment', b'Review Suggested Changes',
                       b'Keep Current Itinerary', b'Use Suggested Itinerary', b'Proposed new destination', b'Retained'):
            self.assertIn(phrase, response.data)
        token = Document(response.get_data(as_text=True)).find('input', name='proposal_token')[0].attrs['value']
        response = self.decide(token, 'keep')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Current itinerary kept', response.data)
        self.assertNotIn(b'proposal_token', response.data)
        self.assertEqual(self.current, before)
        self.mutate.assert_not_called(); self.store.assert_not_called(); self.edit.assert_not_called()
        self.provider.explain.assert_not_called(); self.provider.interpret_adjustment.assert_not_called()

    def test_accept_exact_server_proposal_once_preserves_preferences_and_clears_explanations(self):
        token = self.token()
        preferences = deepcopy(self.current.preferences)
        response = self.decide(token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current.revision, 4)
        self.assertEqual(self.current.preferences, preferences)
        self.assertEqual(self.current.preview.source.selected_place_ids,
                         (self.places[4].id, self.places[1].id, self.places[2].id, self.places[3].id))
        self.mutate.assert_called_once()
        self.assertIn(b'Weather suggestion applied after your approval', response.data)
        self.assertIn(b'Why these places?', response.data)
        self.provider.explain.return_value = {'explanations': [dict(place_id=self.places[4].id, reason='New selected reason')]}
        response = self.client.post(preview.PREVIEW+'/explain', headers=preview.ORIGIN,
            data=dict(csrf_token=self.csrf, expected_revision='4'))
        self.assertIn(b'New selected reason', response.data)
        self.assertEqual([row['place_id'] for row in self.provider.explain.call_args.args[0]['candidates']],
                         list(self.current.preview.source.selected_place_ids))
        self.provider.interpret_adjustment.assert_not_called()

    def test_post_only_csrf_origin_exact_form_bounds_and_browser_ids(self):
        token = self.token()
        self.assertEqual(self.client.get(self.weather_path).status_code, 405)
        self.assertEqual(self.decide(token, selected_place_ids=self.places[5].id).status_code, 400)
        self.assertEqual(self.decide(token, csrf_token='bad').status_code, 403)
        self.assertEqual(self.decide(token, expected_revision='bad').status_code, 400)
        self.assertEqual(self.decide(token, decision='invented').status_code, 400)
        self.assertEqual(self.decide('x'*9000).status_code, 413)
        self.assertEqual(self.client.post(self.weather_path, headers={'Origin': 'https://foreign.invalid'}).status_code, 403)
        self.mutate.assert_not_called()

    def test_forged_and_expired_signed_tokens_are_rejected(self):
        token = self.token()
        self.assertEqual(self.decide('forged').status_code, 409)
        signer = self.namespace['_weather_signer']
        with self.app.test_request_context():
            signed = signer().loads(token)
            with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=1):
                old_token = signer().dumps(signed)
        self.assertEqual(self.decide(old_token).status_code, 409)
        # Signed tokens still cannot be moved to another owner binding.
        with self.app.test_request_context():
            signed['owner'] = 'foreign'
            other = signer().dumps(signed)
        self.assertEqual(self.decide(other).status_code, 409)
        self.mutate.assert_not_called()

    def test_changed_catalog_or_metadata_or_forecast_invalidates_proposal(self):
        token = self.token()
        original_catalog = self.catalog.list_published.return_value
        self.catalog.list_published.return_value = tuple(item for item in self.places if item.id != self.places[4].id)
        self.assertEqual(self.decide(token).status_code, 409)
        self.catalog.list_published.return_value = tuple(replace(item, name='Changed candidate')
            if item.id == self.places[4].id else item for item in self.places)
        self.assertEqual(self.decide(token).status_code, 409)
        self.catalog.list_published.return_value = original_catalog
        metadata = self.metadata
        self.metadata = validate_weather_catalog(metadata_document(self.places, self.exposures | {self.places[4].id: 'unknown'}))
        self.assertEqual(self.decide(token).status_code, 409)
        self.metadata = metadata
        snapshot = self.weather.get_weather.return_value
        self.weather.get_weather.return_value = replace(snapshot, forecast=tuple(
            replace(day, precipitation_probability=75) for day in snapshot.forecast))
        self.assertEqual(self.decide(token).status_code, 409)
        self.mutate.assert_not_called()

    def test_owner_expired_lifecycle_and_stale_revision_protection(self):
        token = self.token()
        foreign_path = self.weather_path.replace(self.current.draft_id, '00000000-0000-0000-0000-000000000099')
        self.assertEqual(self.client.post(foreign_path, headers=preview.ORIGIN, data=dict(csrf_token=self.csrf,
            expected_revision='3', proposal_token=token, decision='accept')).status_code, 404)
        original = self.current
        for change in (dict(state='saved'), dict(state='expired'), dict(expires_at=NOW.replace(year=2000))):
            self.current = replace(original, **change)
            self.assertEqual(self.decide(token).status_code, 409)
        self.current = replace(original, revision=4)
        self.assertEqual(self.decide(token, expected_revision='3').status_code, 409)
        self.mutate.assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.decide(token).status_code, 302)

    def test_conversational_update_invalidates_previous_weather_token(self):
        token = self.token()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.current.revision, 4)
        self.assertEqual(self.decide(token, expected_revision='3').status_code, 409)
        # Changing the form revision does not make its old signed binding valid.
        self.assertEqual(self.decide(token).status_code, 409)
        self.mutate.assert_called_once()

    def test_accept_clears_prior_explanations_then_conversation_remains_available(self):
        self.provider.explain.return_value = {'explanations': [dict(place_id=self.places[0].id, reason='Old outdoor explanation')]}
        response = self.client.post(preview.PREVIEW+'/explain', headers=preview.ORIGIN,
            data=dict(csrf_token=self.csrf, expected_revision='3'))
        self.assertIn(b'Old outdoor explanation', response.data)
        token = Document(response.get_data(as_text=True)).find('input', name='proposal_token')[0].attrs['value']
        response = self.decide(token)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Old outdoor explanation', response.data)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.current.revision, 5)
        self.assertEqual(len(self.current.preview.source.selected_place_ids), 2)

    def test_new_cutoff_settings_or_failed_atomic_write_cannot_be_bypassed(self):
        from itinerary_draft_service import DraftUnavailableError
        from settings_service import SESSION_KEY
        token = self.token()
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'trips'}
        self.assertEqual(self.decide(token).status_code, 409)
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'all'}
        with patch.dict(self.namespace, manila_now=lambda: NOW+timedelta(days=1)):
            self.assertEqual(self.decide(token).status_code, 409)
        self.mutate.assert_not_called()
        before = deepcopy(self.current)
        self.mutate.side_effect = DraftUnavailableError()
        self.assertEqual(self.decide(token).status_code, 503)
        self.mutate.assert_called_once()
        self.assertEqual(self.current, before)

    def test_metadata_provenance_change_invalidates_signed_approval(self):
        token = self.token()
        document = metadata_document(self.places, self.exposures)
        document['destinations'][4]['source_note'] = 'Revised synthetic evidence.'
        self.metadata = validate_weather_catalog(document)
        self.assertEqual(self.decide(token).status_code, 409)
        self.mutate.assert_not_called()

    def test_verified_weather_labels_and_notices_are_escaped(self):
        self.places = tuple(replace(item, name='<img src=x onerror=alert(1)>')
            if item.id == self.places[4].id else item for item in self.places)
        self.catalog.list_published.return_value = self.places
        self.metadata = validate_weather_catalog(metadata_document(self.places, self.exposures))
        response = self.client.get(preview.PREVIEW)
        self.assertIn(b'&lt;img src=x onerror=alert(1)&gt;', response.data)
        self.assertEqual(Document(response.get_data(as_text=True)).find('img'), [])

    def test_unknown_real_metadata_retains_checkpoint4_review_only_behavior(self):
        self.metadata = load_weather_catalog()
        response = self.client.get(preview.PREVIEW)
        self.assertIn(b'Review Itinerary', response.data)
        self.assertNotIn(b'Review Suggested Adjustment', response.data)
        self.assertNotIn(b'proposal_token', response.data)
        self.mutate.assert_not_called()
