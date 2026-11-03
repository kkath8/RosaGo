"""Offline Tourism review helpers. Not imported by the app; never executes SQL."""
from collections import Counter
from pathlib import Path
import re
from types import MappingProxyType
from uuid import UUID
import xml.etree.ElementTree as ET
from zipfile import ZipFile

SOURCE = 'City Tourism Office | RosaGO_Santa_Rosa_POIs.xlsx | Santa Rosa POIs'
SHEET = 'Santa Rosa POIs'
CATEGORY_MAPPING = MappingProxyType({
    'Theme Park / Recreation': 'attraction',
    'Nature / Outdoor Recreation': 'nature',
    'Shopping Mall / Dining': 'shopping',
    'Outlet Shopping / Dining': 'shopping',
    'Shopping Mall / Entertainment': 'shopping',
    'Shopping Mall / Lifestyle': 'shopping',
    'Shopping Mall / Retail': 'shopping',
    'Museum / Cultural Heritage': 'heritage',
    'Religious / Historical Landmark': 'heritage',
    'Historical Landmark': 'heritage',
    'Historical / Heritage Site': 'heritage',
    'Public Park / Recreation': 'nature',
    'Farm / Family Recreation': 'attraction',
    'Garden / Outdoor Recreation': 'nature',
    'Japanese Restaurant': 'dining',
    'Filipino Restaurant': 'dining',
    'Italian Restaurant': 'dining',
})
SOURCE_FIELDS = ('name', 'tourism_type', 'tourism_category', 'tourism_opening_hours_raw',
                 'tourism_closing_hours_raw', 'description', 'address')
VALUE_FIELDS = ('name', 'category', 'description', 'address', 'tourism_type',
                'tourism_category', 'tourism_opening_hours_raw', 'tourism_closing_hours_raw',
                'tourism_hours_status', 'tourism_source', 'tourism_source_row')


def map_category(source_category):
    """Exact source lookup; unsupported labels require human review."""
    if type(source_category) is not str or source_category not in CATEGORY_MAPPING:
        raise ValueError('Unknown Tourism category.')
    return CATEGORY_MAPPING[source_category]


def hours_status(opening, closing):
    """Classify source values without altering them or claiming verification."""
    if any(value is not None and type(value) is not str for value in (opening, closing)):
        raise ValueError('Invalid raw hours.')
    if opening == 'Verify' or closing == 'Verify':
        return 'verify_required'
    if opening in (None, '') and closing in (None, ''):
        return 'not_supplied'
    return 'unverified'


def read_workbook(path):
    """Read the named worksheet verbatim with stdlib; no spreadsheet automation."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(Path(path)) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = [s for s in workbook.findall('m:sheets/m:sheet', ns) if s.get('name') == SHEET]
        if len(sheets) != 1:
            raise ValueError('Expected Tourism worksheet.')
        rel_id = sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in relationships if r.get('Id') == rel_id)
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in s.findall('.//m:t', ns))
                       for s in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', ns)]
        rows = []
        for row in ET.fromstring(archive.read(target)).findall('m:sheetData/m:row', ns):
            cells = {}
            for cell in row.findall('m:c', ns):
                column = re.sub(r'\d', '', cell.get('r'))
                value = cell.find('m:v', ns)
                value = value.text if value is not None else None
                if cell.get('t') == 's':
                    value = strings[int(value)]
                elif cell.get('t') == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall('.//m:t', ns))
                cells[column] = value
            number = int(row.get('r'))
            if number == 1:
                if [cells.get(c) for c in 'ABCDEFGH'] != [
                        'No.', 'Place', 'Type', 'Category', 'Opening Hours', 'Closing Hours', 'Description', 'Address']:
                    raise ValueError('Unexpected Tourism headers.')
            elif any(cells.get(c) is not None for c in 'BCDEFGH'):
                rows.append(dict(zip(SOURCE_FIELDS, (cells.get(c) for c in 'BCDEFGH')))
                            | {'tourism_source': SOURCE, 'tourism_source_row': number})
        return rows


def validate_plan(plan):
    rows = plan['rows']
    if len(rows) != 20 or Counter(row['action'] for row in rows) != {'UPDATE EXISTING': 12, 'INSERT NEW': 8}:
        raise ValueError('Expected 12 updates and 8 inserts.')
    for field in ('id', 'slug', 'tourism_source_row'):
        if len({row[field] for row in rows}) != 20:
            raise ValueError('Duplicate transition identity.')
    if {row['tourism_source_row'] for row in rows} != set(range(2, 22)):
        raise ValueError('Unexpected source rows.')
    for row in rows:
        if (str(UUID(row['id'])) != row['id'] or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', row['slug'])
                or row['tourism_type'] not in ('Local', 'Common') or row['tourism_source'] != SOURCE
                or row['category'] != map_category(row['tourism_category'])
                or row['tourism_hours_status'] != hours_status(row['tourism_opening_hours_raw'], row['tourism_closing_hours_raw'])):
            raise ValueError('Invalid transition metadata.')
        old = row['existing']
        if row['action'] == 'UPDATE EXISTING':
            if old is None or any(row[k] != old[k] for k in ('id', 'slug', 'latitude', 'longitude')) or row['status'] != 'published':
                raise ValueError('Existing identity must be preserved.')
        elif old is not None or row['status'] not in ('draft', 'published') or row['latitude'] is not None or row['longitude'] is not None:
            raise ValueError('New POIs require an explicit draft/published status and no coordinates.')


def _literal(value):
    if value is None:
        return 'NULL'
    if type(value) is int:
        return str(value)
    return "'" + value.replace("'", "''") + "'"


def render_review_sql(plan):
    """Produce text only. No database dependency or execution path exists here."""
    validate_plan(plan)
    lines = [
        '-- REVIEW ONLY. NOT EXECUTED. Not a migration; never run on startup.',
        '-- Requires applied 0011. New POI publication follows each explicit plan status.',
        '-- One-time transition: guards reject identity drift, collisions and replay.',
        'BEGIN;',
        'SET LOCAL standard_conforming_strings = on;',
        'LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;',
        'CREATE TEMP TABLE tourism_before ON COMMIT DROP AS SELECT * FROM public.places;',
        'CREATE TEMP TABLE tourism_review (',
        '    id uuid PRIMARY KEY, slug text UNIQUE NOT NULL, expected_name text, expected_category text,',
        '    name text NOT NULL, category text NOT NULL, description text NOT NULL, address text NOT NULL,',
        '    tourism_type text NOT NULL, tourism_category text NOT NULL,',
        '    tourism_opening_hours_raw text, tourism_closing_hours_raw text, tourism_hours_status text NOT NULL,',
        f'    tourism_source text NOT NULL DEFAULT {_literal(SOURCE)},',
        "    tourism_source_row integer UNIQUE NOT NULL, final_status text NOT NULL CHECK (final_status IN ('draft', 'published'))",
        ') ON COMMIT DROP;',
        'INSERT INTO tourism_review (id, slug, expected_name, expected_category, name, category, description, address,',
        '    tourism_type, tourism_category, tourism_opening_hours_raw, tourism_closing_hours_raw, tourism_hours_status, tourism_source_row, final_status) VALUES',
    ]
    for i, row in enumerate(plan['rows']):
        old = row['existing'] or {}
        values = [row['id'], row['slug'], old.get('name'), old.get('category')]
        values += [row[k] for k in VALUE_FIELDS if k != 'tourism_source']
        values.append(row['status'])
        lines.append('    (' + ', '.join(map(_literal, values)) + (');' if i == 19 else '),'))
    lines += [
        'DO $guard$', 'BEGIN',
        "    IF (SELECT count(*) FROM tourism_review) <> 20 THEN RAISE EXCEPTION 'Expected 20 Tourism rows'; END IF;",
        '    IF (SELECT count(*) FROM tourism_review r JOIN public.places p ON p.id = r.id',
        "        WHERE r.expected_name IS NOT NULL AND (p.name, p.slug, p.category, p.status)",
        "        IS NOT DISTINCT FROM (r.expected_name, r.slug, r.expected_category, 'published'::text)",
        '        AND p.tourism_type IS NULL AND p.tourism_category IS NULL',
        '        AND p.tourism_opening_hours_raw IS NULL AND p.tourism_closing_hours_raw IS NULL',
        '        AND p.tourism_hours_status IS NULL AND p.tourism_source IS NULL AND p.tourism_source_row IS NULL) <> 12 THEN',
        "        RAISE EXCEPTION 'Existing identity/metadata drift: re-review before applying';",
        '    END IF;',
        '    IF EXISTS (SELECT 1 FROM tourism_review r JOIN public.places p ON p.id = r.id OR p.slug = r.slug',
        '        WHERE r.expected_name IS NULL) THEN',
        "        RAISE EXCEPTION 'New UUID or slug already exists: re-review before applying';",
        '    END IF;', 'END;', '$guard$;',
    ]
    assignments = ', '.join(VALUE_FIELDS)
    for row in plan['rows']:
        if row['existing']:
            lines += [f"-- Worksheet row {row['tourism_source_row']}: preserve UUID, slug, coordinates, image and status.",
                      'UPDATE public.places SET', f'    ({assignments}) =',
                      f'    (SELECT {assignments} FROM tourism_review WHERE tourism_source_row = {row["tourism_source_row"]})',
                      f"WHERE id = '{row['id']}'::uuid;"]
        else:
            lines += [f"-- Worksheet row {row['tourism_source_row']}: new identity, no pin, explicit status {row['status']}.",
                      'INSERT INTO public.places (id, slug, ' + assignments + ', latitude, longitude, image_url, status)',
                      f"SELECT '{row['id']}'::uuid, slug, {assignments}, NULL, NULL, NULL, {_literal(row['status'])}",
                      f'FROM tourism_review WHERE tourism_source_row = {row["tourism_source_row"]};']
    target_tuple = ', '.join('p.' + k for k in VALUE_FIELDS)
    review_tuple = ', '.join('r.' + k for k in VALUE_FIELDS)
    lines += [
        'DO $verify$', 'BEGIN',
        '    IF (SELECT count(*) FROM public.places) <> (SELECT count(*) + 8 FROM tourism_before) THEN',
        "        RAISE EXCEPTION 'Expected exactly eight new records'; END IF;",
        '    IF (SELECT count(*) FROM tourism_review r JOIN public.places p ON p.id = r.id',
        f'        WHERE ({target_tuple}) IS NOT DISTINCT FROM ({review_tuple})',
        '        AND p.slug = r.slug',
        '        AND p.status = r.final_status) <> 20 THEN',
        "        RAISE EXCEPTION 'Transition field verification failed'; END IF;",
        '    IF EXISTS (SELECT 1 FROM tourism_before b JOIN public.places p ON p.id = b.id',
        '        JOIN tourism_review r ON r.id = b.id',
        '        WHERE (p.slug, p.latitude, p.longitude, p.image_url, p.status, p.created_at)',
        '        IS DISTINCT FROM (b.slug, b.latitude, b.longitude, b.image_url, b.status, b.created_at)) THEN',
        "        RAISE EXCEPTION 'Existing identity/location preservation failed'; END IF;",
        '    IF EXISTS (SELECT 1 FROM tourism_before b LEFT JOIN public.places p ON p.id = b.id',
        '        WHERE NOT EXISTS (SELECT 1 FROM tourism_review r WHERE r.id = b.id)',
        '        AND to_jsonb(p) IS DISTINCT FROM to_jsonb(b)) THEN',
        "        RAISE EXCEPTION 'Unmatched existing records changed'; END IF;",
        '    IF EXISTS (SELECT 1 FROM tourism_review r JOIN public.places p ON p.id = r.id',
        '        WHERE r.expected_name IS NULL AND (p.latitude IS NOT NULL OR p.longitude IS NOT NULL)) THEN',
        "        RAISE EXCEPTION 'New coordinates must remain null'; END IF;",
        'END;', '$verify$;', 'COMMIT;', '',
    ]
    return '\n'.join(lines)
