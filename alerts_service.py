"""Pure deterministic reminders. No advisory provider or alert persistence."""
from dataclasses import dataclass
from datetime import date

RAIN_CODES = frozenset((51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 97, 99))
PRECIPITATION_THRESHOLD = 60
TRIP_HORIZON_DAYS = 7


@dataclass(frozen=True, slots=True)
class Alert:
    kind: str
    severity: str
    title: str
    message: str
    day: date
    trip_id: str | None = None


def weather_alerts(weather):
    if weather is None:
        return ()
    alerts = []
    if weather.precipitation_mm > 0:
        alerts.append(Alert('weather', 'caution', 'Precipitation reported for Santa Rosa',
            f'Open-Meteo reports {weather.precipitation_mm:g} mm of modelled precipitation '
            f'for its {weather.interval_seconds / 60:g}-minute interval at '
            f'{weather.reported_at:%b %d, %I:%M %p} (Asia/Manila). Consider rain protection.',
            weather.reported_at.date()))
    elif weather.weather_code in RAIN_CODES:
        alerts.append(Alert('weather', 'caution', 'Wet weather in the current model',
            f'Open-Meteo indicates {weather.condition.lower()} for Santa Rosa at '
            f'{weather.reported_at:%b %d, %I:%M %p} (Asia/Manila). Consider rain protection.',
            weather.reported_at.date()))
    for day in weather.forecast:
        if day.precipitation_probability >= PRECIPITATION_THRESHOLD:
            alerts.append(Alert('weather', 'caution', 'Rain protection may be useful',
                f'The Santa Rosa forecast for {day.day:%b %d, %Y} has a '
                f'{day.precipitation_probability:g}% maximum precipitation probability. '
                'Consider rain protection and check the forecast before going out.', day.day))
    return tuple(alerts)


def trip_alerts(trips, *, today):
    alerts = []
    for trip in sorted(trips, key=lambda trip: (trip.visit_date or date.max, trip.id)):
        if trip.visit_date is None:
            continue
        days = (trip.visit_date - today).days
        if not 0 <= days <= TRIP_HORIZON_DAYS:
            continue
        title = 'Your trip is today' if days == 0 else 'Upcoming saved trip'
        message = (f'“{trip.name}” is scheduled for today ({today:%b %d, %Y}, Asia/Manila).'
                   if days == 0 else f'“{trip.name}” is scheduled for {trip.visit_date:%b %d, %Y}.')
        alerts.append(Alert('trip', 'info', title, message, trip.visit_date, trip.id))
    return tuple(alerts)
