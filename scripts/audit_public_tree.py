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
    '.pfx', '.png', '.sqlite', '.webp', '.zip',
}
ALLOWED_MEDIA = {
    'docs/assets/support/alipay.jpg':
        '50589afbf22cbee6e7d124e0d6e40b8b162f7a53a77c50c71561869bfafeba44',
    'docs/assets/support/wechat-pay.png':
        'cedd7f4846be2fc5402419d27eaeb90caf5d2e1e120d1dabe900e7a43322513a',
}
ALLOWED_SPONSOR_TEXT = {
    '.gitignore', '.github/FUNDING.yml', 'CHANGELOG.md', 'README.md', 'SUPPORT.md'
}
PATTERNS = {
    'Windows user-profile path': re.compile(r'(?i)[A-Z]:\\Users\\[^\\\s"\']+'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}'),
    'OpenAI key': re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
    'secret assignment': re.compile(
        r'(?i)(api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*["\'][^"\']{4,}'),
    'payment material': re.compile(r'(?i)(paypal\.me|alipay|wechat.?pay|收款码|付款码)'),
}


def files(tracked: bool) -> list[Path]:
    if tracked:
        output = subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=ROOT)
        return [ROOT / item.decode('utf-8') for item in output.split(b'\0') if item]
    return [path for path in ROOT.rglob('*')
            if path.is_file() and '.git' not in path.parts]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    findings: list[str] = []
    for path in files(args.tracked):
        relative = path.relative_to(ROOT).as_posix()
        if (relative == 'scripts/audit_public_tree.py'
                or relative.startswith(('tests/.artifacts/', 'logs/', 'state/'))):
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
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                if label == 'payment material' and relative in ALLOWED_SPONSOR_TEXT:
                    continue
                findings.append(f'{relative}: {label}')
    if findings:
        print('\n'.join(findings), file=sys.stderr)
        return 1
    print(f'Public-tree audit passed ({len(files(args.tracked))} files).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
