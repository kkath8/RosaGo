"""Dependency-free public Place values shared by catalog reads and pure policy."""
from dataclasses import dataclass
from datetime import datetime
from destination_categories import CATEGORIES


TOURISM_TYPES = frozenset(('Local', 'Common'))
ENVIRONMENTS = ('Indoor', 'Outdoor', 'Mix of Both')
TOURISM_HOURS_STATUSES = frozenset(('unverified', 'verify_required', 'not_supplied'))


@dataclass(frozen=True, slots=True, repr=False)
class Place:
    id: str
    name: str
    slug: str
    description: str
    category: str
    address: str
    latitude: float | None
    longitude: float | None
    image_url: str | None
    created_at: datetime
    updated_at: datetime
    tourism_type: str | None = None
    tourism_category: str | None = None
    tourism_opening_hours_raw: str | None = None
    tourism_closing_hours_raw: str | None = None
    tourism_hours_status: str | None = None
    tourism_source: str | None = None
    tourism_source_row: int | None = None
    environment: str | None = None
    operating_days_raw: str | None = None

    def __repr__(self):
        return '<Place redacted>'
