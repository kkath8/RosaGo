"""Non-sensitive browser-session display preferences; never account authority."""
from dataclasses import dataclass

SESSION_KEY = 'rosago_ui_preferences'
ALERT_DISPLAY_OPTIONS = (
    ('all', 'Weather and trip reminders'),
    ('trips', 'Trip reminders only'),
    ('weather', 'Weather and weather reminders only'),
    ('none', 'Notifications off'),
)
_ALLOWED = frozenset(value for value, _ in ALERT_DISPLAY_OPTIONS)


class SettingsValidationError(ValueError):
    def __init__(self):
        super().__init__('Choose a supported Alerts display option.')


@dataclass(frozen=True, slots=True)
class UserSettings:
    alerts_display: str = 'all'
    personalized: bool = True
    location_enabled: bool = True

    @property
    def show_weather(self):
        return self.alerts_display in ('all', 'weather')

    @property
    def show_trips(self):
        return self.alerts_display in ('all', 'trips')


def validate_settings(values):
    if (type(values) is not dict or set(values) - {'alerts_display', 'personalized', 'location_enabled'} or 'alerts_display' not in values
            or type(values['alerts_display']) is not str or values['alerts_display'] not in _ALLOWED):
        raise SettingsValidationError()
    if any(type(values.get(key, True)) is not bool for key in ('personalized', 'location_enabled')):
        raise SettingsValidationError()
    return UserSettings(values['alerts_display'], values.get('personalized', True), values.get('location_enabled', True))


def get_settings(browser_session):
    try:
        return validate_settings(browser_session.get(SESSION_KEY))
    except SettingsValidationError:
        # Old/malformed session values cannot grant permissions or break the UI.
        return UserSettings()
