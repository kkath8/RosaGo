"""Pure location heuristics over catalog coordinates; no geocoding or routing I/O.

The catalog is responsible for supplying verified locations. Missing or malformed
pairs provide no geographic evidence and never become estimated locations.
"""
from math import asin, cos, isfinite, radians, sin, sqrt


def coordinates(place):
    pair = (place.latitude, place.longitude)
    if all(type(v) in (int, float) and isfinite(v) and abs(v) <= bound
           for v, bound in zip(pair, (90, 180))):
        return pair
    return None


def distance_km(a, b):
    """Haversine distance between two validated coordinate pairs."""
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    value = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * asin(sqrt(min(1, max(0, value))))


def visit_order(items, locations, *, identity=lambda item: item.id):
    """Nearest-next sequence from the first located stop, retaining unknown slots.

    Unknown stops stay in their deterministic positions. Only located stops are
    compared; their distances say nothing about travel through unknown stops.
    """
    known = [item for item in items if identity(item) in locations]
    if len({locations[identity(item)] for item in known}) < 2:
        return tuple(items)
    ordered = [known.pop(0)]
    while known:
        last = locations[identity(ordered[-1])]
        next_item = min(known, key=lambda item: (
            distance_km(last, locations[identity(item)]), identity(item)))
        ordered.append(next_item)
        known.remove(next_item)
    sequence = iter(ordered)
    return tuple(next(sequence) if identity(item) in locations else item for item in items)


def order_places(places):
    locations = {place.id: coordinates(place) for place in places if coordinates(place) is not None}
    return visit_order(places, locations)
