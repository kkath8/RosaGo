"""Read-only live catalog comparison; never writes a draft or changes coordinates.

Run from the project root with .venv/Scripts/python.exe tools/audit_geographic_recommendations.py.
The original policy is retained by select_destinations when no locations are
supplied, so both policies can be compared against the exact same catalog read.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from itinerary_geography import coordinates, distance_km
from itinerary_selection_policy import select_destinations
from places_client import PublicPlacesClient
from places_service import PlacesService
from recommendation_engine import rank_candidates


def compare(places, interests, count):
    preferences = dict(interests=interests, trip_pace='balanced',
                       start_date='2026-11-01', end_date='2026-11-01')
    ranked = rank_candidates(preferences, places).matched
    by_id = {place.id: place for place in places}

    def describe(selected):
        sequence = [by_id[c.place_id] for c in selected]
        legs = []
        for a, b in zip(sequence, sequence[1:]):
            pa, pb = coordinates(a), coordinates(b)
            legs.append(dict(start=a.name, end=b.name,
                             haversine_km=round(distance_km(pa, pb), 3) if pa and pb else None))
        known = [p for p in sequence if coordinates(p) is not None]
        # This is not total itinerary travel: unknown locations are skipped.
        subtotal = sum(distance_km(coordinates(a), coordinates(b)) for a, b in zip(known, known[1:]))
        return dict(visit_sequence=[p.name for p in sequence], adjacent_legs=legs,
                    located_subsequence=[p.name for p in known],
                    located_subsequence_km=round(subtotal, 3))

    return dict(interests=interests, requested_stops=count,
                before=describe(select_destinations(preferences, ranked, place_count=count)),
                after=describe(select_destinations(preferences, ranked, place_count=count, places=places)))


def main():
    load_dotenv('.env')
    metadata = os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true'
    service = PlacesService(PublicPlacesClient(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY')).database_client,
                            tourism_metadata_enabled=metadata)
    try:
        places = service.list_published(limit=100, offset=0)
    except Exception as error:
        raise SystemExit('Read-only catalog audit failed: ' + type(error).__name__) from None
    if len(places) >= 100:
        raise SystemExit('Catalog completeness cannot be established at the 100-place limit.')
    named_example = ['Waltermart Santa Rosa', 'Laguna Central', 'Target Mall',
                     'Waltermart Bel-Air', "Mama Lou's Italian Kitchen",
                     'Vista Mall Sta. Rosa', 'Yamazaki Kitchen Laguna']
    by_name = {p.name: p for p in places}
    example_legs = []
    for start, end in zip(named_example, named_example[1:]):
        a, b = by_name.get(start), by_name.get(end)
        pa, pb = coordinates(a) if a else None, coordinates(b) if b else None
        example_legs.append(dict(start=start, end=end,
                                 haversine_km=round(distance_km(pa, pb), 3) if pa and pb else None))
    report = dict(read_at_utc=datetime.now(timezone.utc).isoformat(),
                  tourism_metadata_enabled=metadata,
                  note='Original request preferences were not supplied. Shopping + Dining, seven stops is a comparable request; current category coverage does not reproduce the exact named set. Distances use catalog coordinates only; NULL legs cannot be evaluated.',
                  user_example_sequence=named_example, user_example_legs=example_legs,
                  catalog=[dict(id=p.id, name=p.name, category=p.category, tourism_type=p.tourism_type,
                                latitude=p.latitude, longitude=p.longitude) for p in places],
                  comparisons=[compare(places, ['shopping', 'dining'], 7),
                               compare(places, ['shopping'], 3)])
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
