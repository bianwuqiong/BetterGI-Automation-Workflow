"""Initialize only retained fake directories; no production config or authorization."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from uuid import uuid4
from scripts.artifact_farming import load_artifact_config

ROOT = Path(__file__).resolve().parents[1]


class ArtifactInitializationTests(unittest.TestCase):
    def test_all_public_examples_are_valid_disabled_zero_budget_templates(self):
        for path in (ROOT / 'config').glob('artifact*.example.json'):
            config = load_artifact_config(path)
            self.assertRegex(config['policy']['scopeId'], r'^\d{8}T\d{6}-[0-9a-f]{8}$')
            self.assertFalse(config['executionEnabled'])
            self.assertEqual(config['policy']['originalResinBudget'], 0)
            self.assertEqual(config['policy']['condensedResinBudget'], 0)
            self.assertEqual(config['policy']['maxCrafts'], 0)

    @unittest.skipUnless(os.name == 'nt' and shutil.which('powershell.exe'), 'Windows PowerShell file-only fixture')
    def test_initialization_mints_local_scope_preserves_existing_and_never_authorizes(self):
        scopes = []
        for _ in range(2):
            root = ROOT / 'tests/.artifacts' / ('artifact-init-' + uuid4().hex[:10])
            (root / 'scripts').mkdir(parents=True)
            (root / 'config').mkdir()
            shutil.copyfile(ROOT / 'scripts/initialize_config.ps1', root / 'scripts/initialize_config.ps1')
            for name in ('settings', 'goals', 'artifact-farming'):
                shutil.copyfile(ROOT / 'config' / (name + '.example.json'), root / 'config' / (name + '.example.json'))
            args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(root / 'scripts/initialize_config.ps1'), '-IncludeArtifactFarming']
            subprocess.run(args, check=True, capture_output=True, timeout=20)
            path = root / 'config/artifact-farming.json'
            config = load_artifact_config(path)
            scopes.append(config['policy']['scopeId'])
            self.assertNotEqual(scopes[-1], '20000101T000000-00000000')
            self.assertFalse(config['executionEnabled'])
            self.assertEqual(config['policy']['originalResinBudget'], 0)
            self.assertEqual(config['policy']['condensedResinBudget'], 0)
            self.assertEqual(config['policy']['maxCrafts'], 0)
            self.assertFalse((root / 'state').exists())
            before = path.read_bytes()
            subprocess.run(args, check=True, capture_output=True, timeout=20)
            self.assertEqual(path.read_bytes(), before)
        self.assertNotEqual(scopes[0], scopes[1])


if __name__ == '__main__':
    unittest.main()
