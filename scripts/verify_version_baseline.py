"""Verify a local version snapshot without starting BetterGI or reading credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def file_hash(path: Path) -> str:
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def verify_snapshot(baseline: Path, workspace: Path | None = None) -> dict:
    baseline = baseline.resolve(strict=True)
    with (baseline / 'files.json').open(encoding='utf-8-sig') as stream:
        entries = json.load(stream)
    if not isinstance(entries, list) or not entries:
        raise ValueError('The baseline inventory is empty or invalid.')
    failures = []
    seen = set()
    resolved_seen = set()
    workspace_checks = 0
    for item in entries:
        relative = item.get('path') if isinstance(item, dict) else None
        if not isinstance(relative, str) or '\\' in relative:
            raise ValueError('Invalid inventory path.')
        parts = PurePosixPath(relative)
        if (parts.is_absolute() or '..' in parts.parts or ':' in relative
                or relative in seen or parts.as_posix() != relative):
            raise ValueError('Unsafe or duplicate inventory path.')
        seen.add(relative)
        path = (baseline / relative).resolve()
        if baseline not in path.parents:
            raise ValueError('Inventory path escaped the snapshot.')
        identity = str(path).casefold()
        if identity in resolved_seen:
            raise ValueError('Duplicate inventory target.')
        resolved_seen.add(identity)
        expected = item.get('sha256')
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
            raise ValueError('Invalid inventory checksum.')
        if type(item.get('bytes')) is not int or item['bytes'] < 0:
            raise ValueError('Invalid inventory size.')
        if not path.is_file():
            failures.append({'path': relative, 'reason': 'missing'})
        elif path.stat().st_size != item.get('bytes') or file_hash(path) != expected.lower():
            failures.append({'path': relative, 'reason': 'checksum_mismatch'})
        if workspace is not None and relative.startswith('production/'):
            current = (workspace.resolve() / relative.removeprefix('production/')).resolve()
            if workspace.resolve() not in current.parents:
                raise ValueError('Workspace comparison path escaped its root.')
            workspace_checks += 1
            if not current.is_file() or file_hash(current) != expected.lower():
                failures.append({'path': relative, 'reason': 'workspace_differs'})
    for path in (baseline / 'production').rglob('*'):
        if path.is_file():
            relative = path.relative_to(baseline).as_posix()
            if relative not in seen:
                failures.append({'path': relative, 'reason': 'unlisted_file'})
    # Live account cookies are deliberately excluded from a version snapshot.
    if (baseline / 'production/config/hoyolab.json').exists():
        failures.append({'path': 'production/config/hoyolab.json', 'reason': 'credential_file_not_allowed'})
    return {'verified': not failures, 'filesChecked': len(entries),
            'workspaceFilesChecked': workspace_checks, 'failures': failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Verify a local automation version baseline')
    parser.add_argument('baseline', type=Path)
    parser.add_argument('--workspace', type=Path,
                        help='Also compare the current workspace with the production snapshot')
    args = parser.parse_args(argv)
    try:
        result = verify_snapshot(args.baseline, args.workspace)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {'verified': False, 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
