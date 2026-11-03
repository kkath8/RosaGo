"""Bounded public grounding. No profile, credential, trip or foreign-user reads."""
import json
import re

MAX_RECOMMENDATION_PLACES = 12
MAX_CHAT_PLACES = 8
MAX_MESSAGE_CHARS = 1000
MAX_CONTEXT_BYTES = 48_000

APP_CONTEXT = {
    'scope': 'RosaGo tourism planning in Santa Rosa, Laguna, Philippines',
    'usage': ['Explore lists published catalog places and their details.',
              'Planner saves preferences, ranks by category-interest matches, and builds untimed previews.',
              'My Trips holds user-saved plans; this assistant cannot read or change them.',
              'Map and Transport calculate routes only for destinations with verified coordinates.',
              'Alerts derives city weather reminders and dated own-trip reminders.'],
    'unsupported': ['public transit routing', 'motorcycle routing', 'ride-hailing bookings',
                    'mixed-mode routing', 'live opening hours', 'prices', 'ratings',
                    'closures', 'live traffic', 'government advisories'],
}


def validate_message(value):
    if type(value) is not str:
        raise ValueError('Enter a message of 1–1000 characters.')
    value = value.replace('\r\n', '\n').replace('\r', '\n').strip()
    if (not 1 <= len(value) <= MAX_MESSAGE_CHARS
            or any((ord(c) < 32 and c not in '\n\t') or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError('Enter a message of 1–1000 characters.')
    return value


def _place(place):
    return dict(place_id=place.id, name=place.name, category=place.category,
                description=place.description[:400], address=place.address[:200],
                routing_coordinates_available=place.latitude is not None and place.longitude is not None)


def recommendation_context(preferences, cards):
    candidates = [_place(card['place']) for card in cards[:MAX_RECOMMENDATION_PLACES]]
    return dict(interests=list(preferences['interests']), candidates=candidates,
        ranking_rule='Category-interest match only. Preserve RosaGo ranking and selection.',
        unknown_constraints=['cost', 'hours', 'duration', 'environment', 'companion suitability',
                             'transport compatibility'],
        explanation_subset=len(cards) > MAX_RECOMMENDATION_PLACES)


def weather_requested(message, history):
    text = ' '.join([message] + [item['text'] for item in history if item['role'] == 'user']).casefold()
    return bool(re.search(r'\b(weather|rain|forecast|temperature|wind|ulan|panahon|bagyo|init)\b', text))


def weather_context(weather):
    if weather is None:
        return {'available': False, 'scope': 'Santa Rosa city weather only'}
    return dict(available=True, scope='Santa Rosa city model/forecast, not destination-specific',
        source='Open-Meteo', reported_at=weather.reported_at.isoformat(),
        temperature_c=weather.temperature_c, apparent_c=weather.apparent_c,
        precipitation_mm=weather.precipitation_mm, interval_seconds=weather.interval_seconds,
        condition=weather.condition, wind_kmh=weather.wind_kmh,
        forecast=[dict(date=day.day.isoformat(), condition=day.condition,
                       minimum_c=day.minimum_c, maximum_c=day.maximum_c,
                       precipitation_probability=day.precipitation_probability)
                  for day in weather.forecast])


def chat_context(message, history, places, routing, weather=None, *, include_weather=False):
    # Lexical retrieval is deterministic; the model never queries the database.
    stop = {'santa', 'rosa', 'laguna', 'the', 'what', 'which', 'where', 'with', 'and',
            'for', 'can', 'are', 'about', 'please', 'would', 'recommend'}
    text = ' '.join([message] + [item['text'] for item in history if item['role'] == 'user'][-2:]).casefold()
    tokens = set(re.findall(r'\w{3,}', text)) - stop
    def score(place):
        name = place.name.casefold()
        body = (place.description + ' ' + place.address).casefold()
        return (100 if name in text else 0) + sum(
            5 * (token in name) + 3 * (token in place.category) + (token in body) for token in tokens)
    selected = sorted(places, key=lambda place: (-score(place), place.slug))[:MAX_CHAT_PLACES]
    context = dict(application=APP_CONTEXT, message=message, history=list(history),
        catalog=[_place(place) for place in selected],
        catalog_is_complete=len(places) < 50 and len(selected) == len(places),
        transport=dict(provider=routing.label, supported_modes=list(routing.modes),
                       calculated_route=None, requires_verified_destination_coordinates=True),
        weather=weather_context(weather) if include_weather else {'provided': False})
    while context['history'] and len(json.dumps(context, ensure_ascii=False).encode('utf-8')) > MAX_CONTEXT_BYTES:
        context['history'] = context['history'][2:]
    if len(json.dumps(context, ensure_ascii=False).encode('utf-8')) > MAX_CONTEXT_BYTES:
        raise ValueError('Assistant context is too large.')
    return context
