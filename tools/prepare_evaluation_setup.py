"""Prepare SQL locally; never connect to or modify a hosted project."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'jfaufpfzfhysqkhcdsrs'
PROTECTED = 'brnkigrrqdrywahvcbvc'
OUTPUT = ROOT / 'evaluation' / 'setup'


def body_digest(text):
    definition = text.index('CREATE OR REPLACE FUNCTION public.rosago_admin_mutate_destination_unlogged(')
    start = text.index('AS $$', definition) + len('AS $$')
    end = text.index('$$;', start)
    return hashlib.md5(text[start:end].replace('\r', '').encode()).hexdigest()


def prepare():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inputs = sorted((ROOT / 'migrations').glob('[0-9][0-9][0-9][0-9]_*.sql'))
    assert len(inputs) == 14, 'Review changed migration inventory before preparing.'
    photo_source = ROOT / 'tools' / 'admin_destination_photo_contract.sql'
    photo = photo_source.read_text(encoding='utf-8')
    assert body_digest(photo) == 'aa4441116ded963faa4e1ee8e3024e4b'
    changed_photo = photo.replace(PROTECTED, PROJECT)
    new_digest = body_digest(changed_photo)
    environment_source = next(source for source in inputs if source.name.startswith('0014_'))
    environment_sql = environment_source.read_text(encoding='utf-8')
    assert body_digest(environment_sql) == '399faf695b6a607f33bf1fb7c2dd9386'
    changed_environment = environment_sql.replace(PROTECTED, PROJECT)
    environment_digest = body_digest(changed_environment)
    changed_environment = changed_environment.replace('aa4441116ded963faa4e1ee8e3024e4b', new_digest)
    changed_environment = changed_environment.replace('399faf695b6a607f33bf1fb7c2dd9386', environment_digest)
    manifest = []
    for source in inputs:
        if source.name.startswith('0014_'):
            items = [(photo_source, '0013b_destination_photo_contract.sql', changed_photo),
                     (source, source.name, changed_environment)]
        else:
            items = [(source, source.name, source.read_text(encoding='utf-8'))]
        for original, name, sql in items:
            assert PROTECTED not in sql, 'Production reference must not enter prepared SQL.'
            header = '-- LOCAL PREPARATION ONLY. Target project: ' + PROJECT + '\n'
            content = header + sql
            (OUTPUT / name).write_text(content, encoding='utf-8', newline='\n')
            manifest.append({'file': name, 'source': original.relative_to(ROOT).as_posix(),
                             'source_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
                             'prepared_sha256': hashlib.sha256(content.encode()).hexdigest()})
    result = {'target_project_ref': PROJECT, 'hosted_execution_authorized': False,
              'ordered_files': manifest,
              'photo_function_expected_md5': new_digest,
              'accounts_or_production_data_included': False}
    fixture = json.loads((ROOT / 'evaluation' / 'synthetic_places.json').read_text(encoding='utf-8'))
    rows = fixture['places']
    columns = ('id', 'name', 'slug', 'description', 'category', 'address', 'latitude',
               'longitude', 'image_url', 'status', 'environment', 'tourism_type',
               'tourism_category', 'tourism_opening_hours_raw', 'tourism_closing_hours_raw',
               'tourism_hours_status', 'tourism_source', 'tourism_source_row')
    assert rows and all(set(row) == set(columns) and row['image_url'] is None for row in rows)
    data = json.dumps(rows)
    assert '$synthetic$' not in data and PROTECTED not in data
    seed = ('-- REVIEW ONLY: synthetic places, new evaluation project ' + PROJECT + '.\n'
            'BEGIN;\nLOCK TABLE public.places IN EXCLUSIVE MODE;\n'
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.places) THEN "
            "RAISE EXCEPTION 'Seed requires empty places; stop and review.'; END IF; END $$;\n"
            'INSERT INTO public.places (' + ','.join(columns) + ')\n'
            'SELECT ' + ','.join(columns) + ' FROM jsonb_populate_recordset(NULL::public.places,\n'
            '$synthetic$' + data + '$synthetic$::jsonb);\nCOMMIT;\n')
    (OUTPUT / 'synthetic_seed.sql').write_text(seed, encoding='utf-8', newline='\n')
    result['synthetic_seed_sha256'] = hashlib.sha256(seed.encode()).hexdigest()
    result['synthetic_seed_runs_after'] = manifest[-1]['file']
    (OUTPUT / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    result = prepare()
    print(json.dumps({'prepared_files': len(result['ordered_files']), 'target': PROJECT,
                      'hosted_changes': 0}))
