"""Travel preferences remain broader than provider-supported routing modes."""

TRANSPORTATION = ('walking', 'bicycle', 'motorcycle', 'private_car',
                  'public_transport', 'ride_hailing', 'mixed_transport')
ROUTE_MODE_LABELS = {'driving': 'Driving', 'walking': 'Walking', 'cycling': 'Cycling'}
PREFERENCE_ROUTE_MODE = {'private_car': 'driving', 'walking': 'walking', 'bicycle': 'cycling'}
ORS_PROFILES = {'driving': 'driving-car', 'walking': 'foot-walking', 'cycling': 'cycling-regular'}


def route_mode_for_preference(preference, supported):
    mode = PREFERENCE_ROUTE_MODE.get(preference)
    return mode if mode in supported else None
