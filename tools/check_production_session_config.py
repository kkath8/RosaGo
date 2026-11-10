"""Offline preflight only. Does not load .env, open clients or print secret values."""
import json
import os
from production_session_runtime import validate_environment

REQUIRED=('ROSAGO_AUTH_MODE','ROSAGO_SESSION_BACKEND','SUPABASE_URL','SUPABASE_KEY','FLASK_SECRET_KEY',
    'ROSAGO_PUBLIC_ORIGIN','ROSAGO_PROXY_HOPS','ROSAGO_PROXY_HEADERS_SANITIZED','ROSAGO_SESSION_DATABASE_URL',
    'ROSAGO_SESSION_KEYRING','ROSAGO_SESSION_NAMESPACE','ROSAGO_USER_SESSION_EPOCH','ROSAGO_ADMIN_SESSION_EPOCH',
    'ROSAGO_AUTHORITY_ID','ROSAGO_AUTHORITY_INCARNATION','ROSAGO_AUTHORITY_MIN_SEQUENCE','ROSAGO_AUTHORITY_ORIGIN',
    'ROSAGO_AUTHORITY_CLIENT_TOKEN','ROSAGO_PROVIDER_ENROLL_TOKEN','ROSAGO_PROVIDER_CHECK_TOKEN','ROSAGO_PROVIDER_REVOKE_TOKEN',
    'ROSAGO_SECURITY_RELEASE_VERIFY_KEY','ROSAGO_SECURITY_RELEASE_JWT')


def check(environment):
    missing=[key for key in REQUIRED if not environment.get(key)]
    valid=False
    if not missing:
        try:validate_environment(environment)
        except RuntimeError:pass
        else:valid=True
    return dict(configuration_valid=valid,missing_variables=missing,
        reason='configuration_and_signed_binding_valid' if valid else 'missing_or_invalid_configuration_or_release',
        infrastructure_contacted=False,provider_qualified=False,deployment_authorized=False)


if __name__=='__main__':
    result=check(os.environ);print(json.dumps(result,indent=2));raise SystemExit(0 if result['configuration_valid'] else 1)
