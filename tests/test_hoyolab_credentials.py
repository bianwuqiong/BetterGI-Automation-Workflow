"""Credential tests use fabricated cookies exclusively."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import hoyolab_credentials as credentials


class CredentialTests(unittest.TestCase):
    def test_rejects_invalid_cookie(self):
        for value in ('', ' ', 'synthetic\nsecret', 'synthetic\rsecret', 'x' * 32769, None):
            with self.assertRaises(credentials.CredentialError):
                credentials.validate_cookie(value)

    def test_legacy_cookie(self):
        self.assertEqual(credentials.load_cookie({'cookie': {'ltuid_v2': '123', 'ltoken_v2': 'synthetic'}}), 'ltuid_v2=123; ltoken_v2=synthetic')
        for cookie in ({'name':'synthetic\n'}, {'name\r':'synthetic'}):
            with self.assertRaises(credentials.CredentialError):
                credentials.load_cookie({'cookie':cookie})

    def test_ciphertext_priority_and_fail_closed(self):
        with patch.object(credentials, 'unprotect_cookie', return_value='synthetic=encrypted') as decrypt:
            self.assertEqual(credentials.load_cookie({'cookieDpapi': 'blob', 'cookie': 'synthetic=legacy'}), 'synthetic=encrypted')
            decrypt.assert_called_once_with('blob')
        with self.assertRaises(credentials.CredentialError):
            credentials.load_cookie({'cookieDpapi': '', 'cookie': 'synthetic=legacy'})

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI required')
    def test_current_user_dpapi_roundtrip_and_encrypted_save(self):
        cookie = 'ltuid_v2=123456; ltoken_v2=fabricated-test-only'
        blob = credentials.protect_cookie(cookie)
        self.assertNotIn(cookie, blob)
        self.assertEqual(credentials.unprotect_cookie(blob), cookie)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hoyolab.json'
            path.write_text(json.dumps({'cookie': 'synthetic=old', 'timeoutSec': 12}), encoding='utf-8')
            credentials.save_cookie_config(path, cookie)
            text = path.read_text(encoding='utf-8')
            config = json.loads(text)
            self.assertNotIn('cookie', config)
            self.assertNotIn('fabricated-test-only', text)
            self.assertTrue(config['enabled'])
            self.assertEqual(config['timeoutSec'], 12)
            self.assertEqual(credentials.load_cookie(config), cookie)
            self.assertEqual(list(Path(directory).glob('.hoyolab-*')), [])

    def test_error_does_not_echo_blob(self):
        with self.assertRaises(credentials.CredentialError) as error:
            credentials.unprotect_cookie('synthetic-secret-invalid-base64')
        self.assertNotIn('synthetic-secret', str(error.exception))
