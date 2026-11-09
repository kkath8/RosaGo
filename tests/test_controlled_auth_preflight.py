"""Offline operator preflight must ignore inherited credentials and never log keys."""
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
KEY = 'sb_publishable_synthetic_offline_fixture'


class ControlledAuthPreflightTests(unittest.TestCase):
    def run_check(self, key):
        main=runpy.run_path(str(ROOT/'tools/check_evaluation_backend.py'))['main']
        output=io.StringIO()
        with patch('evaluation_config.EVALUATION_PUBLIC_KEY_SHA256',
                   frozenset({hashlib.sha256(KEY.encode()).hexdigest()})), \
             patch('getpass.getpass',return_value=key), \
             patch('socket.socket.connect',side_effect=AssertionError('No network')) as network, \
             patch('dotenv.load_dotenv') as dotenv, \
             patch('supabase.create_client') as sdk, redirect_stdout(output):
            code=main()
            network.assert_not_called()
            dotenv.assert_not_called()
            sdk.assert_not_called()
        return code,output.getvalue()

    def test_only_fresh_evaluation_mapping_used_and_key_never_printed(self):
        with patch.dict(os.environ,{'SUPABASE_URL':'https://brnkigrrqdrywahvcbvc.supabase.co',
                                    'SUPABASE_KEY':'inherited-private-marker',
                                    'SUPABASE_STORAGE_SECRET_KEY':'inherited-storage-marker'}):
            code,output=self.run_check(KEY)
        self.assertEqual(code,0)
        for private in (KEY,'inherited-private-marker','inherited-storage-marker','brnkigrrqdrywahvcbvc'):
            self.assertNotIn(private,output)
        self.assertIn('"web_runtime_qualified": false',output)
        self.assertIn('"configuration_saved": false',output)

    def test_unknown_or_secret_key_stops_without_exposing_input(self):
        for key in ('sb_publishable_unverified_private_marker','sb_secret_private_marker'):
            code,output=self.run_check(key)
            self.assertEqual(code,1)
            self.assertNotIn(key,output)
