"""Fail-closed Render entrypoint; production sessions are NOT activated here."""
import os
if os.environ.get('ROSAGO_AUTH_MODE') != 'production':
    raise RuntimeError('Public hosting requires production mode; development sessions are forbidden.')
# Existing production startup refusal must remain until shared sessions/recovery
# are qualified. Do not set development or redis-local to bypass it.
from app import app

