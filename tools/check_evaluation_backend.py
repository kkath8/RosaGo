"""Interactive OFFLINE check only; never imports app, loads dotenv or signs in.

Creates a fresh four-field configuration mapping, ignoring inherited credentials.
Reads only the evaluation PUBLIC key privately; never asks for account passwords,
JWTs, provider secrets or session keys. No configuration is written to disk.
"""
import getpass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_config import validate_evaluation_backend


def main():
    config = {'ROSAGO_EVALUATION':'true',
              'ROSAGO_EVALUATION_PROJECT_REF':'jfaufpfzfhysqkhcdsrs',
              'SUPABASE_URL':'https://jfaufpfzfhysqkhcdsrs.supabase.co'}
    try:
        config['SUPABASE_KEY'] = getpass.getpass('Evaluation publishable key (hidden; not an account password): ')
        result = validate_evaluation_backend(config)
    except (ValueError, EOFError, KeyboardInterrupt):
        print('STOP: Evaluation backend configuration could not be verified.')
        return 1
    finally:
        config.pop('SUPABASE_KEY', None)
    print(json.dumps(dict(result, offline_only=True, configuration_saved=False,
        live_sign_in_performed=False, web_runtime_qualified=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
