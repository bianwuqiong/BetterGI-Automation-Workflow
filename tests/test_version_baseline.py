import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_version_baseline import verify_snapshot


class VersionBaselineTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('baseline-' + uuid4().hex[:10])
        self.root.mkdir(parents=True)
        self.file = self.root / 'production/scripts/example.py'
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'original baseline\n')
        self.entry = {'path': 'production/scripts/example.py', 'bytes': self.file.stat().st_size,
                      'sha256': hashlib.sha256(self.file.read_bytes()).hexdigest()}
        self.write_inventory([self.entry])

    def write_inventory(self, entries):
        (self.root / 'files.json').write_text(json.dumps(entries), encoding='utf-8')

    def test_snapshot_verifies_and_detects_corruption(self):
        self.assertTrue(verify_snapshot(self.root)['verified'])
        self.file.write_bytes(b'corrupted snapshot\n')
        result = verify_snapshot(self.root)
        self.assertFalse(result['verified'])
        self.assertEqual(result['failures'][0]['reason'], 'checksum_mismatch')

    def test_snapshot_rejects_path_traversal_and_duplicates(self):
        for path in ('../escape', '/absolute', 'C:/absolute', r'production\file'):
            self.write_inventory([dict(self.entry, path=path)])
            with self.assertRaises(ValueError):
                verify_snapshot(self.root)
        self.write_inventory([self.entry, self.entry])
        with self.assertRaises(ValueError):
            verify_snapshot(self.root)
        self.write_inventory([self.entry, dict(self.entry, path=self.entry['path'].upper())])
        with self.assertRaises(ValueError):
            verify_snapshot(self.root)

    def test_snapshot_rejects_live_cookie_file(self):
        cookie = self.root / 'production/config/hoyolab.json'
        cookie.parent.mkdir(parents=True)
        cookie.write_text('{}', encoding='utf-8')
        self.assertFalse(verify_snapshot(self.root)['verified'])

    def test_snapshot_rejects_unlisted_file_and_noncanonical_paths(self):
        extra = self.root / 'production/scripts/unlisted.py'
        extra.write_bytes(b'unlisted\n')
        self.assertIn('unlisted_file', [item['reason'] for item in verify_snapshot(self.root)['failures']])
        for path in ('production//scripts/example.py', 'production/./scripts/example.py'):
            self.write_inventory([dict(self.entry, path=path)])
            with self.assertRaises(ValueError):
                verify_snapshot(self.root)

    def test_snapshot_rejects_invalid_hashes_and_sizes(self):
        for change in ({'sha256': 'z' * 64}, {'bytes': True}, {'bytes': -1}, {'bytes': '1'}):
            self.write_inventory([dict(self.entry, **change)])
            with self.assertRaises(ValueError):
                verify_snapshot(self.root)


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell restore')
class WindowsBaselineRestoreTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('restore-baseline-' + uuid4().hex)
        self.workspace = self.root / 'fake-workspace'
        self.baseline = self.root / 'snapshot'
        (self.workspace / 'scripts').mkdir(parents=True)
        (self.workspace / 'config').mkdir()
        (self.workspace / 'state').mkdir()
        (self.baseline / 'production/scripts').mkdir(parents=True)
        for name in ('restore_version_baseline.ps1', 'verify_version_baseline.py'):
            shutil.copyfile(ROOT / 'scripts' / name, self.workspace / 'scripts' / name)
        (self.workspace / 'config/settings.json').write_text(
            json.dumps({'pythonExe': sys.executable}), encoding='utf-8')
        (self.baseline / 'manifest.json').write_text('{}', encoding='utf-8')
        self.target = self.workspace / 'scripts/example.py'
        self.target.write_bytes(b'previous workspace file\n')
        self.original = self.target.read_bytes()
        self.entries = []
        self.add_snapshot('scripts/example.py', b'baseline example\n')

    def add_snapshot(self, relative, content):
        path = self.baseline / 'production' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.entries.append({'path': 'production/' + relative, 'bytes': len(content),
                             'sha256': hashlib.sha256(content).hexdigest()})
        (self.baseline / 'files.json').write_text(json.dumps(self.entries), encoding='utf-8')

    @staticmethod
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    def run_restore(self, apply=True, process_body='@()', task_body='@()'):
        # Never invoke the actual workspace restore entry point. These copied
        # helpers can only target an isolated fake workspace under retained fixtures.
        fixture_root = (ROOT / 'tests/.artifacts').resolve()
        self.assertIn(fixture_root, self.workspace.resolve().parents)
        self.assertIn(fixture_root, self.baseline.resolve().parents)
        command = (
            'function Get-Process { param($ErrorAction) ' + process_body + ' }; '
            'function Get-ScheduledTask { param($TaskName, $ErrorAction) ' + task_body + ' }; '
            '& ' + self.quote(self.workspace / 'scripts/restore_version_baseline.ps1')
            + ' -Baseline ' + self.quote(self.baseline) + (' -Apply' if apply else '')
        )
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                               '-ExecutionPolicy', 'Bypass', '-Command', command],
                              cwd=self.workspace, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=30)

    def junction(self, link, target):
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             'New-Item -ItemType Junction -Path ' + self.quote(link)
             + ' -Value ' + self.quote(target) + ' | Out-Null'],
            capture_output=True, text=True, errors='replace', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_apply_restores_only_listed_files_and_preserves_previous_files(self):
        unrelated = self.workspace / 'scripts/unrelated.py'
        unrelated.write_bytes(b'keep unrelated\n')
        result = self.run_restore()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.target.read_bytes(), b'baseline example\n')
        self.assertEqual(unrelated.read_bytes(), b'keep unrelated\n')
        backups = list((self.workspace / 'backups').glob('before-baseline-restore-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'scripts/example.py').read_bytes(), self.original)
        self.assertRegex(backups[0].name, r'before-baseline-restore-[0-9a-f]{32}$')

    def test_apply_rejects_the_runner_shared_lock(self):
        import msvcrt
        lock_path = self.workspace / 'state/workflow.lock'
        with lock_path.open('a+b') as stream:
            stream.write(b'0')
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                result = self.run_restore()
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Workflow lock is busy', result.stderr)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse((self.workspace / 'backups').exists())

    def test_apply_rejects_unlisted_snapshot_before_overwriting(self):
        (self.baseline / 'production/scripts/unlisted.py').write_bytes(b'unverified\n')
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse((self.workspace / 'scripts/unlisted.py').exists())
        self.assertFalse((self.workspace / 'backups').exists())

    def test_apply_rejects_destination_junction_before_any_overwrite(self):
        outside = self.root / 'outside-workspace'
        outside.mkdir()
        (outside / 'example.txt').write_bytes(b'outside original\n')
        self.add_snapshot('docs/example.txt', b'baseline documentation\n')
        self.junction(self.workspace / 'docs', outside)
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reparse point', result.stderr)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual((outside / 'example.txt').read_bytes(), b'outside original\n')
        self.assertFalse((self.workspace / 'backups').exists())

    def test_apply_rejects_source_and_backup_junctions(self):
        source = self.baseline / 'shared-source'
        source.mkdir()
        self.junction(self.baseline / 'production/docs', source)
        self.add_snapshot('docs/example.txt', b'baseline documentation\n')
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reparse point', result.stderr)
        self.assertEqual(self.target.read_bytes(), self.original)

        # A separate fixture keeps each failure independent and preserves junctions.
        self.setUp()
        backup_target = self.root / 'outside-backups'
        backup_target.mkdir()
        self.junction(self.workspace / 'backups', backup_target)
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reparse point', result.stderr)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(list(backup_target.iterdir()), [])

    def test_apply_rejects_running_game_and_running_task(self):
        for kwargs in ({'process_body': "[pscustomobject]@{ ProcessName = 'GenshinImpact' }"},
                       {'task_body': "[pscustomobject]@{ State = 'Running' }"}):
            result = self.run_restore(**kwargs)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.target.read_bytes(), self.original)
            self.assertFalse((self.workspace / 'backups').exists())

    def test_preview_does_not_restore_or_create_backup(self):
        result = self.run_restore(apply=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"Ready":  true', result.stdout)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse((self.workspace / 'backups').exists())


if __name__ == '__main__':
    unittest.main()
