"""Pure rain-exposure proposals. No Gemini, provider access or persistence."""
from dataclasses import dataclass
from datetime import date
import hashlib

from itinerary_preview import canonical_json, compute_catalog_fingerprint, compute_preview_digest
from recommendation_engine import rank_candidates
from place_model import Place

LESS_EXPOSED = frozenset(('indoor', 'covered'))
EXPOSED = frozenset(('outdoor', 'mixed'))


@dataclass(frozen=True, slots=True)
class Replacement:
    day: date
    previous: Place
    proposed: Place
    previous_exposure: str
    proposed_exposure: str


@dataclass(frozen=True, slots=True)
class WeatherProposal:
    places: tuple
    replacements: tuple = ()
    notices: tuple = ()


def build_weather_proposal(preferences, days, catalog, review, metadata):
    if review is None or not review.pretrip or not review.concerns:
        return None
    current = tuple(stop['place'] for day in days for stop in day['stops'])
    if any(concern.severity == 'strong' for concern in review.concerns):
        return WeatherProposal(current, notices=(
            'Stronger weather concerns require review; RosaGo does not propose replacements for severe weather.',))
    rainy_dates = {concern.day for concern in review.concerns if concern.severity == 'caution'}
    by_id = {place.id: place for place in catalog}
    if any(place.id not in by_id or by_id[place.id] != place for place in current):
        raise ValueError('Current selection must resolve to the published catalog.')
    ranked = None
    used = {place.id for place in current}
    proposed, replacements, notices = [], [], []
    for day in days:
        for stop in day['stops']:
            previous = stop['place']
            exposure = metadata.for_place(previous).exposure
            replacement = None
            if day['date'] in rainy_dates:
                if exposure == 'unknown':
                    notices.append(f'{previous.name}: exposure is unknown; retained without assuming indoor or outdoor conditions.')
                elif exposure in EXPOSED:
                    if ranked is None:
                        ranked = rank_candidates(preferences, catalog).matched
                    eligible = [by_id[candidate.place_id] for candidate in ranked
                        if candidate.place_id not in used
                        and metadata.for_place(by_id[candidate.place_id]).exposure in LESS_EXPOSED]
                    # Prefer the same category, then the existing deterministic ID
                    # ordering within current interests. Never expand interests.
                    eligible.sort(key=lambda place: (place.category != previous.category, place.id))
                    if eligible:
                        replacement = eligible[0]
                        used.add(replacement.id)
                        replacements.append(Replacement(day['date'], previous, replacement, exposure,
                                                        metadata.for_place(replacement).exposure))
                    else:
                        notices.append(f'{previous.name}: no verified less-exposed alternative matches your current interests; retained.')
            proposed.append(replacement or previous)
    return WeatherProposal(tuple(proposed), tuple(replacements), tuple(notices))


def proposal_binding(draft, catalog, metadata, review, proposal):
    """Bind approval to the full bounded catalog, curation, plan and forecast.

    The existing DB fingerprint contract remains unchanged. This separate signed
    binding includes slug identity and curated provenance without invalidating old
    stored Previews or requiring a migration of historical contracts.
    """
    document = dict(draft_id=draft.draft_id, revision=draft.revision,
        preview=compute_preview_digest(draft.preview),
        catalog=compute_catalog_fingerprint(tuple(catalog), publication_confirmed=True),
        slugs=sorted((dict(id=place.id, slug=place.slug) for place in catalog), key=lambda row: row['id']),
        metadata=metadata.fingerprint,
        forecast=[dict(day=concern.day.isoformat(), code=concern.weather_code,
                       probability=str(concern.probability), severity=concern.severity) for concern in review.concerns],
        outside=[day.isoformat() for day in review.outside_range],
        unavailable=[day.isoformat() for day in review.unavailable_dates],
        proposed_ids=[place.id for place in proposal.places])
    return hashlib.sha256(canonical_json(document)).hexdigest()
