"""Versioned, project-bound category registry; legacy behavior until qualified.

The reviewed file is an operator-controlled mirror of the database registry.
It is never populated from browser input. No I/O to Supabase occurs here.
"""
from collections.abc import Mapping, Set
from functools import lru_cache
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlsplit

LEGACY_LABELS = {'attraction': 'Attractions', 'dining': 'Dining', 'shopping': 'Shopping',
                 'accommodation': 'Accommodation', 'nature': 'Nature', 'heritage': 'Heritage',
                 'industrial': 'Industrial Tourism'}
KEY = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


class CategoryConfigurationError(ValueError):
    def __init__(self):
        super().__init__('Catalog category configuration is unavailable or unqualified.')


def parse_registry(document, *, project_ref):
    if (type(document) is not dict or document.get('schema_version') != 1
            or document.get('approved') is not True or document.get('project_ref') != project_ref
            or type(document.get('categories')) is not list or not 7 <= len(document['categories']) <= 2000):
        raise CategoryConfigurationError()
    result = {}
    for item in document['categories']:
        if (type(item) is not dict or set(item) != {'key', 'label', 'parent_key'}
                or type(item['key']) is not str or not 1 <= len(item['key']) <= 120
                or not KEY.fullmatch(item['key']) or item['key'] in result
                or type(item['label']) is not str or not 1 <= len(item['label']) <= 250
                or item['label'] != item['label'].strip()
                or any(ord(c) < 32 for c in item['label'])
                or (item['parent_key'] is not None and type(item['parent_key']) is not str)):
            raise CategoryConfigurationError()
        result[item['key']] = MappingProxyType(dict(item))
    if any(key not in result or result[key]['label'] != label or result[key]['parent_key'] is not None
           for key, label in LEGACY_LABELS.items()):
        raise CategoryConfigurationError()
    for key in result:
        visited = set()
        node = key
        while node is not None:
            if node not in result or node in visited:
                raise CategoryConfigurationError()
            visited.add(node)
            node = result[node]['parent_key']
    return MappingProxyType(result)


@lru_cache(maxsize=8)
def _registry(enabled, path, project_ref):
    if not enabled:
        return MappingProxyType({key: MappingProxyType(dict(key=key, label=label, parent_key=None))
                                 for key, label in LEGACY_LABELS.items()})
    try:
        if not path or not project_ref:
            raise CategoryConfigurationError()
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise CategoryConfigurationError()
                result[key] = value
            return result
        return parse_registry(json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs),
                              project_ref=project_ref)
    except (OSError, ValueError, TypeError):
        raise CategoryConfigurationError() from None


def flexible_catalog_enabled():
    return os.getenv('ROSAGO_FLEXIBLE_CATALOG_ENABLED', '').lower() == 'true'


def category_registry():
    host = urlsplit(os.getenv('SUPABASE_URL', '')).hostname or ''
    project_ref = host.removesuffix('.supabase.co') if host.endswith('.supabase.co') else ''
    return _registry(flexible_catalog_enabled(), os.getenv('ROSAGO_CATEGORY_REGISTRY_PATH', ''), project_ref)


class CategoryKeys(Set):
    @classmethod
    def _from_iterable(cls, values):
        return frozenset(values)

    def __contains__(self, value):
        return type(value) is str and value in category_registry()

    def __iter__(self):
        return iter(category_registry())

    def __len__(self):
        return len(category_registry())


class CategoryLabels(Mapping):
    def __getitem__(self, key):
        return category_registry()[key]['label']

    def __iter__(self):
        return iter(category_registry())

    def __len__(self):
        return len(category_registry())


def category_matches(category, interest):
    registry = category_registry()
    if category not in registry or interest not in registry:
        return False
    node = category
    while node is not None:
        if node == interest:
            return True
        node = registry[node]['parent_key']
    return False


CATEGORIES = CategoryKeys()
CATEGORY_LABELS = CategoryLabels()
