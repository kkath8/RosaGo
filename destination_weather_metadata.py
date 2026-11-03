"""Curated, versioned catalog sidecar. No inference, database changes or network."""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlsplit

from itinerary_preview import canonical_json
from place_model import CATEGORIES

EXPOSURES = ('indoor', 'covered', 'mixed', 'outdoor', 'unknown')
METADATA_PATH = Path(__file__).resolve().parent / 'data/santa_rosa_places/weather_metadata.json'
MAX_METADATA_BYTES = 64_000


@dataclass(frozen=True, slots=True)
class WeatherMetadata:
    exposure: str = 'unknown'
    source_url: str | None = None
    source_note: str | None = None
    verified_on: str | None = None

    def __post_init__(self):
        if type(self.exposure) is not str or self.exposure not in EXPOSURES:
            raise ValueError('Invalid weather metadata.')
        provenance = (self.source_url, self.source_note, self.verified_on)
        if self.exposure == 'unknown':
            if any(value is not None for value in provenance):
                raise ValueError('Unknown exposure must not claim verification.')
            return
        for value, maximum in ((self.source_url, 2048), (self.source_note, 500), (self.verified_on, 10)):
            if (type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip()
                    or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
                raise ValueError('Verified exposure requires bounded provenance.')
        url = urlsplit(self.source_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Expected an HTTPS factual source.')
        if date.fromisoformat(self.verified_on).isoformat() != self.verified_on:
            raise ValueError('Expected an ISO verification date.')


UNKNOWN = WeatherMetadata()


@dataclass(frozen=True, slots=True)
class WeatherCatalog:
    records: object
    fingerprint: str
    available: bool = True

    def for_place(self, place):
        row = self.records.get(place.slug)
        # Renamed, moved or recategorized destinations need renewed curation. A slug
        # alone does not prove that the metadata still describes this catalog row.
        return row[3] if row and row[:3] == (place.name, place.category, place.address) else UNKNOWN


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate metadata key.')
        result[key] = value
    return result


def validate_weather_catalog(document):
    if (type(document) is not dict or set(document) != {'schema_version', 'destinations'}
            or type(document['schema_version']) is not int or document['schema_version'] != 1
            or type(document['destinations']) is not list or len(document['destinations']) > 100):
        raise ValueError('Invalid weather catalog.')
    records = {}
    for row in document['destinations']:
        if type(row) is not dict or set(row) != {'slug', 'name', 'category', 'address', 'exposure', 'source_url', 'source_note', 'verified_on'}:
            raise ValueError('Invalid weather catalog row.')
        for key, maximum in (('slug', 120), ('name', 150), ('address', 500)):
            if (type(row[key]) is not str or not 1 <= len(row[key]) <= maximum
                    or row[key] != row[key].strip() or any(ord(c) < 32 for c in row[key])):
                raise ValueError('Invalid weather catalog identity.')
        if (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', row['slug']) or row['slug'] in records
                or type(row['category']) is not str or row['category'] not in CATEGORIES):
            raise ValueError('Invalid weather catalog identity.')
        metadata = WeatherMetadata(*(row[key] for key in ('exposure', 'source_url', 'source_note', 'verified_on')))
        records[row['slug']] = (row['name'], row['category'], row['address'], metadata)
    encoded = canonical_json(document)
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError('Weather metadata is too large.')
    return WeatherCatalog(MappingProxyType(records), hashlib.sha256(encoded).hexdigest())


def load_weather_catalog(path=METADATA_PATH):
    try:
        with path.open('rb') as source:
            content = source.read(MAX_METADATA_BYTES + 1)
        if len(content) > MAX_METADATA_BYTES:
            raise ValueError('Weather metadata is too large.')
        return validate_weather_catalog(json.loads(content, object_pairs_hook=_unique))
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        # A broken/missing curation file must never hide the public itinerary.
        return WeatherCatalog(MappingProxyType({}), 'unavailable', available=False)
