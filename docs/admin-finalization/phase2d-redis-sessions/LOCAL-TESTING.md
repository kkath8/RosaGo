# Local qualification only

Do not set production mode to redis-local or point tests at a deployed service. The production startup safeguard remains unconditional. Use a disposable Redis and synthetic provider clients only; do not load production credentials into these tests.

The tested service was a local `redis:7.4.7` Docker container named `rosago-phase2d-local`, published only at `127.0.0.1:16379`, with `--appendonly yes --appendfsync always --maxmemory-policy noeviction`. No host directory or production volume was mounted. Its image digest was `sha256:976ab0f0939b78c06d802bcd3bea44c5142ea9a756a57b861e08819817f768c8`. The container is disposable; local AOF tests are not failover qualification.

Install the pinned requirements into the existing virtual environment. In PowerShell, set `ROSAGO_TEST_REDIS_URL=redis://127.0.0.1:16379/0` explicitly, then run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_redis_sessions.py -q -p no:cacheprovider
```

Tests allocate random namespaces and delete only their own keys and temporary ACL identity. They never FLUSHDB/FLUSHALL. Windows must allow spawning a local process/IPC for the separate-process checks. Run ordinary regressions without that opt-in variable. JavaScript tests use Node's `--test --test-isolation=none` on the existing frontend test files.

`local_fault_checks.py` intentionally stops/restarts only the named disposable container and temporarily reduces its maxmemory. It verifies the image and loopback port mapping first; do not reuse that name for a shared service. Run it separately from other tests, with local Docker access. It writes sanitized results.

The browser fixture patches dotenv loading, uses synthetic identities and provider responses, permits server socket connections only to loopback Redis, and alternates requests between two Flask instances. It listens only at `127.0.0.1:5080`. The CDP script expects a fresh headless Chrome profile at debugging port 9248. Stop both processes and remove only that generated temporary profile afterward. Six screenshots and a 17-check result file are saved in this directory. Do not expose this fixture publicly.

Actual local application opt-in inputs are:

| Variable | Local value/meaning |
| --- | --- |
| `ROSAGO_AUTH_MODE` | `redis-local` |
| `ROSAGO_SESSION_REDIS_USER_URL`, `ROSAGO_SESSION_REDIS_ADMIN_URL` | Numeric loopback-only Redis URLs; credentials, if used, are secret. |
| `ROSAGO_SESSION_NAMESPACE` | Unique application/environment prefix, letters/digits/underscore/hyphen, at most 64 characters. |
| `ROSAGO_USER_SESSION_EPOCH`, `ROSAGO_ADMIN_SESSION_EPOCH` | Externally supplied stable realm epochs with the same character bound. |
| `ROSAGO_SESSION_KEYRING` | Secret JSON: `{"current":"key-id","keys":{"key-id":"<base64 encoding of 32 random bytes>"}}`. Optional old key IDs are decrypt-only. Never save actual key material here. |

All workers must share those compatible values. Production connection support, approved readiness/failover controls, secure origin/proxy wiring and secret provisioning are intentionally not enabled by these local inputs. The proposed Phase 2C production environment contract still requires review; this patch does not implement every proposed deployment variable.
