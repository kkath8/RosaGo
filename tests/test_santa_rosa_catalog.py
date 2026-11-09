"""Review the real SQL seed rows through the application's public parser offline."""
from collections import Counter
import json
from pathlib import Path
import re
import unittest
from uuid import uuid4

from places_service import parse_place_row


class SantaRosaCatalogTests(unittest.TestCase):
    def test_sql_contains_all_reviewed_places_as_readable_published_records(self):
        folder = Path(__file__).resolve().parents[1] / 'data' / 'santa_rosa_places' / 'archive'
        reviewed = json.loads((folder / 'places.json').read_text(encoding='utf-8'))
        sql = (folder / 'publish.sql').read_text(encoding='utf-8')
        # Parse literal seed values as text. No SQL engine or SQL execution.
        insert = sql.split('INSERT INTO rosago_requested_places (', 1)[1].split(';\n', 1)[0]
        columns_text, values_text = insert.split(') VALUES', 1)
        columns = [name.strip() for name in columns_text.split(',')]
        rows = []
        for line in values_text.strip().splitlines():
            tokens = re.findall(r"'(?:[^']|'')*'|NULL", line)
            self.assertEqual(len(tokens), len(columns))
            values = [None if token == 'NULL' else token[1:-1].replace("''", "'") for token in tokens]
            rows.append(dict(zip(columns, values)))
        self.assertEqual(rows, reviewed)
        self.assertEqual(len(rows), 28)
        self.assertEqual(len({row['slug'] for row in rows}), 28)
        self.assertEqual(Counter(row['category'] for row in rows),
                         {'heritage': 9, 'industrial': 4, 'attraction': 6, 'shopping': 9})
        for row in rows:
            self.assertEqual(row['status'], 'published')
            place = parse_place_row(row | dict(id=str(uuid4()),
                created_at='2026-10-22T00:00:00Z', updated_at='2026-10-22T00:00:00Z'))
            self.assertIsNone(place.latitude)
            self.assertIsNone(place.longitude)
