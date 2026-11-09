"""Fail-closed Render entrypoint with offline validation before any app clients."""
import os
if os.environ.get('ROSAGO_AUTH_MODE') != 'production':
    raise RuntimeError('Public hosting requires production mode; development sessions are forbidden.')
from production_session_runtime import validate_environment
validate_environment(os.environ)
# Session installation then performs live private-store/authority checks in the
# worker. Missing evidence/infrastructure prevents import; no development fallback.
from app import app

