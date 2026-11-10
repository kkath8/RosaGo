"""Evaluation component probe; no app startup, signing, Auth or database writes.

Default is offline. --live-readonly requires explicitly selected non-secret hosts
and private process environment. Never loads .env or prints exception details.
Passing this probe is NOT production/security-release qualification.
"""
import argparse
from contextlib import nullcontext
import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from authority_http_transport import AuthorityHTTPTransport
from protected_session_authority import AuthorityBinding, ProtectedRevisionAuthority
from production_session_runtime import _verify_pool

PROJECT = 'jfaufpfzfhysqkhcdsrs'
REQUIRED = ('SUPABASE_URL', 'ROSAGO_SESSION_DATABASE_URL', 'ROSAGO_SESSION_NAMESPACE',
    'ROSAGO_USER_SESSION_EPOCH', 'ROSAGO_ADMIN_SESSION_EPOCH', 'ROSAGO_AUTHORITY_ORIGIN',
    'ROSAGO_AUTHORITY_ID', 'ROSAGO_AUTHORITY_INCARNATION', 'ROSAGO_AUTHORITY_MIN_SEQUENCE',
    'ROSAGO_AUTHORITY_CLIENT_TOKEN')


def configuration(env, host, origin):
    if any(not env.get(k) for k in REQUIRED):
        raise ValueError()
    if env['SUPABASE_URL'] != 'https://' + PROJECT + '.supabase.co':
        raise ValueError()
    if any(v and k.startswith('PG') for k, v in env.items()):
        raise ValueError()
    if not host or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}', host):
        raise ValueError()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError()
    if host.endswith(('.supabase.co', '.supabase.com')):
        raise ValueError()
    values = conninfo_to_dict(env['ROSAGO_SESSION_DATABASE_URL'])
    if set(values) - {'host', 'port', 'dbname', 'user', 'password', 'sslmode',
                     'sslrootcert', 'connect_timeout', 'application_name'}:
        raise ValueError()
    if (values.get('host') != host or values.get('port', '5432') != '5432'
            or values.get('user') != 'rosago_session_app'
            or not re.fullmatch(r'rosago_sessions(?:_[a-z0-9_]+)?', values.get('dbname', ''))
            or not 32 <= len(values.get('password', '')) <= 256
            or values.get('sslmode') != 'verify-full' or values.get('sslrootcert') != 'system'
            or values.get('connect_timeout', '2') not in ('1', '2')):
        raise ValueError()
    parsed = urlsplit(origin or '')
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or origin != 'https://' + parsed.hostname
            or parsed.hostname in ('localhost', '127.0.0.1', '::1')
            or origin != env['ROSAGO_AUTHORITY_ORIGIN']):
        raise ValueError()
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise ValueError()
    if not re.fullmatch(r'evaluation_[A-Za-z0-9_-]{1,53}', env['ROSAGO_SESSION_NAMESPACE']):
        raise ValueError()
    epochs = {r: env['ROSAGO_' + r.upper() + '_SESSION_EPOCH'] for r in ('user', 'admin')}
    if len(set(epochs.values())) != 2 or any(not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', v) for v in epochs.values()):
        raise ValueError()
    token = env['ROSAGO_AUTHORITY_CLIENT_TOKEN']
    if not 32 <= len(token) <= 256 or any(not 0x21 <= ord(c) <= 0x7e for c in token):
        raise ValueError()
    if env.get('ROSAGO_AUTHORITY_OPERATOR_TOKEN') or env.get('CLOUDFLARE_API_TOKEN'):
        raise ValueError()
    binding = AuthorityBinding(env['ROSAGO_AUTHORITY_ID'], env['ROSAGO_AUTHORITY_INCARNATION'],
                               int(env['ROSAGO_AUTHORITY_MIN_SEQUENCE']))
    values.update(connect_timeout='2', application_name='rosago-evaluation-readonly-probe')
    return make_conninfo(**values), binding, epochs


class ExistingConnection:
    def __init__(self, conn):
        self.conn = conn

    def connection(self, **kwargs):
        return nullcontext(self.conn)


def probe(env, *, live=False, database_host=None, authority_origin=None):
    result = dict(project_ref=PROJECT, mode='live-readonly' if live else 'offline',
        missing_variables=[k for k in REQUIRED if not env.get(k)],
        configuration_valid=False, database_tls_and_acl_passed=False,
        authority_descriptor_passed=False, infrastructure_contact_attempted=False,
        supabase_contacted=False, live_signins_performed=False,
        session_mutations_performed=False, provider_security_qualified=False,
        application_startup_qualified=False, deployment_authorized=False)
    try:
        conninfo, binding, epochs = configuration(env, database_host, authority_origin)
    except Exception:
        result['stop_reason'] = 'missing_or_invalid_evaluation_configuration'
        return result
    result['configuration_valid'] = True
    if not live:
        result['stop_reason'] = 'live_probe_not_requested'
        return result
    result['infrastructure_contact_attempted'] = True
    try:
        # Connection is read-only from its first transaction; no pool reconnects.
        with psycopg.connect(conninfo, autocommit=True, row_factory=dict_row,
                client_encoding='UTF8', options='-c default_transaction_read_only=on -c statement_timeout=2000') as conn:
            with conn.transaction():
                row = conn.execute("SELECT current_setting('transaction_read_only') AS readonly, "
                    "ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
                # pg_stat_ssl describes the backend hop. Managed TLS proxies can
                # terminate verified client TLS before that hop. Require libpq's
                # actual client TLS state; verify-full/root trust are mandatory
                # above, and a handshake/certificate error never reaches here.
                if not row or row['readonly'] != 'on' or conn.pgconn.ssl_in_use is not True:
                    raise ValueError()
            _verify_pool(ExistingConnection(conn))
        result['database_tls_and_acl_passed'] = True
    except Exception:
        result['stop_reason'] = 'database_connection_tls_or_acl_failed'
        return result
    transport = None
    try:
        transport = AuthorityHTTPTransport(authority_origin + '/v1/authority',
            env['ROSAGO_AUTHORITY_CLIENT_TOKEN'], expected_path='/v1/authority')
        authority = ProtectedRevisionAuthority(transport, binding)
        authority.maintain()
        descriptor = authority.descriptor(env['ROSAGO_SESSION_NAMESPACE'])
        if descriptor['state'] != 'OPEN' or descriptor['epochs'] != epochs:
            raise ValueError()
        result['authority_descriptor_passed'] = True
        result['stop_reason'] = 'component_readonly_checks_passed_live_security_tests_still_required'
    except Exception:
        result['stop_reason'] = 'authority_tls_binding_or_readiness_failed'
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                result['authority_descriptor_passed'] = False
                result['stop_reason'] = 'authority_cleanup_failed'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-readonly', action='store_true')
    parser.add_argument('--database-host')
    parser.add_argument('--authority-origin')
    args = parser.parse_args()
    result = probe(os.environ, live=args.live_readonly, database_host=args.database_host,
                   authority_origin=args.authority_origin)
    print(json.dumps(result, indent=2))
    return 0 if result['authority_descriptor_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
