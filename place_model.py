"""Dependency-free public Place values shared by catalog reads and pure policy."""
from dataclasses import dataclass
from datetime import datetime


CATEGORIES = frozenset(('attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage'))


@dataclass(frozen=True, slots=True, repr=False)
class Place:
    id: str
    name: str
    slug: str
    description: str
    category: str
    address: str
    latitude: float
    longitude: float
    image_url: str | None
    created_at: datetime
    updated_at: datetime

    def __repr__(self):
        return '<Place redacted>'
