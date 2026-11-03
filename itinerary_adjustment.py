"""Strict AI intent vocabulary and pure supported preference changes. No AI selection."""
from copy import deepcopy

from itinerary_draft_service import validate_complete_preferences, TRIP_PACES
from place_model import CATEGORIES

UNSUPPORTED = {
    'budget': 'Exact budget planning is not available in itinerary adjustment yet.',
    'time': 'Exact end times and opening-hours planning are not available yet.',
    'environment': 'Indoor or outdoor filtering is not available in itinerary adjustment yet.',
    'replacement': 'To change places, try changing your interests or number of destinations.',
    'other': 'I can adjust your interests, pace, or number of destinations.',
}
CHANGE_KEYS = {'set_interests', 'add_interests', 'remove_interests', 'pace', 'place_count'}


def validate_adjustment(value):
    if (type(value) is not dict or set(value) != {'intent', 'changes', 'unsupported_requests'}
            or type(value['intent']) is not str or value['intent'] not in ('modify', 'clarify')
            or type(value['changes']) is not dict or set(value['changes']) != CHANGE_KEYS):
        raise ValueError('Invalid adjustment.')
    changes = value['changes']
    for key in ('set_interests', 'add_interests', 'remove_interests'):
        items = changes[key]
        if key == 'set_interests' and items is None:
            continue
        if (type(items) is not list or len(items) > 6
                or any(type(item) is not str or item not in CATEGORIES for item in items)
                or len(set(items)) != len(items) or (key == 'set_interests' and not items)):
            raise ValueError('Invalid adjustment.')
    pace, count = changes['pace'], changes['place_count']
    if ((pace is not None and (type(pace) is not str or pace not in TRIP_PACES))
            or (count is not None and (type(count) is not int or not 1 <= count <= 100))
            or (changes['set_interests'] is not None and (changes['add_interests'] or changes['remove_interests']))
            or set(changes['add_interests']) & set(changes['remove_interests'])):
        raise ValueError('Invalid adjustment.')
    unsupported = value['unsupported_requests']
    if (type(unsupported) is not list or len(unsupported) > len(UNSUPPORTED)
            or any(type(item) is not str or item not in UNSUPPORTED for item in unsupported)
            or len(set(unsupported)) != len(unsupported)):
        raise ValueError('Invalid adjustment.')
    if value['intent'] == 'clarify' and any((changes['set_interests'], changes['add_interests'],
            changes['remove_interests'], pace is not None, count is not None)):
        raise ValueError('Invalid adjustment.')
    return deepcopy(value)


def adjusted_preferences(preferences, interpretation):
    changes = validate_adjustment(interpretation)['changes']
    updated = deepcopy(preferences)
    if changes['set_interests'] is not None:
        updated['interests'] = sorted(changes['set_interests'])
    elif changes['add_interests'] or changes['remove_interests']:
        updated['interests'] = sorted((set(updated['interests']) | set(changes['add_interests']))
                                      - set(changes['remove_interests']))
    if changes['pace'] is not None:
        updated['trip_pace'] = changes['pace']
    return validate_complete_preferences(updated)


def adjustment_schema():
    interests = {'type': 'array', 'maxItems': 6, 'uniqueItems': True,
                 'items': {'type': 'string', 'enum': sorted(CATEGORIES)}}
    return {'type': 'object', 'additionalProperties': False,
        'properties': {'intent': {'type': 'string', 'enum': ['modify', 'clarify']},
            'changes': {'type': 'object', 'additionalProperties': False,
                'properties': {'set_interests': {'anyOf': [interests, {'type': 'null'}]},
                    'add_interests': interests, 'remove_interests': interests,
                    'pace': {'type': ['string', 'null'], 'enum': [*TRIP_PACES, None]},
                    'place_count': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 100}},
                'required': sorted(CHANGE_KEYS)},
            'unsupported_requests': {'type': 'array', 'maxItems': len(UNSUPPORTED), 'uniqueItems': True,
                'items': {'type': 'string', 'enum': list(UNSUPPORTED)}}},
        'required': ['intent', 'changes', 'unsupported_requests']}
