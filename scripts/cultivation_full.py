"""Bounded supervisor for the supported cultivation daily; never upgrades a target.

Children retain the existing shared workflow lock, resource ledger and evidence
checks. This parent holds a separate OS lock and never retries a resource node.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

try:
    from .cultivation import _target
except ImportError:
    from cultivation import _target

TERMINAL = {'planned', 'completed', 'partial', 'failed', 'unknown'}
RUN_ID = re.compile(r'\d{8}T\d{6}-[0-9a-f]{8}\Z')


def target_identity(target):
    normalized = _target(target)
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def game_day(now):
    return (now.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).date().isoformat()


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('missing or invalid bounded evidence file')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('evidence must be an object')
    return value


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def orchestration_lock(path):
    """Keep the lock file, releasing only the OS lock (no file deletion)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def phases(with_routes=False, route_session_config=None, preparation_config='config/party-preparation.json'):
    if not preparation_config:
        raise ValueError('mandatory party preparation requires an explicit local config')
    def preparation(name):
        return {'name': name, 'profile': 'party-preparation', 'maximumMinutes': 5,
                'minimumMinutes': 5, 'preparationConfig': str(preparation_config)}
    result = [preparation('party-preparation-before-routes' if with_routes else 'party-preparation-before-cultivation')]
    if with_routes:
        if not route_session_config:
            raise ValueError('material routes require an explicit session config')
        result.append({'name': 'material-routes', 'profile': 'material-route-session',
                       'maximumMinutes': 10, 'minimumMinutes': 10,
                       'routeSessionConfig': str(route_session_config)})
        # Routes can damage or incapacitate a party member. A prior recovery
        # does not establish fresh health before the resource-consuming domain.
        result.append(preparation('party-preparation-before-cultivation'))
    elif route_session_config:
        raise ValueError('route session config requires --with-material-routes')
    result.append({'name': 'cultivation-daily', 'profile': 'cultivation',
                   'maximumMinutes': 20, 'minimumMinutes': 15})
    return result


def child_command(root, phase, minutes, dry_run):
    """Argument arrays only; never invoke core or add a budget/repeat override."""
    script = 'run_daily.ps1' if dry_run else 'run_daily_recorded.ps1'
    argv = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(Path(root) / 'scripts' / script), '-Profile', phase['profile'],
            '-TimeoutMinutes', str(minutes)]
    if phase['profile'] == 'cultivation':
        argv += ['-CultivationMode', 'execute']
    if phase.get('routeSessionConfig'):
        argv += ['-RouteSessionConfig', phase['routeSessionConfig']]
    if phase.get('preparationConfig'):
        argv += ['-PreparationConfig', phase['preparationConfig']]
    if dry_run:
        argv += ['-DryRun', '-NoDelay']
    return argv


def verify_preparation(value, identifier):
    """The completed reader proof must establish all four current party members."""
    required = ('reportVerified', 'preparationCompleted', 'allowStatueRevival',
                'noRouteExecution', 'noItemConsumption', 'noRevivalItemConsumption',
                'noResinSpend', 'noFood', 'noCrafting', 'noUpgrade')
    if not isinstance(value, dict) or value.get('mode') != 'party-preparation' or 'noRevive' in value or any(value.get(key) is not True for key in required):
        raise ValueError('party preparation lacks completed free-statue/no-item scope proof')
    native = value.get('nativeResult', {})
    if (native.get('task') != 'party-preparation' or native.get('runId') != identifier
            or native.get('status') != 'completed' or native.get('evidenceVerified') is not True
            or 'noRevive' in native or type(native.get('teamObservationCount')) is not int or native['teamObservationCount'] != 2):
        raise ValueError('party preparation lacks scoped two-frame native proof')
    rows = native.get('slotHealthEvidence')
    names = native.get('actualTeam')
    if not isinstance(rows, list) or len(rows) != 4 or not isinstance(names, list) or len(names) != 4 or len(set(names)) != 4:
        raise ValueError('party preparation does not identify four distinct members')
    for slot, (row, name) in enumerate(zip(rows, names), 1):
        ratio = row.get('ratio')
        hp, maximum = row.get('hp'), row.get('maxHp')
        if (row.get('slot') != slot or row.get('name') != name or row.get('identityVerified') is not True
                or type(ratio) not in (int, float) or not math.isfinite(ratio) or not .8 <= ratio <= 1
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in (hp, maximum))
                or not 0 < hp <= maximum or abs(ratio - hp / maximum) > 1e-9
                or any(type(row.get(key)) is not int or row[key] != 2
                       for key in ('observations', 'identityObservations', 'ocrMatchingObservations'))):
            raise ValueError('party preparation has dead/low/unknown HP or unverified member identity')
    return names


def dispatch_scope_blocker(result):
    """Require the independent dispatch contract, never commission/click flags.

    The current native engine cannot produce this verified contract. Future
    receipt/post-state verification must establish it before the parent can
    certify the supported full daily scope.
    """
    dispatch = result.get('dispatchVerification')
    if not isinstance(dispatch, dict):
        return 'dispatchVerification is missing or invalid; collection, reassignment and post-state remain unverified'
    expected = {'status': 'verified', 'collectionStatus': 'completed',
                'reassignmentStatus': 'completed', 'postStateStatus': 'completed'}
    for field, value in expected.items():
        if dispatch.get(field) != value:
            return f'dispatchVerification.{field} is not {value}; full daily dispatch scope remains unverified'
    if dispatch.get('evidenceVerified') is not True:
        return 'dispatchVerification.evidenceVerified is not true; full daily dispatch scope remains unverified'
    if result.get('fullDailyScopeVerified') is not True:
        return 'fullDailyScopeVerified is not true; full daily dispatch scope remains unverified'
    return None


def verify_cultivation_target_archive(bundle, expected_target):
    result = bundle['result']
    report = bundle.get('cultivationReport')
    summary = result.get('cultivation')
    if (not isinstance(report, dict) or not isinstance(summary, dict) or summary.get('reportVerified') is not True
            or summary.get('runId') != result['runId'] or report.get('runId') != result['runId']
            or report.get('mode') != 'execute' or report.get('readOnly') is not False
            or report.get('status') != 'success' or report.get('targetReached') is not False
            or _target(report.get('target')) != _target(expected_target)):
        raise ValueError('cultivation archive is not verified for the requested parent target')


def verify_bundle(bundle, phase, day, dry_run=False, *, expected_target):
    result = bundle['result']
    identifier = result.get('runId')
    if not isinstance(identifier, str) or not RUN_ID.fullmatch(identifier):
        raise ValueError('invalid child run ID')
    if result.get('gameDate') != day or result.get('profile') != phase['profile']:
        raise ValueError('child day/profile does not match requested phase')
    outcome = result.get('outcome')
    claimed_outcome = outcome
    completion_blocker = reason = None
    dispatch_verified = None
    expected_target = _target(expected_target)
    if phase['profile'] == 'cultivation' and (
            result.get('cultivationTarget') != expected_target or result.get('cultivationMode') != 'execute'):
        raise ValueError('child is not bound to the requested cultivation target/execution mode')
    if outcome not in TERMINAL or not result.get('finishedAt'):
        raise ValueError('child result is not terminal')
    if dry_run:
        if outcome != 'planned' or result.get('executionOutcome') != 'not_started':
            raise ValueError('preview child was not a non-executing plan')
    elif outcome == 'completed':
        if result.get('executionOutcome') != 'exited' or result.get('exitCode') != 0:
            raise ValueError('completed child lacks a normal terminal exit')
        recording = bundle.get('recording', {})
        if recording.get('complete') is not True or recording.get('frameCoveragePassed') is not True:
            raise ValueError('completed child recording is not verified')
        expected = {'领取邮件', '培养材料', '领取每日奖励'} if phase['profile'] == 'cultivation' else {'队伍免费恢复'} if phase['profile'] == 'party-preparation' else {'刀镡路线'}
        if set(result.get('requestedProfileTasks', [])) != expected:
            raise ValueError('child requested task scope differs from the supported daily')
        if phase['profile'] == 'cultivation':
            verify_cultivation_target_archive(bundle, expected_target)
            reason = dispatch_scope_blocker(result)
            dispatch_verified = reason is None
            if reason:
                # Preserve the completed commission/material claim evidence.
                # Only the parent's broader supported-daily scope is partial.
                outcome, completion_blocker = 'partial', 'dispatch_unverified'
        if phase['profile'] == 'party-preparation':
            verify_preparation(result.get('partyPreparation'), identifier)
    return {'phase': phase['name'], 'profile': phase['profile'], 'runId': identifier,
            'parentTarget': expected_target, 'parentTargetSha256': target_identity(expected_target),
            'gameDate': day, 'outcome': outcome, 'executionOutcome': result.get('executionOutcome'),
            'claimedOutcome': claimed_outcome, 'completionBlocker': completion_blocker, 'reason': reason,
            'resultPath': bundle['resultPath'], 'recordingPath': bundle.get('recordingPath'),
            'resumed': bundle.get('resumed', False),
            'graphicsIsolation': result.get('graphicsIsolation', {}),
            'resumedVerifiedTasks': result.get('resumedVerifiedTasks', []),
            'cultivation': result.get('cultivation'),
            'tasks': result.get('tasks', []),
            'dispatchVerification': result.get('dispatchVerification'),
            'fullDailyScopeVerified': result.get('fullDailyScopeVerified'),
            'dispatchScopeVerified': dispatch_verified,
            'partyPreparation': result.get('partyPreparation'),
            'preparationReportPath': bundle.get('preparationReportPath'),
            'cultivationAuthorization': result.get('cultivationAuthorization')}


def supervise(host, *, with_routes=False, route_session_config=None, dry_run=False,
              authorized=False, maximum_minutes=None, resume_ids=(),
              preparation_config='config/party-preparation.json'):
    maximum_minutes = (35 if with_routes else 25) if maximum_minutes is None else maximum_minutes
    if type(maximum_minutes) is not int or not 20 <= maximum_minutes <= 35:
        raise ValueError('whole-run limit must be an integer from 20 to 35 minutes')
    if not dry_run and not authorized:
        raise ValueError('real execution requires explicit --authorized user invocation')
    target = _target(host.load_target())
    requested = phases(with_routes, route_session_config, preparation_config)
    start, clock_start = host.now(), host.monotonic()
    day = game_day(start)
    deadline = clock_start + maximum_minutes * 60
    report = {'schemaVersion': 1, 'kind': 'supported-cultivation-daily', 'gameDate': day,
              'startedAt': start.isoformat(), 'mode': 'preview' if dry_run else 'execute',
              'outcome': 'running', 'target': target, 'targetSha256': target_identity(target), 'targetReached': False,
              'successMeaning': '仅确认已核验的培养日常节点；不代表目标等级、天赋或武器升级完成',
              'maximumMinutes': maximum_minutes, 'coreTargetMinutes': 20,
              'materialRoutesMeasuredSeparately': with_routes, 'partyPreparationMeasuredSeparately': True,
              'allowStatueRevival': True, 'noRevivalItemConsumption': True,
              'fullDailyScopeVerified': None if dry_run else False,
              'phases': [], 'pendingPhases': [],
              'errors': [], 'authorizationSource': 'explicit-cli-user-start' if authorized else None}
    resumed = {}
    try:
        if dry_run and resume_ids:
            raise ValueError('preview cannot reuse actual child success')
        for identifier in resume_ids:
            bundle = host.read_bundle(identifier)
            if bundle['result'].get('profile') == 'party-preparation':
                raise ValueError('old preparation cannot establish fresh party health before new combat')
            phase = next((p for p in requested if p['profile'] == bundle['result'].get('profile')), None)
            if phase is None or phase['name'] in resumed:
                raise ValueError('resume child is unrelated or duplicate')
            if _target(host.load_target()) != target:
                raise ValueError('cultivation target changed while resuming the parent')
            child = verify_bundle(bundle, phase, day, expected_target=target)
            if child['outcome'] != 'completed':
                if child.get('completionBlocker') == 'dispatch_unverified':
                    child['resumeRejected'] = True
                    report['phases'].append(child)
                    raise ValueError('resume rejected: ' + child['reason'])
                raise ValueError('only verified same-day completed phases can be resumed')
            host.verify_resume_scope(bundle, phase, target)
            child['resumed'] = True
            resumed[phase['name']] = child
        for index, phase in enumerate(requested):
            if game_day(host.now()) != day:
                raise ValueError('game day changed; no next child started')
            if _target(host.load_target()) != target:
                raise ValueError('cultivation target changed during parent; no next child started')
            if phase['name'] in resumed:
                report['phases'].append(resumed[phase['name']])
                continue
            remaining = math.floor((deadline - host.monotonic()) / 60)
            if remaining < phase['minimumMinutes']:
                report['pendingPhases'] = [p['name'] for p in requested[index:]]
                report['errors'].append('insufficient remaining time; resource phase was not started')
                break
            if not dry_run and phase['profile'] == 'cultivation':
                report['resourceGate'] = host.validate_resource_gate(day, target)
            minutes = min(phase['maximumMinutes'], remaining)
            if game_day(host.now() + timedelta(minutes=minutes, seconds=120)) != day:
                report['pendingPhases'] = [p['name'] for p in requested[index:]]
                report['errors'].append('child budget could cross the next game-day reset; not started')
                break
            bundle = host.run_phase(phase, minutes, dry_run, deadline, day)
            child = verify_bundle(bundle, phase, day, dry_run, expected_target=target)
            if any(prior['runId'] == child['runId'] for prior in report['phases']):
                raise ValueError('different phases cannot reuse a child run ID')
            if not dry_run and child['outcome'] == 'completed' and phase['profile'] == 'party-preparation':
                host.verify_preparation_scope(bundle, phase)
            report['phases'].append(child)
            if _target(host.load_target()) != target:
                raise ValueError('cultivation target changed while child ran; no next phase started')
            if game_day(host.now()) != day:
                raise ValueError('child crossed the game-day boundary')
            expected = 'planned' if dry_run else 'completed'
            if child['outcome'] != expected:
                report['pendingPhases'] = [p['name'] for p in requested[index + 1:]]
                report['errors'].append(child.get('reason') or 'child was not verified complete; no retry or next phase')
                break
        if not report['errors'] and len(report['phases']) == len(requested):
            report['outcome'] = 'planned' if dry_run else 'completed'
        else:
            report['outcome'] = 'partial' if any(p['outcome'] in {'completed', 'partial'} for p in report['phases']) else 'failed'
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        report['errors'].append(str(error)[:400])
        if getattr(host, 'last_child_reference', None):
            report['interruptedChild'] = dict(host.last_child_reference)
        report['outcome'] = 'partial' if any(p['outcome'] in {'completed', 'partial'} for p in report['phases']) else 'unknown'
        report['pendingPhases'] = [p['name'] for p in requested if p['name'] not in {c['phase'] for c in report['phases'] if c['outcome'] == 'completed'}]
    if not dry_run:
        report['fullDailyScopeVerified'] = report['outcome'] == 'completed' and any(
            child['profile'] == 'cultivation' and child['outcome'] == 'completed'
            and child.get('dispatchScopeVerified') is True for child in report['phases'])
    report['finishedAt'] = host.now().isoformat()
    report['wallSeconds'] = round(host.monotonic() - clock_start, 3)
    return report


class LocalHost:
    def __init__(self, root, directory):
        self.root, self.directory = Path(root).resolve(), Path(directory)

    @staticmethod
    def now():
        return datetime.now(timezone.utc)

    @staticmethod
    def monotonic():
        return time.monotonic()

    def load_target(self):
        """Read this machine's current config; never migrate another target or budget."""
        return _target(read_json(self.root / 'config/cultivation.json').get('target'))

    def read_bundle(self, identifier):
        if not isinstance(identifier, str) or not RUN_ID.fullmatch(identifier):
            raise ValueError('invalid child ID')
        directory = self.root / 'logs/runs' / identifier
        result = read_json(directory / 'result.json')
        bundle = {'result': result, 'resultPath': str(directory / 'result.json')}
        if (directory / 'recording.json').is_file():
            recording = read_json(directory / 'recording.json')
            if result.get('outcome') == 'completed':
                video = Path(recording.get('file', ''))
                if video.resolve().parent != directory.resolve() or not video.is_file():
                    raise ValueError('recording video is not in the child run')
            bundle.update(recording=recording, recordingPath=str(directory / 'recording.json'))
        if result.get('profile') == 'party-preparation' and result.get('outcome') == 'completed':
            archive = directory / 'party-preparation-report.json'
            bundle.update(preparationReport=read_json(archive), preparationReportPath=str(archive))
        if result.get('profile') == 'cultivation' and result.get('outcome') == 'completed':
            archive = directory / 'cultivation-report.json'
            bundle.update(cultivationReport=read_json(archive), cultivationReportPath=str(archive))
        return bundle

    def verify_preparation_scope(self, bundle, phase):
        try:
            from .material_route import load_party_preparation_config, build_party_preparation_group, verify_party_preparation_report
        except ImportError:
            from material_route import load_party_preparation_config, build_party_preparation_group, verify_party_preparation_report
        config = load_party_preparation_config(phase['preparationConfig'])
        names = verify_preparation(bundle['result'].get('partyPreparation'), bundle['result']['runId'])
        if config.get('allowStatueRevival') is not True or names != config.get('expectedTeam'):
            raise ValueError('party preparation differs from the explicit expected team/free-statue policy')
        report = bundle['preparationReport']
        if report.get('runId') != bundle['result']['runId'] or report.get('nativeResult') != bundle['result']['partyPreparation']['nativeResult']:
            raise ValueError('party preparation archive differs from its authoritative result')
        directory = Path(bundle['resultPath']).parent
        result = bundle['result']
        group = read_json(directory / 'party-preparation-group.json')
        if group != build_party_preparation_group(result['runId'], config, game_date=result['gameDate']):
            raise ValueError('party preparation group differs from the requested bounded config')
        settings = read_json(self.root / 'config/settings.json')
        executable = Path(settings['bettergiExe'])
        if not executable.is_absolute():
            executable = self.root / executable
        verified = verify_party_preparation_report((directory / 'bettergi.log').read_text(encoding='utf-8-sig'),
            executable.parent, result['runId'], group, 'AutoGame_' + result['runId'], execution_outcome='exited')
        if verified['outcome'] != 'completed' or verified.get('partyPreparationReport') != report:
            raise ValueError('party preparation did not pass the independent scoped archive/log verifier')

    def verify_resume_scope(self, bundle, phase, expected_target):
        expected_target = _target(expected_target)
        if self.load_target() != expected_target:
            raise ValueError('resume target no longer matches the local cultivation config')
        result = bundle['result']
        if phase['profile'] == 'cultivation':
            if result.get('cultivationTarget') != expected_target or result.get('cultivationMode') != 'execute':
                raise ValueError('resume cultivation target/mode mismatch')
            verify_cultivation_target_archive(bundle, expected_target)
        else:
            try:
                from .material_route import load_route_session_config, build_route_session_group
            except ImportError:
                from material_route import load_route_session_config, build_route_session_group
            group = read_json(Path(bundle['resultPath']).parent / 'material-route-group.json')
            config = load_route_session_config(phase['routeSessionConfig'])
            if group != build_route_session_group(result['runId'], config, game_date=result['gameDate']):
                raise ValueError('resume route session config mismatch')

    def validate_resource_gate(self, day, expected_target):
        try:
            from .cultivation import load_cultivation_config
            from .cultivation_validation import constrain_validation
        except ImportError:
            from cultivation import load_cultivation_config
            from cultivation_validation import constrain_validation
        config = load_cultivation_config(self.root / 'config/cultivation.json', 'execute')
        policy = config['policy']
        if (config['target'] != _target(expected_target) or policy['allowBoss'] or policy['allowCrafting']
                or not policy['allowDomain'] or not policy['validationMode']
                or not policy['requireZhongliShieldCast'] or policy['maxSteps'] != 1
                or policy['originalResinBudget'] != 20 or policy['condensedResinBudget'] != 0
                or policy['domainResin'] != 'original'):
            raise ValueError('supported daily requires the unchanged one-step original20 policy')
        settings = read_json(self.root / 'config/settings.json')
        executable = Path(settings['bettergiExe'])
        if not executable.is_absolute():
            executable = self.root / executable
        _, gate = constrain_validation(self.root, executable.parent, config,
                                      'full-readonly-' + uuid4().hex[:12], day, assign=False)
        if (gate['originalResinCap'] != 60 or gate['condensedResinCap'] != 0
                or gate['priorReservedOriginal'] != 40 or gate['runtimeOriginalResinBudget'] != 20
                or 'domain' in gate['alreadyAttemptedSources']):
            raise ValueError('remaining cumulative initial-validation resource gate is not exactly20')
        return {**{key: gate[key] for key in ('scopeId', 'gameDate', 'originalResinCap',
                'condensedResinCap', 'priorReservedOriginal', 'runtimeOriginalResinBudget')},
                'target': config['target'], 'targetSha256': target_identity(config['target'])}

    @staticmethod
    def owns_runner(runner_pid, parent_pid):
        """Read only PID ancestry, never process command lines or credentials."""
        if type(runner_pid) is not int or runner_pid <= 0 or os.name != 'nt':
            return False
        import ctypes
        from ctypes import wintypes
        class Entry(ctypes.Structure):
            _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                        ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                        ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                        ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                        ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError('could not verify child runner ancestry')
        parents = {}
        try:
            entry = Entry()
            entry.dwSize = ctypes.sizeof(Entry)
            found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while found:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        current, seen = runner_pid, set()
        while current and current not in seen:
            if current == parent_pid:
                return True
            seen.add(current)
            current = parents.get(current)
        return False

    def run_phase(self, phase, minutes, dry_run, deadline, day):
        runs = self.root / 'logs/runs'
        before = {p.name for p in runs.iterdir()} if runs.exists() else set()
        previous = read_json(self.root / 'state/current-run.json').get('runId') if (self.root / 'state/current-run.json').exists() else None
        started = self.now()
        owned_id, stop_sent, stopped_at = None, False, None
        output_path = self.directory / (phase['name'] + '.log')
        with output_path.open('w', encoding='utf-8') as output:
            process = subprocess.Popen(child_command(self.root, phase, minutes, dry_run),
                                       cwd=self.root, stdout=output, stderr=subprocess.STDOUT,
                                       shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while process.poll() is None:
                current_path = self.root / 'state/current-run.json'
                if not dry_run and current_path.exists():
                    current = read_json(current_path)
                    identifier = current.get('runId')
                    if identifier != previous and identifier not in before:
                        triggered = datetime.fromisoformat(current['triggeredAt'].replace('Z', '+00:00'))
                        if (current.get('gameDate') == day and current.get('profile') == phase['profile']
                                and triggered >= started - timedelta(seconds=2)
                                and self.owns_runner(current.get('runnerPid'), process.pid)):
                            if owned_id is not None and owned_id != identifier:
                                raise ValueError('child run identity changed')
                            owned_id = identifier
                            self.last_child_reference = {'phase': phase['name'], 'runId': owned_id,
                                'gameDate': day, 'resultPath': str(runs / owned_id / 'result.json')}
                expired = self.monotonic() >= deadline or game_day(self.now()) != day
                if expired and not stop_sent:
                    if stopped_at is None:
                        stopped_at = self.monotonic()
                    if owned_id:
                        subprocess.run([sys.executable, '-B', str(self.root / 'scripts/workflow.py'),
                                        '--root', str(self.root), 'stop', '--run-id', owned_id],
                                       cwd=self.root, stdout=output, stderr=subprocess.STDOUT,
                                       shell=False, check=False, timeout=30,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        stop_sent = True
                if stopped_at is not None and self.monotonic() - stopped_at >= 120:
                    raise RuntimeError('child cleanup did not finish; no unrelated process was terminated')
                time.sleep(1)
        candidates = []
        for path in runs.iterdir() if runs.exists() else ():
            if path.name in before or not RUN_ID.fullmatch(path.name) or not (path / 'result.json').is_file():
                continue
            result = read_json(path / 'result.json')
            if result.get('profile') == phase['profile'] and result.get('gameDate') == day:
                candidates.append(path.name)
        if owned_id:
            if candidates != [owned_id]:
                raise ValueError('ambiguous child artifacts or identity mismatch')
        elif dry_run and len(candidates) == 1:
            # The wrapper forwards workflow's own terminal summary to this
            # process-owned log. A directory appearing alone is not provenance.
            summaries = []
            for line in output_path.read_text(encoding='utf-8-sig').splitlines():
                try:
                    summary = json.loads(line)
                except ValueError:
                    continue
                if isinstance(summary, dict) and summary.get('runId') == candidates[0]:
                    summaries.append(summary)
            if len(summaries) != 1:
                raise ValueError('preview child lacks its process-owned terminal summary')
            owned_id = candidates[0]
        else:
            raise ValueError('no uniquely scoped authoritative child result')
        bundle = self.read_bundle(owned_id)
        self.last_child_reference = {'phase': phase['name'], 'runId': owned_id,
            'gameDate': day, 'resultPath': bundle['resultPath'],
            'recordingPath': bundle.get('recordingPath')}
        if stop_sent:
            raise RuntimeError('parent deadline/game-day stop requested; no next phase')
        if process.returncode != 0 and bundle['result'].get('outcome') in {'planned', 'completed'}:
            raise ValueError('child process exit contradicts its result')
        return bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--authorized', action='store_true', help='explicit user-authorized real invocation')
    parser.add_argument('--with-material-routes', action='store_true')
    parser.add_argument('--route-session-config', type=Path)
    parser.add_argument('--preparation-config', type=Path, default=Path('config/party-preparation.json'))
    parser.add_argument('--maximum-minutes', type=int, default=None)
    parser.add_argument('--resume-child', action='append', default=[])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-full-' + uuid4().hex[:8]
    directory = root / 'logs/cultivation-full' / identifier
    try:
        with orchestration_lock(root / 'state/cultivation-full.lock'):
            directory.mkdir(parents=True, exist_ok=False)
            config = args.route_session_config
            if config:
                config = config if config.is_absolute() else root / config
                config = config.resolve()
                if not config.is_relative_to(root / 'config') or not config.is_file() or any(c in str(config) for c in '\r\n"'):
                    raise ValueError('route config must be an existing local config file')
            preparation = args.preparation_config
            preparation = preparation if preparation.is_absolute() else root / preparation
            preparation = preparation.resolve()
            if not preparation.is_relative_to(root / 'config') or not preparation.is_file() or any(c in str(preparation) for c in '\r\n"'):
                raise ValueError('party preparation config must be an existing local config file')
            report = supervise(LocalHost(root, directory), with_routes=args.with_material_routes,
                               route_session_config=config, dry_run=args.dry_run, authorized=args.authorized,
                               maximum_minutes=args.maximum_minutes, resume_ids=args.resume_child,
                               preparation_config=preparation)
            report.update(runId=identifier, resultPath=str(directory / 'result.json'))
            if config:
                report['routeSessionConfigSha256'] = hashlib.sha256(config.read_bytes()).hexdigest()
            report['preparationConfigSha256'] = hashlib.sha256(preparation.read_bytes()).hexdigest()
            atomic_json(directory / 'result.json', report)
            print(json.dumps({k: report[k] for k in ('runId', 'gameDate', 'outcome', 'targetReached', 'resultPath', 'errors')}, ensure_ascii=False))
            return 0 if report['outcome'] in {'planned', 'completed'} else 4
    except (ValueError, OSError) as error:
        print(json.dumps({'outcome': 'failed', 'errors': [str(error)[:400]]}, ensure_ascii=False))
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
