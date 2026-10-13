"""Local authorization ledger for cumulative initial validation, caller holds workflow lock."""
from __future__ import annotations

import copy
from datetime import timedelta
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path

try:
    from cultivation import _json_file, _object, _run_id, _safe_path, _target, _timestamp, _integer
except ImportError:
    from scripts.cultivation import _json_file, _object, _run_id, _safe_path, _target, _timestamp, _integer


def _read(path: Path) -> dict:
    path = _safe_path(path)
    if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("initial-validation evidence missing or too large")
    return _object(_json_file(path), "initial-validation evidence")


def _source(root: Path, value: dict, allowed: set[Path] | None = None) -> Path:
    value = _object(value, 'no-commit audit source')
    relative = value.get('path')
    digest = value.get('sha256')
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('no-commit source must be a local relative path')
    path = _safe_path(root / relative)
    if not path.is_relative_to(root) or not path.is_file() or (allowed is not None and path not in allowed):
        raise ValueError('no-commit audit source escaped its run')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid no-commit source SHA256')
    actual = hashlib.sha256()
    with path.open('rb') as content:
        for block in iter(lambda: content.read(1024 * 1024), b''):
            actual.update(block)
    if actual.hexdigest() != digest:
        raise ValueError('no-commit source SHA256 changed')
    return path


def _historical_no_commit(root: Path, identifier: str, scope: str, game_date: str,
                          target: dict, report_paths: list[Path], reports: list[dict]) -> dict | None:
    """A separately reviewed historical case releases one reservation, never task success."""
    path = _safe_path(root / 'state/cultivation-no-commit-reviews' / (identifier + '.json'))
    if not os.path.lexists(path):
        return None
    audit = _read(path)
    fixed = {'schemaVersion': 1, 'kind': 'historical-boss-no-commit', 'runId': identifier,
             'stepId': identifier + ':step-1', 'scopeId': scope, 'gameDate': game_date,
             'reviewId': 'historical-no-commit:' + identifier + ':step-1',
             'configuredOriginalCost': 40, 'releasedOriginalReservation': 40,
             'observedOriginalSpent': 0, 'verdict': 'no-commit', 'reviewedBy': 'root-agent'}
    if any(type(audit.get(key)) is not type(value) or audit[key] != value for key, value in fixed.items()) or _target(audit.get('target')) != target:
        raise ValueError('historical no-commit review scope/verdict mismatch')
    reason = audit.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValueError('historical no-commit review requires a bounded independent reason')
    assertions = _object(audit.get('assertions'), 'no-commit assertions')
    if any(assertions.get(name) is not True for name in ('uninterruptedVideoReviewed', 'logAndFramesReviewed',
                                                      'noSupplement', 'noRewardSubmission', 'bossAliveAtRevive')):
        raise ValueError('historical no-commit review lacks independent video/supplement checks')
    sources = _object(audit.get('sources'), 'no-commit sources')
    report_sources = sources.get('reports')
    if not isinstance(report_sources, list) or len(report_sources) != len(report_paths):
        raise ValueError('no-commit review must bind every existing report mirror')
    expected_paths = {_safe_path(item) for item in report_paths}
    supplied_paths = [_source(root, item, expected_paths) for item in report_sources]
    if set(supplied_paths) != expected_paths or len(supplied_paths) != len(set(supplied_paths)):
        raise ValueError('no-commit report mirror coverage mismatch')
    run_dir = _safe_path(root / 'logs/runs' / identifier)
    source_paths = {}
    for name, filename in (('log', 'bettergi.log'), ('recording', 'recording.json'), ('video', 'genshin-window.mkv')):
        source_paths[name] = _source(root, sources.get(name), {_safe_path(run_dir / filename)})
    recording = _read(source_paths['recording'])
    if recording.get('complete') is not True or recording.get('frameCoveragePassed') is not True or _safe_path(recording.get('file', '')) != source_paths['video']:
        raise ValueError('no-commit recording incomplete or belongs to another video')
    coverage = recording.get('frameCoverage')
    if type(coverage) not in (float, int) or not .99 <= coverage <= 1:
        raise ValueError('no-commit video coverage insufficient')
    video_start = _timestamp(recording.get('startedAt'), 'recording startedAt')
    video_end = _timestamp(recording.get('stoppedAt'), 'recording stoppedAt')
    duration = float(recording.get('probe', {}).get('format', {}).get('duration', 0))
    if not 0 < duration < 3600:
        raise ValueError('invalid no-commit recording duration')
    frames = _object(sources.get('frames'), 'no-commit frames')
    frame_dir = _safe_path(root / 'tests/.artifacts' / ('no-commit-audit-' + identifier.split('-')[0]))
    observations = _object(audit.get('observations'), 'no-commit observations')
    times, offsets = {}, {}
    for name in ('startMap', 'endMap', 'revive'):
        frame = _source(root, frames.get(name))
        if not frame.is_relative_to(frame_dir) or frame.suffix.lower() != '.png':
            raise ValueError('no-commit frame is outside retained audit artifacts')
        observation = _object(observations.get(name), 'no-commit frame observation')
        offset = _integer(observation.get('videoOffsetSeconds'), 0, 3599, 'videoOffsetSeconds')
        timestamp = _timestamp(observation.get('observedAtUTC'), 'frame observedAtUTC')
        if not video_start <= timestamp <= video_end or offset > duration or abs((timestamp - video_start).total_seconds() - offset) > .01:
            raise ValueError('no-commit frame timestamp/video offset mismatch')
        offsets[name], times[name] = offset, timestamp
    if not offsets['startMap'] < offsets['revive'] < offsets['endMap'] or not 0 < offsets['endMap'] - offsets['startMap'] < 480:
        raise ValueError('no-commit interval could conceal natural resin recovery')
    start_count = _integer(observations['startMap'].get('originalResin'), 40, 200, 'startMap originalResin')
    end_count = _integer(observations['endMap'].get('originalResin'), 40, 200, 'endMap originalResin')
    next_restore = _integer(observations['startMap'].get('nextRestoreSeconds'), 1, 480, 'nextRestoreSeconds')
    if start_count != end_count or offsets['endMap'] - offsets['startMap'] >= next_restore:
        raise ValueError('no-commit original resin balance/recovery countdown mismatch')
    for report in reports:
        if report.get('status') != 'unknown' or len(report.get('steps', [])) != 1:
            raise ValueError('historical no-commit only supports a single unknown boss attempt')
        step = report['steps'][0]
        if step.get('stepId') != fixed['stepId'] or step.get('type') != 'boss' or step.get('status') != 'unknown' or 'after' in step or 'actualResinDelta' in step:
            raise ValueError('historical no-commit cannot replace observed after/commit evidence')
        parameters = _object(step.get('parameterEvidence'), 'no-commit boss parameters')
        checks = {'SpecifyRunCount': True, 'RunCount': 1, 'UseFragileResin': False,
                  'UseTransientResin': False, 'ReviveRetryCount': 0,
                  'ReturnToStatueAfterEachRound': False, 'RewardRecognitionEnabled': True}
        if any(type(parameters.get(key)) is not type(value) or parameters[key] != value for key, value in checks.items()):
            raise ValueError('historical no-commit boss could use supplemental resin or repeated claims')
        _integer(parameters.get('Timeout'), 120, 180, 'boss Timeout')
        before = _object(step.get('resinBefore'), 'no-commit source resinBefore')
        if before.get('originalVerified') is not True or before.get('mainUiRestored') is not True or type(before.get('originalResin')) is not int or before['originalResin'] != start_count:
            raise ValueError('no-commit map readings differ from verified original report')
        observed = _timestamp(before.get('observedAt'), 'source resin observedAt')
        started = _timestamp(step.get('startedAt'), 'source step startedAt')
        finished = _timestamp(step.get('finishedAt'), 'source step finishedAt')
        if not observed <= started <= times['startMap'] < finished <= times['endMap'] or not 0 < (times['endMap'] - observed).total_seconds() < 480:
            raise ValueError('no-commit observations do not bracket the attempted step')
        if _timestamp(audit.get('reviewedAtUTC'), 'reviewedAtUTC') < times['endMap']:
            raise ValueError('no-commit review predates its evidence')
        policy = _object(report.get('policy'), 'no-commit source policy')
        if type(policy.get('condensedResinBudget')) is not int or policy['condensedResinBudget'] != 0 or policy.get('allowCrafting') is not False or policy.get('domainResin') != 'original':
            raise ValueError('historical no-commit scope could spend other resources')
    log = source_paths['log'].read_text(encoding='utf-8-sig')
    if not all(text in log for text in ('检测到复苏界面', '取消自动任务', 'TpTask.SwitchArea')):
        raise ValueError('no-commit death/cancellation evidence missing')
    if any(text in log for text in ('领奖成功', '本轮奖励识别结果', '首领奖励领取成功', '领取奖励成功')):
        raise ValueError('no-commit review conflicts with positive reward evidence')
    local_end = times['endMap'].astimezone(timezone(timedelta(hours=8)))
    latest_header = None
    cancellations = []
    for line in log.splitlines():
        match = re.match(r'^\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]', line.strip())
        if match:
            latest_header = local_end.replace(hour=int(match[1]), minute=int(match[2]), second=int(match[3]), microsecond=int(match[4])*1000)
        if '取消自动任务' in line and latest_header is not None:
            cancellations.append(latest_header)
    if len(cancellations) != 1 or not times['revive'] <= cancellations[0] <= times['endMap']:
        raise ValueError('no-commit end map does not follow the uniquely timestamped native cancellation')
    return {'reviewId': audit['reviewId'], 'stepId': fixed['stepId'], 'path': str(path),
            'reviewSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'releasedOriginalReservation': 40, 'observedOriginalSpent': 0,
            'historicalOutcomeRetained': 'unknown'}


def _historical_no_attempt(root: Path, identifier: str, scope: str, game_date: str,
                           target: dict, prior: dict) -> dict | None:
    """Independently audited reader-only abort; absence of a checkpoint alone is insufficient."""
    audit_path = _safe_path(root / 'state/cultivation-no-commit-reviews' / (identifier + '.json'))
    if not os.path.lexists(audit_path):
        return None
    audit = _read(audit_path)
    fixed = {'schemaVersion': 1, 'kind': 'historical-pre-resource-no-attempt',
             'reviewId': 'historical-no-attempt:' + identifier, 'runId': identifier,
             'scopeId': scope, 'gameDate': game_date, 'verdict': 'no-resource-attempt',
             'releasedOriginalReservation': 0, 'observedOriginalSpent': 0, 'reviewedBy': 'root-agent'}
    if any(type(audit.get(k)) is not type(v) or audit[k] != v for k, v in fixed.items()) or _target(audit.get('target')) != target:
        raise ValueError('historical no-attempt review scope/verdict mismatch')
    if not isinstance(audit.get('reason'), str) or not audit['reason'].strip() or len(audit['reason']) > 2000:
        raise ValueError('historical no-attempt independent reason missing')
    assertions = _object(audit.get('assertions'), 'no-attempt assertions')
    if any(assertions.get(k) is not True for k in ('uninterruptedVideoReviewed', 'noResourceEntrySeen',
            'checkpointContractReviewed', 'runtimeSourceIdentityReviewed', 'noSupplement', 'characterReaderOnly')):
        raise ValueError('no-attempt review lacks independent source/video checks')
    run_dir = _safe_path(root / 'logs/runs' / identifier)
    sources = _object(audit.get('sources'), 'no-attempt sources')
    paths = {}
    for key, filename in (('result', 'result.json'), ('log', 'bettergi.log'), ('group', 'cultivation-group.json'),
                          ('recording', 'recording.json'), ('video', 'genshin-window.mkv')):
        paths[key] = _source(root, sources.get(key), {_safe_path(run_dir / filename)})
    for key in ('operator', 'main'):
        paths[key] = _source(root, sources.get(key))
        if not paths[key].is_relative_to(_safe_path(root / 'backups')) or paths[key].name != key + '.js':
            raise ValueError('no-attempt runtime sources require retained exact-name backups')
    if _read(paths['result']) != prior or prior.get('outcome') != 'failed' or prior.get('cultivationLaunchAttempted') is not True:
        raise ValueError('no-attempt source is not the original failed launched run')
    authorization = _object(prior.get('cultivationAuthorization'), 'prior authorization')
    errors = prior.get('errors')
    if (prior.get('runId') != identifier or prior.get('gameDate') != game_date or prior.get('cultivationTarget') != target
            or authorization.get('scopeId') != scope or not isinstance(errors, list)
            or not any(isinstance(e, str) and '[WinError 5]' in e and 'current-run.json' in e and '.tmp' in e for e in errors)):
        raise ValueError('no-attempt original run lacks matching atomic-replace failure evidence')
    group = _read(paths['group'])
    projects = group.get('Projects')
    if group.get('Name') != 'AutoGameCultivation_' + identifier or not isinstance(projects, list) or len(projects) != 1:
        raise ValueError('no-attempt cultivation group scope mismatch')
    settings = _object(projects[0].get('JsScriptSettingsObject'), 'source group settings')
    policy = _object(json.loads(settings.get('policyJson', 'null')), 'source policy')
    if (settings.get('runId') != identifier or settings.get('mode') != 'execute'
            or _target(json.loads(settings.get('targetConfigJson', 'null'))) != target
            or policy.get('validationScopeId') != scope or policy.get('validationMode') is not True):
        raise ValueError('no-attempt source group target/policy mismatch')
    operator = paths['operator'].read_text(encoding='utf-8-sig')
    main = paths['main'].read_text(encoding='utf-8-sig')
    required = ['const raw=await api.getCharacter(', 'report.steps.push(step);',
                'const checkpointPath=`record/${input.runId}.json`;', 'await api.writeText(checkpointPath,checkpoint)',
                'api.readText(checkpointPath)!==checkpoint', 'await api.runBoss(']
    indexes = [operator.find(token) for token in required]
    if any(index < 0 for index in indexes) or indexes != sorted(indexes) or not re.search(r'getCharacter:\s*\(name,categories\)=>characterDevelopmentTask\.GetCharacter\(name,categories\)', main):
        raise ValueError('no-attempt retained source lacks reviewed reader/checkpoint-before-resource contract')
    checkpoint_end = operator.find("throw new Error('领奖前记录写入失败", indexes[3])
    resource_entries = [match.start() for match in re.finditer(r'await api\.run(?:Boss|Domain|Crafting)\(', operator)]
    if checkpoint_end < 0 or not resource_entries or min(resource_entries) <= checkpoint_end:
        raise ValueError('no-attempt source could enter a resource operation before verified checkpoint')
    recording = _read(paths['recording'])
    if (recording.get('complete') is not True or recording.get('frameCoveragePassed') is not True
            or type(recording.get('frameCoverage')) not in (float, int) or not .98 <= recording['frameCoverage'] <= 1
            or _safe_path(recording.get('file', '')) != paths['video']):
        raise ValueError('no-attempt recording identity/coverage incomplete')
    start = _timestamp(recording.get('startedAt'), 'recording startedAt')
    stop = _timestamp(recording.get('stoppedAt'), 'recording stoppedAt')
    duration = float(recording.get('probe', {}).get('format', {}).get('duration', 0))
    if not 100 <= duration <= 180 or not 0 < (stop-start).total_seconds() <= 190:
        raise ValueError('no-attempt reader-only recording duration unsupported')
    frames = sources.get('frames')
    frame_dir = _safe_path(root / 'tests/.artifacts' / ('no-attempt-audit-' + identifier.split('-')[0]))
    if not isinstance(frames, list) or len(frames) != 6:
        raise ValueError('no-attempt full-video review requires six retained contact sheets')
    frame_paths = [_source(root, frame) for frame in frames]
    if {p.name for p in frame_paths} != {f'interval-{index:02}.png' for index in range(1, 7)} or any(not p.is_relative_to(frame_dir) for p in frame_paths):
        raise ValueError('no-attempt full-video contact-sheet coverage mismatch')
    observations = _object(audit.get('observations'), 'no-attempt observations')
    interval = _object(observations.get('videoInterval'), 'video interval')
    end_offset = _integer(interval.get('endOffsetSeconds'), 100, 180, 'endOffsetSeconds')
    if interval.get('startOffsetSeconds') != 0 or type(interval.get('startOffsetSeconds')) is not int or interval.get('sampleIntervalSeconds') != 1 or type(interval.get('sampleIntervalSeconds')) is not int or end_offset != int(duration) or _integer(interval.get('reviewedSampleCount'), 101, 181, 'reviewedSampleCount') != end_offset+1:
        raise ValueError('no-attempt reviewed interval must span the complete one-second sampled recording')
    role = _object(observations.get('roleMenu'), 'role menu observation')
    role_offset = _integer(role.get('videoOffsetSeconds'), 0, 180, 'role videoOffsetSeconds')
    role_at = _timestamp(role.get('observedAtUTC'), 'role observedAtUTC')
    reader = _object(observations.get('lastReader'), 'last reader observation')
    reader_at = _timestamp(reader.get('observedAtUTC'), 'last reader observedAtUTC')
    exit_at = _timestamp(observations.get('nativeWindowExitAtUTC'), 'nativeWindowExitAtUTC')
    if reader.get('state') != 'OpenFilterPanel' or not start <= reader_at <= exit_at <= role_at <= stop or role_offset > duration or abs((role_at-start).total_seconds()-role_offset) > .01 or _timestamp(audit.get('reviewedAtUTC'), 'reviewedAtUTC') < stop:
        raise ValueError('no-attempt reader/exit/video observations mismatch')
    log = paths['log'].read_text(encoding='utf-8-sig')
    if any(token in log for token in ('AutoBoss', 'AutoDomain', 'RunCultivationCraft', 'CULTIVATION_RESIN_OBSERVATION',
            '本轮奖励识别结果', '领奖成功', 'CountInventoryItemTask', '[AUTO_GAME_EVENT]')):
        raise ValueError('no-attempt log contains post-reader/resource evidence')
    states = re.findall(r'(?:当前状态[：:]|状态转换成功[：:])\s*(\w+)', log)
    if not states or states[-1] != 'OpenFilterPanel' or any(state not in ('MainUi', 'OpenCharacterList', 'OpenFilterPanel') for state in states):
        raise ValueError('no-attempt log advanced beyond permitted early reader states')
    latest_header = None
    logged_reader = logged_exit = None
    local_date = exit_at.astimezone(timezone(timedelta(hours=8)))
    for line in log.splitlines():
        match = re.match(r'^\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]', line.strip())
        if match:
            latest_header = local_date.replace(hour=int(match[1]), minute=int(match[2]), second=int(match[3]), microsecond=int(match[4])*1000)
        if '当前状态：OpenFilterPanel' in line:
            logged_reader = latest_header
        if '主窗体退出' in line:
            logged_exit = latest_header
    if logged_reader != reader_at or logged_exit != exit_at or _timestamp(prior.get('finishedAt'), 'prior finishedAt') < exit_at:
        raise ValueError('no-attempt observed reader/native exit times differ from actual log')
    return {'reviewId': audit['reviewId'], 'path': str(audit_path),
            'reviewSha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(),
            'releasedOriginalReservation': 0, 'observedOriginalSpent': 0,
            'historicalOutcomeRetained': 'failed', 'resourceAttempted': False}


def _pre_battle_no_commit(root: Path, identifier: str, scope: str, game_date: str,
                          target: dict, report_paths: list[Path], reports: list[dict]) -> dict:
    """Independent pre-battle proof releases its checkpoint, without inventing an after balance."""
    audit_path = _safe_path(root / 'state/cultivation-no-commit-reviews' / (identifier + '.json'))
    audit = _read(audit_path)
    expected_target = {'characterName': '梦见月瑞希', 'targetLevel': 90,
        'talentTargets': {'normal': 9, 'skill': 9, 'burst': 9},
        'includeEquippedWeapon': True, 'weaponTargetLevel': 90}
    if scope != 'mizuki-first-validation-20261008' or game_date != '2026-10-08' or target != expected_target:
        raise ValueError('pre-battle review is outside its supported validation scope')
    fixed = {'schemaVersion': 1, 'kind': 'pre-battle-boss-no-commit', 'runId': identifier,
        'stepId': identifier + ':step-1', 'scopeId': scope, 'gameDate': game_date,
        'reviewId': 'pre-battle-no-commit:' + identifier + ':step-1',
        'configuredOriginalCost': 40, 'releasedOriginalReservation': 40,
        'observedOriginalSpent': 0, 'verdict': 'no-commit', 'reviewedBy': 'root-agent'}
    if any(type(audit.get(k)) is not type(v) or audit[k] != v for k, v in fixed.items()) or _target(audit.get('target')) != target:
        raise ValueError('pre-battle review scope/step/verdict mismatch')
    if not isinstance(audit.get('reason'), str) or not audit['reason'].strip() or len(audit['reason']) > 2000:
        raise ValueError('pre-battle review requires independent bounded reasoning')
    checks = _object(audit.get('immutableProofChecks'), 'pre-battle immutable proof checks')
    for name in ('runtimeDeploymentIdentityReviewed', 'checkpointBeforeBossEntryReviewed',
                 'navigationBeforeFightBeforeClaimReviewed', 'completeIntervalReviewed',
                 'noBattleEntry', 'noRewardEntry', 'noSupplement', 'bossAliveAtStop'):
        if checks.get(name) is not True:
            raise ValueError('pre-battle independent proof check missing: ' + name)
    sources = _object(audit.get('sources'), 'pre-battle sources')
    supplied = sources.get('reports')
    expected_reports = {_safe_path(p) for p in report_paths}
    if not isinstance(supplied, list) or len(supplied) != len(expected_reports):
        raise ValueError('pre-battle review must bind every existing report mirror')
    report_sources = [_source(root, s, expected_reports) for s in supplied]
    if set(report_sources) != expected_reports or len(set(report_sources)) != len(report_sources):
        raise ValueError('pre-battle report mirror coverage mismatch')
    run_dir = _safe_path(root / 'logs/runs' / identifier)
    paths = {key: _source(root, sources.get(key), {_safe_path(run_dir / filename)}) for key, filename in
        (('result', 'result.json'), ('group', 'cultivation-group.json'), ('log', 'bettergi.log'),
         ('recording', 'recording.json'), ('video', 'genshin-window.mkv'))}
    backup = _safe_path(root / 'backups' / ('pre-battle-abort-source-' + identifier.split('-')[0]))
    for key, filename in (('operator', 'operator.js'), ('main', 'main.js'), ('autoBoss', 'AutoBossTask.cs'), ('dll', 'BetterGI.dll')):
        paths[key] = _source(root, sources.get(key), {_safe_path(backup / filename)})
    paths['runtimeIdentity'] = _source(root, sources.get('runtimeIdentity'))
    if not paths['runtimeIdentity'].is_relative_to(_safe_path(root / 'backups')) or paths['runtimeIdentity'].suffix != '.json':
        raise ValueError('pre-battle deployment identity requires an immutable retained backup')
    identity = _read(paths['runtimeIdentity'])
    if (identity.get('schemaVersion') != 1 or type(identity.get('schemaVersion')) is not int
            or identity.get('runId') != identifier or identity.get('gameDate') != game_date
            or identity.get('reviewedBy') != 'live-operator' or identity.get('sourceMatchesExecutedBinary') is not True):
        raise ValueError('pre-battle runtime deployment identity mismatch')
    identity_sources = _object(identity.get('sources'), 'runtime identity sources')
    for key in ('operator', 'main', 'autoBoss', 'dll'):
        _source(root, identity_sources.get(key), {paths[key]})
        if identity_sources[key] != sources[key]:
            raise ValueError('pre-battle runtime identity differs from reviewed source/DLL')
    result, recording = _read(paths['result']), _read(paths['recording'])
    authorization = _object(result.get('cultivationAuthorization'), 'pre-battle authorization')
    if (result.get('runId') != identifier or result.get('gameDate') != game_date or result.get('cultivationTarget') != target
            or result.get('outcome') != 'unknown' or result.get('executionOutcome') != 'cancelled'
            or result.get('cultivationLaunchAttempted') is not True or authorization.get('scopeId') != scope
            or authorization.get('originalResinCap') != 60 or type(authorization.get('originalResinCap')) is not int
            or authorization.get('condensedResinCap') != 0 or type(authorization.get('condensedResinCap')) is not int):
        raise ValueError('pre-battle source result/authorization mismatch')
    game_pid = _integer(recording.get('gamePid'), 1, 2**31-1, 'recording gamePid')
    closed = result.get('gamePidsClosedByGuard')
    if (not isinstance(closed, list) or closed != [game_pid] or any(type(pid) is not int for pid in closed)
            or identity.get('gamePid') != game_pid or type(identity.get('gamePid')) is not int
            or result.get('recording') != recording or recording.get('complete') is not True
            or recording.get('frameCoveragePassed') is not True or _safe_path(recording.get('file', '')) != paths['video']):
        raise ValueError('pre-battle native stop/recording identity mismatch')
    def number(value, minimum, maximum, label):
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError('invalid pre-battle ' + label)
        return float(value)
    number(recording.get('frameCoverage'), .99, 1, 'video coverage')
    duration = number(float(recording.get('probe', {}).get('format', {}).get('duration', 0)), 1, 3600, 'video duration')
    video_start = _timestamp(recording.get('startedAt'), 'pre-battle video start')
    video_stop = _timestamp(recording.get('stoppedAt'), 'pre-battle video stop')
    if not 0 <= (video_stop - video_start).total_seconds() - duration <= 5:
        raise ValueError('pre-battle video stop does not cover its encoded interval')
    finished = _timestamp(result.get('finishedAt'), 'pre-battle result finishedAt')
    if not video_stop <= finished or _timestamp(audit.get('reviewedAtUTC'), 'pre-battle reviewedAtUTC') < finished:
        raise ValueError('pre-battle review predates the completed stop evidence')
    _timestamp(identity.get('reviewedAtUTC'), 'runtime identity reviewedAtUTC')
    group = _read(paths['group'])
    projects = group.get('Projects')
    if group.get('Name') != 'AutoGameCultivation_' + identifier or not isinstance(projects, list) or len(projects) != 1:
        raise ValueError('pre-battle source group mismatch')
    settings = _object(projects[0].get('JsScriptSettingsObject'), 'pre-battle group settings')
    group_policy = _object(json.loads(settings.get('policyJson', 'null')), 'pre-battle group policy')
    if (settings.get('runId') != identifier or settings.get('mode') != 'execute'
            or _target(json.loads(settings.get('targetConfigJson', 'null'))) != target
            or group_policy.get('validationScopeId') != scope or group_policy.get('validationMode') is not True):
        raise ValueError('pre-battle group target/scope mismatch')
    before = None
    for report in reports:
        if report.get('status') != 'unknown' or len(report.get('steps', [])) != 1:
            raise ValueError('pre-battle requires one original unknown boss checkpoint')
        step = report['steps'][0]
        if (step.get('stepId') != fixed['stepId'] or step.get('type') != 'boss' or step.get('status') != 'unknown'
                or any(k in step for k in ('after', 'resinAfter', 'actualResinDelta', 'resultEvidence', 'finishedAt', 'completedRounds'))):
            raise ValueError('pre-battle review conflicts with after/commit evidence')
        parameters = _object(step.get('parameterEvidence'), 'pre-battle boss parameters')
        safe = {'SpecifyRunCount': True, 'RunCount': 1, 'UseFragileResin': False, 'UseTransientResin': False,
            'ReviveRetryCount': 0, 'ReturnToStatueAfterEachRound': False, 'RewardRecognitionEnabled': True}
        if any(type(parameters.get(k)) is not type(v) or parameters[k] != v for k, v in safe.items()):
            raise ValueError('pre-battle boss parameters allow refill/retry or multiple claims')
        if not step.get('bossName') or parameters.get('BossName') != step['bossName']:
            raise ValueError('pre-battle boss identity differs from checkpoint')
        _integer(parameters.get('Timeout'), 120, 180, 'pre-battle boss Timeout')
        policy = _object(report.get('policy'), 'pre-battle report policy')
        for candidate in (policy, group_policy):
            if (candidate.get('allowCrafting') is not False or candidate.get('allowRoutes') is not False
                    or candidate.get('allowWeekly') is not False or candidate.get('domainResin') != 'original'
                    or type(candidate.get('condensedResinBudget')) is not int or candidate['condensedResinBudget'] != 0):
                raise ValueError('pre-battle source could spend other resources')
        observation = _object(step.get('resinBefore'), 'pre-battle verified before')
        if observation.get('originalVerified') is not True or observation.get('mainUiRestored') is not True:
            raise ValueError('pre-battle before observation is not verified')
        _integer(observation.get('originalResin'), 40, 200, 'pre-battle original before')
        observed = _timestamp(observation.get('observedAt'), 'pre-battle original observedAt')
        started = _timestamp(step.get('startedAt'), 'pre-battle step startedAt')
        if not video_start <= observed <= started < video_stop or (started - observed).total_seconds() > 90:
            raise ValueError('pre-battle checkpoint/before outside reviewed recording')
        if before is not None and (observation != before or step != reports[0]['steps'][0]):
            raise ValueError('pre-battle original report mirrors disagree')
        before = observation
    operator = paths['operator'].read_text(encoding='utf-8-sig')
    main = paths['main'].read_text(encoding='utf-8-sig')
    boss = paths['autoBoss'].read_text(encoding='utf-8-sig')
    tokens = ('report.steps.push(step);', 'const checkpointPath=`record/${input.runId}.json`;',
        'await api.writeText(checkpointPath,checkpoint)', 'api.readText(checkpointPath)!==checkpoint')
    indexes = [operator.find(token) for token in tokens]
    entries = [m.start() for m in re.finditer(r'await api\.run(?:Boss|Domain|Crafting)\(', operator)]
    if (any(i < 0 for i in indexes) or indexes != sorted(indexes) or not entries or min(entries) <= indexes[-1]
            or 'dispatcher.RunAutoBossTask(param,cts.Token)' not in main):
        raise ValueError('pre-battle retained JS checkpoint/resource contract mismatch')
    loop_start = boss.find('private async Task RunBossLoop()')
    loop_end = boss.find('\n    private ', loop_start + 1)
    loop = boss[loop_start:loop_end] if loop_start >= 0 and loop_end > loop_start else ''
    phase_tokens = ('await NavigateToBoss();', 'await RunAutoFight();', 'await NavigateToReward();', 'await TakeReward();')
    phase_indexes = [loop.find(token) for token in phase_tokens]
    if (any(i < 0 for i in phase_indexes) or phase_indexes != sorted(phase_indexes)
            or any(loop.count(token) != 1 for token in phase_tokens)
            or not re.search(r'private\s+async\s+Task\s+RunAutoFight\(\)\s*\{\s*_logger\.LogInformation\("\{Name\}：执行战斗策略",\s*Name\);', boss)):
        raise ValueError('pre-battle source lacks unconditional fight-entry marker and ordered phases')
    log = paths['log'].read_text(encoding='utf-8-sig')
    if (not re.search(r'自动首领讨伐[^\n]*[：:]前往', log) or '主窗体退出' not in log
            or any(token in log for token in ('执行战斗策略', '已进入征讨之花领奖界面', '首领奖励领取成功',
                '本轮奖励识别结果', '领奖成功', '领取奖励成功'))
            or re.search(r'已使用[^\n]*(?:脆弱|须臾|树脂)', log)):
        raise ValueError('pre-battle log contains battle/claim/refill or lacks navigation/stop evidence')
    frame_dir = _safe_path(root / 'tests/.artifacts' / ('no-commit-audit-' + identifier.split('-')[0]))
    paths['metadata'] = _source(root, sources.get('metadata'), {_safe_path(frame_dir / 'review-metadata.json')})
    metadata = _read(paths['metadata'])
    samples = sources.get('frames')
    if not isinstance(samples, list) or len(samples) != 9:
        raise ValueError('pre-battle requires all nine reviewed contact sheets')
    frames = [_source(root, sample, {_safe_path(frame_dir / f'sheet-{index:02}.png')})
              for index, sample in enumerate(samples, 1)]
    offset = _integer(metadata.get('RequestedOffsetStart'), 0, 3599, 'pre-battle interval start')
    count = _integer(metadata.get('ReviewedSampleCount'), 1, 3600, 'pre-battle real samples')
    if (metadata.get('RunId') != identifier or metadata.get('SampleFps') != 1 or type(metadata.get('SampleFps')) is not int
            or metadata.get('ContactSheets') != 9 or type(metadata.get('ContactSheets')) is not int
            or metadata.get('PaddedCellsExcluded') is not True or count != int(duration) - offset
            or math.ceil(count / 20) != 9 or abs(number(metadata.get('RecordingDuration'), 1, 3600, 'review duration') - duration) > .001
            or metadata.get('BalanceAtStop') != 'not_observed'
            or metadata.get('NoRefillOrRewardUiObserved') is not True or metadata.get('NoBattleStrategyOrClaimEntryObserved') is not True
            or offset > (started - video_start).total_seconds()
            or metadata.get('ObservedBeforeOriginal') != before['originalResin']
            or _timestamp(metadata.get('BeforeObservedAt'), 'review before observedAt') != _timestamp(before['observedAt'], 'source before observedAt')):
        raise ValueError('pre-battle video review interval/sample/checkpoint mismatch')
    first = number(metadata.get('FirstEncodedPts'), offset, offset + .2, 'first encoded PTS')
    last = number(metadata.get('LastEncodedPts'), duration - .2, duration, 'last encoded PTS')
    number(metadata.get('MaximumEncodedGapSeconds'), .001, .2, 'encoded frame gap')
    encoded = _integer(metadata.get('EncodedFrames'), 1, 54000, 'review encoded frame count')
    fps = _integer(recording.get('settings', {}).get('frameRate'), 15, 15, 'recording fps')
    if not .98 <= encoded / ((last - first) * fps) <= 1.02:
        raise ValueError('pre-battle encoded interval continuity inconsistent')
    file_hashes = metadata.get('FileHashes')
    required_hashes = {paths['video'], paths['log'], *report_sources, *frames}
    if not isinstance(file_hashes, list) or len(file_hashes) != len(required_hashes):
        raise ValueError('pre-battle metadata lacks original evidence hash coverage')
    supplied_hashes = set()
    for item in file_hashes:
        item = _object(item, 'pre-battle metadata file hash')
        path = _safe_path(item.get('Path', ''))
        if path not in required_hashes or path in supplied_hashes or item.get('Hash', '').lower() != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('pre-battle metadata hash/path mismatch')
        supplied_hashes.add(path)
    return {'kind': fixed['kind'], 'reviewId': audit['reviewId'], 'stepId': fixed['stepId'], 'path': str(audit_path),
        'reviewSha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(), 'releasedOriginalReservation': 40,
        'observedOriginalSpent': 0, 'historicalOutcomeRetained': 'unknown', 'balanceAfterStop': 'not_observed'}


def _game_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid validation gameDate')
    if datetime.strptime(value, '%Y-%m-%d').date().isoformat() != value:
        raise ValueError('invalid validation gameDate')
    return value


def _authorized_game_date(value: str) -> str:
    authorized = _timestamp(value, 'authorizedAtUTC')
    return (authorized.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).date().isoformat()


def _continuation(root: Path, receipt: dict, game_date: str) -> dict:
    """Bind a dated explicit resume to an immutable receipt snapshot, never a new cap.

    The independently written snapshot preserves the assigned prefix at approval.
    Only assignedRunIds may subsequently grow in the working receipt; neither
    approval artifact nor snapshot is rewritten by the runner.
    """
    path = _safe_path(root / 'state/cultivation-validation-continuations' / (game_date + '.json'))
    approval = _read(path)
    fixed = {'schemaVersion': 1, 'kind': 'initial-validation-continuation',
             'scopeId': receipt['scopeId'], 'gameDate': game_date,
             'originalResinCap': receipt['originalResinCap'], 'condensedResinCap': 0}
    if (set(approval) != set(fixed) | {'target', 'authorizedAtUTC', 'authorizationSource', 'parentReceipt'}
            or any(type(approval.get(key)) is not type(value) or approval[key] != value for key, value in fixed.items())
            or _target(approval.get('target')) != _target(receipt['target'])
            or game_date <= receipt['gameDate'] or _authorized_game_date(approval.get('authorizedAtUTC')) != game_date):
        raise ValueError('initial-validation continuation date/target/scope/cap mismatch')
    provenance = _object(approval.get('authorizationSource'), 'continuation authorizationSource')
    instruction = provenance.get('instruction')
    if (set(provenance) != {'kind', 'recordedBy', 'instruction'}
            or provenance.get('kind') != 'explicit-user-resume' or provenance.get('recordedBy') != 'root-agent'
            or not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 6000):
        raise ValueError('continuation requires explicit user resume provenance')
    parent = _object(approval.get('parentReceipt'), 'continuation parentReceipt')
    if set(parent) != {'path', 'sha256'}:
        raise ValueError('invalid continuation parentReceipt')
    snapshot_path = _source(root, parent)
    if snapshot_path.parent != _safe_path(root / 'state/cultivation-authorization-snapshots'):
        raise ValueError('continuation requires an immutable authorization snapshot')
    snapshot = _read(snapshot_path)
    if ({key: value for key, value in snapshot.items() if key != 'assignedRunIds'}
            != {key: value for key, value in receipt.items() if key != 'assignedRunIds'}):
        raise ValueError('continuation parent receipt changed')
    prefix = snapshot.get('assignedRunIds')
    if not isinstance(prefix, list):
        raise ValueError('invalid continuation assigned prefix')
    for identifier in prefix:
        _run_id(identifier)
    if len(prefix) != len(set(prefix)) or receipt['assignedRunIds'][:len(prefix)] != prefix:
        raise ValueError('continuation assigned prefix changed')
    return {'gameDate': game_date, 'path': path.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'parentReceipt': copy.deepcopy(parent)}


def _daily_receipt(root: Path, config: dict, game_date: str) -> tuple[Path, dict]:
    scope = config['policy'].get('validationScopeId')
    if not isinstance(scope, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', scope):
        raise ValueError('daily authorization scope missing')
    path = _safe_path(root / 'state/cultivation-daily-authorizations' / (scope + '.json'))
    receipt = _read(path)
    keys = {'schemaVersion', 'scopeId', 'gameDate', 'purpose', 'target', 'originalResinCap',
            'condensedResinCap', 'authorizedAtUTC', 'authorizationSource', 'parentReceipt', 'runtimeIdentity', 'assignedRunIds'}
    if (set(receipt) != keys or type(receipt.get('schemaVersion')) is not int or receipt['schemaVersion'] != 1
            or receipt.get('scopeId') != scope or receipt.get('purpose') != 'daily-original-domain'
            or _game_date(receipt.get('gameDate')) != game_date
            or _authorized_game_date(receipt.get('authorizedAtUTC')) != game_date
            or _target(receipt.get('target')) != _target(config['target'])):
        raise ValueError('daily authorization date/target/purpose mismatch')
    _integer(receipt.get('originalResinCap'), 0, 200, 'daily originalResinCap')
    _integer(receipt.get('condensedResinCap'), 0, 0, 'daily condensedResinCap')
    provenance = _object(receipt.get('authorizationSource'), 'daily authorizationSource')
    instruction = provenance.get('instruction')
    if (set(provenance) != {'kind', 'recordedBy', 'instruction'}
            or provenance.get('kind') != 'explicit-user-daily-original' or provenance.get('recordedBy') != 'root-agent'
            or not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 6000):
        raise ValueError('daily authorization requires direct user instruction provenance')
    parent = _object(receipt.get('parentReceipt'), 'daily parentReceipt')
    if set(parent) != {'path', 'sha256', 'scopeId'}:
        raise ValueError('daily parent snapshot reference malformed')
    snapshot = _source(root, {key: parent[key] for key in ('path', 'sha256')})
    if snapshot.parent != _safe_path(root / 'state/cultivation-authorization-snapshots'):
        raise ValueError('daily parent must be an immutable authorization snapshot')
    old = _read(snapshot)
    # Bind the original receipt without rewriting its assigned IDs or transferring
    # old unknowns/success into the independent new grant.
    if (old.get('scopeId') != parent['scopeId'] or old.get('purpose') != 'initial-validation'
            or old.get('scopeId') == scope or _target(old.get('target')) != config['target']
            or snapshot.read_bytes() != (root / 'state/cultivation-authorization.json').read_bytes()):
        raise ValueError('daily parent receipt changed or scope was reused')
    assigned = receipt['assignedRunIds']
    if not isinstance(assigned, list) or len(assigned) != len(set(assigned)):
        raise ValueError('daily assignedRunIds malformed')
    for identifier in assigned:
        _run_id(identifier)
    if set(assigned) & set(old.get('assignedRunIds', [])):
        raise ValueError('daily scope cannot inherit initial-validation run IDs')
    identity = _object(receipt.get('runtimeIdentity'), 'daily runtimeIdentity')
    if set(identity) != {'domainSource', 'engineDll'}:
        raise ValueError('daily runtime identity requires protected domain source and engine DLL')
    if identity['domainSource']['path'] != 'src/bettergi-custom/BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.SingleOriginal20.cs':
        raise ValueError('daily identity is not the protected domain source')
    if identity['engineDll']['path'] != 'BetterGI_custom/BetterGI.dll':
        raise ValueError('daily identity is not the configured BetterGI engine DLL')
    return path, receipt


def _daily_runtime(root: Path, receipt: dict) -> tuple[dict, dict | None]:
    """Immutable reader and narrow exit-classifier epochs preserve historical identities."""
    original = receipt['runtimeIdentity']
    path = root / 'state/cultivation-daily-runtime-transitions' / (receipt['scopeId'] + '.json')
    exit_path = root / 'state/cultivation-daily-exit-transitions' / (receipt['scopeId'] + '.json')
    exit_change = _read(exit_path) if os.path.lexists(exit_path) else None
    if not os.path.lexists(path):
        if exit_change is not None:
            raise ValueError('exit classifier epoch requires its immutable reader epoch')
        _source(root, original['domainSource'])
        _source(root, original['engineDll'])
        return original, None
    transition = _read(path)
    fixed = {'schemaVersion': 1, 'kind': 'reader-only-runtime-transition', 'scopeId': receipt['scopeId'],
             'gameDate': receipt['gameDate'], 'reviewedBy': 'root-agent', 'priorRuntimeIdentity': original}
    if any(type(transition.get(k)) is not type(v) or transition[k] != v for k, v in fixed.items()):
        raise ValueError('daily runtime transition scope/prior identity mismatch')
    reason = transition.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValueError('daily runtime transition lacks bounded source-review reason')
    effective = _timestamp(transition.get('effectiveAtUTC'), 'runtime effectiveAtUTC')
    if _authorized_game_date(transition['effectiveAtUTC']) != receipt['gameDate'] or effective > datetime.now(timezone.utc):
        raise ValueError('daily runtime transition time outside current grant')
    snapshot = _source(root, transition.get('parentReceipt'))
    if snapshot.parent != root / 'state/cultivation-authorization-snapshots':
        raise ValueError('daily runtime transition receipt snapshot misplaced')
    parent = _read(snapshot)
    if ({k: v for k, v in parent.items() if k != 'assignedRunIds'} != {k: v for k, v in receipt.items() if k != 'assignedRunIds'}
            or not isinstance(parent.get('assignedRunIds'), list)
            or receipt['assignedRunIds'][:len(parent['assignedRunIds'])] != parent['assignedRunIds']):
        raise ValueError('daily runtime transition grant or assigned prefix changed')
    for identifier in parent['assignedRunIds']:
        old_result = _read(root / 'logs/runs' / _run_id(identifier) / 'result.json')
        if (old_result.get('runId') != identifier or old_result.get('gameStillRunning') is not False
                or _timestamp(old_result.get('finishedAt'), 'pre-cutover run finish') > effective):
            raise ValueError('daily runtime transition predates closure of an assigned run')
    backup = _source(root, transition.get('oldDllBackup'))
    if not backup.is_relative_to(root / 'backups') or transition['oldDllBackup']['sha256'] != original['engineDll']['sha256']:
        raise ValueError('daily runtime transition old DLL was not preserved')
    current = _object(transition.get('currentRuntimeIdentity'), 'runtime current identity')
    if (set(current) != set(original) or current.get('domainSource') != original['domainSource']
            or current.get('engineDll', {}).get('path') != original['engineDll']['path']
            or current['engineDll'].get('sha256') == original['engineDll']['sha256']):
        raise ValueError('daily runtime transition changed protected domain source or did not change DLL')
    if exit_change is None:
        _source(root, original['domainSource'])
        _source(root, current['engineDll'])
    prefix = 'src/bettergi-custom/BetterGenshinImpact/'
    allowed = {prefix + 'Core/Script/Dependence/Dispatcher.cs',
               prefix + 'GameTask/Common/Job/BackpackInventoryEvidence.cs',
               prefix + 'GameTask/Common/Job/ReadBackpackInventoryTask.cs'}
    changes = transition.get('reviewedSourceChanges')
    if not isinstance(changes, list) or not changes or len(changes) > len(allowed):
        raise ValueError('daily runtime transition source manifest missing')
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'path', 'before', 'after'} or change['path'] not in allowed or change['path'] in seen:
            raise ValueError('daily runtime transition source change is outside reader-only whitelist')
        seen.add(change['path'])
        after = _source(root, change['after'])
        if after != _safe_path(root / change['path']):
            raise ValueError('daily runtime transition source after path mismatch')
        if change['before'] is None:
            if not Path(change['path']).name.startswith(('BackpackInventory', 'ReadBackpack')):
                raise ValueError('daily runtime transition cannot add a dispatcher')
        else:
            before = _source(root, change['before'])
            if not before.is_relative_to(root / 'backups') or change['before']['sha256'] == change['after']['sha256']:
                raise ValueError('daily runtime transition source before not backed up or unchanged')
    if prefix + 'Core/Script/Dependence/Dispatcher.cs' not in seen:
        raise ValueError('daily runtime transition must bind the actual dispatcher change')
    metadata = {'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'effectiveAtUTC': transition['effectiveAtUTC'], 'currentRuntimeIdentity': current,
                     'priorRuntimeIdentity': original, 'parentReceipt': transition['parentReceipt'],
                     'oldDllBackup': transition['oldDllBackup']}
    if exit_change is not None:
        latest, exit_metadata = _daily_exit_epoch(root, receipt, current, metadata, exit_path, exit_change)
        metadata['exitTransition'] = exit_metadata
        return latest, metadata
    return current, metadata


def _classifier_parts(content: bytes):
    marker = b'internal static bool HasProtectedLoadingBackground(ImageRegion capture)'
    start = content.find(marker)
    if start < 0 or content.find(marker, start + 1) >= 0:
        raise ValueError('exit classifier source method missing or duplicated')
    opening = content.find(b'{', start)
    depth = 0
    for end in range(opening, len(content)):
        if content[end:end+1] == b'{': depth += 1
        elif content[end:end+1] == b'}':
            depth -= 1
            if depth == 0:
                return content[:opening], content[opening:end+1], content[end+1:]
    raise ValueError('exit classifier source method malformed')


def _daily_exit_epoch(root, receipt, previous, reader_metadata, path, change):
    fixed = {'schemaVersion': 1, 'kind': 'dark-loading-classifier-fix', 'scopeId': receipt['scopeId'],
             'gameDate': receipt['gameDate'], 'reviewedBy': 'root-agent', 'priorRuntimeIdentity': previous}
    if any(type(change.get(k)) is not type(v) or change[k] != v for k,v in fixed.items()):
        raise ValueError('exit classifier epoch scope/prior mismatch')
    prior_ref = change.get('previousTransition', {})
    prior_path = _source(root, prior_ref)
    if prior_path != root / reader_metadata['path'] or prior_ref.get('sha256') != reader_metadata['sha256']:
        raise ValueError('exit classifier epoch did not bind the immutable reader transition')
    effective = _timestamp(change.get('effectiveAtUTC'), 'exit epoch effectiveAtUTC')
    if (effective <= _timestamp(reader_metadata['effectiveAtUTC'], 'reader cutover')
            or effective > datetime.now(timezone.utc) or _authorized_game_date(change['effectiveAtUTC']) != receipt['gameDate']
            or not isinstance(change.get('reason'), str) or not change['reason'].strip() or len(change['reason']) > 2000):
        raise ValueError('exit classifier epoch cutover/review invalid')
    snapshot = _source(root, change.get('parentReceipt'))
    parent = _read(snapshot)
    if (snapshot.parent != root / 'state/cultivation-authorization-snapshots'
            or {k:v for k,v in parent.items() if k!='assignedRunIds'} != {k:v for k,v in receipt.items() if k!='assignedRunIds'}
            or not isinstance(parent.get('assignedRunIds'),list)
            or receipt['assignedRunIds'][:len(parent['assignedRunIds'])] != parent['assignedRunIds']):
        raise ValueError('exit classifier epoch receipt prefix changed')
    for identifier in parent['assignedRunIds']:
        prior = _read(root/'logs/runs'/_run_id(identifier)/'result.json')
        if prior.get('gameStillRunning') is not False or _timestamp(prior.get('finishedAt'),'pre-exit-cutover finish')>effective:
            raise ValueError('exit classifier epoch changed during an assigned run')
    dll = _source(root, change.get('oldDllBackup'))
    old_source = _source(root, change.get('oldDomainSourceBackup'))
    if (not dll.is_relative_to(root/'backups') or not old_source.is_relative_to(root/'backups')
            or change['oldDllBackup']['sha256'] != previous['engineDll']['sha256']
            or change['oldDomainSourceBackup']['sha256'] != previous['domainSource']['sha256']):
        raise ValueError('exit classifier epoch prior source/DLL not preserved')
    current = _object(change.get('currentRuntimeIdentity'),'exit current identity')
    if (set(current) != set(previous) or any(current.get(k,{}).get('path')!=previous[k]['path'] for k in previous)
            or any(current[k].get('sha256')==previous[k]['sha256'] for k in previous)):
        raise ValueError('exit classifier epoch must explicitly change domain source and engine DLL')
    _source(root,current['engineDll']); after_source = _source(root,current['domainSource'])
    changes = change.get('reviewedSourceChanges')
    expected_change = {'path': previous['domainSource']['path'], 'before': change['oldDomainSourceBackup'], 'after': current['domainSource']}
    if changes != [expected_change]:
        raise ValueError('exit classifier epoch changed files outside the protected partial predicate')
    before_parts, after_parts = _classifier_parts(old_source.read_bytes()), _classifier_parts(after_source.read_bytes())
    if before_parts[0]!=after_parts[0] or before_parts[2]!=after_parts[2] or before_parts[1]==after_parts[1]:
        raise ValueError('exit classifier fix altered code outside loading classification')
    return current, {'path': path.relative_to(root).as_posix(), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'effectiveAtUTC':change['effectiveAtUTC'], 'priorRuntimeIdentity':previous, 'currentRuntimeIdentity':current,
        'oldDomainSourceBackup':change['oldDomainSourceBackup'], 'oldDllBackup':change['oldDllBackup'],
        'previousTransition':prior_ref,'parentReceipt':change['parentReceipt']}


def _runtime_sources(root, identity, receipt, transition):
    """Metadata retains production paths; historical bytes are checked in real backups."""
    source, dll = identity['domainSource'], identity['engineDll']
    if transition:
        exit_epoch = transition.get('exitTransition')
        if exit_epoch and identity != exit_epoch['currentRuntimeIdentity']:
            if source != exit_epoch['priorRuntimeIdentity']['domainSource']:
                raise ValueError('historical runtime domain source is not the preserved era')
            source = exit_epoch['oldDomainSourceBackup']
            if identity == exit_epoch['priorRuntimeIdentity']: dll = exit_epoch['oldDllBackup']
        if identity == receipt['runtimeIdentity']: dll = transition['oldDllBackup']
    _source(root,source); _source(root,dll)


def _historical_runtime(prior: dict, receipt: dict, transition: dict | None) -> dict:
    if transition is None:
        return receipt['runtimeIdentity']
    started = _timestamp(prior.get('triggeredAt'), 'prior triggeredAt')
    exit_epoch = transition.get('exitTransition')
    if exit_epoch and started >= _timestamp(exit_epoch['effectiveAtUTC'],'exit cutover'):
        return exit_epoch['currentRuntimeIdentity']
    return (transition['currentRuntimeIdentity'] if started >= _timestamp(transition['effectiveAtUTC'], 'cutover')
            else transition['priorRuntimeIdentity'])


def _daily_verified_run(root: Path, bgi: Path, identifier: str, prior: dict, report: dict, *, mirrors=None) -> bool:
    try:
        from cultivation import verify_cultivation_report
    except ImportError:
        from scripts.cultivation import verify_cultivation_report
    observation = prior.get('cultivation')
    steps = report.get('steps', [])
    if (not isinstance(observation, dict) or observation.get('reportVerified') is not True
            or observation.get('claimedStatus') != 'success' or report.get('status') != 'success'
            or not steps or observation.get('verifiedStepIds') != [step['stepId'] for step in steps]):
        return False
    event = {'runId': identifier, 'mode': 'execute', 'status': 'success', 'claimedStatus': 'success',
             'evidenceVerified': True, 'readOnly': False, 'reportRelativePath': f'record/{identifier}.json'}
    checked = verify_cultivation_report(event, bgi, identifier, 'execute', report['target'],
                                      root / 'logs/runs' / identifier, expected_policy=report['policy'])
    if checked['status'] != 'success' or checked['cultivation'] != observation:
        return False
    # The runner archives the verifier's canonical public report. Its top-level
    # inventory intentionally drops raw guide OCR provenance after verification.
    # Compare the entire archive to that exact canonical report, preserving every
    # paid-step/count/resin field; a raw durable checkpoint is also a valid mirror.
    if mirrors is not None and any(mirror != report and mirror != checked['report'] for mirror in mirrors):
        return False
    # A resource observation alone cannot certify the native domain's exit.
    # Only the native success event in this run's exact step interval qualifies.
    return _daily_native_exit(root / 'logs/runs' / identifier / 'bettergi.log', steps)


def _daily_native_exit(log_path: Path, steps: list) -> bool:
    if not log_path.is_file() or log_path.stat().st_size > 20 * 1024 * 1024:
        return False
    markers = []
    latest_header = None
    for line in log_path.read_text(encoding='utf-8-sig').splitlines():
        header = re.match(r'^\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]', line.strip())
        if header:
            latest_header = tuple(int(value) for value in header.groups())
        if '单次原粹20提交后已安全退出到世界双帧，native不宣称已消费或发奖，交外层库存/余额验收' in line:
            if latest_header is None:
                return False
            markers.append(latest_header)
    if len(markers) != len(steps):
        return False
    for step, marker in zip(steps, markers):
        start = _timestamp(step['startedAt'], 'daily step startedAt').astimezone(timezone(timedelta(hours=8)))
        stop = _timestamp(step['finishedAt'], 'daily step finishedAt').astimezone(start.tzinfo)
        at = start.replace(hour=marker[0], minute=marker[1], second=marker[2], microsecond=marker[3] * 1000)
        if not any(start <= at + timedelta(days=offset) <= stop for offset in (-1, 0, 1)):
            return False
        parameters = step.get('parameterEvidence', {})
        if (parameters.get('RequireZhongliShieldCast') is not True or parameters.get('CombatOnly') is not False
                or parameters.get('ResinPriorityList') != ['原粹树脂']):
            return False
    return True


def _review_run_sources(root, bgi, identifier, sources, mode, target):
    """Hash-bind raw and canonical mirrors, then independently verify the raw report."""
    try:
        from cultivation import verify_cultivation_report
    except ImportError:
        from scripts.cultivation import verify_cultivation_report
    directory = root / 'logs/runs' / _run_id(identifier)
    paths = {}
    for key, filename in (('result', 'result.json'), ('archiveReport', 'cultivation-report.json'),
                          ('log', 'bettergi.log'), ('recording', 'recording.json'), ('video', 'genshin-window.mkv')):
        paths[key] = _source(root, sources.get(key), {_safe_path(directory / filename)})
    paths['rawReport'] = _source(root, sources.get('rawReport'),
        {_safe_path(bgi / 'User/JsScript/AutoGameCultivation/record' / (identifier + '.json'))})
    prior, raw, archive = (_read(paths[key]) for key in ('result', 'rawReport', 'archiveReport'))
    if prior.get('runId') != identifier or prior.get('executionOutcome') != 'exited' or (mode == 'execute' and prior.get('gameStillRunning') is not False):
        raise ValueError('reconciliation run did not finish with its game closed')
    event = {'runId': identifier, 'mode': mode, 'status': raw.get('status'), 'claimedStatus': raw.get('status'),
             'evidenceVerified': True, 'readOnly': mode == 'scan', 'reportRelativePath': f'record/{identifier}.json'}
    checked = verify_cultivation_report(event, bgi, identifier, mode, target, directory, expected_policy=raw.get('policy'))
    if (checked.get('cultivation') is None or checked['cultivation'] != prior.get('cultivation')
            or checked.get('report') != archive):
        raise ValueError('reconciliation raw/canonical/result report verification mismatch')
    recording = _read(paths['recording'])
    coverage = recording.get('frameCoverage')
    if (recording.get('complete') is not True or recording.get('frameCoveragePassed') is not True
            or type(coverage) not in (int, float) or not .70 <= coverage <= 1
            or _safe_path(recording.get('file', '')) != paths['video']):
        raise ValueError('reconciliation recording missing or insufficient')
    if not _timestamp(recording.get('startedAt'), 'video start') <= _timestamp(raw.get('startedAt'), 'report start') <= _timestamp(raw.get('finishedAt'), 'report finish') <= _timestamp(recording.get('stoppedAt'), 'video stop'):
        raise ValueError('reconciliation recording does not cover report interval')
    return prior, raw, paths


def _prelaunch_before_trigger(observed_at, triggered_at, launched_at):
    """Runner ISO timestamps without fractions declare one-second resolution.

    A high-resolution zero-process observation may fall after the serialized
    trigger's lower bound. It must remain inside that same second and strictly
    before even the lower bound of the actual launch timestamp.
    """
    observed = _timestamp(observed_at, 'prelaunch observedAt')
    triggered = _timestamp(triggered_at, 'scan triggeredAt')
    launched = _timestamp(launched_at, 'scan launchedAt')
    whole_seconds = isinstance(triggered_at, str) and bool(re.search(r'T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$', triggered_at))
    before_trigger = observed < triggered + timedelta(seconds=1) if whole_seconds else observed <= triggered
    return before_trigger and observed < launched


def _paid_exit_observation(root, audit, raw, paths, transition):
    """Human-reviewed immediate balance and real stage frames; never synthesize old after."""
    if not transition or not transition.get('exitTransition'):
        raise ValueError('paid exit recovery requires the explicit classifier-fix epoch')
    step = raw['steps'][0]
    if (step.get('after') is not None or step.get('resinAfter') is not None or step.get('actualResinDelta') is not None
            or step.get('reason') != '单次原粹20提交后安全退出未获双帧世界证明；结果未知，禁止再次领奖或普通退出兜底'):
        raise ValueError('paid exit recovery supports only the unchanged specific protected exit failure')
    before = step.get('resinBefore', {})
    start, finish = _timestamp(step['startedAt'],'exit step start'), _timestamp(step['finishedAt'],'exit step finish')
    before_at = _timestamp(before.get('observedAt'),'exit before resin')
    if (before.get('originalVerified') is not True or before.get('condensedVerified') is not True
            or before.get('mainUiRestored') is not True or before.get('condensedResin')!=0
            or not 0 <= (start-before_at).total_seconds()<=120):
        raise ValueError('paid exit recovery lacks actual fresh verified pre-claim resin')
    count_before = _integer(before.get('originalResin'),20,200,'exit original before')
    parameters = step.get('parameterEvidence',{})
    if (parameters.get('RequireZhongliShieldCast') is not True or parameters.get('CombatOnly') is not False
            or parameters.get('ResinPriorityList') != ['原粹树脂']):
        raise ValueError('paid exit recovery actual protected parameter contract missing')
    log = paths['log'].read_text(encoding='utf-8-sig')
    submit = '单次原粹20提交请求已发送：Original20第一行和独立使用按钮双帧；singleClick=True'
    classic = '受保护单次领奖：经典结果页奖励仅作观察，paid状态仍待外层库存/余额，不累加native成功轮数'
    if (log.count(submit)!=1 or log.count(classic)!=1 or log.index(submit)>log.index(classic)
            or '单次原粹20提交后已安全退出到世界双帧' in log):
        raise ValueError('paid exit recovery submit/classic/failed-native-exit provenance mismatch')
    # Cross-bind the exact original API reading; visual paid observation is an
    # additional source with its own clock, not a fabricated same-run API delta.
    observations = []
    for line in log.splitlines():
        if '[CULTIVATION_RESIN_OBSERVATION]' in line:
            try:
                value=json.loads(line.split('[CULTIVATION_RESIN_OBSERVATION]',1)[1].strip())
                if isinstance(value,str): value=json.loads(value)
                observations.append(value)
            except (ValueError,TypeError): raise ValueError('paid exit recovery old resin log malformed')
    if not any(all(value.get(k)==before.get(k) for k in ('originalResin','condensedResin','observedAt','originalVerified','condensedVerified','mainUiRestored')) for value in observations):
        raise ValueError('paid exit recovery pre-claim report/log resin mismatch')
    recording = _read(paths['recording'])
    video_start = _timestamp(recording.get('startedAt'),'exit video start')
    video_stop = _timestamp(recording.get('stoppedAt'),'exit video stop')
    def frame_ref(frame, *, require_time=False):
        actual = _source(root,frame.get('frame'))
        if (not (actual.is_relative_to(root/'tests/.artifacts') or actual.is_relative_to(root/'logs/diagnostics'))
                or actual.suffix.lower()!='.png'):
            raise ValueError('paid exit recovery stage frame outside retained artifacts')
        offset=frame.get('videoOffsetSeconds')
        if type(offset) not in (int,float) or not math.isfinite(offset) or offset<0:
            raise ValueError('paid exit recovery stage video offset invalid')
        projected=video_start+timedelta(seconds=offset)
        if not video_start<=projected<=video_stop or not start<=projected<=finish:
            raise ValueError('paid exit recovery frame offset outside original step/video')
        if require_time:
            at=_timestamp(frame.get('observedAtUTC'),'reviewed paid frame time')
            if abs((at-projected).total_seconds())>2 or not start<=at<=finish:
                raise ValueError('paid exit recovery paid frame timestamp not bound to recorded video')
            return actual,at
        return actual,projected
    paid=_object(audit.get('immediatePaidObservation'),'immediate classic paid observation')
    if (paid.get('source')!='reviewed-classic-reward-frame' or paid.get('reviewedBy')!='root-agent'
            or paid.get('videoSha256')!=audit['oldSources']['video']['sha256'] or paid.get('condensedResin')!=0):
        raise ValueError('paid exit recovery immediate observation provenance mismatch')
    _,paid_at=frame_ref(paid,require_time=True)
    count=_integer(paid.get('originalResin'),0,200,'observed immediate original resin')
    if not 18<=count_before-count<=20:
        raise ValueError('paid exit recovery observed balance does not support one original20')
    replay_path=_source(root,audit.get('exitClassifierReplay'))
    replay=_read(replay_path)
    latest=transition['exitTransition']['currentRuntimeIdentity']
    manifest=_read(_source(root,audit.get('classifierSourceManifest')))
    if (manifest.get('candidateDll',{}).get('sha256','').lower()!=latest['engineDll']['sha256']
            or manifest.get('sourceChanges',[{}])[0].get('afterSha256','').lower()!=latest['domainSource']['sha256']
            or manifest.get('privateFrameClassificationArtifact',{}).get('sha256','').lower()!=audit['exitClassifierReplay']['sha256']
            or manifest.get('validation',{}).get('selectedRegressionFailed')!=0):
        raise ValueError('paid exit recovery classifier source/test manifest mismatch')
    if (replay.get('schemaVersion')!=1 or replay.get('sourceOnlyClassifier')!='HasProtectedLoadingBackground'
            or replay.get('runId')!=raw['runId'] or replay.get('noRuntimeCompletionInference') is not True
            or replay.get('validation',{}).get('productionClassifierUnitAssertionsPassed') is not True):
        raise ValueError('paid exit recovery classifier replay is not from the reviewed fixed runtime')
    loading,world=[],[]
    for recorded in replay.get('frames',[]):
        private=_safe_path(recorded.get('privatePath',''))
        if not private.is_relative_to(root): raise ValueError('paid exit recovery replay escaped workspace')
        frame={'frame':{'path':private.relative_to(root).as_posix(),'sha256':recorded.get('sha256','').lower()},
               'videoOffsetSeconds':recorded.get('videoOffsetSeconds'),'loadingBackground':recorded.get('afterBackgroundClassifierExpected')}
        if recorded.get('nativeCaptureTimestamp') is not None:
            raise ValueError('paid exit recovery replay falsely substitutes a native capture timestamp')
        if frame['loadingBackground'] is True: loading.append(frame)
        elif frame['loadingBackground'] is False: world.append(frame)
    if not isinstance(loading,list) or not isinstance(world,list) or len(loading)<2 or len(world)<2:
        raise ValueError('paid exit recovery needs two actual loading and two outside-world stage frames')
    stages,seen=[],set()
    for expected,frames in ((True,loading),(False,world)):
        for frame in frames:
            path,at=frame_ref(frame)
            if path in seen or frame.get('loadingBackground') is not expected:
                raise ValueError('paid exit recovery stage classifier result or independent frame mismatch')
            seen.add(path);stages.append(at)
    if (stages!=sorted(stages) or not paid_at<stages[0] or stages[len(loading)]<=stages[len(loading)-1]
            or (stages[-1]-stages[0]).total_seconds()>30):
        raise ValueError('paid exit recovery loading/world chain ordering or 30-second deadline mismatch')
    outside = audit.get('outsideWorldFrames',[])
    if not isinstance(outside,list) or len(outside)<2:
        raise ValueError('paid exit recovery outside-world frame review missing')
    outside_seen=set()
    for frame in outside:
        actual,at=frame_ref(frame)
        if (actual not in seen or actual in outside_seen or frame.get('outsideWorldObserved') is not True
                or frame.get('reviewedBy')!='root-agent' or at<stages[len(loading)]):
            raise ValueError('paid exit recovery outside-world frame review not bound to classifier replay')
        outside_seen.add(actual)
    return count,paid_at


def _paid_inventory_reconciliation(root, bgi, receipt, identifier, prior, report, transition):
    """A bounded independent review permits new claims, never refunds or replays this unknown."""
    path = root / 'state/cultivation-paid-reconciliations' / (identifier + '.json')
    exit_path = root / 'state/cultivation-paid-exit-recoveries' / (identifier + '.json')
    exit_recovery = os.path.lexists(exit_path)
    if exit_recovery:
        if os.path.lexists(path): raise ValueError('unknown attempt has multiple incompatible reconciliation reviews')
        path = exit_path
    elif not os.path.lexists(path): return None
    audit = _read(path)
    fixed = {'schemaVersion': 1, 'kind': 'paid-exit-recovery-review' if exit_recovery else 'paid-domain-inventory-reconciliation', 'scopeId': receipt['scopeId'],
             'runId': identifier, 'stepId': identifier + ':step-1', 'gameDate': receipt['gameDate'],
             'chargedOriginalReservation': 20, 'releasedOriginalReservation': 0,
             'historicalOutcomeRetained': 'unknown', 'reviewedBy': 'root-agent',
             'coverageLimit': 'bounded-recordings-and-closed-game-boundaries'}
    if any(type(audit.get(k)) is not type(v) or audit[k] != v for k, v in fixed.items()):
        raise ValueError('paid reconciliation scope/cost/historical outcome mismatch')
    if not isinstance(audit.get('reason'), str) or not audit['reason'].strip() or len(audit['reason']) > 2000:
        raise ValueError('paid reconciliation requires independent bounded review reason')
    authorization_snapshot = _source(root, audit.get('authorizationSnapshot'))
    authorization = _read(authorization_snapshot)
    if (authorization_snapshot.parent != root / 'state/cultivation-authorization-snapshots'
            or {k: v for k, v in authorization.items() if k != 'assignedRunIds'} != {k: v for k, v in receipt.items() if k != 'assignedRunIds'}
            or not isinstance(authorization.get('assignedRunIds'), list)
            or identifier not in authorization['assignedRunIds']
            or receipt['assignedRunIds'][:len(authorization['assignedRunIds'])] != authorization['assignedRunIds']):
        raise ValueError('paid reconciliation authorization snapshot changed')
    old, old_raw, old_paths = _review_run_sources(root, bgi, identifier, audit.get('oldSources', {}), 'execute', receipt['target'])
    if old != prior or old_raw != report or old_raw.get('status') != 'unknown' or len(old_raw.get('steps', [])) != 1:
        raise ValueError('paid reconciliation is not the immutable original single unknown step')
    step = old_raw['steps'][0]
    chain = {'114009', '114010', '114011', '114012'}
    if (step.get('stepId') != fixed['stepId'] or step.get('status') != 'unknown' or step.get('type') != 'domain'
            or step.get('resin') != 'original' or set(step.get('before', {})) != chain
            or any(row.get('status') != 'exact' or type(row.get('count')) is not int for row in step['before'].values())
            or (not exit_recovery and (set(step.get('after', {})) != chain
                or step['after']['114010'].get('status') != 'unknown' or step['after']['114010'].get('count') is not None
                or any(step['after'][k].get('status') != 'exact' for k in chain - {'114010'})))):
        raise ValueError('paid reconciliation only supports one missing Iron stack after a protected original20')
    try:
        from cultivation import _domain_evidence, _resin_evidence
    except ImportError:
        from scripts.cultivation import _domain_evidence, _resin_evidence
    _domain_evidence(step, bgi / 'User/JsScript/AutoGameCultivation', old_raw['policy'], chain)
    if exit_recovery:
        old_count, after_at = _paid_exit_observation(root, audit, old_raw, old_paths, transition)
    else:
        _resin_evidence(step, 20)
        if not _daily_native_exit(old_paths['log'], [step]):
            raise ValueError('paid reconciliation native safe exit unverified')
        old_count, after_at = step['resinAfter']['originalResin'], _timestamp(step['resinAfter']['observedAt'], 'old resin after')
    scan_id, resin_id = audit.get('inventoryRunId'), audit.get('resinRunId')
    if scan_id == identifier or resin_id == identifier:
        raise ValueError('paid reconciliation requires independent later read-only probes')
    scan, scan_raw, scan_paths = _review_run_sources(root, bgi, scan_id, audit.get('inventorySources', {}), 'scan', receipt['target'])
    resin, resin_raw, resin_paths = _review_run_sources(root, bgi, resin_id, audit.get('resinSources', {}), 'scan', receipt['target'])
    probe_identity = _object(audit.get('probeRuntimeIdentity'), 'paid reconciliation probe runtime identity')
    expected_identity = _historical_runtime(scan,receipt,transition)
    if probe_identity != expected_identity:
        raise ValueError('paid reconciliation probe runtime identity mismatch')
    if _historical_runtime(resin,receipt,transition) != probe_identity:
        raise ValueError('paid reconciliation probes span different runtime eras')
    _runtime_sources(root,probe_identity,receipt,transition)
    if exit_recovery and (transition is None or not transition.get('exitTransition')
            or probe_identity!=transition['exitTransition']['currentRuntimeIdentity']):
        raise ValueError('paid exit recovery requires a fresh probe from the reviewed fixed engine')
    for probe, raw, sources in ((scan, scan_raw, scan_paths), (resin, resin_raw, resin_paths)):
        if (probe.get('gameDate') != receipt['gameDate'] or raw.get('readOnly') is not True or raw.get('steps') != []
                or probe.get('cultivationMode') != 'scan' or any(raw.get('policy', {}).get(k) is True for k in ('allowBoss', 'allowCrafting'))):
            raise ValueError('paid reconciliation probe is not same-day read-only')
        log = sources['log'].read_text(encoding='utf-8-sig')
        if any(token in log for token in ('单次原粹20提交', '本轮奖励识别结果', 'RunCultivationCraft', 'AutoBossTask', 'AutoDomainTask')):
            raise ValueError('paid reconciliation probe contains a resource operation')
    if scan_raw.get('profile') != old_raw.get('profile'):
        raise ValueError('paid reconciliation character/weapon progress changed')
    inventory = scan_raw.get('inventory', {})
    for material in chain:
        row = inventory.get(material, {})
        if (row.get('status') != 'exact' or row.get('source') not in ('backpack_selected_stack', 'character_weapon_guide_tooltip')
                or row.get('verified') is not True or type(row.get('count')) is not int
                or row['count'] < step['before'][material]['count']
                or (not exit_recovery and material != '114010' and row['count'] != step['after'][material]['count'])):
            raise ValueError('paid reconciliation named stack or known-after continuity mismatch')
    if not any(inventory[k]['count'] > step['before'][k]['count'] for k in chain):
        raise ValueError('paid reconciliation lacks observed positive material chain')
    snapshot = resin_raw.get('resinObservation', {})
    observed = _timestamp(snapshot.get('observedAt'), 'reconciliation resin observedAt')
    elapsed = (observed - after_at).total_seconds()
    if (not 0 < elapsed <= 7200 or not _timestamp(resin_raw['startedAt'], 'probe start') <= observed <= _timestamp(resin_raw['finishedAt'], 'probe finish')
            or snapshot.get('originalVerified') is not True or snapshot.get('condensedVerified') is not True
            or snapshot.get('mainUiRestored') is not True or snapshot.get('condensedResin') != 0):
        raise ValueError('paid reconciliation fresh resin or bounded recovery interval unverified')
    current_count = _integer(snapshot.get('originalResin'), 0, 200, 'reconciliation original resin')
    if not min(200, old_count + math.floor(elapsed / 480)) - 1 <= current_count <= min(200, old_count + math.ceil(elapsed / 480)) + 1:
        raise ValueError('paid reconciliation resin interval could conceal another expense or supplement')
    resin_log = resin_paths['log'].read_text(encoding='utf-8-sig')
    log_observations = []
    for line in resin_log.splitlines():
        if '[CULTIVATION_RESIN_OBSERVATION]' not in line:
            continue
        payload = line.split('[CULTIVATION_RESIN_OBSERVATION]', 1)[1].strip()
        try:
            value = json.loads(payload)
            if isinstance(value, str): value = json.loads(value)
        except (ValueError, TypeError):
            raise ValueError('paid reconciliation raw resin log malformed')
        log_observations.append(value)
    if len(log_observations) != 1 or any(log_observations[0].get(k) != snapshot.get(k) for k in ('originalResin', 'condensedResin', 'observedAt', 'originalVerified', 'condensedVerified', 'verified', 'mainUiRestored')):
        raise ValueError('paid reconciliation fresh resin report/log mismatch')
    if _timestamp(scan_raw['startedAt'], 'inventory probe start') < _timestamp(old_raw['finishedAt'], 'old finish'):
        raise ValueError('paid reconciliation independent inventory/resin observations out of order')
    if scan_id == resin_id:
        if scan_raw.get('metadata', {}).get('diagnostic') != 'inventory-and-resin':
            raise ValueError('paid reconciliation same-run probe must export actual inventory then fresh resin')
        def frame_times(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == 'observedAt' and type(item) in (int, float): yield item
                    else: yield from frame_times(item)
            elif isinstance(value, list):
                for item in value: yield from frame_times(item)
        times = [at for material in chain for at in frame_times(inventory[material].get('evidence'))]
        if not times or max(times) > observed.timestamp() * 1000:
            raise ValueError('paid reconciliation resin was observed before inventory frames')
    elif _timestamp(scan_raw['finishedAt'], 'inventory probe finish') > observed:
        raise ValueError('paid reconciliation later resin probe predates completed inventory scan')
    if transition is not None and _timestamp(scan.get('triggeredAt'), 'inventory triggeredAt') < _timestamp(transition['effectiveAtUTC'], 'runtime cutover'):
        raise ValueError('paid reconciliation backpack API probe predates reader runtime cutover')
    boundaries = _object(audit.get('ownedBoundaries'), 'reconciliation owned boundaries')
    closed_path = _source(root, boundaries.get('oldClosed'))
    closed = _read(closed_path)
    if (closed.get('runId') != identifier or type(closed.get('gameBGIProcesses')) is not int or closed['gameBGIProcesses'] != 0 or closed.get('settingsMatch') is not True
            or closed.get('graphicsRegistryMatchesSnapshot') is not True
            or not _timestamp(old_raw['finishedAt'], 'old finish') <= _timestamp(closed.get('finishedAt'), 'closed boundary') <= _timestamp(scan.get('triggeredAt'), 'new probe start')):
        raise ValueError('paid reconciliation original closed-game boundary mismatch')
    fresh_path = _source(root, boundaries.get('newPrelaunch'))
    fresh = _read(fresh_path)
    if (fresh.get('runId') != scan_id or type(fresh.get('gameBGIProcesses')) is not int or fresh['gameBGIProcesses'] != 0
            or _timestamp(fresh.get('observedAtUTC'), 'prelaunch observedAt') < _timestamp(closed['finishedAt'], 'old closed')
            or not _prelaunch_before_trigger(fresh.get('observedAtUTC'), scan.get('triggeredAt'), scan.get('launchedAt'))):
        raise ValueError('paid reconciliation new closed-game prelaunch boundary mismatch')
    runtimes = boundaries.get('probeRuntimes')
    if not isinstance(runtimes, list) or len(runtimes) != len({scan_id, resin_id}):
        raise ValueError('paid reconciliation requires actual owned process/runtime snapshots')
    supplied = set()
    for runtime_ref in runtimes:
        owned = _read(_source(root, runtime_ref))
        rid = owned.get('runId')
        if rid not in {scan_id, resin_id} or rid in supplied:
            raise ValueError('paid reconciliation duplicate or mismatched probe process record')
        supplied.add(rid)
        probe, raw = (scan, scan_raw) if rid == scan_id else (resin, resin_raw)
        if (owned.get('bettergiPid') != probe.get('bettergiPid') or type(owned.get('bettergiPid')) is not int
                or owned['bettergiPid'] <= 0 or type(owned.get('gamePid')) is not int or owned['gamePid'] <= 0
                or owned.get('runtimeIdentity') != probe_identity
                or not _timestamp(probe.get('launchedAt'), 'probe launchedAt') <= _timestamp(owned.get('observedAtUTC'), 'owned process observation') <= _timestamp(raw['finishedAt'], 'probe report finish')):
            raise ValueError('paid reconciliation actual probe ownership/runtime mismatch')
    reviews = audit.get('videoReviews')
    if not isinstance(reviews, list) or len(reviews) != len({identifier, scan_id, resin_id}):
        raise ValueError('paid reconciliation requires reviewed frames for every owned video')
    reviewed_ids = set()
    for review in reviews:
        if review.get('runId') not in {identifier, scan_id, resin_id} or not isinstance(review.get('frames'), list) or len(review['frames']) < 2:
            raise ValueError('paid reconciliation video review lacks independent start/end frames')
        if review['runId'] in reviewed_ids:
            raise ValueError('paid reconciliation duplicate video stage review')
        reviewed_ids.add(review['runId'])
        seen_frames = set()
        for frame in review['frames']:
            frame_path = _source(root, frame)
            if (not frame_path.is_relative_to(root / 'tests/.artifacts') or frame_path.suffix.lower() != '.png'
                    or frame_path in seen_frames):
                raise ValueError('paid reconciliation reviewed frame outside retained artifacts')
            seen_frames.add(frame_path)
    if _timestamp(audit.get('reviewedAtUTC'), 'reconciliation reviewedAt') < observed:
        raise ValueError('paid reconciliation review predates its source evidence')
    return {k: audit[k] for k in ('runId', 'stepId', 'chargedOriginalReservation', 'releasedOriginalReservation', 'historicalOutcomeRetained', 'coverageLimit')} | {
        'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'inventoryRunId': scan_id, 'resinRunId': resin_id, 'eligibility': 'new-claims-only-no-replay'}


def constrain_daily(root, bettergi_dir, config, run_id, game_date, *, assign=False) -> tuple[dict, dict]:
    """Independent dated grant; durable attempted claims remain charged even if unknown."""
    root, bgi = _safe_path(root), _safe_path(bettergi_dir)
    if bgi != _safe_path(root / 'BetterGI_custom'):
        raise ValueError('daily grant is bound to its fingerprinted BetterGI engine')
    result = copy.deepcopy(config)
    policy = result['policy']
    _run_id(run_id)
    game_date = _game_date(game_date)
    path, receipt = _daily_receipt(root, result, game_date)
    runtime, transition = _daily_runtime(root, receipt)
    if (policy.get('validationMode') or policy.get('allowBoss') or policy.get('allowCrafting')
            or policy.get('condensedResinBudget') != 0 or policy.get('domainResin') != 'original'
            or policy.get('validationAttemptedSources') or policy.get('requireZhongliShieldCast') is not True):
        raise ValueError('daily scope permits original-only domains')
    if run_id in receipt['assignedRunIds']:
        raise ValueError('daily runId already assigned; replay forbidden')
    reserved, ready, unknown, evidence = 0, False, [], []
    reconciliations, reconciliation_probes = [], set()
    for identifier in receipt['assignedRunIds']:
        directory = root / 'logs/runs' / identifier
        prior = _read(directory / 'result.json')
        authorization = prior.get('cultivationAuthorization', {})
        if (prior.get('runId') != identifier or prior.get('gameDate') != game_date
                or prior.get('cultivationTarget') != result['target'] or authorization.get('scopeId') != receipt['scopeId']
                or authorization.get('purpose') != receipt['purpose'] or authorization.get('originalResinCap') != receipt['originalResinCap']
                or authorization.get('runtimeIdentity') != _historical_runtime(prior, receipt, transition)):
            raise ValueError('daily prior result scope mismatch')
        paths = [bgi / 'User/JsScript/AutoGameCultivation/record' / (identifier + '.json'), directory / 'cultivation-report.json']
        reports = [_read(item) for item in paths if os.path.lexists(item)]
        if not reports:
            if prior.get('cultivationLaunchAttempted') is not False or prior.get('launchedAt') or prior.get('bettergiPid'):
                raise ValueError('daily assigned launch missing durable report; replay forbidden')
            evidence.append({'runId': identifier, 'reservedOriginal': 0, 'evidence': 'explicit-not-launched'})
            continue
        attempts = {}
        for report in reports:
            if (report.get('runId') != identifier or report.get('mode') != 'execute'
                    or _target(report.get('target')) != result['target'] or report.get('policy', {}).get('validationScopeId') != receipt['scopeId']
                    or report.get('policy', {}).get('dailyMode') is not True or report.get('policy', {}).get('validationMode') is not False
                    or not isinstance(report.get('steps'), list)):
                raise ValueError('daily report scope mismatch')
            for index, step in enumerate(report['steps'], 1):
                if (not isinstance(step, dict) or step.get('type') != 'domain' or step.get('stepId') != f'{identifier}:step-{index}'
                        or step.get('validationAttempt') is not False or type(step.get('maxClaims')) is not int
                        or step['maxClaims'] != 1 or step.get('resin') != 'original'):
                    raise ValueError('daily attempt checkpoint malformed')
                attempts[step['stepId']] = 20
        used = sum(attempts.values())
        reserved += used
        # Require final matching mirrors, independently checked inventory/resin,
        # and native safe exit. A stale checkpoint is still charged conservatively.
        verified = bool(attempts) and _daily_verified_run(root, bgi, identifier, prior, reports[0], mirrors=reports)
        ready = ready or verified
        review = (_paid_inventory_reconciliation(root, bgi, receipt, identifier, prior, reports[0], transition)
                  if attempts and not verified else None)
        if review is not None:
            probes = {review['inventoryRunId'], review['resinRunId']}
            if reconciliation_probes & probes:
                raise ValueError('paid reconciliation read-only evidence reused across unknown attempts')
            reconciliation_probes.update(probes)
            reconciliations.append(review)
        if attempts and not verified and review is None:
            unknown.append(identifier)
        evidence.append({'runId': identifier, 'reservedOriginal': used,
                         'evidence': 'verified-original-domain' if verified else 'reconciled-paid-unknown-no-replay' if review is not None else 'durable-attempt-checkpoint',
                         'reconciliationReview': review})
    requested = _integer(policy.get('originalResinBudget'), 0, 200, 'daily originalResinBudget')
    remaining = max(0, receipt['originalResinCap'] - reserved)
    policy['originalResinBudget'] = 0 if unknown else min(requested, remaining, 200 if ready else 20)
    policy['maxSteps'] = policy['maxSteps'] if ready and not unknown else 1
    policy['domainValidated'] = False  # Never trust a manually toggled production flag.
    policy['dailyDomainReady'] = ready and not unknown
    policy['validationAttemptedSources'] = []
    summary = {'scopeId': receipt['scopeId'], 'purpose': receipt['purpose'], 'gameDate': game_date,
               'originalResinCap': receipt['originalResinCap'], 'condensedResinCap': 0,
               'priorReservedOriginal': reserved, 'runtimeOriginalResinBudget': policy['originalResinBudget'],
               'dailyDomainReady': policy['dailyDomainReady'], 'strictFirst20': not policy['dailyDomainReady'],
               'unknownRuns': unknown, 'priorRuns': evidence, 'parentReceipt': receipt['parentReceipt'],
               'authorizationSource': receipt['authorizationSource'], 'runtimeIdentity': runtime}
    summary['reconciledPaidUnknownRuns'] = [review['runId'] for review in reconciliations]
    summary['paidReconciliationReviews'] = reconciliations
    if transition is not None:
        summary['runtimeTransition'] = transition
    if assign:
        receipt['assignedRunIds'].append(run_id)
        temporary = _safe_path(path.with_name(path.name + '.tmp'))
        with temporary.open('w', encoding='utf-8') as output:
            json.dump(receipt, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    return result, summary


def constrain_validation(root, bettergi_dir, config, run_id, game_date, *, assign=False) -> tuple[dict, dict]:
    """Cap requested spending by all prior attempted claims, never reimburse uncertain commits."""
    result = copy.deepcopy(config)
    policy = result["policy"]
    if policy.get('dailyMode'):
        return constrain_daily(root, bettergi_dir, result, run_id, game_date, assign=assign)
    if not policy.get("validationMode"):
        return result, {}
    _run_id(run_id)
    root, bgi = _safe_path(root), _safe_path(bettergi_dir)
    receipt_path = _safe_path(root / "state/cultivation-authorization.json")
    receipt = _read(receipt_path)
    scope = policy.get("validationScopeId")
    if not scope or receipt.get("schemaVersion") != 1 or type(receipt.get("schemaVersion")) is not int or receipt.get("scopeId") != scope:
        raise ValueError("initial validation requires matching independent local authorization")
    original_date = _game_date(receipt.get('gameDate'))
    game_date = _game_date(game_date)
    if receipt.get("purpose") != "initial-validation" or _target(receipt.get("target")) != _target(result["target"]):
        raise ValueError("initial-validation authorization date/target/purpose mismatch")
    if _authorized_game_date(receipt.get('authorizedAtUTC')) != original_date:
        raise ValueError("authorization timestamp outside authorized game day")
    cap = _integer(receipt.get("originalResinCap"), 0, 60, "originalResinCap")
    _integer(receipt.get("condensedResinCap"), 0, 0, "condensedResinCap")
    assigned = receipt.get("assignedRunIds")
    if not isinstance(assigned, list):
        raise ValueError("invalid assignedRunIds")
    for identifier in assigned:
        _run_id(identifier)
    if len(assigned) != len(set(assigned)):
        raise ValueError("duplicate assignedRunIds")
    if run_id in assigned:
        raise ValueError("initial-validation runId already assigned; replay forbidden")
    continuations = {}
    if game_date != original_date:
        continuations[game_date] = _continuation(root, receipt, game_date)
    reserved, attempted, evidence = 0, set(), []
    no_commit_reviews = []
    no_attempt_reviews = []
    for identifier in assigned:
        run_dir = _safe_path(root / "logs/runs" / identifier)
        prior_path = run_dir / 'result.json'
        # Same-day legacy checkpoints predate per-run date evidence. A cross-day
        # continuation requires the authoritative result for every assigned run.
        prior = _read(prior_path) if game_date != original_date or os.path.lexists(prior_path) else None
        prior_date = original_date
        if prior is not None:
            prior_date = _game_date(prior.get('gameDate'))
            authorization = _object(prior.get('cultivationAuthorization'), 'prior authorization')
            if (prior.get('runId') != identifier or prior.get('cultivationTarget') != result['target']
                    or authorization.get('scopeId') != scope or prior_date < original_date or prior_date > game_date
                    or ('gameDate' in authorization and authorization['gameDate'] != prior_date)
                    or (prior_date == original_date and authorization.get('executionContinuation') is not None)):
                raise ValueError('assigned validation result date/target/scope mismatch')
            if prior_date != original_date:
                if prior_date not in continuations:
                    continuations[prior_date] = _continuation(root, receipt, prior_date)
                if (authorization.get('executionContinuation') != continuations[prior_date]
                        or authorization.get('gameDate') != prior_date
                        or type(authorization.get('originalResinCap')) is not int or authorization['originalResinCap'] != cap
                        or type(authorization.get('condensedResinCap')) is not int or authorization['condensedResinCap'] != 0):
                    raise ValueError('assigned continuation run provenance/cap mismatch')
        reports = [bgi / "User/JsScript/AutoGameCultivation/record" / (identifier + ".json"),
                   run_dir / "cultivation-report.json"]
        existing_paths = [path for path in reports if os.path.lexists(path)]
        existing = [_read(path) for path in existing_paths]
        if not existing:
            prior = prior if prior is not None else _read(prior_path)
            authorization = prior.get("cultivationAuthorization", {})
            if prior.get("runId") != identifier or prior.get("gameDate") != prior_date or prior.get("cultivationTarget") != result["target"] or authorization.get("scopeId") != scope or prior.get("cultivationLaunchAttempted") is not False or prior.get("launchedAt") or prior.get("bettergiPid"):
                review = _historical_no_attempt(root, identifier, scope, prior_date, result['target'], prior)
                if review is None:
                    raise ValueError("assigned validation run has no report and no proven prelaunch record")
                no_attempt_reviews.append(review)
                evidence.append({'runId': identifier, 'gameDate': prior_date, 'reservedOriginal': 0,
                                 'evidence': 'independently-reviewed-historical-pre-resource-abort',
                                 'noAttemptReview': review})
                continue
            evidence.append({"runId": identifier, "gameDate": prior_date, "reservedOriginal": 0, "evidence": "explicit-not-launched"})
            continue
        attempts = {}
        for report in existing:
            if report.get("runId") != identifier or report.get("mode") != "execute" or _target(report.get("target")) != result["target"] or report.get("policy", {}).get("validationScopeId") != scope or report.get("policy", {}).get("validationMode") is not True or ('gameDate' in report and report['gameDate'] != prior_date):
                raise ValueError("assigned validation report scope mismatch")
            steps = report.get("steps")
            if not isinstance(steps, list):
                raise ValueError("assigned validation checkpoint malformed")
            for index, step in enumerate(steps, 1):
                if not isinstance(step, dict) or step.get("type") not in ("boss", "domain") or step.get("validationAttempt") is not True or step.get("stepId") != f"{identifier}:step-{index}" or type(step.get("maxClaims")) is not int or step["maxClaims"] != 1 or step.get("resin") != "original":
                    raise ValueError("assigned validation attempted step malformed")
                kind = step["type"]
                key = step["stepId"]
                if key in attempts and attempts[key] != kind:
                    raise ValueError("checkpoint copies disagree on attempted source")
                attempts[key] = kind
        review_path = _safe_path(root / 'state/cultivation-no-commit-reviews' / (identifier + '.json'))
        review_kind = _read(review_path).get('kind') if os.path.lexists(review_path) else None
        review = (_pre_battle_no_commit(root, identifier, scope, prior_date, result['target'], existing_paths, existing)
                  if review_kind == 'pre-battle-boss-no-commit' else
                  _historical_no_commit(root, identifier, scope, prior_date, result['target'], existing_paths, existing))
        attempted_reservation = sum(40 if kind == 'boss' else 20 for kind in attempts.values())
        if review is not None:
            if attempts.get(review['stepId']) != 'boss' or (review.get('kind') != 'pre-battle-boss-no-commit' and
                    any(item.get('kind') != 'pre-battle-boss-no-commit' for item in no_commit_reviews)):
                raise ValueError('only one independently reviewed historical boss reservation may be released per scope')
            if any(item['reviewId'] == review['reviewId'] or item['stepId'] == review['stepId'] for item in no_commit_reviews):
                raise ValueError('duplicate independently reviewed boss reservation')
            no_commit_reviews.append(review)
            # Recompute the ledger from assigned attempts. This removes this
            # one old reservation; it never adds a new cap or task success.
            del attempts[review['stepId']]
        used = sum(40 if kind == "boss" else 20 for kind in attempts.values())
        reserved += used
        attempted.update(attempts.values())
        evidence.append({"runId": identifier, "gameDate": prior_date, "reservedOriginal": used, "evidence": "durable-attempt-checkpoint",
                         'attemptedOriginalReservation': attempted_reservation,
                         'noCommitReview': review})
    remaining = max(0, cap - reserved)
    requested = _integer(policy.get("originalResinBudget"), 0, 60, "originalResinBudget")
    policy["originalResinBudget"] = min(requested, remaining)
    policy["condensedResinBudget"] = 0
    policy["validationAttemptedSources"] = sorted(attempted)
    summary = {"scopeId": scope, "gameDate": game_date, "originalResinCap": cap,
               "condensedResinCap": 0, "priorReservedOriginal": reserved,
               "runtimeOriginalResinBudget": policy["originalResinBudget"],
               "alreadyAttemptedSources": sorted(attempted), "priorRuns": evidence}
    summary['releasedNoCommitOriginal'] = sum(item['releasedOriginalReservation'] for item in no_commit_reviews)
    summary['noCommitReviews'] = no_commit_reviews
    summary['noAttemptReviews'] = no_attempt_reviews
    if game_date in continuations:
        summary['originalGameDate'] = original_date
        summary['executionContinuation'] = continuations[game_date]
    if assign:
        receipt["assignedRunIds"].append(run_id)
        temporary = _safe_path(receipt_path.with_name(receipt_path.name + ".tmp"))
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(receipt, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, receipt_path)
    return result, summary
