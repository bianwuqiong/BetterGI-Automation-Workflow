"""Read the fixed count OCR assets from the runner's trusted BetterGI directory.

Native evidence never chooses a filesystem path. This module only reads files;
it does not change the configured OCR model or any user configuration.
"""
import hashlib
import json
from pathlib import Path

COUNT_MODEL_ASSETS = (
    ('PpOcrDetV4', 'Assets/Model/PaddleOCR/Det/V4/PP-OCRv4_mobile_det_infer/slim.onnx'),
    ('PpOcrRecV4', 'Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/slim.onnx'),
    ('PpOcrRecV6', 'Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/slim.onnx'),
    ('PpOcrRecV4-labels', 'Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/inference.yml'),
    ('PpOcrRecV6-labels', 'Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/inference.yml'),
)
COUNT_MODEL_PIN_METHOD = 'actual_bundled_open_read_sha256_hold_session'


def _path(root, relative):
    candidate = root / relative
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('named-count fixed asset escaped trusted runtime')
    return resolved


def _config(root):
    path = _path(root, 'User/Config.json')
    with path.open('rb') as stream:
        content = stream.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise ValueError('named-count runtime configuration is unbounded')
    try:
        value = json.loads(content.decode('utf-8-sig'))['otherConfig']['ocrConfig']['paddleOcrModelConfig']
    except (UnicodeError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('named-count actual configured OCR model unavailable') from error
    if type(value) is not int or value != 8:
        raise ValueError('named-count fixed dual-model method requires actual configured V6')
    return hashlib.sha256(content).digest()


def read_named_count_model_assets(trusted_runtime_root):
    """Return independent local fingerprints; caller must supply the runner's root.

    The five relative paths and model identifiers are fixed here, never copied
    from the game report. The native session's pinMethod is checked separately.
    """
    if trusted_runtime_root is None:
        raise ValueError('named-count verification requires trusted BetterGI runtime root')
    root = Path(trusted_runtime_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('named-count trusted runtime root is not a directory')
    config_before = _config(root)
    assets = []
    fingerprints = []
    for model_name, relative in COUNT_MODEL_ASSETS:
        path = _path(root, relative)
        with path.open('rb') as stream:
            before = path.stat()
            if not 0 < before.st_size <= 1024 * 1024 * 1024:
                raise ValueError('named-count actual OCR model size invalid')
            digest = hashlib.sha256()
            length = 0
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                length += len(block)
                if length > before.st_size:
                    raise ValueError('named-count model changed during independent read')
                digest.update(block)
            after = path.stat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if length != before.st_size or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('named-count model changed during independent read')
        fingerprints.append((relative, identity))
        assets.append({'modelName': model_name, 'relativePath': relative,
                       'sha256': digest.hexdigest(), 'length': length})
    if _config(root) != config_before:
        raise ValueError('named-count OCR configuration changed during independent read')
    for relative, identity in fingerprints:
        final = _path(root, relative).stat()
        if identity != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns):
            raise ValueError('named-count model set changed during independent read')
    return {'rawPaddleConfig': 8, 'rawPaddleName': 'V6',
            'fixedDetectorConfig': 7, 'fixedDetectorName': 'V4', 'assets': assets}
