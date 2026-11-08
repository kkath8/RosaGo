# Phase 2F local qualification instructions

Use only an owned disposable loopback Redis, synthetic provider clients and an independent **local unsynchronized filesystem** directory. Never use a production Redis URL, production credential/key, network filesystem or shared/OneDrive authority directory. No SQL is used: the local authority is LMDB metadata, not the business database.

Install the pinned requirements into the local venv. The existing venv received `lmdb==1.7.5`. The tested container is `redis:7.4.7`, bound only to `127.0.0.1:16379`, with AOF, fsync-always and noeviction. Do not reuse the fixed fault-harness container names for anything shared.

Set the opt-in test variable in the test shell, then run:

```powershell
$env:ROSAGO_TEST_REDIS_URL='redis://127.0.0.1:16379/0'
.venv\Scripts\python.exe -m pytest tests/test_redis_sessions.py tests/test_session_readiness.py -q -p no:cacheprovider
```

Windows must permit temporary LMDB files, byte locks, IPC and spawned processes. Tests use unique namespaces/temporary authority directories and delete only their own keys/ACL identity. No FLUSHDB/FLUSHALL. Without the opt-in URL the real-Redis cases are skipped; the ordinary full regression suite is run separately.

Application local Redis initialization additionally requires `ROSAGO_SESSION_AUTHORITY_PATH`. The directory must already have an explicitly bootstrapped `LocalRevisionAuthority(path, bootstrap=True)` and `.configure(namespace, {'user': user_epoch, 'admin': admin_epoch})`. This is a local operator/test step, not automatic application fallback. All workers must use the same compatible namespace/epochs/keyring/authority directory and quota policy. Retain the existing per-realm loopback URL, namespace/epoch and secret keyring variables. Do not print or save actual keyring bytes; the fixtures generate them in memory.

`qualify_backend.py` stops/restarts only its inspected disposable container, creates/removes a second loopback stale-copy container, triggers real OOM/eviction, demonstrates the correlated-store-rollback limitation, then measures 2,000 session pairs and four-thread operations. Run it separately from all other Redis tests/browser processes, with local Docker access. It records only counts, sizes, rates and result categories.

`browser_fixture.py` starts two actual Flask worker processes on loopback ports 5101/5102 and a router on 5100. A startup handshake records their actual PIDs and source hashes in `worker-processes.json`; stale listeners cannot silently satisfy startup. Provider access is synthetic; worker socket connections are restricted to loopback Redis. `browser_checks.mjs` uses a fresh Chrome profile/CDP port 9250. It saves six screenshots and 24 checks. After testing, POST `/__local_stop` only to this private local fixture to stop both actual workers through their local shutdown endpoints and release the authority directory, then close the owned Chrome/profile. These routes exist only in the fixture, never in RosaGo.

`ROSAGO_LOCAL_HTTPS_QUALIFICATION=true` explicitly enables the separate local HTTPS/proxy configuration tests. It requires canonical `ROSAGO_PUBLIC_ORIGIN`, JSON `ROSAGO_TRUSTED_HOSTS`, exact `ROSAGO_PROXY_HOPS`, and `ROSAGO_PROXY_HEADERS_SANITIZED=true` when hops are nonzero. It cannot enable production mode. Offline `validate_settings` tests require production-shaped TLS/secure-cookie configuration but return `production_approved=false` and make no remote connection.

Do not restore the local authority alongside Redis, silently recreate it at startup, or treat a local LMDB map as a safe multi-host service. A Redis-only rollback is fenced by the preserved metadata; restoring both stores can revive authority. Production remains blocked until independently protected authority storage and qualified recovery/control-plane enforcement exist.
