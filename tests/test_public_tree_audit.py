import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import audit_public_tree as audit


class PublicTreeAuditTests(unittest.TestCase):
    def setUp(self):
        # Retain anonymous fixtures under the ignored test directory for recovery.
        self.root = Path(__file__).resolve().parent / '.artifacts' / ('public-audit-' + uuid4().hex)
        self.root.mkdir(parents=True)

    def write(self, relative, data=b'{}\n'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_force_tracked_local_config_rejected_even_without_secrets(self):
        paths = [self.write(name) for name in (
            'config/settings.json', 'config/cultivation.json', 'config/hoyolab.json',
            'config/unknown-local.json', 'config/nested/accounts.json',
        )]
        findings = audit.audit_paths(paths, root=self.root, tracked=True)
        self.assertEqual(len(findings), len(paths))
        self.assertTrue(all('local configuration' in finding for finding in findings))

    def test_example_config_namings_allowed_but_content_still_scanned(self):
        paths = [self.write('config/settings.example.json'),
                 self.write('config/hoyolab.json.example')]
        self.assertEqual(audit.audit_paths(paths, root=self.root, tracked=True), [])
        paths[0].write_text('UID: ' + '1' * 9, encoding='utf-8')
        self.assertIn('game UID assignment', audit.audit_paths(paths, root=self.root, tracked=True)[0])

    def canonical_preset(self):
        return (audit.ROOT / 'config/genshin-compat-profile.json').read_text(
            encoding='utf-8-sig').encode('utf-8')

    def test_canonical_public_preset_allows_normalized_utf8_lf_only(self):
        canonical = self.canonical_preset()
        variants = (canonical, canonical.replace(b'\n', b'\r\n'),
                    b'\xef\xbb\xbf' + canonical.replace(b'\n', b'\r'))
        for data in variants:
            with self.subTest(encoding_prefix=data[:3]):
                path = self.write('config/genshin-compat-profile.json', data)
                self.assertEqual(audit.audit_paths([path], root=self.root, tracked=True), [])

    def test_public_preset_tamper_rejected_and_content_still_scanned(self):
        path = self.write('config/genshin-compat-profile.json', self.canonical_preset() + b'\n')
        self.assertIn('preset hash mismatch', audit.audit_paths([path], root=self.root, tracked=True)[0])
        path.write_text(self.canonical_preset().decode('utf-8') + 'UID: ' + '1' * 9,
                        encoding='utf-8')
        findings = audit.audit_paths([path], root=self.root, tracked=True)
        self.assertTrue(any('preset hash mismatch' in finding for finding in findings))
        self.assertTrue(any('game UID assignment' in finding for finding in findings))
        path.write_bytes(b'\xff')
        self.assertIn('not valid UTF-8', audit.audit_paths([path], root=self.root, tracked=True)[0])

    def test_public_preset_exception_is_bound_to_exact_path(self):
        for relative in ('config/genshin-compat-local.json', 'config/other-profile.json',
                         'config/nested/genshin-compat-profile.json',
                         'state/genshin-compat-local.json'):
            with self.subTest(path=relative):
                path = self.write(relative, self.canonical_preset())
                findings = audit.audit_paths([path], root=self.root, tracked=True)
                self.assertEqual(len(findings), 1)
                self.assertIn('tracked', findings[0])

    def test_private_and_generated_paths_rejected_case_insensitively(self):
        names = (
            'logs/run.json', 'state/ledger.json', 'backups/config.json',
            '.codex-remote-attachments/notes.txt', 'src/source.cs',
            'BetterGI/User/config.json', 'BetterGI_custom/readme.txt',
            'better-genshin-impact/LICENSE', 'tests/.artifacts/report.json',
            'bgi-scripts/plugin/record/run.json', 'script/bin/output.txt',
            'script/obj/build.json', 'scripts/__pycache__/entry.pyc',
            'manual-graphics.json', 'recording.json', 'results.json',
            '.env', 'nested/.env.local',
        )
        for name in names:
            with self.subTest(path=name):
                self.assertIsNotNone(audit.private_path_reason(name))
                self.assertIsNotNone(audit.private_path_reason(name.upper().replace('/', '\\')))

    def test_tracked_private_file_rejected_before_reading(self):
        missing_private = self.root / 'BetterGI_custom/User/config.json'
        findings = audit.audit_paths([missing_private], root=self.root, tracked=True)
        self.assertEqual(findings, ['BetterGI_custom/User/config.json: private runtime directory tracked'])

    def test_untracked_scan_skips_private_runtime_files(self):
        path = self.write('logs/private.json', b'not public')
        self.assertEqual(audit.audit_paths([path], root=self.root, tracked=False), [])

    def test_sponsor_media_requires_exact_reviewed_hash_and_path(self):
        payload = b'anonymous test media'
        path = self.write('docs/assets/support/fixture.png', payload)
        expected = hashlib.sha256(payload).hexdigest()
        with patch.dict(audit.ALLOWED_MEDIA, {'docs/assets/support/fixture.png': expected}):
            self.assertEqual(audit.audit_paths([path], root=self.root, tracked=True), [])
            copied = self.write('docs/copied.png', payload)
            self.assertIn('blocked or unreviewed', audit.audit_paths([copied], root=self.root, tracked=True)[0])
            path.write_bytes(payload + b'changed')
            self.assertIn('blocked or unreviewed', audit.audit_paths([path], root=self.root, tracked=True)[0])

    def test_sponsor_text_exception_does_not_bypass_secret_checks(self):
        sponsor_text = b'ali' + b'pay'
        allowed = self.write('SUPPORT.md', sponsor_text)
        other = self.write('docs/new-support.md', sponsor_text)
        self.assertEqual(audit.audit_paths([allowed], root=self.root, tracked=True), [])
        self.assertIn('payment material', audit.audit_paths([other], root=self.root, tracked=True)[0])
        allowed.write_text('ali' + 'pay\n' + 'ghp_' + 'x' * 25, encoding='utf-8')
        self.assertIn('GitHub token', audit.audit_paths([allowed], root=self.root, tracked=True)[0])

    def test_live_run_identifiers_rejected_in_docs_but_synthetic_tests_allowed(self):
        synthetic = ('20261011T' + '123456-' + 'a' * 8).encode()
        doc = self.write('docs/check.md', synthetic)
        test = self.write('tests/example.py', synthetic)
        self.assertIn('private live run identifier', audit.audit_paths([doc], root=self.root, tracked=True)[0])
        self.assertEqual(audit.audit_paths([test], root=self.root, tracked=True), [])

    def test_recordings_and_dump_files_rejected_without_known_secret_shapes(self):
        for suffix in ('.mp4', '.mkv', '.dmp', '.log', '.jsonl', '.key'):
            with self.subTest(suffix=suffix):
                path = self.write('docs/capture' + suffix, b'anonymous bytes')
                self.assertIn('blocked or unreviewed', audit.audit_paths([path], root=self.root, tracked=True)[0])


if __name__ == '__main__':
    unittest.main()
