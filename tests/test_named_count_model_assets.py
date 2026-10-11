import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.named_count_model_assets import COUNT_MODEL_ASSETS, read_named_count_model_assets


class NamedCountModelAssetsTests(unittest.TestCase):
    def runtime(self, root):
        config = root / 'User/Config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'otherConfig': {'ocrConfig': {'paddleOcrModelConfig': 8}}}), encoding='utf-8')
        for name, relative in COUNT_MODEL_ASSETS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('anonymous fixture ' + name).encode())

    def test_exact_fixed_files_and_actual_configuration_are_read_without_mutation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.runtime(root)
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob('*') if path.is_file()}
            proof = read_named_count_model_assets(root)
            self.assertEqual((proof['rawPaddleConfig'], proof['fixedDetectorConfig']), (8, 7))
            self.assertEqual([(r['modelName'], r['relativePath']) for r in proof['assets']], list(COUNT_MODEL_ASSETS))
            for asset in proof['assets']:
                data = before[Path(asset['relativePath'])]
                self.assertEqual(asset['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(asset['length'], len(data))
            self.assertEqual(before, {path.relative_to(root): path.read_bytes() for path in root.rglob('*') if path.is_file()})

    def test_missing_runtime_never_accepts_hashes_from_a_report(self):
        with self.assertRaises(ValueError):
            read_named_count_model_assets(None)

    def test_wrong_model_boolean_and_missing_configuration_reject(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.runtime(root)
            for value in (7, True, '8', None):
                (root / 'User/Config.json').write_text(json.dumps({'otherConfig': {'ocrConfig': {'paddleOcrModelConfig': value}}}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_named_count_model_assets(root)
            (root / 'User/Config.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_named_count_model_assets(root)

    def test_empty_fixed_model_and_missing_file_reject(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.runtime(root)
            path = root / COUNT_MODEL_ASSETS[0][1]
            path.write_bytes(b'')
            with self.assertRaises(ValueError):
                read_named_count_model_assets(root)
            # Recoverable rename rather than deleting an existing test artifact.
            path.rename(path.with_suffix('.retained'))
            with self.assertRaises(FileNotFoundError):
                read_named_count_model_assets(root)
