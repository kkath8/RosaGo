"""Prototype utility pages over real catalog/trip services; no schema changes."""
import hashlib
import hmac
from contextlib import ExitStack
from datetime import date
from uuid import UUID

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, session, url_for
from auth_helpers import login_required
from destination_weather_metadata import load_weather_catalog
from place_search import search_published
from places_service import PlacesUnavailableError, PlacesConsistencyError
from trip_service import TripServiceError, TripValidationError, remove_place, reorder_places
from alerts_service import Alert, trip_alerts
from itinerary_weather import forecast_review
from profile_service import profile_initials, ProfileServiceError


def personal_scope(user_id):
    # Public UI namespace only: it confers no server authority and contains no
    # identity, session handle, access token or refresh token.
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    return hmac.new(key, ('personal-ui:' + user_id).encode(), hashlib.sha256).hexdigest()[:24]


def visitor_place(place):
    return not place.slug.startswith('rosago-test-v1-')


def notification_cards(values, trips=()):
    """Visitor copy/links over existing alerts; detection rules stay in alerts_service."""
    by_id = {getattr(trip, 'id', None): trip for trip in trips
             if isinstance(getattr(trip, 'id', None), str)}
    rows, weather_days = [], set()
    for alert in values:
        if (getattr(alert, 'kind', None) not in ('weather', 'trip')
                or type(getattr(alert, 'day', None)) is not date):
            continue
        if alert.kind == 'weather':
            if alert.day in weather_days:
                continue  # One weather notification per date, not per provider signal.
            weather_days.add(alert.day)
        trip_id = getattr(alert, 'trip_id', None)
        title = getattr(alert, 'title', '')
        title = title if isinstance(title, str) else ''
        identifier = hashlib.sha256((alert.kind + '|' + alert.day.isoformat() + '|' + (trip_id if isinstance(trip_id, str) else '') + '|' + title).encode()).hexdigest()[:24]
        trip = by_id.get(trip_id) if isinstance(trip_id, str) else None
        try:
            destination = url_for('trips_detail', trip_id=str(UUID(trip.id))) if trip else None
        except (ValueError, AttributeError):
            destination = None
        rows.append(dict(id=identifier, kind=alert.kind,
            title=('Your trip is today' if title == 'Your trip is today' else 'Upcoming trip') if alert.kind == 'trip' else 'Weather may affect your trip',
            name=trip.name if trip and isinstance(getattr(trip, 'name', None), str) else '', day=alert.day.isoformat(),
            date_label=alert.day.strftime('%B %d, %Y'),
            message=('Your trip is coming up soon.' if title != 'Your trip is today' else 'Your trip is scheduled for today.') if alert.kind == 'trip' else 'Rain may affect this trip. Review the forecast and plan for rain protection.',
            action_label='View Trip' if destination else 'View Weather' if alert.kind == 'weather' else None,
            url=destination or (url_for('alerts', _anchor='weather') if alert.kind == 'weather' else None)))
    return rows


def alerts_notification_cards(weather, trips, *, now):
    """City weather is information; only forecast concerns for trips notify."""
    values = list(trip_alerts(trips, today=now.date()))
    for trip in trips:
        if trip.visit_date is None or trip.visit_date <= now.date():
            continue
        review = forecast_review(weather, (trip.visit_date,), now=now)
        if review.concerns:
            concern = review.concerns[0]
            values.append(Alert('weather', concern.severity, concern.title, '', trip.visit_date, trip.id))
    return notification_cards(values, trips)


def init_user_features(app, helpers):
    bp = Blueprint('features', __name__)

    def response_json(value, status=200):
        response = jsonify(value)
        response.status_code = status
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @bp.get('/api/user/avatar')
    def user_avatar():
        """Caller-only display initials; no names, email, tokens, or cached identity."""
        try:
            with helpers['normal_authenticated']():
                try:
                    profile = helpers['get_own_profile'](g.auth)
                except ProfileServiceError:
                    return response_json({'error': 'Profile is temporarily unavailable.'}, 503)
                return response_json({'initials': profile_initials(
                    profile.first_name if profile else None, profile.last_name if profile else None)})
        except helpers['NormalAuthEntryError'] as error:
            return response_json({'error': 'Profile is unavailable.'},
                                 401 if error.kind == 'unauthenticated' else 503)

    @bp.get('/api/places')
    def catalog():
        try:
            places = search_published(current_app.extensions['rosago_places'], '')
            weather = load_weather_catalog()
        except (PlacesUnavailableError, PlacesConsistencyError):
            return response_json({'error': 'Destinations are temporarily unavailable.'}, 503)
        return response_json({'places': [dict(id=p.id, slug=p.slug, name=p.name,
            category=p.category, address=p.address, description=p.description,
            tourism_type=getattr(p, 'tourism_type', None),
            tourism_category=getattr(p, 'tourism_category', None),
            environment=getattr(p, 'environment', None),
            operating_days_raw=getattr(p, 'operating_days_raw', None),
            exposure=weather.for_place(p).exposure,
            image_url=p.image_url,
            detail_url=url_for('places_detail', slug=p.slug),
            map_url=url_for('map_index', destination=p.slug) if p.latitude is not None and p.longitude is not None else None)
            for p in places if visitor_place(p)]})

    @bp.get('/saved')
    def saved():
        return render_template('library/places.html', library_kind='saved', heading='Saved places')

    @bp.get('/api/weather')
    def city_weather():
        snapshot = current_app.extensions['rosago_weather'].get_weather()
        if snapshot is None:
            return response_json({'error': 'Weather is temporarily unavailable. No sample is being shown.'}, 503)
        return response_json(dict(city='Santa Rosa, Laguna', provider='Open-Meteo', sample=False,
            temperature_c=snapshot.temperature_c, condition=snapshot.condition,
            apparent_c=snapshot.apparent_c,
            reported_at=snapshot.reported_at.isoformat(),
            forecast=[dict(day=d.day.isoformat(), condition=d.condition,
                minimum_c=d.minimum_c, maximum_c=d.maximum_c,
                precipitation_probability=d.precipitation_probability) for d in snapshot.forecast]))

    @bp.get('/visited')
    def visited():
        return render_template('library/places.html', library_kind='visited', heading='Visited places')

    @bp.get('/events')
    def events():
        return redirect(url_for('index'), code=302)

    @bp.get('/budget')
    def budget():
        # A direct new-tab visit must use the verified account's device scope,
        # rather than relying on sessionStorage left by another RosaGo page.
        with ExitStack() as stack:
            if helpers['read_auth_session_id']() is not None:
                try:
                    stack.enter_context(helpers['normal_authenticated']())
                except helpers['NormalAuthEntryError']:
                    pass  # Personal planning remains usable without an account.
                else:
                    return helpers['_render_trip_page']('library/budget.html')
        return render_template('library/budget.html', ui_scope='guest', ui_authenticated=False)

    @bp.get('/help')
    def help_page():
        return render_template('library/help.html')

    @bp.get('/api/user/trips')
    @login_required
    def trip_summaries():
        try:
            trips = helpers['list_user_trips'](g.auth, limit=50, offset=0)
        except TripServiceError:
            return response_json({'error': 'Trips are temporarily unavailable.'}, 503)
        return response_json({'trips': [dict(id=t.id, name=t.name,
            visit_date=t.visit_date.isoformat() if t.visit_date else None,
            detail_url=url_for('trips_detail', trip_id=t.id)) for t in trips],
            'bounded': len(trips) == 50})

    @bp.get('/user/bag')
    @login_required
    def bag():
        return helpers['_render_trip_page']('library/bag.html', csrf=helpers['_trip_csrf']())

    @bp.get('/api/user/notices')
    @login_required
    def notices():
        preferences = helpers['get_settings'](session)
        now = helpers['manila_now']()
        weather = current_app.extensions['rosago_weather'].get_weather() if preferences.show_weather else None
        unavailable = False
        upcoming = ()
        if preferences.show_trips:
            try:
                upcoming = helpers['list_upcoming_trips'](g.auth, today=now.date(), days=7, limit=51)
            except TripServiceError:
                unavailable = True
        rows = alerts_notification_cards(weather, upcoming[:50], now=now)
        return response_json({'notices': rows, 'weather_available': weather is not None,
                              'trips_unavailable': unavailable, 'request_driven': True})

    def ids(values, maximum=20):
        if not 1 <= len(values) <= maximum or len(set(values)) != len(values):
            raise TripValidationError()
        if any(str(UUID(v)) != v for v in values):
            raise TripValidationError()
        return values

    def save_places(place_ids, name, visit_date):
        # Existing operations own RLS/ownership/publication enforcement. Never
        # retry an ambiguous write or erase a partially saved real trip.
        trip = helpers['create_trip'](g.auth, name=name, visit_date=visit_date)
        try:
            for place_id in place_ids:
                helpers['add_place'](g.auth, trip.id, place_id)
        except TripServiceError:
            return redirect(url_for('trips_detail', trip_id=trip.id, notice='partial'), code=303)
        return redirect(url_for('trips_detail', trip_id=trip.id, notice='saved'), code=303)

    @bp.post('/user/bag')
    @login_required
    def save_bag():
        failure = helpers['_trip_post_check']({'csrf_token', 'name', 'visit_date', 'selected_place_ids'},
                                             repeated={'selected_place_ids'})
        if failure is not None:
            return failure
        try:
            selected = ids(request.form.getlist('selected_place_ids'))
            published = {p.id for p in search_published(current_app.extensions['rosago_places'], '') if visitor_place(p)}
            if not set(selected) <= published:
                return 'A selected destination is unavailable. Review your bag.', 409
            visit_date = helpers['_trip_date'](request.form['visit_date'])
            return save_places(selected, request.form['name'], visit_date)
        except (ValueError, TripValidationError):
            return 'Choose 1–20 published destinations and a valid trip name/date.', 400
        except (PlacesUnavailableError, PlacesConsistencyError):
            return 'Destinations are temporarily unavailable. Your bag has not been saved.', 503
        except TripServiceError as error:
            return helpers['_trip_failure'](error, mutation=True)

    @bp.post('/user/itinerary/<uuid:draft_id>/save-trip')
    @login_required
    def save_preview(draft_id):
        failure = helpers['_trip_post_check']({'csrf_token', 'expected_revision', 'name'})
        if failure is not None:
            return failure
        try:
            draft, failure = helpers['_preview_draft'](draft_id, 'preview_ready')
            if failure:
                return failure
            if request.form['expected_revision'] != str(draft.revision):
                return 'Your preview changed. Reload it before saving.', 409
            selected = ids(list(draft.preview.source.selected_place_ids))
            places = search_published(current_app.extensions['rosago_places'], '')
            by_id = {p.id: p for p in places if visitor_place(p)}
            if not set(selected) <= by_id.keys():
                return 'A selected destination is unavailable. Rebuild your preview.', 409
            from itinerary_preview import compute_catalog_fingerprint
            if compute_catalog_fingerprint(tuple(by_id[i] for i in selected), publication_confirmed=True) != draft.preview.source.catalog_fingerprint:
                return 'Destination information changed. Rebuild your preview before saving.', 409
            from datetime import date
            visit_date = date.fromisoformat(draft.preferences['start_date'])
            return save_places(selected, request.form['name'], visit_date)
        except (ValueError, TripValidationError):
            return 'Use a valid name and a preview of 1–20 destinations.', 400
        except (PlacesUnavailableError, PlacesConsistencyError):
            return 'Destinations are temporarily unavailable. No trip was saved.', 503
        except helpers['DraftError'] as error:
            return helpers['_draft_failure'](error)
        except TripServiceError as error:
            return helpers['_trip_failure'](error, mutation=True)

    @bp.post('/user/trips/<uuid:trip_id>/remove-place')
    @login_required
    def remove_destination(trip_id):
        failure = helpers['_trip_post_check']({'csrf_token', 'place_id'})
        if failure is not None:
            return failure
        try:
            remove_place(g.auth, str(trip_id), request.form['place_id'])
        except TripServiceError as error:
            return helpers['_trip_failure'](error, mutation=True)
        return redirect(url_for('trips_detail', trip_id=trip_id), code=303)

    @bp.post('/user/trips/<uuid:trip_id>/duplicate')
    @login_required
    def duplicate_trip(trip_id):
        failure = helpers['_trip_post_check']({'csrf_token'})
        if failure is not None:
            return failure
        try:
            detail = helpers['get_user_trip'](g.auth, str(trip_id), membership_limit=21, after_position=0)
            if detail is None:
                return 'Trip not found.', 404
            if len(detail.memberships) > 20:
                return 'Duplicate supports at most 20 destinations. Create a new trip for a larger plan.', 409
            if detail.next_after_position is not None:
                tail = helpers['get_user_trip'](g.auth, str(trip_id), membership_limit=1,
                                               after_position=detail.next_after_position)
                if tail is None or tail.memberships:
                    return 'Reload this trip before duplicating it.', 409
            selected = [m.place_id for m in detail.memberships]
            published = {p.id for p in search_published(current_app.extensions['rosago_places'], '') if visitor_place(p)}
            if len(set(selected)) != len(selected) or not set(selected) <= published:
                return 'A destination is unavailable. Review this trip before duplicating it.', 409
            return save_places(selected, detail.trip.name[:94] + ' copy', detail.trip.visit_date)
        except (PlacesUnavailableError, PlacesConsistencyError):
            return 'Destinations are temporarily unavailable. No copy was created.', 503
        except TripServiceError as error:
            return helpers['_trip_failure'](error, mutation=True)

    @bp.post('/user/trips/<uuid:trip_id>/move-place')
    @login_required
    def move_destination(trip_id):
        failure = helpers['_trip_post_check']({'csrf_token', 'place_id', 'direction'})
        if failure is not None:
            return failure
        if request.form['direction'] not in ('up', 'down'):
            return 'Choose a valid direction.', 400
        try:
            ordered, cursor = [], 0
            while True:
                detail = helpers['get_user_trip'](g.auth, str(trip_id), membership_limit=100, after_position=cursor)
                if detail is None:
                    return 'Trip not found.', 404
                ordered.extend(m.place_id for m in detail.memberships)
                if len(ordered) > 1000 or len(set(ordered)) != len(ordered):
                    return 'Reload this trip before reordering its destinations.', 409
                next_cursor = detail.next_after_position
                if next_cursor is None:
                    break
                if next_cursor <= cursor:
                    return 'Reload this trip before reordering its destinations.', 409
                cursor = next_cursor
            selected = request.form['place_id']
            if selected not in ordered:
                return 'This destination is no longer in the trip.', 409
            start = ordered.index(selected)
            end = start + (-1 if request.form['direction'] == 'up' else 1)
            if 0 <= end < len(ordered):
                ordered[start], ordered[end] = ordered[end], ordered[start]
                reorder_places(g.auth, str(trip_id), ordered)
        except TripServiceError as error:
            return helpers['_trip_failure'](error, mutation=True)
        return redirect(url_for('trips_detail', trip_id=trip_id), code=303)

    app.register_blueprint(bp)
