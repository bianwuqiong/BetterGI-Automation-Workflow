#!/usr/bin/env python3
"""Fail when tracked/public files contain common private-data or secret shapes."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
TEXT_LIMIT = 5 * 1024 * 1024
BLOCKED_SUFFIXES = {
    '.7z', '.bmp', '.dll', '.exe', '.gif', '.jpeg', '.jpg', '.pdb', '.pem',
    '.pfx', '.png', '.sqlite', '.webp', '.zip', '.key', '.log', '.jsonl',
    '.mkv', '.mp4', '.dmp',
}
PRIVATE_DIRECTORIES = {
    'logs', 'state', 'backups', '.codex-remote-attachments', 'src',
    'bettergi', 'bettergi_custom', 'better-genshin-impact',
}
PRIVATE_ROOT_FILES = {'manual-graphics.json', 'recording.json', 'results.json'}
DOCUMENT_RUN_ID = re.compile(r'\b20\d{6}T\d{6}-[a-fA-F0-9]{8}\b')
REVIEWED_PUBLIC_CONFIG = {
    # Immutable public preset from the transfer manifest, never a local snapshot.
    # Hash is UTF-8 without BOM with CRLF/CR normalized to LF.
    'config/genshin-compat-profile.json':
        'cd5304d7e78183c4b7a7a98aa755954ff79ca28c8c789b5c9b06fd3ca1d54ae5',
}
ALLOWED_MEDIA = {
    'docs/assets/support/alipay.jpg':
        '50589afbf22cbee6e7d124e0d6e40b8b162f7a53a77c50c71561869bfafeba44',
    'docs/assets/support/wechat-pay.png':
        'cedd7f4846be2fc5402419d27eaeb90caf5d2e1e120d1dabe900e7a43322513a',
}
ALLOWED_SPONSOR_TEXT = {
    '.gitignore', '.github/FUNDING.yml', 'CHANGELOG.md', 'README.md', 'SUPPORT.md',
    'docs/TRANSFER_MANIFEST_2026-10-11.json'
}
PATTERNS = {
    'Windows user-profile path': re.compile(r'(?i)[A-Z]:\\Users\\[^\\\s"\']+'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}'),
    'OpenAI key': re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
    'secret assignment': re.compile(
        r'(?i)(api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*["\'][^"\']{4,}'),
    'payment material': re.compile(r'(?i)(paypal\.me|alipay|wechat.?pay|收款码|付款码)'),
    'HoYoLAB live token': re.compile(r'(?i)(cookie_token_v2|ltoken_v2|account_id_v2|ltuid_v2)[=:][\s"\'v2_]*[A-Za-z0-9_-]{25,}'),
    'local project path': re.compile(r'(?i)[A-Z]:[\\/](?:aiproject|HoYoPlay)(?:[\\/]|\b)'),
    'game UID assignment': re.compile(
        r'(?i)(?:\bUID\b|game[_-]?uid)\s*[:=：]\s*["\']?[1-9]\d{8,9}\b'),
}


def files(tracked: bool) -> list[Path]:
    if tracked:
        output = subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=ROOT)
        return [ROOT / item.decode('utf-8') for item in output.split(b'\0') if item]
    return [path for path in ROOT.rglob('*')
            if path.is_file() and '.git' not in path.parts]


def private_path_reason(relative: str) -> str | None:
    """Check names before opening files, including force-added ignored paths."""
    parts = relative.replace('\\', '/').lower().split('/')
    if parts[0] in PRIVATE_DIRECTORIES or parts[:2] == ['tests', '.artifacts']:
        return 'private runtime directory'
    if any(part in {'bin', 'obj', '__pycache__'} for part in parts[:-1]):
        return 'generated build directory'
    if parts[0] == 'bgi-scripts' and 'record' in parts[:-1]:
        return 'private script record directory'
    if parts[0] == 'config':
        name = parts[-1]
        if (relative not in REVIEWED_PUBLIC_CONFIG
                and not name.endswith(('.example.json', '.json.example'))):
            return 'local configuration (only example JSON is public)'
    if len(parts) == 1 and parts[0] in PRIVATE_ROOT_FILES:
        return 'private runtime file'
    if parts[-1] == '.env' or parts[-1].startswith('.env.'):
        return 'local environment file'
    return None


def audit_paths(paths: list[Path], *, root: Path, tracked: bool) -> list[str]:
    findings: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        reason = private_path_reason(relative)
        if reason:
            if tracked:
                findings.append(f'{relative}: {reason} tracked')
            continue
        if not path.is_file():
            findings.append(f'{relative}: public file missing')
            continue
        if relative == 'scripts/audit_public_tree.py':
            continue
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            expected = ALLOWED_MEDIA.get(relative)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected != actual:
                findings.append(f'{relative}: blocked or unreviewed binary/media type')
            continue
        if path.stat().st_size > TEXT_LIMIT:
            findings.append(f'{relative}: unexpectedly large file')
            continue
        expected_config_hash = REVIEWED_PUBLIC_CONFIG.get(relative)
        try:
            text = path.read_text(encoding='utf-8-sig',
                                  errors='strict' if expected_config_hash else 'replace')
        except UnicodeDecodeError:
            findings.append(f'{relative}: reviewed public preset is not valid UTF-8')
            continue
        if expected_config_hash:
            # read_text performs universal newline normalization; still scan all
            # patterns below even when the reviewed preset hash has changed.
            actual_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if actual_hash != expected_config_hash:
                findings.append(f'{relative}: reviewed public preset hash mismatch')
        if relative.lower().startswith('docs/') and DOCUMENT_RUN_ID.search(text):
            findings.append(f'{relative}: private live run identifier in documentation')
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                if label == 'payment material' and relative in ALLOWED_SPONSOR_TEXT:
                    continue
                findings.append(f'{relative}: {label}')
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    paths = files(args.tracked)
    findings = audit_paths(paths, root=ROOT, tracked=args.tracked)
    if findings:
        print('\n'.join(findings), file=sys.stderr)
        return 1
    print(f'Public-tree audit passed ({len(paths)} files).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
