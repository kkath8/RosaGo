"""Request-driven city forecast review. Advisory only: no selection or writes."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from alerts_service import RAIN_CODES, PRECIPITATION_THRESHOLD
from weather_service import CONDITIONS, FORECAST_DAYS, MANILA

# Product review triggers, not scientific safety limits or official warnings.
# WMO/Open-Meteo: heavy/freezing rain, violent showers, thunderstorms/hail.
STRONG_CONCERN_CODES = frozenset((65, 67, 82, 95, 96, 97, 99))


@dataclass(frozen=True, slots=True)
class ForecastConcern:
    day: date
    severity: str
    condition: str
    weather_code: int
    probability: float

    @property
    def title(self):
        return ('Severe weather may affect the itinerary' if self.severity == 'strong'
                else 'Rain may affect the itinerary')


@dataclass(frozen=True, slots=True)
class ForecastReview:
    concerns: tuple = ()
    outside_range: tuple = ()
    unavailable_dates: tuple = ()
    checked_at: datetime | None = None
    pretrip: bool = True


def before_requested_start(constraints, now):
    """The requested first daily window is a cutoff, not a started-trip record."""
    start = datetime.combine(constraints.start_date,
                             time.fromisoformat(constraints.daily_start_time), tzinfo=MANILA)
    return now.astimezone(MANILA) < start


def forecast_review(weather, dates, *, now):
    """Review only supplied itinerary dates; never use today's rain for future dates.

    Input snapshots come from the existing validated WeatherService. Unknown WMO
    codes without a probability trigger are unavailable, not a quiet forecast.
    No previous forecast is persisted, so this reports current concerns rather
    than claiming that weather changed since a previous observation.
    """
    today = now.astimezone(MANILA).date()
    dates = tuple(sorted(set(dates)))
    if not 1 <= len(dates) <= 7:
        raise ValueError('Expected one to seven itinerary dates.')
    outside = tuple(day for day in dates if not 0 <= (day - today).days < FORECAST_DAYS)
    relevant = tuple(day for day in dates if day not in outside)
    # Defense in depth against stale snapshots after local midnight or long waits.
    fresh = (weather is not None and weather.forecast
             and weather.forecast[0].day == today
             and -timedelta(minutes=5) <= now - weather.fetched_at <= timedelta(minutes=5)
             and -timedelta(minutes=5) <= now - weather.reported_at <= timedelta(minutes=90))
    if not fresh:
        return ForecastReview(outside_range=outside, unavailable_dates=relevant)
    by_date = {day.day: day for day in weather.forecast}
    concerns, unavailable = [], []
    for day in relevant:
        forecast = by_date.get(day)
        if forecast is None:
            unavailable.append(day)
        elif forecast.weather_code in STRONG_CONCERN_CODES:
            concerns.append(ForecastConcern(day, 'strong', forecast.condition,
                                            forecast.weather_code, forecast.precipitation_probability))
        elif (forecast.weather_code in RAIN_CODES
              or forecast.precipitation_probability >= PRECIPITATION_THRESHOLD):
            concerns.append(ForecastConcern(day, 'caution', forecast.condition,
                                            forecast.weather_code, forecast.precipitation_probability))
        elif forecast.weather_code not in CONDITIONS:
            unavailable.append(day)
    return ForecastReview(tuple(concerns), outside, tuple(unavailable), weather.fetched_at)
