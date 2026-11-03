"""Review the real SQL seed rows through the application's public parser offline."""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import unittest
from uuid import uuid4

from places_service import parse_place_row


class SantaRosaCatalogTests(unittest.TestCase):
    def test_sql_contains_all_reviewed_places_as_readable_published_records(self):
        folder = Path(__file__).resolve().parents[1] / 'data' / 'santa_rosa_places'
        reviewed = json.loads((folder / 'places.json').read_text(encoding='utf-8'))
        sql = (folder / 'publish.sql').read_text(encoding='utf-8')
        # Execute the actual INSERT values locally, without running PostgreSQL DDL
        # or touching Supabase. This also verifies Unicode and SQL string escaping.
        insert = sql.split('INSERT INTO rosago_requested_places (', 1)[1].split(';\n', 1)[0]
        columns = list(reviewed[0])
        with sqlite3.connect(':memory:') as db:
            db.row_factory = sqlite3.Row
            db.execute('CREATE TABLE rosago_requested_places (' + ','.join(columns) + ')')
            db.execute('INSERT INTO rosago_requested_places (' + insert)
            rows = [dict(row) for row in db.execute('SELECT * FROM rosago_requested_places')]
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
