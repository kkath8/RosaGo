"""Strict server-side parsing for the v1 quiz. No I/O or ownership authority."""
from datetime import date
from decimal import Decimal
import re

from itinerary_draft_service import (
    MAX_REVISION, DraftValidationError, TRANSPORTATION, TRIP_PACES, ACTIVITIES,
    ENVIRONMENTS, TEXT_LIMITS, preference_text,
)
from places_service import CATEGORIES


COMPANIONS = ('solo', 'couple', 'family', 'friends', 'group')
VALUE_FIELDS = ('companion_type', 'budget', 'start_date', 'end_date',
                'daily_start_time', 'daily_end_time', 'transportation', 'trip_pace',
                'environment_preference', 'other_interests', 'additional_preferences')
REPEATED_FIELDS = frozenset(('interests', 'activity_preferences'))
FORM_FIELDS = frozenset((*VALUE_FIELDS, *REPEATED_FIELDS, 'expected_revision', 'csrf_token'))


class QuizTimeWindowError(DraftValidationError):
    """Valid clock values that do not form a forward, same-day window."""


def expected_revision(value):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', value) or not 1 <= int(value) < MAX_REVISION:
        raise DraftValidationError()
    return int(value)


def parse_quiz_form(form):
    """Accept one value per scalar and repeated controlled choice fields."""
    if (set(form) - FORM_FIELDS or FORM_FIELDS - REPEATED_FIELDS - set(form)
            or any(len(form.getlist(key)) != 1 for key in FORM_FIELDS - REPEATED_FIELDS)):
        raise DraftValidationError()
    revision = expected_revision(form['expected_revision'])
    interests = form.getlist('interests')
    activities = form.getlist('activity_preferences')
    if (not 1 <= len(interests) <= 6 or len(set(interests)) != len(interests)
            or any(value not in CATEGORIES for value in interests)
            or not 1 <= len(activities) <= 6 or len(set(activities)) != len(activities)
            or any(value not in ACTIVITIES for value in activities)
            or form['trip_pace'] not in TRIP_PACES
            or form['environment_preference'] not in ENVIRONMENTS
            or form['companion_type'] not in COMPANIONS
            or form['transportation'] not in TRANSPORTATION):
        raise DraftValidationError()
    budget = form['budget']
    centavos = None
    if budget != '':
        if not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,2})?', budget):
            raise DraftValidationError()
        centavos = int(Decimal(budget) * 100)
        if centavos > 10000000:
            raise DraftValidationError()
    dates = []
    for key in ('start_date', 'end_date'):
        parsed = None
        if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', form[key]):
            try:
                parsed = date.fromisoformat(form[key])
            except ValueError:
                pass
        if parsed is None:
            raise DraftValidationError()
        dates.append(parsed)
    if not 0 <= (dates[1] - dates[0]).days <= 6:
        raise DraftValidationError()
    times = []
    for key in ('daily_start_time', 'daily_end_time'):
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', form[key]):
            raise DraftValidationError()
        times.append(form[key] + ':00')
    if times[1] <= times[0]:
        raise QuizTimeWindowError()
    return revision, dict(interests=interests, companion_type=form['companion_type'],
                          budget_centavos=centavos, start_date=form['start_date'],
                          end_date=form['end_date'], daily_start_time=times[0],
                          daily_end_time=times[1], transportation=form['transportation'],
                          trip_pace=form['trip_pace'], activity_preferences=activities,
                          environment_preference=form['environment_preference'],
                          **{key: preference_text(form[key], maximum) for key, maximum in TEXT_LIMITS.items()},
                          timezone='Asia/Manila')


def form_values(preferences=None):
    values = {key: '' for key in VALUE_FIELDS}
    values['interests'] = []
    values['activity_preferences'] = []
    if preferences is not None:
        values.update({key: preferences.get(key) or '' for key in VALUE_FIELDS if key != 'budget'})
        values['interests'] = list(preferences['interests'])
        values['activity_preferences'] = list(preferences.get('activity_preferences', []))
        amount = preferences['budget_centavos']
        values['budget'] = '' if amount is None else f'{amount // 100}.{amount % 100:02d}'
    return values


def submitted_values(form):
    # Bounded strings only; Jinja autoescapes these. Never echo unknown fields.
    values = {key: form.get(key, '')[:TEXT_LIMITS.get(key, 100)] for key in VALUE_FIELDS}
    values['interests'] = [value for value in form.getlist('interests')[:6] if value in CATEGORIES]
    values['activity_preferences'] = [value for value in form.getlist('activity_preferences')[:6] if value in ACTIVITIES]
    return values
