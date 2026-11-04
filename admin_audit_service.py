"""Bounded, read-only access to the existing destination audit history.

The caller must establish fresh Admin membership. The request-owned client and
the table's existing Admin SELECT policy independently enforce that boundary.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import re
from uuid import UUID

from admin_management_service import BASIC_FIELDS, TOURISM_FIELDS, PHOTO_FIELDS, operational_overview
from admin_places_service import AdminPlacesError, STATUSES, _context, _execute

PAGE_SIZE = 25
MAX_PAGE = 100000
ACTION_LABELS = {
    'create': 'Created', 'edit': 'Updated', 'publish': 'Published',
    'draft': 'Moved to draft', 'archive': 'Archived', 'restore': 'Restored',
}
PROJECTION = 'id,actor_id,action,destination_id,occurred_at,summary,destination:places(name,slug)'
DIRECTORY_PAGE_SIZE = 25
DIRECTORY_MAX_PAGE = 100000  # Existing operational_overview contract.


@dataclass(frozen=True)
class AuditEntry:
    id: str
    actor_id: str
    action: str
    destination_id: str
    occurred_at: datetime
    submitted_fields: tuple[str, ...]
    resulting_status: str
    destination_name: str | None
    destination_slug: str | None
    actor_name: str | None = None
    actor_email: str | None = None


@dataclass(frozen=True)
class AuditPage:
    rows: tuple[AuditEntry, ...]
    has_next: bool
    actor_lookup_complete: bool = True


def _actors(context, actor_ids):
    """Reuse the Admin directory in batches, never fetch once per audit row.

    The existing RPC supports paginated name/email search, not UUID filtering.
    Read each required directory page once, retain only requested actors, and
    stop as soon as they are found. No service key or cross-user profile read.
    A missing/deleted account or failed lookup must not hide audit history.
    """
    if not actor_ids:
        return {}, True
    actors = {}
    expected_total = None
    for page in range(1, DIRECTORY_MAX_PAGE + 1):
        try:
            directory = operational_overview(context, page=page)
        except AdminPlacesError:
            return actors, False
        total = directory['users_total']
        rows = directory['users']
        if expected_total is None:
            expected_total = total
        # Do not mistake a changing or truncated directory for a deleted actor.
        if (total != expected_total or directory['users_matching'] != total
                or len(rows) != min(DIRECTORY_PAGE_SIZE, max(0, total - (page - 1) * DIRECTORY_PAGE_SIZE))):
            return actors, False
        for user in rows:
            if user['identifier'] in actor_ids:
                name = (user['name'] or '').strip() or None
                email = (user['email'] or '').strip() or None
                actors[user['identifier']] = (name, email)
        if actor_ids <= actors.keys() or page * DIRECTORY_PAGE_SIZE >= total:
            return actors, True
    return actors, False


def _uuid(value):
    if type(value) is not str:
        raise ValueError()
    if str(UUID(value)) != value:
        raise ValueError()
    return value


def _entry(row):
    if type(row) is not dict or set(row) != {
            'id', 'actor_id', 'action', 'destination_id', 'occurred_at', 'summary', 'destination'}:
        raise ValueError()
    for key in ('id', 'actor_id', 'destination_id'):
        _uuid(row[key])
    if type(row['action']) is not str or row['action'] not in ACTION_LABELS:
        raise ValueError()
    if type(row['occurred_at']) is not str:
        raise ValueError()
    occurred = datetime.fromisoformat(row['occurred_at'])
    if occurred.tzinfo is None or occurred.utcoffset() is None:
        raise ValueError()
    summary = row['summary']
    if type(summary) is not dict or set(summary) != {'submitted_fields', 'resulting_status'}:
        raise ValueError()
    fields = summary['submitted_fields']
    if (type(fields) is not list or len(fields) > len(BASIC_FIELDS + TOURISM_FIELDS + PHOTO_FIELDS)
            or any(type(field) is not str or field not in BASIC_FIELDS + TOURISM_FIELDS + PHOTO_FIELDS for field in fields)
            or len(fields) != len(set(fields))
            or type(summary['resulting_status']) is not str or summary['resulting_status'] not in STATUSES):
        raise ValueError()
    destination = row['destination']
    if destination is not None:
        if (type(destination) is not dict or set(destination) != {'name', 'slug'}
                or type(destination['name']) is not str or not 1 <= len(destination['name']) <= 150
                or type(destination['slug']) is not str or len(destination['slug']) > 120
                or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', destination['slug'])):
            raise ValueError()
    return AuditEntry(row['id'], row['actor_id'], row['action'], row['destination_id'],
        occurred.astimezone(timezone(timedelta(hours=8))), tuple(sorted(fields)),
        summary['resulting_status'], destination['name'] if destination else None,
        destination['slug'] if destination else None)


def audit_page(context, *, action=None, page=1):
    """Read one page plus a lookahead row; never infer absence from a failure."""
    _context(context)
    if ((action is not None and (type(action) is not str or action not in ACTION_LABELS))
            or type(page) is not int or not 1 <= page <= MAX_PAGE):
        raise ValueError('Invalid audit action or page.')
    query = context.client.table('admin_destination_audit').select(PROJECTION)
    if action is not None:
        query = query.eq('action', action)
    response = _execute(query.order('occurred_at', desc=True).order('id', desc=True)
                        .range((page - 1) * PAGE_SIZE, page * PAGE_SIZE))
    rows = getattr(response, 'data', None)
    try:
        if type(rows) is not list or len(rows) > PAGE_SIZE + 1:
            raise ValueError()
        entries = tuple(_entry(row) for row in rows)
        if len({entry.id for entry in entries}) != len(entries):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise AdminPlacesError() from None
    visible = entries[:PAGE_SIZE]
    actors, complete = _actors(context, {entry.actor_id for entry in visible})
    visible = tuple(replace(entry, actor_name=actors.get(entry.actor_id, (None, None))[0],
                            actor_email=actors.get(entry.actor_id, (None, None))[1]) for entry in visible)
    return AuditPage(visible, len(entries) > PAGE_SIZE, complete)
