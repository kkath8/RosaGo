"""Validated city-level Open-Meteo forecasts with a single bounded public cache."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import math
import threading
import time

import httpx


MANILA = timezone(timedelta(hours=8), 'Asia/Manila')
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
# Open-Meteo geocoding / GeoNames 1687894: Santa Rosa, Province of Laguna, PH.
# City weather context only. These are not destination entrance coordinates.
CITY_LATITUDE, CITY_LONGITUDE = 14.31222, 121.11139
FORECAST_DAYS = 3
CURRENT_FIELDS = ('temperature_2m', 'apparent_temperature', 'precipitation',
                  'weather_code', 'wind_speed_10m')
DAILY_FIELDS = ('weather_code', 'temperature_2m_min', 'temperature_2m_max',
                'precipitation_probability_max')
CONDITIONS = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Depositing rime fog', 51: 'Light drizzle', 53: 'Moderate drizzle',
    55: 'Dense drizzle', 56: 'Light freezing drizzle', 57: 'Dense freezing drizzle',
    61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain', 66: 'Light freezing rain',
    67: 'Heavy freezing rain', 71: 'Slight snowfall', 73: 'Moderate snowfall',
    75: 'Heavy snowfall', 77: 'Snow grains', 80: 'Slight rain showers',
    81: 'Moderate rain showers', 82: 'Violent rain showers', 85: 'Slight snow showers',
    86: 'Heavy snow showers', 95: 'Thunderstorm', 96: 'Thunderstorm with slight hail',
    97: 'Heavy thunderstorm', 99: 'Thunderstorm with heavy hail',
}


def manila_now():
    return datetime.now(MANILA)


def condition_label(code):
    return CONDITIONS.get(code, 'Condition unavailable')


@dataclass(frozen=True, slots=True)
class ForecastDay:
    day: date
    weather_code: int
    minimum_c: float
    maximum_c: float
    precipitation_probability: float

    @property
    def condition(self):
        return condition_label(self.weather_code)


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    reported_at: datetime
    fetched_at: datetime
    interval_seconds: int
    temperature_c: float
    apparent_c: float | None
    precipitation_mm: float
    wind_kmh: float
    weather_code: int
    forecast: tuple[ForecastDay, ...]

    @property
    def condition(self):
        return condition_label(self.weather_code)


class WeatherValidationError(ValueError):
    def __init__(self):
        super().__init__('Weather data is unavailable.')


def _number(value, minimum, maximum):
    if (type(value) not in (int, float) or not minimum <= value <= maximum
            or not math.isfinite(value)):
        raise WeatherValidationError()
    return float(value)


def _code(value):
    if type(value) is not int or not 0 <= value <= 99:
        raise WeatherValidationError()
    return value


def _fresh(snapshot, now):
    return (snapshot.forecast[0].day == now.date()
            and -timedelta(minutes=5) <= now - snapshot.reported_at <= timedelta(minutes=90))


def parse_weather(data, *, now):
    """Reject missing/invalid required fields rather than fabricating fallback values."""
    if (type(data) is not dict or data.get('error') or data.get('timezone') != 'Asia/Manila'
            or type(data.get('utc_offset_seconds')) is not int or data['utc_offset_seconds'] != 28800):
        raise WeatherValidationError()
    latitude = _number(data['latitude'], -90, 90)
    longitude = _number(data['longitude'], -180, 180)
    # The returned coordinates describe the model grid cell, not a GPS location.
    if abs(latitude - CITY_LATITUDE) > 0.5 or abs(longitude - CITY_LONGITUDE) > 0.5:
        raise WeatherValidationError()
    current, daily = data['current'], data['daily']
    current_units, daily_units = data['current_units'], data['daily_units']
    if any(type(part) is not dict for part in (current, daily, current_units, daily_units)):
        raise WeatherValidationError()
    required_units = {'time': 'iso8601', 'interval': 'seconds', 'temperature_2m': '°C',
                      'precipitation': 'mm', 'wind_speed_10m': 'km/h', 'weather_code': 'wmo code'}
    if any(current_units.get(key) != value for key, value in required_units.items()):
        raise WeatherValidationError()
    if any(daily_units.get(key) != value for key, value in {
        'time': 'iso8601', 'weather_code': 'wmo code', 'temperature_2m_min': '°C',
        'temperature_2m_max': '°C', 'precipitation_probability_max': '%',
    }.items()):
        raise WeatherValidationError()
    if type(current['time']) is not str or 'T' not in current['time']:
        raise WeatherValidationError()
    reported = datetime.fromisoformat(current['time'])
    if reported.tzinfo is None:
        reported = reported.replace(tzinfo=MANILA)
    elif reported.utcoffset() != timedelta(hours=8):
        raise WeatherValidationError()
    interval = current['interval']
    if type(interval) is not int or not 1 <= interval <= 3600:
        raise WeatherValidationError()
    apparent = current.get('apparent_temperature')
    if apparent is not None:
        if current_units.get('apparent_temperature') != '°C':
            raise WeatherValidationError()
        apparent = _number(apparent, -120, 100)
    for key in ('time', *DAILY_FIELDS):
        if type(daily[key]) is not list or len(daily[key]) != FORECAST_DAYS:
            raise WeatherValidationError()
    days = []
    for index in range(FORECAST_DAYS):
        day = date.fromisoformat(daily['time'][index])
        if day.isoformat() != daily['time'][index] or day != now.date() + timedelta(days=index):
            raise WeatherValidationError()
        low = _number(daily['temperature_2m_min'][index], -100, 70)
        high = _number(daily['temperature_2m_max'][index], -100, 70)
        if low > high:
            raise WeatherValidationError()
        days.append(ForecastDay(day, _code(daily['weather_code'][index]), low, high,
                    _number(daily['precipitation_probability_max'][index], 0, 100)))
    snapshot = WeatherSnapshot(reported, now, interval,
        _number(current['temperature_2m'], -100, 70), apparent,
        _number(current['precipitation'], 0, 1000), _number(current['wind_speed_10m'], 0, 500),
        _code(current['weather_code']), tuple(days))
    if not _fresh(snapshot, now):
        raise WeatherValidationError()
    return snapshot


class WeatherService:
    """One city, one cache entry. No user data, keys, disk writes or stale fallback."""
    def __init__(self, *, http_factory=httpx.Client, clock=time.monotonic, now=manila_now):
        self._http_factory, self._clock, self._now = http_factory, clock, now
        self._lock = threading.Lock()
        self._snapshot, self._expires, self._cache_day = None, 0, None

    def get_weather(self):
        with self._lock:
            now, tick = self._now(), self._clock()
            if (tick < self._expires and self._cache_day == now.date()
                    and (self._snapshot is None or _fresh(self._snapshot, now))):
                return self._snapshot
            snapshot = None
            try:
                params = dict(latitude=CITY_LATITUDE, longitude=CITY_LONGITUDE, timezone='Asia/Manila',
                    current=','.join(CURRENT_FIELDS), daily=','.join(DAILY_FIELDS),
                    forecast_days=FORECAST_DAYS, temperature_unit='celsius',
                    wind_speed_unit='kmh', precipitation_unit='mm', timeformat='iso8601')
                with self._http_factory(timeout=8, follow_redirects=False, trust_env=False) as client:
                    with client.stream('GET', FORECAST_URL, params=params) as response:
                        if response.status_code != 200:
                            raise WeatherValidationError()
                        content = bytearray()
                        for chunk in response.iter_bytes():
                            content.extend(chunk)
                            if len(content) > 128_000:
                                raise WeatherValidationError()
                        snapshot = parse_weather(json.loads(content), now=now)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, OverflowError):
                # No raw provider diagnostics or response text reach the view or logs.
                snapshot = None
            self._snapshot, self._cache_day = snapshot, now.date()
            self._expires = self._clock() + (300 if snapshot is not None else 60)
            return snapshot
