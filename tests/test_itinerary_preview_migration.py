"""Offline SQL contracts and serializer model; never connect to any database.

The model checks the explicit SQL serialization algorithm against frozen Python
bytes, not PostgreSQL execution. Migration self-checks repeat the vectors upon
future authorized application. These tests do not prove RLS or concurrency.
"""
import hashlib
import json
from pathlib import Path
import re
import unittest

import itinerary_builder as builder
import itinerary_preview as preview
from recommendation_engine import POLICY_VERSION
from test_itinerary_preview import (
    CANONICAL_VECTOR, VECTOR_HASHES, CATALOG_VECTOR, CATALOG_VECTOR_HASH,
    SOURCE_VECTOR, SOURCE_VECTOR_HASH,
)


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / 'migrations/0007_itinerary_preview_lifecycle.sql').read_text(encoding='utf-8')
CODE = re.sub(r'--[^\n]*', '', SQL)
FLAT = ' '.join(CODE.split())


def function_body(name):
    return re.search(r'CREATE FUNCTION public\.' + name + r'\(.*?AS \$\$(.*?)\$\$;',
                     CODE, re.S).group(1)


def sql_serializer_model(value):
    """Transliterate the SQL's explicit scalar/array/object rules, without dumps.

    Read the SQL escape table rather than independently duplicating it. Other
    operations are pinned structurally in test_serializer_algorithm_contract.
    Validated manifests/catalogs are bounded well below serializer limits.
    """
    body = function_body('rosago_preview_canonical_json')
    escapes = {int(code): '\\' + suffix for code, suffix in re.findall(
        r"WHEN (\d+) THEN pg_catalog.chr\(92\) \|\| '([^']*)'", body)}
    escapes[92] = '\\\\'

    def serialize(item):
        if item is None:
            return 'null'
        if type(item) is bool:
            return 'true' if item else 'false'
        if type(item) is int and -(2 ** 63) <= item < 2 ** 63:
            return str(item)
        if type(item) is str:
            encoded = []
            for char in item:
                code = ord(char)
                if code == 0 or 0xD800 <= code <= 0xDFFF:
                    raise ValueError('Not representable in UTF8 JSONB')
                encoded.append(escapes.get(code, '\\u' + format(code, '04x') if code < 32 else char))
            return '"' + ''.join(encoded) + '"'
        if type(item) is list:
            return '[' + ','.join(map(serialize, item)) + ']'
        if type(item) is dict:
            return '{' + ','.join(serialize(key) + ':' + serialize(item[key])
                                  for key in sorted(item, key=lambda key: key.encode('utf-8'))) + '}'
        raise ValueError('Unsupported JSON value')

    return serialize(value).encode('utf-8')


class PreviewMigrationTests(unittest.TestCase):
    def test_immutable_live_migrations(self):
        expected = {
            '0001_profiles.sql': '3d1164c291775e56a6d52eec0f47f8169a5ae811c5de8410864b705a00b406f5',
            '0002_places.sql': '472757526f37398e67408bd4871f6cb729c66084c29d09a38349d4e0d81864ea',
            '0003_trips.sql': '419cbf2977a0b3646326d041338af66277d4f7a8340e3a6a1ad24f4eb187cb6d',
            '0004_itinerary_foundation.sql': '0754c2aa007f95d61158468f627ece33bf8b8183ccb7d0cc8d372a4b840b9298',
            '0005_itinerary_draft_lifecycle.sql': '935cc40b7d783e78b11f1ee64f660456d3f3f42c6617fe35d7d32442bc382e9a',
            '0006_itinerary_preference_extension.sql': '88c789b180e9c340e56abf1c32c26bc7ddbec3ce2e4c0497b1398858cbf852fc',
        }
        for name, digest in expected.items():
            data = (ROOT / 'migrations' / name).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)

    def test_additive_scope_and_privileges(self):
        names = re.findall(r'CREATE FUNCTION public\.(\w+)\(', CODE)
        self.assertEqual(len(names), 6)
        self.assertEqual(CODE.count('SECURITY DEFINER'), 2)
        self.assertEqual(CODE.count("SET search_path = ''"), 6)
        self.assertEqual(CODE.count('OWNER TO postgres;'), 6)
        self.assertEqual(CODE.count('FROM PUBLIC, anon, authenticated, service_role;'), 1)
        grant = re.findall(r'GRANT .*?;', FLAT)
        self.assertEqual(grant, [
            'GRANT EXECUTE ON FUNCTION public.rosago_itinerary_draft_store_preview(uuid, bigint, jsonb), '
            'public.rosago_itinerary_draft_return_to_editing(uuid, bigint) TO authenticated;'])
        self.assertNotRegex(FLAT, r'\b(CREATE OR REPLACE|CREATE TABLE|ALTER TABLE|CREATE EXTENSION|DROP|TRUNCATE|INSERT|DELETE FROM)\b')
        self.assertNotIn('accepted_preview_digest', CODE)
        self.assertNotRegex(CODE, r'public\.trip(?:s|_places|_itinerary|_stop_plans)\b')
        self.assertNotIn('SQLERRM', CODE)
        self.assertTrue(CODE.strip().startswith('BEGIN;'))
        self.assertTrue(CODE.strip().endswith('COMMIT;'))

    def test_rpc_ownership_revision_expiry_and_states(self):
        for name in ('rosago_itinerary_draft_store_preview', 'rosago_itinerary_draft_return_to_editing'):
            body = ' '.join(function_body(name).split())
            for clause in (
                'owner_id uuid := auth.uid()', 'IF owner_id IS NULL',
                'p_expected_revision IS NULL', 'p_expected_revision NOT BETWEEN 1 AND 9223372036854775806',
                'draft.id = p_draft_id AND draft.user_id = owner_id FOR UPDATE',
                'IF NOT FOUND THEN', "ERRCODE = 'P0002', MESSAGE = 'Draft update rejected.'",
                'draft.revision = p_expected_revision', 'draft.schema_version = 1',
                'draft.expires_at > pg_catalog.clock_timestamp()', 'revision = draft.revision + 1',
                "current_setting('transaction_isolation') <> 'read committed'",
                'RETURNING draft.id, draft.state, draft.revision',
            ):
                self.assertIn(clause, body, name)
            self.assertEqual(body.count('revision = draft.revision + 1'), 1)
            self.assertLess(body.index('FOR UPDATE'), body.index('RETURN QUERY UPDATE'))
            self.assertNotRegex(body, r'SET (?:expires_at|preferences|saved_at|saved_trip_id)')
        store = function_body('rosago_itinerary_draft_store_preview')
        self.assertIn("locked_draft.state NOT IN ('editing', 'preview_ready')", store)
        self.assertIn('locked_draft.expires_at <= pg_catalog.clock_timestamp()', store)
        self.assertIn("locked_draft.state = 'preview_ready' AND", store)
        self.assertIn("(locked_draft.preview #> '{source,selected_place_ids}')", store)
        self.assertIn("SET preview = p_candidate_preview, state = 'preview_ready'", store)
        editing = function_body('rosago_itinerary_draft_return_to_editing')
        self.assertIn("SET preview = NULL, state = 'editing'", editing)
        self.assertIn("draft.state = 'preview_ready'", editing)

    def test_schema_preferences_and_policy_match_python(self):
        body = function_body('rosago_validate_itinerary_preview')
        for document, keys in (('p_preview', preview._PREVIEW_KEYS),
                               ('source_doc', preview._SOURCE_KEYS),
                               ('constraints_doc', preview._CONSTRAINT_KEYS),
                               ('day_doc', {'date', 'stops'})):
            found = re.search(r'rosago_preview_json_keys\(' + document + r', ARRAY\[(.*?)\]', body, re.S)
            self.assertEqual(set(re.findall(r"'([^']*)'", found.group(1))), set(keys))
        for constant in (builder.POLICY_VERSION, POLICY_VERSION, 'personalized', 'rosago:source:v1:'):
            self.assertIn(constant, body)
        self.assertIn('public.rosago_validate_draft_preferences(p_preferences)', body)
        self.assertIn('validated_preferences IS DISTINCT FROM p_preferences', body)
        self.assertIn('(constraints_doc -> field_name) IS DISTINCT FROM (validated_preferences -> field_name)', body)
        self.assertIn("(p_preview -> 'source_version') IS DISTINCT FROM pg_catalog.jsonb_build_object(", body)
        self.assertIn("'kind', 'draft', 'version', 'v1:'", body)
        self.assertIn('pg_catalog.to_jsonb(p_draft_id::text)', body)
        self.assertIn('pg_catalog.to_jsonb(p_revision)', body)

    def test_days_stops_equal_count_and_unresolved(self):
        body = ' '.join(function_body('rosago_validate_itinerary_preview').split())
        for clause in (
            'destination_count NOT BETWEEN 1 AND 100', 'identity::uuid = ANY(selected_ids)',
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            'day_count NOT BETWEEN 1 AND 7', "jsonb_array_length(p_preview -> 'days') <> day_count",
            "pg_catalog.to_char(first_date + day_index, 'YYYY-MM-DD')",
            'destination_count / day_count + CASE WHEN day_index < destination_count % day_count THEN 1 ELSE 0 END',
            "jsonb_array_length(day_doc -> 'stops') <> expected_count",
            'stop_index := stop_index + 1', 'stop_index <> destination_count',
            'stop_doc IS DISTINCT FROM pg_catalog.jsonb_build_object(',
            "'place_id', selected_ids[stop_index]::text, 'order', stop_index, 'source', 'recommended', 'keep_place', true",
            "validated_preferences -> 'budget_centavos' <> 'null'::jsonb",
            "unresolved := unresolved || '[\"budget_feasibility\"]'::jsonb",
            "(p_preview -> 'unresolved_constraints') IS DISTINCT FROM unresolved",
            'PERFORM public.rosago_preview_canonical_json(p_preview)',
            'pg_catalog.octet_length(p_preview::text) > 262144',
        ):
            self.assertIn(clause, body)
        unresolved = json.loads(re.search(r"unresolved jsonb := '([^']*)'", body).group(1))
        self.assertEqual(tuple(unresolved), builder.UNRESOLVED_CONSTRAINTS)

    def test_place_locking_and_catalog_exact_facts(self):
        body = ' '.join(function_body('rosago_itinerary_draft_store_preview').split())
        for clause in (
            'WHERE place.id = ANY(selected_ids) ORDER BY place.id FOR SHARE LOOP',
            "place_row.status <> 'published'", "locked_draft.preferences -> 'interests' ? place_row.category",
            'locked_count <> pg_catalog.cardinality(selected_ids)',
            "public.rosago_preview_hash('rosago:catalog:v1:', catalog)",
            "pg_catalog.starts_with(place_row.slug, 'rosago-test-v1-')",
            'pg_catalog.btrim(place_row.name, whitespace)', 'pg_catalog.btrim(place_row.address, whitespace)',
        ):
            self.assertIn(clause, body)
        for forbidden in ('place_row.description', 'place_row.image_url', 'place_row.updated_at',
                          'place_row.latitude', 'place_row.longitude'):
            self.assertNotIn(forbidden, body)
        self.assertNotIn('FOR KEY SHARE', body)
        self.assertLess(body.index('FOR SHARE LOOP'), body.index('RETURN QUERY UPDATE'))
        keys = re.search(r'catalog := catalog.*?jsonb_build_object\((.*?)\)\);', body).group(1)
        self.assertEqual(set(re.findall(r"'([^']*)',", keys)),
                         {'id', 'category', 'status', 'published', 'name', 'address', 'is_test_record'})

    def test_serializer_algorithm_contract(self):
        body = ' '.join(function_body('rosago_preview_canonical_json').split())
        for clause in (
            'p_depth NOT BETWEEN 0 AND 16', 'pg_catalog.octet_length(result) > 262144',
            'result::numeric NOT BETWEEN -9223372036854775808 AND 9223372036854775807',
            'ORDER BY o.key COLLATE "C"',
            'WITH ORDINALITY AS a(value, ordinal) ORDER BY a.ordinal',
            "separator := ','", "|| ':' || public.rosago_preview_canonical_json(entry.value, p_depth + 1)",
            'code := pg_catalog.ascii(character)', 'WHEN 92 THEN pg_catalog.chr(92) || pg_catalog.chr(92)',
            "pg_catalog.chr(92) || 'u' || pg_catalog.lpad(pg_catalog.to_hex(code), 4, '0')",
            "result COLLATE \"C\" !~ '^-?(0|[1-9][0-9]*)$'",
        ):
            self.assertIn(clause, body)
        self.assertNotIn('result := p_value::text', body)
        hashing = function_body('rosago_preview_hash')
        self.assertIn('pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(', hashing)
        self.assertIn("p_domain || public.rosago_preview_canonical_json(p_value), 'UTF8')), 'hex')", hashing)
        self.assertIn("current_setting('server_encoding') <> 'UTF8'", CODE)

    def test_frozen_sql_vectors_and_hashes(self):
        rows = re.findall(r"\('(rosago:[a-z]+:v1:)', \$vector\$(.*?)\$vector\$, '([0-9a-f]{64})'\)", SQL)
        expected = [(domain.decode(), CANONICAL_VECTOR, digest) for domain, digest in VECTOR_HASHES.items()]
        expected += [('rosago:catalog:v1:', CATALOG_VECTOR, CATALOG_VECTOR_HASH),
                     ('rosago:source:v1:', SOURCE_VECTOR, SOURCE_VECTOR_HASH)]
        self.assertEqual(rows, expected)
        for domain, canonical, digest in rows:
            value = json.loads(canonical)
            encoded = sql_serializer_model(value)
            self.assertEqual(encoded, canonical.encode('utf-8'))
            self.assertEqual(encoded, preview.canonical_json(value))
            self.assertEqual(hashlib.sha256(domain.encode() + encoded).hexdigest(), digest)
        self.assertIn('public.rosago_preview_canonical_json(vector.canonical::jsonb) <> vector.canonical', CODE)
        self.assertIn('public.rosago_preview_hash(vector.domain, vector.canonical::jsonb) <> vector.digest', CODE)

    def test_serializer_controls_unicode_order_and_integers(self):
        values = [dict(escape=''.join(chr(i) for i in range(1, 128))),
                  {'\U0001f600': 'e\u0301', '\ue000': 'é', '\u0085': '東京', 'a': '\u2028\u2029/'},
                  {'z': {'z': 1, 'a': 2}, 'a': [2, 1]},
                  [-(2 ** 63), 2 ** 63 - 1, 0, True, False, None]]
        for value in values:
            self.assertEqual(sql_serializer_model(value), preview.canonical_json(value))
        for value in (1.0, 2 ** 63, -(2 ** 63) - 1, '\x00', '\ud800'):
            with self.assertRaises(ValueError):
                sql_serializer_model(value)


if __name__ == '__main__':
    unittest.main()
