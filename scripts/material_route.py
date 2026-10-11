"""One fixed, zero-resin route with independent evidence and conservative day leases.

All ledger mutations require the caller's existing workflow RunLock. A started
lease is never released, even when a report is missing or cancellation occurs.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re

try:
    from cultivation import _integer, _json_file, _object, _package_files, _run_id, _safe_path, _text, _timestamp
    from analyze_run import _config_reference, _event_from_line, _FAILURE_RE, _GROUP_MARKER_RE, _MARKER_RE, _parse_rewards, _parse_resin_events
except ImportError:
    from scripts.cultivation import _integer, _json_file, _object, _package_files, _run_id, _safe_path, _text, _timestamp
    from scripts.analyze_run import _config_reference, _event_from_line, _FAILURE_RE, _GROUP_MARKER_RE, _MARKER_RE, _parse_rewards, _parse_resin_events

TASK_ID = 'auto-game-material-route'
TASK_NAME = '刀镡路线'
PLUGIN_NAME = 'AutoGameMaterialRoute'
MODE = 'material-route'
STRATEGY_NAME = '木偶星超导'
MATERIAL_IDS = ('112044', '112045', '112046')
LEDGER_NAME = 'material-route-day-ledger.json'
OVERLAP_DISTANCE = 80.0


def game_date_at(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('route clock must be timezone aware')
    return (now.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).date().isoformat()


def _game_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid gameDate')
    datetime.fromisoformat(value)
    return value


def _point(value):
    row = _object(value, 'fight point')
    for key in ('x', 'y'):
        if type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) or abs(row[key]) > 100000:
            raise ValueError('fight point needs finite map coordinates')
    return {'x': row['x'], 'y': row['y']}


def normalize_route(route):
    row = _object(route, 'route')
    relative = _text(row.get('relativePath'), 'route relativePath', 600)
    path = PurePosixPath(relative)
    if ('\\' in relative or ':' in relative or path.is_absolute() or '..' in path.parts
            or relative != path.as_posix() or len(path.parts) < 2 or path.parts[0] != 'auto_game_handguard'
            or path.suffix.lower() != '.json'):
        raise ValueError('route must be a scoped AutoPathing relative JSON path')
    digest = row.get('sha256')
    commit = row.get('catalogCommit')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('route requires a fixed SHA256')
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('route requires a fixed catalog commit')
    points = row.get('fightPoints')
    if not isinstance(points, list) or not 1 <= len(points) <= 500:
        raise ValueError('route needs explicit fight points')
    return {'relativePath': relative, 'sha256': digest, 'catalogCommit': commit,
            'name': _text(row.get('name'), 'route name', 250), 'fightPoints': [_point(p) for p in points]}


def verify_route_file(bettergi_dir, route):
    route = normalize_route(route)
    base = _safe_path(Path(bettergi_dir) / 'User/AutoPathing')
    path = _safe_path(base / route['relativePath'])
    if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('fixed route is missing or outside package scope')
    if hashlib.sha256(path.read_bytes()).hexdigest() != route['sha256']:
        raise ValueError('fixed route hash changed')
    manifest_path = _safe_path(base / 'auto_game_handguard/manifest.json')
    if not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError('fixed route whitelist manifest missing or too large')
    manifest = _object(_json_file(manifest_path), 'route manifest')
    entries = manifest.get('routes')
    if not isinstance(entries, list) or not entries:
        raise ValueError('route manifest has no whitelist entries')
    matching = [r for r in entries if isinstance(r, dict) and r.get('path') == route['relativePath']]
    if len(matching) != 1 or matching[0].get('sha256') != route['sha256']:
        raise ValueError('route path/hash not uniquely pinned in whitelist manifest')
    raw = _object(_json_file(path), 'pathing file')
    points = [_point(p) for p in raw.get('positions', []) if p.get('action') == 'fight']
    if points != route['fightPoints']:
        raise ValueError('route fight coordinates differ from pinned catalog')
    return route


def inject_material_route_task(template):
    return _inject_material_task(template, TASK_ID, TASK_NAME)


def _inject_material_task(template, task_id, task_name):
    result = copy.deepcopy(_object(template, 'template'))
    definitions = _object(result.get('TaskDefinitions'), 'TaskDefinitions')
    enabled = _object(result.get('TaskEnabledList'), 'TaskEnabledList')
    order = result.get('TaskOrder')
    if not isinstance(order, list) or len(order) != len(set(order)) or any(k not in definitions or k not in enabled for k in order):
        raise ValueError('invalid route TaskOrder')
    if (task_id in definitions and definitions[task_id] != task_name
            or any(v == task_name and k != task_id for k, v in definitions.items())):
        raise ValueError('material route task ID/name collision')
    definitions[task_id], enabled[task_id] = task_name, True
    if task_id not in order:
        order.append(task_id)
    return result


def prepare_material_route_plugin(source_dir, bettergi_dir, *, dry_run=False):
    """Read-only package gate; deployment/backup is a separate reviewed operation."""
    source = _safe_path(source_dir)
    destination = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME)
    if not source.is_dir():
        raise ValueError('material route source plugin missing')
    files = _package_files(source)
    if not {'manifest.json', 'main.js'} <= set(files):
        raise ValueError('material route package requires manifest.json and main.js')
    if not dry_run and (not destination.is_dir() or files != _package_files(destination)):
        raise ValueError('material route deployed plugin differs from reviewed source')
    return {'verified': not dry_run, 'sourceVerified': True, 'pluginDirectory': str(destination),
            'sourceSha256': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}


def build_route_group(run_id, private_config, route, *, game_date, max_minutes=8, timeout_seconds=None):
    _run_id(run_id)
    _game_date(game_date)
    route = normalize_route(route)
    minutes = _integer(max_minutes, 1, 8, 'route maxMinutes')
    policy = _object(_object(private_config, 'private config').get('policy', {}), 'route policy')
    party = _text(private_config.get('partyName', policy.get('domainPartyName')), 'partyName')
    group = {'Name': PLUGIN_NAME + '_' + run_id, 'Projects': [{
        'Name': TASK_NAME, 'FolderName': PLUGIN_NAME, 'Type': 'Javascript', 'Status': 'Enabled',
        'Schedule': 'Daily', 'RunNum': 1, 'AllowJsNotification': False,
        'JsScriptSettingsObject': {'runId': run_id, 'gameDate': game_date, 'mode': MODE,
            'route': route, 'partyName': party, 'strategyName': STRATEGY_NAME,
            'routeJson': json.dumps(route, ensure_ascii=False, separators=(',', ':')),
            'requireZhongliShield': True, 'maxMinutes': minutes,
            'originalResinBudget': 0, 'condensedResinBudget': 0, 'fragileResinBudget': 0,
            'transientResinBudget': 0, 'allowCrafting': False, 'allowUpgrade': False}}]}
    settings = group['Projects'][0]['JsScriptSettingsObject']
    if timeout_seconds is not None:
        settings['timeoutSeconds'] = _integer(timeout_seconds, 60, 480, 'route timeoutSeconds')
    if private_config.get('expectedTeam') is not None:
        settings['expectedTeam'] = normalize_expected_team(private_config['expectedTeam'])
        settings['expectedTeamJson'] = json.dumps(settings['expectedTeam'], ensure_ascii=False, separators=(',', ':'))
    return group


def _ledger(root):
    path = _safe_path(Path(root) / 'state' / LEDGER_NAME)
    ledger = _json_file(path) if path.exists() else {'schemaVersion': 1, 'days': {}}
    if ledger.get('schemaVersion') != 1 or type(ledger.get('schemaVersion')) is not int:
        raise ValueError('invalid material route ledger schema')
    for day, entries in _object(ledger.get('days'), 'route ledger days').items():
        _game_date(day)
        if not isinstance(entries, list):
            raise ValueError('invalid material route ledger day')
        for entry in entries:
            _object(entry, 'route lease')
            _run_id(entry.get('runId'))
            normalize_route(entry.get('route'))
            if entry.get('status') not in ('started', 'completed', 'partial', 'failed', 'unknown', 'cancelled', 'timeout'):
                raise ValueError('invalid route lease status')
            for key in ('wallSeconds', 'reservedSeconds', 'farmingSeconds'):
                if key in entry and (type(entry[key]) not in (int, float) or not math.isfinite(entry[key]) or entry[key] < 0):
                    raise ValueError('invalid material route ledger time')
    return path, ledger


def _charged_route_native_seconds(entry):
    """An unattempted zero is conditional on its audit, never an actual elapsed time.

    The caller already excludes currently valid no-attempt receipts. If their
    sources change, restore the full reservation without rewriting old facts.
    Actual attempted native zero-second outcomes keep their existing semantics.
    """
    evidence = entry.get('evidence')
    no_attempt = entry.get('noAttemptVerified') is True or (
        isinstance(evidence, dict) and evidence.get('noAttemptVerified') is True)
    if no_attempt:
        return entry.get('reservedSeconds', 480)
    return entry.get('farmingSeconds', entry.get('reservedSeconds', 480))


def constrain_route_day(root, game_date, route, *, now=None, overlap_distance=OVERLAP_DISTANCE,
                        budget_seconds=480):
    """Do not retry consumed/uncertain points; versions and authors cannot bypass it."""
    _game_date(game_date)
    if now is not None and game_date_at(now) != game_date:
        raise ValueError('material route gameDate is stale')
    route = normalize_route(route)
    _, ledger = _ledger(root)
    if type(overlap_distance) not in (int, float) or not math.isfinite(overlap_distance) or overlap_distance < 1:
        raise ValueError('invalid conservative overlap distance')
    _integer(budget_seconds, 1, 480, 'route native farming budget seconds')
    live_leases = [entry for entry in ledger['days'].get(game_date, [])
                  if not _verified_no_attempt_review(root, entry) and not _verified_session_no_attempt(root, entry)]
    used = sum(_charged_route_native_seconds(entry) for entry in live_leases)
    if used + budget_seconds > 1800:
        raise ValueError('material route daily farming budget of 30 minutes would be exceeded')
    for prior in live_leases:
        previous = prior['route']
        if previous['relativePath'] == route['relativePath'] or previous['sha256'] == route['sha256']:
            raise ValueError('route already reserved this game day: ' + prior['runId'])
        for first in previous['fightPoints']:
            for second in route['fightPoints']:
                distance = math.hypot(first['x'] - second['x'], first['y'] - second['y'])
                if distance <= overlap_distance:
                    raise ValueError(f'route fight points potentially overlap ({distance:.2f} map units <= {overlap_distance}) a same-day lease: ' + prior['runId'])
    return {'eligible': True, 'gameDate': game_date, 'route': route, 'overlapDistance': overlap_distance,
            'dailyUsedSeconds': used, 'reservedSeconds': budget_seconds}


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _safe_path(path.with_name(path.name + '.tmp'))
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def assign_route_day(root, game_date, route, run_id, *, now=None, overlap_distance=OVERLAP_DISTANCE, budget_seconds=480):
    """Reserve before game execution, under the caller-held shared RunLock."""
    _run_id(run_id)
    now = now or datetime.now(timezone.utc)
    eligibility = constrain_route_day(root, game_date, route, now=now, overlap_distance=overlap_distance,
                                     budget_seconds=budget_seconds)
    path, ledger = _ledger(root)
    if any(entry['runId'] == run_id for entries in ledger['days'].values() for entry in entries):
        raise ValueError('material route runId already has a ledger lease')
    lease = {'runId': run_id, 'gameDate': game_date, 'status': 'started',
             'startedAt': now.isoformat(), 'route': eligibility['route'], 'reservedSeconds': budget_seconds}
    ledger['days'].setdefault(game_date, []).append(lease)
    _atomic(path, ledger)
    return copy.deepcopy(lease)


def finalize_route_day(root, game_date, run_id, outcome, *, now=None, evidence=None, wall_seconds=None, farming_seconds=None):
    """Every terminal outcome retains the route and point reservation."""
    _run_id(run_id)
    _game_date(game_date)
    if outcome not in ('completed', 'partial', 'failed', 'unknown', 'cancelled', 'timeout'):
        raise ValueError('invalid material route terminal outcome')
    path, ledger = _ledger(root)
    matches = [r for r in ledger['days'].get(game_date, []) if r['runId'] == run_id]
    if len(matches) != 1:
        raise ValueError('material route lease not unique or missing')
    lease = matches[0]
    if lease['status'] != 'started':
        if lease['status'] != outcome:
            raise ValueError('material route terminal lease cannot be rewritten')
        return copy.deepcopy(lease)
    lease.update(status=outcome, finishedAt=(now or datetime.now(timezone.utc)).isoformat())
    if wall_seconds is not None:
        if type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds) or wall_seconds < 0:
            raise ValueError('invalid route actual wall seconds')
        lease['wallSeconds'] = wall_seconds
    if farming_seconds is not None:
        if type(farming_seconds) not in (int, float) or not math.isfinite(farming_seconds) or not 0 <= farming_seconds <= lease['reservedSeconds'] + 5:
            raise ValueError('invalid native farming seconds')
        lease['farmingSeconds'] = farming_seconds
    if evidence is not None:
        lease['evidence'] = copy.deepcopy(_object(evidence, 'route evidence'))
    _atomic(path, ledger)
    return copy.deepcopy(lease)


def _counts(value):
    rows = _object(value, 'route inventory')
    if set(rows) != set(MATERIAL_IDS):
        raise ValueError('route inventory must contain exactly three handguard IDs')
    counts = {}
    for key in MATERIAL_IDS:
        row = _object(rows[key], 'inventory row')
        if row.get('status') != 'exact':
            raise ValueError('route inventory is not exact')
        counts[key] = _integer(row.get('count'), 0, 999999999, 'actual inventory count')
    return counts


def _exact_fields(row, expected, name):
    if any(type(row.get(k)) is not type(v) or row[k] != v for k, v in expected.items()):
        raise ValueError(name + ' scope or policy mismatch')


def _native_parameters(settings):
    parameters = {'runId': settings['runId'], 'routePath': settings['route']['relativePath'],
        'sha256': settings['route']['sha256'], 'partyName': settings['partyName'],
        'strategyName': settings['strategyName'], 'requireZhongliShield': True,
        'timeoutSeconds': settings.get('timeoutSeconds', settings['maxMinutes'] * 60)}
    if 'expectedTeam' in settings:
        parameters['expectedTeam'] = normalize_expected_team(settings['expectedTeam'])
    return parameters


def _no_attempt_path(root, run_id):
    return _safe_path(Path(root) / 'logs/runs' / _run_id(run_id) / 'material-route-no-attempt-review.json')


def audit_route_no_attempt(root, run_id, *, segments=None):
    """Prove an intact owned lifecycle stopped at the world-entry gate.

    Absence of a report alone is never sufficient. Reconstruct the complete
    archive from pinned raw-log slices, require the gate's positive waiting
    evidence and process exit, and reject every downstream execution marker.
    """
    root = _safe_path(root)
    _run_id(run_id)
    directory = _safe_path(root / 'logs/runs' / run_id)
    sources = {}

    def source(path):
        path = _safe_path(path)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('no-attempt source missing or outside workspace')
        data = path.read_bytes()
        sources[str(path.relative_to(root)).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
        return path, data

    result_path, _ = source(directory / 'result.json')
    result = _object(_json_file(result_path), 'no-attempt original result')
    if (result.get('runId') != run_id or result.get('mode') != MODE
            or result.get('outcome') not in ('unknown', 'failed')
            or result.get('executionOutcome') not in ('cancelled', 'timeout', 'blocked_or_failed')
            or result.get('expectedTasks') != [TASK_NAME]):
        raise ValueError('no-attempt original result scope/stage mismatch')
    game_date = _game_date(result.get('gameDate'))
    start, end = (_timestamp(result.get(k), k) for k in ('launchedAt', 'finishedAt'))
    if game_date_at(start) != game_date or game_date_at(end) != game_date or not 0 < (end-start).total_seconds() <= 16*60+5:
        raise ValueError('no-attempt original interval invalid')
    pid = _integer(result.get('bettergiPid'), 1, 2147483647, 'no-attempt owned PID')
    group_path, _ = source(directory / 'material-route-group.json')
    group = _object(_json_file(group_path), 'no-attempt group')
    settings = _object(group['Projects'][0]['JsScriptSettingsObject'], 'no-attempt settings')
    expected = build_route_group(run_id, {'partyName': settings['partyName'], 'expectedTeam': settings.get('expectedTeam')}, settings['route'],
        game_date=game_date, max_minutes=settings['maxMinutes'])
    if group != expected:
        raise ValueError('no-attempt group scope changed')
    runtime_group = _safe_path(result.get('runtimeMaterialRouteGroup', ''))
    runtime_config = _safe_path(result.get('runtimeConfig', ''))
    bettergi = runtime_config.parents[2]
    config_name = 'AutoGame_' + run_id
    if (runtime_config != _safe_path(bettergi / 'User/OneDragon' / (config_name + '.json'))
            or runtime_group != _safe_path(bettergi / 'User/ScriptGroup' / (group['Name'] + '.json'))):
        raise ValueError('no-attempt runtime config/group names changed')
    for candidate in (runtime_group, directory / 'one-dragon.json', runtime_config):
        source(candidate)
    if _json_file(runtime_group) != group:
        raise ValueError('no-attempt runtime group differs from archive')
    dragon = _object(_json_file(runtime_config), 'no-attempt runtime config')
    if dragon != _json_file(directory / 'one-dragon.json') or dragon.get('Name') != config_name or dragon.get('SkipFinalRewardCheck') is not True:
        raise ValueError('no-attempt runtime one-dragon differs from isolated archive')
    selected = [dragon.get('TaskDefinitions', {}).get(k) for k, v in dragon.get('TaskEnabledList', {}).items() if v is True]
    if selected != [group['Name']]:
        raise ValueError('no-attempt runtime config could execute another task')
    # Bind both deployed binaries and the source of the startup-before-group gate.
    source(bettergi / 'BetterGI.exe')
    source(bettergi / 'BetterGI.dll')
    controller, _ = source(root / 'src/bettergi-custom/BetterGenshinImpact/ViewModel/Pages/OneDragonFlowViewModel.cs')
    gate, _ = source(root / 'src/bettergi-custom/BetterGenshinImpact/Service/ScriptService.cs')
    controller_text, gate_text = controller.read_text(encoding='utf-8'), gate.read_text(encoding='utf-8')
    if ('await ScriptService.StartGameTask();' not in controller_text
            or controller_text.index('await ScriptService.StartGameTask();') >= controller_text.index('配置组任务执行:')
            or 'StartGameTask(bool waitForMainUi = true)' not in gate_text
            or '当前不在游戏主界面，等待进入主界面后执行任务' not in gate_text):
        raise ValueError('no-attempt startup gate source contract missing')
    archived_log, archive_bytes = source(directory / 'bettergi.log')
    offsets_path, _ = source(directory / 'log-offsets.json')
    offsets = _object(_json_file(offsets_path), 'no-attempt log offsets')
    raw_directory = _safe_path(bettergi / 'log')
    if segments is None:
        segments = [{'path': str(p), 'offset': offsets.get(str(p), 0),
                     'length': p.stat().st_size - offsets.get(str(p), 0)}
                    for p in sorted(raw_directory.glob('*.log'))]
    if not isinstance(segments, list) or not segments:
        raise ValueError('no-attempt raw logs absent')
    chunks, pinned = [], []
    for row in segments:
        row = _object(row, 'no-attempt raw log slice')
        path = _safe_path(row.get('path', ''))
        if not path.is_relative_to(raw_directory) or path.suffix != '.log' or not path.is_file():
            raise ValueError('no-attempt raw log path invalid')
        offset = _integer(row.get('offset'), 0, 2**63-1, 'raw offset')
        length = _integer(row.get('length'), 0, 2**63-1, 'raw length')
        if offset != offsets.get(str(path), 0) or path.stat().st_size < offset + length:
            raise ValueError('no-attempt raw log truncated or offset changed')
        if not length:
            continue
        with path.open('rb') as stream:
            stream.seek(offset)
            data = stream.read(length)
        if b'\xef\xbf\xbd' in data:
            raise ValueError('no-attempt raw log encoding is incomplete')
        chunks.append(data.decode('utf-8-sig', errors='strict'))
        pinned.append({'path': str(path), 'offset': offset, 'length': length, 'sha256': hashlib.sha256(data).hexdigest()})
    raw = '\n'.join(chunks)
    records = re.split(r'(?=^\[\d{2}:\d{2}:\d{2}\.\d+\])', raw, flags=re.M)
    owned = []
    for record in records:
        if not record.strip():
            continue
        header = record.split('\n', 1)[0]
        match = re.search(r':P(\d+)(?=:|\])', header)
        if not match:
            raise ValueError('no-attempt raw log has an unscoped record')
        if int(match.group(1)) == pid:
            owned.append(record)
    text = ''.join(owned)
    if text.replace('\n', os.linesep).encode('utf-8') != archive_bytes:
        raise ValueError('no-attempt archive does not equal complete owned raw log')
    local_start, local_end = (stamp.astimezone(timezone(timedelta(hours=8))) for stamp in (start, end))
    observed_times = []
    for record in owned:
        match = re.match(r'\[(\d{2}:\d{2}:\d{2}\.\d+)\]', record)
        if not match:
            raise ValueError('no-attempt raw record time missing')
        parsed = datetime.fromisoformat(str(local_start.date()) + 'T' + match[1] + '+08:00')
        candidates = [parsed + timedelta(days=delta) for delta in (-1, 0, 1)]
        matched = [t for t in candidates if local_start-timedelta(seconds=5) <= t <= local_end+timedelta(seconds=5)]
        if len(matched) != 1 or observed_times and matched[0] < observed_times[-1]:
            raise ValueError('no-attempt raw log time is outside owned lifecycle')
        observed_times.append(matched[0])
    lines = text.splitlines()
    references = [name for line in lines if (name := _config_reference(line))]
    if (not references or set(references) != {config_name} or len(references) != 2
            or '实例 IPC v2 已启动：Primary' not in text or '主窗体实例化' not in text
            or '主窗体退出' not in owned[-1]):
        raise ValueError('no-attempt full startup/config/exit lifecycle incomplete')
    waits = re.findall(r'启动等待中尝试前台鼠标点击.*?等待已进行 (\d+)s', text)
    if ('当前不在游戏主界面，等待进入主界面后执行任务' not in text
            or len(waits) < 2 or max(map(int, waits)) < 35):
        raise ValueError('no-attempt positive world-entry wait evidence missing')
    if (any(_GROUP_MARKER_RE.search(line) or _MARKER_RE.search(line) for line in lines)
            or re.search(r'\[AUTO_GAME_EVENT\]|material-route|地图追踪|路线执行|拾取|战斗|配置组任务启动|启用配置组任务的数量|一条龙和配置组任务结束', text)):
        raise ValueError('no-attempt log contains downstream script/native/resource evidence')
    record_dir = _safe_path(bettergi / 'User/JsScript' / PLUGIN_NAME / 'record')
    if ((directory / 'material-route-report.json').exists()
            or record_dir.exists() and any(p.name.startswith(run_id) for p in record_dir.iterdir())):
        raise ValueError('no-attempt route record/checkpoint exists')
    _, ledger = _ledger(root)
    matches = [entry for entry in ledger['days'].get(game_date, []) if entry['runId'] == run_id]
    if (len(matches) != 1 or matches[0]['status'] not in ('unknown', 'failed')
            or normalize_route(matches[0]['route']) != settings['route']
            or matches[0].get('evidence', {}).get('routeCompleted') is True
            or matches[0].get('evidence', {}).get('fightPointEvidence')):
        raise ValueError('no-attempt ledger scope or evidence contradicts no execution')
    return {'schemaVersion': 1, 'kind': 'material-route-preworld-no-attempt', 'runId': run_id,
        'gameDate': game_date, 'route': settings['route'], 'verdict': 'no-route-attempt',
        'stage': 'waiting-for-world-main-ui-before-script-group', 'sourceSha256': sources,
        'rawLogSegments': pinned, 'recordDirectory': str(record_dir), 'worldWaitCount': len(waits),
        'ownedPid': pid, 'releasedNativeReservationSeconds': matches[0].get('reservedSeconds', 480)}


def write_route_no_attempt_review(root, run_id):
    """Write the separate audit under the caller-held RunLock; never edit old facts."""
    path = _no_attempt_path(root, run_id)
    proof = audit_route_no_attempt(root, run_id)
    if path.exists():
        if _json_file(path) != proof:
            raise ValueError('no-attempt existing review differs; original receipt preserved')
    else:
        _atomic(path, proof)
    return proof


def _verified_no_attempt_review(root, entry):
    path = _no_attempt_path(root, entry['runId'])
    if not path.exists():
        return False
    try:
        receipt = _object(_json_file(path), 'no-attempt receipt')
        if receipt.get('gameDate') != entry['gameDate'] or receipt.get('route') != normalize_route(entry['route']):
            return False
        fresh = audit_route_no_attempt(root, entry['runId'], segments=receipt.get('rawLogSegments'))
        return receipt == fresh
    except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError):
        return False


def load_route_config(path):
    raw = _object(_json_file(_safe_path(path)), 'private route config')
    if set(raw) - {'partyName', 'strategyName', 'requireZhongliShield', 'timeoutSeconds', 'route', 'overlapDistance', 'expectedTeam'}:
        raise ValueError('unsupported private route config field')
    _exact_fields(raw, {'strategyName': STRATEGY_NAME, 'requireZhongliShield': True}, 'route config')
    timeout = _integer(raw.get('timeoutSeconds', 480), 60, 480, 'route timeoutSeconds')
    if timeout % 60:
        raise ValueError('route timeoutSeconds must be full minutes')
    clean = {'partyName': _text(raw.get('partyName'), 'route partyName'),
             'strategyName': STRATEGY_NAME, 'requireZhongliShield': True, 'timeoutSeconds': timeout,
             'route': normalize_route(raw.get('route')), 'overlapDistance': raw.get('overlapDistance', OVERLAP_DISTANCE)}
    if 'expectedTeam' in raw:
        clean['expectedTeam'] = normalize_expected_team(raw['expectedTeam'])
    return clean


def _verify_route_party_health(events, parameters, native, group_index, native_index):
    """Validate new engine health events when present; leave legacy archives intact."""
    matches = [(i, e) for i, e in events if e['task'] == 'material-route-party-health']
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError('route requires at most one scoped party-health event')
    health_i, health = matches[0]
    starts = [(i, e) for i, e in events if e['task'] == MODE and e.get('status') == 'started']
    if len(starts) != 1 or not group_index < starts[0][0] < health_i < native_index:
        raise ValueError('party health is outside the native start/end interval')
    _exact_fields(_object(starts[0][1].get('parameterEvidence'), 'health native start'), parameters, 'health native start')
    expected = parameters.get('expectedTeam')
    if expected is None:
        expected = native.get('actualTeam') if native.get('status') == 'completed' else health.get('actualTeam')
    expected = normalize_expected_team(expected)
    _exact_fields(health, {'runId': parameters['runId'], 'status': 'verified', 'actualTeam': expected,
        'minimumHpRatio': .8, 'activeSlotRestored': 4, 'teamObservationCount': 2,
        'noFood': True, 'noRevive': True}, 'route party health')
    if native.get('status') == 'completed' or native.get('actualTeam'):
        if native.get('actualTeam') != expected:
            raise ValueError('party health differs from native actual team')
    teams = [(i, e) for i, e in events if e['task'] == 'material-route-team']
    if 'expectedTeam' in parameters:
        if len(teams) != 1 or not starts[0][0] < teams[0][0] < health_i:
            raise ValueError('party health requires preceding exact-slot team proof')
        _exact_fields(teams[0][1], {'status': 'verified', 'expectedTeam': expected, 'actualTeam': expected,
            'slots': [1, 2, 3, 4], 'twoFrames': True}, 'health team')
    elif teams:
        raise ValueError('party health team event lacks pinned expected slots')
    if any(i <= health_i for i, e in events if e['task'] in {'material-route-fight', 'material-route-shield-cast'}):
        raise ValueError('route combat began before current party health proof')
    rows = health.get('slotHealthEvidence')
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError('party health requires four independently verified slots')
    for slot, (name, row) in enumerate(zip(expected, rows), 1):
        _exact_fields(_object(row, 'route slot health'), {'slot': slot, 'name': name, 'observations': 2,
            'identityVerified': True, 'identityObservations': 2, 'ocrMatchingObservations': 2}, 'route slot health')
        hp, maximum, ratio = (row.get(key) for key in ('hp', 'maxHp', 'ratio'))
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (hp, maximum, ratio))
                or not 0 < hp <= maximum or hp / maximum < .8 or abs(ratio - hp / maximum) > 1e-9):
            raise ValueError('route party health is dead, below80%, unknown or contradictory')
    return health


def verify_material_route_report(text, bettergi_dir, run_id, group, config_name, execution_outcome='running', *, inventory_only=False):
    """A JS return is insufficient: reconcile scope, native end, points and actual counts."""
    _run_id(run_id)
    analysis = {'schemaVersion': 1, 'outcome': 'unknown', 'tasks': [{'name': TASK_NAME,
        'status': 'unknown', 'reason': 'route evidence not independently verified', 'evidence': []}],
        'rewards': {}, 'resinEvents': [], 'warnings': [], 'flowEnded': False, 'cultivation': None,
        'materialRoute': {'mode': MODE, 'reportVerified': False, 'routeCompleted': False,
                          'materialGainsVerified': False, 'targetReached': False}}
    lines = text.splitlines()
    try:
        settings = _object(group['Projects'][0]['JsScriptSettingsObject'], 'route settings')
        expected_group = build_route_group(run_id, {'partyName': settings['partyName'], 'expectedTeam': settings.get('expectedTeam')},
            settings['route'], game_date=settings['gameDate'], max_minutes=settings['maxMinutes'],
            timeout_seconds=settings.get('timeoutSeconds'))
        if group != expected_group:
            raise ValueError('material route generated group changed')
        references = [v for line in lines if (v := _config_reference(line))]
        groups = [(i, m) for i, line in enumerate(lines) if (m := _GROUP_MARKER_RE.search(line))]
        if not references or set(references) != {config_name} or len(groups) != 1 or groups[0][1].groups() != ('1', '1') or any(_MARKER_RE.search(line) for line in lines):
            raise ValueError('route needs unique current config and one JS group')
        allowed = {TASK_NAME, MODE, 'material-route-fight', 'material-route-shield-cast', 'material-route-inventory', 'material-route-team', 'material-route-party-health'}
        events = []
        for i, line in enumerate(lines):
            event = _event_from_line(line)
            if event is None and '[AUTO_GAME_EVENT]' in line:
                raise ValueError('malformed material route machine event')
            if event is None:
                continue
            if event.get('task') not in allowed or event.get('runId') != run_id or i <= groups[0][0]:
                raise ValueError('foreign or unscoped material route event')
            if (event.get('rewardClaimed') is True or event.get('resinSpendEnabled') is True
                    or event.get('rewards') not in (None, {}) or event.get('resinEvents') not in (None, [])
                    or any(event.get(k) not in (None, 0) for k in ('originalResinSpent', 'condensedResinSpent', 'fragileResinUsed', 'transientResinUsed'))):
                raise ValueError('route contains resin/reward claims')
            events.append((i, event))
        if (_parse_rewards(lines) or _parse_resin_events(lines) or any(re.search(r'已进入.*领奖|奖励领取成功|获得奖励|成功分解圣遗物|已使用.*树脂', line) for line in lines)):
            raise ValueError('route contains reward/resin log markers')
        plugins = [(i, e) for i, e in events if e['task'] == TASK_NAME]
        if len(plugins) != 1:
            raise ValueError('route needs one scoped plugin report event')
        plugin_i, plugin = plugins[0]
        _exact_fields(plugin, {'runId': run_id, 'gameDate': settings['gameDate'], 'mode': MODE,
            'reportRelativePath': f'record/{run_id}.json', 'evidenceVerified': True}, 'plugin')
        path = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('material route report missing or too large')
        report = _object(_json_file(path), 'material route report')
        _exact_fields(report, {'schemaVersion': 1, 'runId': run_id, 'gameDate': settings['gameDate'],
            'mode': MODE, 'partyName': settings['partyName'], 'strategyName': STRATEGY_NAME,
            'requireZhongliShield': True, 'noResinSpend': True, 'noCrafting': True,
            'noUpgrade': True, 'targetReached': False, 'rewards': {}, 'resinEvents': []}, 'report')
        if normalize_route(report.get('route')) != settings['route']:
            raise ValueError('route report identity changed')
        # Retain scoped raw evidence even if a later independent check fails.
        analysis['materialRouteReport'] = report
        status = report.get('status')
        if status not in ('success', 'failed', 'unknown', 'blocked', 'cancelled', 'timeout') or plugin.get('status') != status:
            raise ValueError('invalid or contradictory route status')
        start, finish = (_timestamp(report.get(k), k) for k in ('startedAt', 'finishedAt'))
        seconds = (finish - start).total_seconds()
        wall = report.get('wallSeconds')
        if type(wall) not in (int, float) or not math.isfinite(wall) or not 0 <= seconds <= 16 * 60 + 5 or abs(wall - seconds) > 2:
            raise ValueError('route report timing is invalid or exceeds runner budget')
        if game_date_at(start) != settings['gameDate'] or game_date_at(finish) != settings['gameDate']:
            raise ValueError('route report crossed game-day boundary')
        inventories = {}
        inventory_errors = []
        for phase in ('before', 'after'):
            field = phase + 'Inventory'
            if report.get(field) is None:
                inventory_errors.append(phase + ' actual inventory is missing')
                continue
            try:
                actual = _counts(report[field])
            except (ValueError, TypeError) as error:
                inventory_errors.append(phase + ': ' + str(error))
                continue
            scans = [(i, e) for i, e in events if e['task'] == 'material-route-inventory' and e.get('phase') == phase]
            if (len(scans) != 1 or scans[0][1].get('counts') != actual
                    or any(type(v) is not int for v in scans[0][1].get('counts', {}).values())):
                inventory_errors.append(phase + ' actual inventory differs from scoped scan evidence')
                continue
            try:
                _exact_fields(scans[0][1], {'gameDate': settings['gameDate'], 'status': 'exact'}, 'inventory')
            except ValueError as error:
                inventory_errors.append(phase + ': ' + str(error))
                continue
            inventories[phase] = actual
            analysis['materialRoute'].update(actualInventory=copy.deepcopy(inventories))
        native_ends = [(i, e) for i, e in events if e['task'] == MODE and e.get('status') != 'started']
        if len(native_ends) != 1:
            raise ValueError('route needs exactly one native terminal event')
        native_i, native = native_ends[0]
        if not groups[0][0] < native_i < plugin_i:
            raise ValueError('native route terminal event is outside report interval')
        parameters = _native_parameters(settings)
        _exact_fields(native, {k: parameters[k] for k in ('runId', 'routePath', 'sha256')}, 'native')
        _exact_fields(_object(native.get('parameterEvidence'), 'native actual parameters'), parameters, 'native readback')
        _exact_fields(_object(report.get('parameterEvidence'), 'parameterEvidence'), parameters, 'actual native parameters')
        point_evidence = []
        for i, event in events:
            if event['task'] == 'material-route-fight':
                _exact_fields(event, {'routePath': parameters['routePath'], 'sha256': parameters['sha256']}, 'fight scope')
                point_evidence.append({'line': i + 1, 'status': event.get('status'), 'pointId': event.get('pointId'), **_point(event)})
        analysis['materialRoute']['fightPointEvidence'] = point_evidence
        native_result = _object(report.get('nativeResult'), 'nativeResult')
        for key in ('status', 'runId', 'routePath', 'sha256', 'completedFightPoints', 'observedHoldCasts', 'cleanupCompleted', 'actualTeam'):
            if type(native_result.get(key)) is not type(native.get(key)) or native_result.get(key) != native.get(key):
                raise ValueError('route native return and terminal event disagree')
        # C# double JSON 341889.0 becomes JS number JSON 341889 after
        # parse/stringify. Only elapsed time permits that lossless numeric form.
        returned_elapsed, native_elapsed = native_result.get('elapsedMs'), native.get('elapsedMs')
        if (type(returned_elapsed) not in (int, float) or type(native_elapsed) not in (int, float)
                or not math.isfinite(returned_elapsed) or not math.isfinite(native_elapsed)
                or returned_elapsed != native_elapsed):
            raise ValueError('route native return and terminal elapsed time disagree')
        if type(native_elapsed) not in (int, float) or not math.isfinite(native_elapsed) or not 0 <= native_elapsed <= parameters['timeoutSeconds'] * 1000 + 5000:
            raise ValueError('route native elapsed time exceeds bound')
        health = _verify_route_party_health(events, parameters, native, groups[0][0], native_i)
        if health is not None:
            analysis['materialRoute'].update(partyHealthVerified=True, slotHealthEvidence=health['slotHealthEvidence'])
        if native.get('status') == 'completed':
            if status not in ('success', 'unknown'):
                raise ValueError('non-success report contradicts native completion')
            _exact_fields(native, {'status': 'completed', 'cleanupCompleted': True,
                'shieldEvidence': 'hold_skill_cooldown_observed', 'noResinSpend': True,
                'noCrafting': True, 'noUpgrade': True, 'noFood': True, 'noRevive': True,
                'ordinaryPick': True, 'mainUiRestored': True}, 'native completion')
            if report.get('nativeReturnCompleted') is not True or any(_FAILURE_RE.search(line) for line in lines[groups[0][0]:]):
                raise ValueError('route claimed completion contradicts a failure')
            casts = _integer(native.get('observedHoldCasts'), 1, 10000, 'observed hold casts')
            team = native.get('actualTeam')
            if (not isinstance(team, list) or len(team) != 4 or any(not isinstance(name, str) or not name.strip() for name in team)
                    or len(set(team)) != 4 or '钟离' not in team):
                raise ValueError('native route actual team does not verify Zhongli')
            if 'expectedTeam' in settings and team != settings['expectedTeam']:
                raise ValueError('native route actual team differs from expected slots')
            native_starts = [(i, e) for i, e in events if e['task'] == MODE and e.get('status') == 'started']
            if len(native_starts) != 1 or not groups[0][0] < native_starts[0][0] < native_i:
                raise ValueError('route requires unique native start and end')
            _exact_fields(_object(native_starts[0][1].get('parameterEvidence'), 'native start parameters'), parameters, 'native start')
            teams = [(i, e) for i, e in events if e['task'] == 'material-route-team']
            if 'expectedTeam' in settings:
                if len(teams) != 1 or not native_starts[0][0] < teams[0][0] < native_i:
                    raise ValueError('route requires one scoped two-frame exact-slot team event')
                team_i, team_event = teams[0]
                _exact_fields(team_event, {'status': 'verified', 'expectedTeam': settings['expectedTeam'],
                    'actualTeam': settings['expectedTeam'], 'slots': [1, 2, 3, 4], 'twoFrames': True}, 'team')
                if type(team_event.get('skipPartyMenu')) is not bool:
                    raise ValueError('team skipPartyMenu must be an actual boolean')
                if any(i < team_i for i, e in events if e['task'] in {'material-route-fight', 'material-route-shield-cast'}):
                    raise ValueError('combat began before exact-slot team verification')
            elif teams:
                raise ValueError('team event without pinned expected slots')
            fights = [(i, e) for i, e in events if e['task'] == 'material-route-fight' and e.get('status') == 'cleared']
            expected = settings['route']['fightPoints']
            completed = native.get('completedFightPoints')
            if (not isinstance(completed, list) or any(not isinstance(p, str) for p in completed)
                    or len(set(completed)) != len(completed) or len(fights) != len(expected)
                    or _integer(native.get('fightPointCount'), 1, 500, 'fightPointCount') != len(expected)):
                raise ValueError('route fight cleanup coverage incomplete')
            observed = []
            for i, event in fights:
                _exact_fields(event, {'routePath': parameters['routePath'], 'sha256': parameters['sha256'],
                    'battleEndDetected': True, 'enemyObserved': True,
                    'evidence': 'enemy_bloodbar_observed_then_party_setup_progress_white_yellow_detected_and_pickup_returned'}, 'fight')
                if not groups[0][0] < i < native_i:
                    raise ValueError('fight outside native interval')
                observed.append(_point(event))
            if observed != expected:
                raise ValueError('route cleaned points differ from pinned coordinates')
            if completed != [event.get('pointId') for _, event in fights]:
                raise ValueError('native completed points disagree with fight events')
            shield_events = [(i, e) for i, e in events if e['task'] == 'material-route-shield-cast']
            if len(shield_events) != casts:
                raise ValueError('native observed casts disagree with shield events')
            for i, event in shield_events:
                _exact_fields(event, {'routePath': parameters['routePath'], 'sha256': parameters['sha256'],
                    'status': 'cast_observed', 'evidence': 'hold_skill_cooldown_observed'}, 'shield')
                if not native_starts[0][0] < i < native_i:
                    raise ValueError('shield evidence outside route interval')
            analysis['materialRoute'].update(routeCompleted=True, observedHoldCasts=casts, actualTeam=team)
            if status == 'success':
                if inventory_errors or set(inventories) != {'before', 'after'}:
                    raise ValueError('; '.join(inventory_errors) or 'actual inventory incomplete')
                if not (next(i for i, e in events if e['task'] == 'material-route-inventory' and e.get('phase') == 'before') < native_starts[0][0]
                        < native_i < next(i for i, e in events if e['task'] == 'material-route-inventory' and e.get('phase') == 'after') < plugin_i):
                    raise ValueError('inventory phases do not surround native route')
                gains = {k: inventories['after'][k] - inventories['before'][k] for k in MATERIAL_IDS}
                claimed_gains = report.get('materialGains')
                if (not isinstance(claimed_gains, dict) or any(type(v) is not int for v in claimed_gains.values())
                        or any(v < 0 for v in gains.values()) or claimed_gains != gains or report.get('materialGainsVerified') is not True):
                    raise ValueError('material inventory delta contradicts report')
                analysis['materialRoute'].update(materialGainsVerified=True,
                    materialGains=gains, zeroGains=not any(gains.values()))
                analysis['tasks'][0].update(status='success', reason='native route cleanup and actual inventory independently verified',
                    evidence=[{'line': native_i + 1, 'text': lines[native_i]}])
            else:
                analysis['warnings'].extend(inventory_errors)
                analysis['tasks'][0].update(status='unknown', reason='native route completed; material gains remain unverified')
        else:
            if native.get('status') == 'completed':
                raise ValueError('non-success report contradicts native completion')
            if native.get('status') not in ('failed', 'cancelled', 'timeout'):
                raise ValueError('invalid native route terminal status')
            analysis['tasks'][0].update(status='unknown' if status == 'unknown' else 'failed', reason='route did not complete; same-day replay remains blocked')
            if inventory_only and not inventory_errors and set(inventories) == {'before', 'after'}:
                starts = [(i, e) for i, e in events if e['task'] == MODE and e.get('status') == 'started']
                before_i = next(i for i, e in events if e['task'] == 'material-route-inventory' and e.get('phase') == 'before')
                after_i = next(i for i, e in events if e['task'] == 'material-route-inventory' and e.get('phase') == 'after')
                gains = {k: inventories['after'][k] - inventories['before'][k] for k in MATERIAL_IDS}
                if (len(starts) == 1 and before_i < starts[0][0] < native_i < after_i < plugin_i
                        and all(v >= 0 for v in gains.values()) and report.get('materialGains') == gains
                        and all(type(v) is int for v in report.get('materialGains', {}).values())
                        and report.get('materialGainsVerified') is True):
                    analysis['materialRoute'].update(materialGainsVerified=True, inventoryOnly=True,
                        materialGains=gains, zeroGains=not any(gains.values()))
        ends = [i for i, line in enumerate(lines) if '一条龙和配置组任务结束' in line]
        if len(ends) > 1:
            raise ValueError('multiple material route flow endings')
        analysis['flowEnded'] = len(ends) == 1 and ends[0] > plugin_i
        analysis['materialRoute'].update(reportVerified=True, reportPath=str(path), route=settings['route'], noResinSpend=True)
        analysis['materialRoute']['farmingSeconds'] = native_elapsed / 1000
        analysis['materialRouteReport'] = report
        task_status = analysis['tasks'][0]['status']
        analysis['outcome'] = ('completed' if task_status == 'success' and analysis['flowEnded'] and execution_outcome == 'exited'
            else 'partial' if task_status == 'success' else 'failed' if task_status == 'failed' else 'unknown')
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as error:
        analysis['tasks'][0].update(status='unknown', reason='route evidence not independently verified', evidence=[])
        analysis['materialRoute'].update(materialGainsVerified=False)
        analysis['warnings'].append('刀镡路线证据尚未核验：' + str(error))
    return analysis


verify_material_route_analysis = verify_material_route_report

SESSION_MODE = 'material-route-session'
RECOVERY_MODE = 'material-recovery'
RECOVERY_TASK_ID = 'auto-game-material-recovery'
RECOVERY_TASK_NAME = '材料安全恢复'

PREPARATION_MODE = 'party-preparation'
PREPARATION_TASK_ID = 'auto-game-party-preparation'
PREPARATION_TASK_NAME = '队伍免费恢复'
PREPARATION_STATUE = {'id': '4', 'country': '蒙德', 'area': '风起地',
    'x': -1265.917, 'y': 1928.381, 'arrivalX': -1266.3422, 'arrivalY': 1934.3658}
PREPARATION_FLAGS = {'noItemConsumption': True, 'noRevivalItemConsumption': True,
    'noResinSpend': True, 'noFood': True, 'noCrafting': True, 'noUpgrade': True}


def normalize_preparation_config(raw):
    raw = _object(raw, 'party preparation config')
    if set(raw) != {'expectedTeam', 'allowStatueRevival', 'timeoutSeconds'}:
        raise ValueError('preparation accepts only expectedTeam, allowStatueRevival and timeoutSeconds')
    _exact_fields(raw, {'allowStatueRevival': True, 'timeoutSeconds': 120}, 'preparation config')
    if type(raw['timeoutSeconds']) is not int:
        raise ValueError('preparation timeoutSeconds must be the integer 120')
    return {'expectedTeam': normalize_expected_team(raw['expectedTeam']),
        'allowStatueRevival': True, 'timeoutSeconds': 120}


def load_party_preparation_config(path):
    return normalize_preparation_config(_json_file(_safe_path(path)))


def inject_party_preparation_task(template):
    return _inject_material_task(template, PREPARATION_TASK_ID, PREPARATION_TASK_NAME)


def build_party_preparation_group(run_id, config, *, game_date):
    _run_id(run_id)
    _game_date(game_date)
    request = dict(runId=run_id, **normalize_preparation_config(config))
    return {'Name': PLUGIN_NAME + '_' + run_id, 'Projects': [{
        'Name': PREPARATION_TASK_NAME, 'FolderName': PLUGIN_NAME, 'Type': 'Javascript', 'Status': 'Enabled',
        'Schedule': 'Daily', 'RunNum': 1, 'AllowJsNotification': False,
        'JsScriptSettingsObject': {'runId': run_id, 'gameDate': game_date, 'mode': PREPARATION_MODE,
            'preparationJson': json.dumps(request, ensure_ascii=False, separators=(',', ':')),
            'originalResinBudget': 0, 'condensedResinBudget': 0, 'fragileResinBudget': 0,
            'transientResinBudget': 0, 'allowCrafting': False, 'allowUpgrade': False}}]}


def verify_party_preparation_report(text, bettergi_dir, run_id, group, config_name, execution_outcome='running'):
    """Verify free statue healing/revival independently; never read farming leases or inventory."""
    analysis = {'schemaVersion': 1, 'outcome': 'unknown', 'tasks': [{'name': PREPARATION_TASK_NAME,
        'status': 'unknown', 'reason': 'party preparation evidence not independently verified', 'evidence': []}],
        'rewards': {}, 'resinEvents': [], 'warnings': [], 'flowEnded': False, 'cultivation': None,
        'partyPreparation': {'mode': PREPARATION_MODE, 'reportVerified': False, 'preparationCompleted': False}}
    try:
        _run_id(run_id)
        settings = _object(group['Projects'][0]['JsScriptSettingsObject'], 'preparation settings')
        request = _object(json.loads(settings['preparationJson']), 'preparation request')
        config = {key: request[key] for key in ('expectedTeam', 'allowStatueRevival', 'timeoutSeconds')}
        if group != build_party_preparation_group(run_id, config, game_date=settings['gameDate']):
            raise ValueError('preparation group or bounded request changed')
        lines = text.splitlines()
        references = [value for line in lines if (value := _config_reference(line))]
        groups = [(i, match) for i, line in enumerate(lines) if (match := _GROUP_MARKER_RE.search(line))]
        if (not references or set(references) != {config_name} or len(groups) != 1
                or groups[0][1].groups() != ('1', '1') or any(_MARKER_RE.search(line) for line in lines)):
            raise ValueError('preparation needs unique current config and exactly one isolated JS group')
        events = []
        for i, line in enumerate(lines):
            event = _event_from_line(line)
            if event is None and '[AUTO_GAME_EVENT]' in line:
                raise ValueError('malformed preparation event')
            if event is None:
                continue
            if event.get('task') not in {PREPARATION_MODE, PREPARATION_TASK_NAME} or event.get('runId') != run_id or i <= groups[0][0]:
                raise ValueError('preparation contains foreign, farming, inventory or combat event')
            if (event.get('rewardClaimed') is True or event.get('resinSpendEnabled') is True
                    or event.get('rewards') not in (None, {}) or event.get('resinEvents') not in (None, [])
                    or any(event.get(key) not in (None, 0) for key in ('originalResinSpent', 'condensedResinSpent', 'fragileResinUsed', 'transientResinUsed'))):
                raise ValueError('preparation contains resource claims')
            events.append((i, event))
        if (_parse_rewards(lines) or _parse_resin_events(lines)
                or any(re.search(r'奖励领取成功|获得奖励|成功分解圣遗物|已使用.*树脂|使用复苏道具|食用料理', line) for line in lines)):
            raise ValueError('preparation contains item, reward or resin log markers')
        plugins = [(i, e) for i, e in events if e['task'] == PREPARATION_TASK_NAME]
        starts = [(i, e) for i, e in events if e['task'] == PREPARATION_MODE and e.get('status') == 'started']
        finishes = [(i, e) for i, e in events if e['task'] == PREPARATION_MODE and e.get('status') != 'started']
        if len(plugins) != 1 or len(starts) != 1 or len(finishes) != 1:
            raise ValueError('preparation requires one native start, terminal and JS report')
        plugin_i, plugin = plugins[0]
        native_i, native = finishes[0]
        if not groups[0][0] < starts[0][0] < native_i < plugin_i:
            raise ValueError('preparation lifecycle order changed')
        for event in (starts[0][1], native):
            if not _lossless_json_equal(event.get('parameterEvidence'), request):
                raise ValueError('native preparation parameters differ')
            if not _lossless_json_equal(event.get('statue'), PREPARATION_STATUE):
                raise ValueError('native preparation statue differs from fixed engine catalog')
        _exact_fields(native, PREPARATION_FLAGS, 'preparation zero-item scope')
        if 'noRevive' in native:
            raise ValueError('preparation must not claim noRevive because statue revival is permitted')
        elapsed = native.get('elapsedMs')
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= 125000:
            raise ValueError('invalid preparation elapsed time')
        if native.get('status') not in ('completed', 'failed', 'timeout', 'cancelled'):
            raise ValueError('invalid native preparation status')
        completed = native['status'] == 'completed'
        if completed:
            _exact_fields(native, {'evidenceVerified': True, 'loadingObserved': True, 'positionVerified': True,
                'mainUiRestored': True, 'grounded': True, 'noRevivePrompt': True, 'teamVerified': True,
                'activeSlotRestored': 4, 'cleanupCompleted': True, 'revivalMayHaveOccurred': True,
                'teamObservationCount': 2, 'statueProximityVerified': True, 'statueProximityObservationCount': 2,
                'actualTeam': request['expectedTeam']}, 'preparation completion')
            if type(native['teamObservationCount']) is not int or type(native['activeSlotRestored']) is not int:
                raise ValueError('preparation team and active slot counts must be integers')
            position = _point(native.get('actualPosition'))
            if math.hypot(position['x'] - PREPARATION_STATUE['arrivalX'], position['y'] - PREPARATION_STATUE['arrivalY']) > 20:
                raise ValueError('preparation arrival differs from fixed statue')
            if math.hypot(position['x'] - PREPARATION_STATUE['x'], position['y'] - PREPARATION_STATUE['y']) > 5:
                raise ValueError('preparation lacks actual position within five units of fixed statue')
            if 'statueApproachPerformed' in native and type(native['statueApproachPerformed']) is not bool:
                raise ValueError('statue approach observation must be an actual boolean')
            health = native.get('slotHealthEvidence')
            if not isinstance(health, list) or len(health) != 4:
                raise ValueError('preparation requires four current health proofs')
            for slot, (name, row) in enumerate(zip(request['expectedTeam'], health), 1):
                _exact_fields(_object(row, 'slot health'), {'slot': slot, 'name': name, 'observations': 2,
                    'identityVerified': True, 'identityObservations': 2, 'ocrMatchingObservations': 2}, 'slot health identity')
                if any(type(row[key]) is not int for key in ('slot', 'observations', 'identityObservations', 'ocrMatchingObservations')):
                    raise ValueError('slot identity evidence counts must be integers')
                hp, maximum, ratio = (row.get(k) for k in ('hp', 'maxHp', 'ratio'))
                if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (hp, maximum, ratio))
                        or not 0 < hp <= maximum or hp / maximum < .8 or abs(ratio - hp / maximum) > 1e-9):
                    raise ValueError('current health is dead, too low or inconsistent')
        elif native.get('evidenceVerified') is not False:
            raise ValueError('failed preparation cannot claim verified completion')
        _exact_fields(plugin, {'runId': run_id, 'gameDate': settings['gameDate'], 'mode': PREPARATION_MODE,
            'reportRelativePath': 'record/' + run_id + '.json', 'evidenceVerified': True}, 'preparation plugin')
        path = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('preparation report missing or too large')
        report = _object(_json_file(path), 'preparation report')
        _exact_fields(report, dict(PREPARATION_FLAGS, schemaVersion=1, runId=run_id, gameDate=settings['gameDate'],
            mode=PREPARATION_MODE, allowStatueRevival=True, targetReached=False, rewards={}, resinEvents=[]), 'preparation report')
        if 'noRevive' in report or not _lossless_json_equal(report.get('parameterEvidence'), request):
            raise ValueError('preparation report scope or parameters changed')
        if not _lossless_json_equal(report.get('nativeResult'), native):
            raise ValueError('native preparation return differs from terminal event')
        if report.get('status') not in ('success', 'failed', 'unknown', 'cancelled', 'timeout') or plugin.get('status') != report['status']:
            raise ValueError('contradictory preparation report status')
        if completed and report['status'] not in ('success', 'unknown') or not completed and report['status'] == 'success':
            raise ValueError('JS preparation success contradicts native result')
        start, finish = (_timestamp(report.get(key), key) for key in ('startedAt', 'finishedAt'))
        wall = report.get('wallSeconds')
        if (type(wall) not in (int, float) or not math.isfinite(wall) or not 0 <= wall <= 300
                or not 0 <= (finish - start).total_seconds() <= 300 or abs(wall - (finish - start).total_seconds()) > 2
                or elapsed > wall * 1000 + 2000 or game_date_at(start) != settings['gameDate'] or game_date_at(finish) != settings['gameDate']):
            raise ValueError('preparation exceeds five-minute bound or crosses game day')
        ends = [i for i, line in enumerate(lines) if '一条龙和配置组任务结束' in line]
        if len(ends) > 1:
            raise ValueError('preparation has multiple flow endings')
        analysis['flowEnded'] = len(ends) == 1 and ends[0] > plugin_i
        analysis['partyPreparationReport'] = report
        analysis['partyPreparation'].update(reportVerified=True, preparationCompleted=completed,
            nativeResult=native, reportPath=str(path), allowStatueRevival=True, noRouteExecution=True,
            wallSeconds=wall, preparationSeconds=elapsed / 1000, **PREPARATION_FLAGS)
        task_status = ('success' if completed and report['status'] == 'success'
            else 'failed' if not completed and report['status'] != 'unknown' else 'unknown')
        analysis['tasks'][0].update(status=task_status, reason='fixed free statue and four current healthy slots verified'
            if task_status == 'success' else 'party preparation did not independently complete',
            evidence=[{'line': plugin_i + 1, 'text': lines[plugin_i]}])
        analysis['outcome'] = ('completed' if task_status == 'success' and analysis['flowEnded'] and execution_outcome == 'exited'
            else 'partial' if task_status == 'success' else 'failed' if task_status == 'failed' else 'unknown')
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration) as error:
        analysis['warnings'].append('队伍免费恢复证据尚未核验：' + str(error))
    return analysis


def normalize_expected_team(value):
    if (not isinstance(value, list) or len(value) != 4
            or any(not isinstance(name, str) or not name.strip() or name != name.strip() for name in value)
            or len(set(value)) != 4 or '钟离' not in value):
        raise ValueError('expectedTeam must identify exactly four distinct slots including Zhongli')
    return list(value)


def inject_material_recovery_task(template):
    return _inject_material_task(template, RECOVERY_TASK_ID, RECOVERY_TASK_NAME)


def normalize_recovery_config(raw):
    raw = _object(raw, 'material recovery config')
    if set(raw) != {'partyName', 'expectedTeam', 'safeHub', 'timeoutSeconds'}:
        raise ValueError('recovery config accepts only partyName, expectedTeam, safeHub and timeoutSeconds')
    _exact_fields(raw, {'safeHub': 'mondstadt-city'}, 'recovery config')
    return {'partyName': _text(raw['partyName'], 'partyName'), 'expectedTeam': normalize_expected_team(raw['expectedTeam']),
        'safeHub': 'mondstadt-city', 'timeoutSeconds': _integer(raw['timeoutSeconds'], 1, 60, 'recovery timeoutSeconds')}


def load_material_recovery_config(path):
    return normalize_recovery_config(_json_file(_safe_path(path)))


def build_route_recovery_group(run_id, config, *, game_date):
    _run_id(run_id)
    _game_date(game_date)
    config = normalize_recovery_config(config)
    request = dict(config, runId=run_id, sessionId=run_id, stage='startup')
    return {'Name': PLUGIN_NAME + '_' + run_id, 'Projects': [{
        'Name': RECOVERY_TASK_NAME, 'FolderName': PLUGIN_NAME, 'Type': 'Javascript', 'Status': 'Enabled',
        'Schedule': 'Daily', 'RunNum': 1, 'AllowJsNotification': False,
        'JsScriptSettingsObject': {'runId': run_id, 'gameDate': game_date, 'mode': RECOVERY_MODE,
            'recoveryJson': json.dumps(request, ensure_ascii=False, separators=(',', ':')),
            'originalResinBudget': 0, 'condensedResinBudget': 0, 'fragileResinBudget': 0,
            'transientResinBudget': 0, 'allowCrafting': False, 'allowUpgrade': False}}]}


def _lossless_json_equal(first, second):
    if type(first) in (int, float) and type(second) in (int, float):
        return math.isfinite(first) and math.isfinite(second) and first == second
    if type(first) is not type(second):
        return False
    if isinstance(first, dict):
        return set(first) == set(second) and all(_lossless_json_equal(first[key], second[key]) for key in first)
    if isinstance(first, list):
        return len(first) == len(second) and all(_lossless_json_equal(a, b) for a, b in zip(first, second))
    return first == second


def verify_material_recovery_report(text, bettergi_dir, run_id, group, config_name, execution_outcome='running'):
    """Verify one resource-free safe-hub operation without route selection or farming leases."""
    analysis = {'schemaVersion': 1, 'outcome': 'unknown', 'tasks': [{'name': RECOVERY_TASK_NAME,
        'status': 'unknown', 'reason': 'material safe-hub recovery evidence not independently verified', 'evidence': []}],
        'rewards': {}, 'resinEvents': [], 'warnings': [], 'flowEnded': False, 'cultivation': None,
        'materialRecovery': {'mode': RECOVERY_MODE, 'reportVerified': False, 'recoveryCompleted': False,
            'noRouteExecution': False}}
    try:
        _run_id(run_id)
        settings = _object(group['Projects'][0]['JsScriptSettingsObject'], 'recovery settings')
        request = _object(json.loads(settings['recoveryJson']), 'recovery request')
        config = {key: request[key] for key in ('partyName', 'expectedTeam', 'safeHub', 'timeoutSeconds')}
        if group != build_route_recovery_group(run_id, config, game_date=settings['gameDate']):
            raise ValueError('recovery generated group or request changed')
        lines = text.splitlines()
        references = [value for line in lines if (value := _config_reference(line))]
        groups = [(i, match) for i, line in enumerate(lines) if (match := _GROUP_MARKER_RE.search(line))]
        if (not references or set(references) != {config_name} or len(groups) != 1
                or groups[0][1].groups() != ('1', '1') or any(_MARKER_RE.search(line) for line in lines)):
            raise ValueError('recovery requires unique current config and exactly one isolated JS group')
        events = []
        for i, line in enumerate(lines):
            event = _event_from_line(line)
            if event is None and '[AUTO_GAME_EVENT]' in line:
                raise ValueError('malformed recovery event')
            if event is None:
                continue
            if event.get('task') not in {'material-route-recovery', RECOVERY_TASK_NAME} or event.get('runId') != run_id or i <= groups[0][0]:
                raise ValueError('recovery-only run contains foreign, route, inventory, fight or loot evidence')
            if (event.get('rewardClaimed') is True or event.get('resinSpendEnabled') is True
                    or event.get('rewards') not in (None, {}) or event.get('resinEvents') not in (None, [])
                    or any(event.get(key) not in (None, 0) for key in ('originalResinSpent', 'condensedResinSpent', 'fragileResinUsed', 'transientResinUsed'))):
                raise ValueError('recovery run contains resource claims')
            events.append((i, event))
        if (_parse_rewards(lines) or _parse_resin_events(lines)
                or any(re.search(r'奖励领取成功|获得奖励|成功分解圣遗物|已使用.*树脂', line) for line in lines)):
            raise ValueError('recovery run contains forbidden reward or resource log markers')
        plugins = [(i, event) for i, event in events if event['task'] == RECOVERY_TASK_NAME]
        if len(plugins) != 1:
            raise ValueError('recovery requires exactly one JS report event')
        plugin_i, plugin = plugins[0]
        _exact_fields(plugin, {'runId': run_id, 'gameDate': settings['gameDate'], 'mode': RECOVERY_MODE,
            'reportRelativePath': 'record/' + run_id + '.json', 'evidenceVerified': True}, 'recovery plugin')
        path = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('recovery report missing or too large')
        report = _object(_json_file(path), 'recovery report')
        _exact_fields(report, {'schemaVersion': 1, 'runId': run_id, 'sessionId': run_id,
            'gameDate': settings['gameDate'], 'mode': RECOVERY_MODE, 'noResinSpend': True,
            'noFood': True, 'noRevive': True, 'noCrafting': True, 'noUpgrade': True, 'targetReached': False,
            'rewards': {}, 'resinEvents': []}, 'recovery report')
        if 'parameterEvidence' in report and report['parameterEvidence'] != request:
            raise ValueError('recovery report requested parameters changed')
        analysis['materialRecoveryReport'] = report
        if report.get('status') not in ('success', 'failed', 'unknown', 'cancelled', 'timeout') or plugin.get('status') != report['status']:
            raise ValueError('invalid or contradictory recovery status')
        start, finish = (_timestamp(report.get(key), key) for key in ('startedAt', 'finishedAt'))
        wall = report.get('wallSeconds')
        if (type(wall) not in (int, float) or not math.isfinite(wall) or not 0 <= wall <= 4 * 60 + 5
                or not 0 <= (finish - start).total_seconds() <= 4 * 60 + 5
                or abs(wall - (finish - start).total_seconds()) > 2
                or game_date_at(start) != settings['gameDate'] or game_date_at(finish) != settings['gameDate']):
            raise ValueError('recovery timing exceeds four-minute outer bound or crosses game day')
        payload = dict(config, sessionId=run_id)
        native = _verify_recovery(events, {'runId': run_id}, payload, 'startup', groups[0][0], plugin_i)
        if len([event for _, event in events if event['task'] == 'material-route-recovery']) != 2:
            raise ValueError('recovery-only run needs one native start and one terminal event')
        if native.get('parameterEvidence') != request:
            raise ValueError('native recovery actual request differs from bounded settings')
        returned = _object(report.get('nativeResult'), 'recovery nativeResult')
        if not _lossless_json_equal(returned, native):
            raise ValueError('recovery native return disagrees with terminal machine event')
        completed = native['status'] == 'completed'
        if completed and report['status'] not in ('success', 'unknown') or not completed and report['status'] == 'success':
            raise ValueError('JS recovery success contradicts native result')
        ends = [i for i, line in enumerate(lines) if '一条龙和配置组任务结束' in line]
        if len(ends) > 1:
            raise ValueError('recovery has multiple flow endings')
        analysis['flowEnded'] = len(ends) == 1 and ends[0] > plugin_i
        analysis['materialRecovery'].update(reportVerified=True, noRouteExecution=True, recoveryCompleted=completed,
            nativeResult=native, reportPath=str(path), noResinSpend=True, noFood=True, noRevive=True,
            wallSeconds=wall, recoverySeconds=native['elapsedMs'] / 1000)
        task_status = ('success' if completed and report['status'] == 'success'
            else 'failed' if native['status'] in ('failed', 'cancelled', 'timeout') and report['status'] != 'unknown' else 'unknown')
        analysis['tasks'][0].update(status=task_status, reason='fixed safe hub, exact team and zero-resource scope verified'
            if task_status == 'success' else 'safe-hub recovery did not independently complete',
            evidence=[{'line': plugin_i + 1, 'text': lines[plugin_i]}])
        analysis['outcome'] = ('completed' if task_status == 'success' and analysis['flowEnded'] and execution_outcome == 'exited'
            else 'partial' if task_status == 'success' else 'failed' if task_status == 'failed' else 'unknown')
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration) as error:
        analysis['warnings'].append('材料安全恢复证据尚未核验：' + str(error))
        analysis['materialRecovery'].update(reportVerified=False, recoveryCompleted=False, noRouteExecution=False)
        analysis['outcome'] = 'unknown'
        analysis['tasks'][0].update(status='unknown', reason='material safe-hub recovery evidence not independently verified', evidence=[])
    return analysis


def load_route_session_config(path):
    return normalize_session_config(_json_file(_safe_path(path)))


def normalize_session_config(raw):
    raw = _object(raw, 'route session config')
    if set(raw) - {'partyName', 'expectedTeam', 'strategyName', 'requireZhongliShield', 'safeHub', 'segments', 'overlapDistance'}:
        raise ValueError('unsupported route session config field')
    _exact_fields(raw, {'strategyName': STRATEGY_NAME, 'requireZhongliShield': True, 'safeHub': 'mondstadt-city'}, 'session config')
    rows = raw.get('segments')
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError('route session requires exactly two segments')
    clean = {'partyName': _text(raw.get('partyName'), 'partyName'),
        'expectedTeam': normalize_expected_team(raw.get('expectedTeam')), 'strategyName': STRATEGY_NAME,
        'requireZhongliShield': True, 'safeHub': 'mondstadt-city',
        'overlapDistance': raw.get('overlapDistance', OVERLAP_DISTANCE), 'segments': []}
    for row in rows:
        row = _object(row, 'route segment')
        if set(row) != {'route', 'timeoutSeconds'}:
            raise ValueError('segment needs only route and timeoutSeconds')
        clean['segments'].append({'route': normalize_route(row['route']),
            'timeoutSeconds': _integer(row['timeoutSeconds'], 60, 480, 'segment timeoutSeconds')})
    return clean


def build_route_session_group(session_id, config, *, game_date):
    _run_id(session_id)
    _game_date(game_date)
    config = normalize_session_config(config)
    payload = {k: copy.deepcopy(config[k]) for k in ('partyName', 'expectedTeam', 'strategyName', 'requireZhongliShield', 'safeHub')}
    payload.update(schemaVersion=1, sessionId=session_id, gameDate=game_date,
        segments=[dict(row, runId=_run_id(session_id + '-s' + str(i)), segmentId='s' + str(i))
                  for i, row in enumerate(config['segments'], 1)])
    return {'Name': PLUGIN_NAME + '_' + session_id, 'Projects': [{
        'Name': TASK_NAME, 'FolderName': PLUGIN_NAME, 'Type': 'Javascript', 'Status': 'Enabled',
        'Schedule': 'Daily', 'RunNum': 1, 'AllowJsNotification': False,
        'JsScriptSettingsObject': {'runId': session_id, 'gameDate': game_date, 'mode': SESSION_MODE,
            'sessionJson': json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
            'originalResinBudget': 0, 'condensedResinBudget': 0, 'fragileResinBudget': 0,
            'transientResinBudget': 0, 'allowCrafting': False, 'allowUpgrade': False}}]}


def _session_payload(group):
    settings = _object(group['Projects'][0]['JsScriptSettingsObject'], 'session settings')
    payload = _object(json.loads(settings['sessionJson']), 'session payload')
    config = {k: copy.deepcopy(payload[k]) for k in ('partyName', 'expectedTeam', 'strategyName', 'requireZhongliShield', 'safeHub')}
    config['segments'] = [{k: row[k] for k in ('route', 'timeoutSeconds')} for row in payload['segments']]
    if build_route_session_group(payload['sessionId'], config, game_date=payload['gameDate']) != group:
        raise ValueError('route session group changed')
    return payload


def _routes_overlap(first, second, distance):
    return (first['relativePath'] == second['relativePath'] or first['sha256'] == second['sha256']
        or any(math.hypot(a['x'] - b['x'], a['y'] - b['y']) <= distance
               for a in first['fightPoints'] for b in second['fightPoints']))


def constrain_route_session_day(root, game_date, config, *, now=None):
    config = normalize_session_config(config)
    checks = [constrain_route_day(root, game_date, row['route'], now=now,
        overlap_distance=config['overlapDistance'], budget_seconds=row['timeoutSeconds']) for row in config['segments']]
    total = sum(row['timeoutSeconds'] for row in config['segments'])
    if checks[0]['dailyUsedSeconds'] + total > 1800:
        raise ValueError('combined route session exceeds remaining 30-minute daily native budget')
    if _routes_overlap(config['segments'][0]['route'], config['segments'][1]['route'], config['overlapDistance']):
        raise ValueError('session segments potentially overlap')
    return {'eligible': True, 'gameDate': game_date, 'dailyUsedSeconds': checks[0]['dailyUsedSeconds'],
        'reservedSeconds': total, 'segments': checks}


def assign_route_session_day(root, game_date, config, session_id, *, now=None):
    config = normalize_session_config(config)
    now = now or datetime.now(timezone.utc)
    eligibility = constrain_route_session_day(root, game_date, config, now=now)
    payload = _session_payload(build_route_session_group(session_id, config, game_date=game_date))
    path, ledger = _ledger(root)
    existing = {entry['runId'] for entries in ledger['days'].values() for entry in entries}
    if session_id in existing or any(row['runId'] in existing for row in payload['segments']):
        raise ValueError('session already has a day lease')
    leases = [dict(runId=row['runId'], segmentId=row['segmentId'], sessionId=session_id, gameDate=game_date,
        status='started', startedAt=now.isoformat(), route=row['route'], reservedSeconds=row['timeoutSeconds'])
        for row in payload['segments']]
    ledger['days'].setdefault(game_date, []).extend(leases)
    _atomic(path, ledger)
    return {'sessionId': session_id, 'gameDate': game_date, 'reservedSeconds': eligibility['reservedSeconds'], 'segments': copy.deepcopy(leases)}


def _verify_recovery(events, row, payload, phase, after_index, before_index):
    matches = [(i, e) for i, e in events if e.get('task') == 'material-route-recovery'
               and e.get('runId') == row['runId'] and e.get('stage') == phase and e.get('status') != 'started']
    if len(matches) != 1:
        raise ValueError('segment requires exactly one verified ' + phase + ' recovery')
    index, recovery = matches[0]
    if not after_index < index < before_index:
        raise ValueError('recovery is outside segment boundaries')
    starts = [(i, e) for i, e in events if e.get('task') == 'material-route-recovery'
              and e.get('runId') == row['runId'] and e.get('stage') == phase and e.get('status') == 'started']
    if len(starts) != 1 or not after_index < starts[0][0] < index:
        raise ValueError('recovery requires exactly one ordered native start')
    request = _object(recovery.get('parameterEvidence'), 'recovery parameters')
    if starts[0][1].get('parameterEvidence') != request:
        raise ValueError('recovery start and end parameters differ')
    _exact_fields(request, {'runId': row['runId'], 'sessionId': payload['sessionId'], 'expectedTeam': payload['expectedTeam'],
        'partyName': payload['partyName'], 'stage': phase, 'safeHub': payload['safeHub']}, 'recovery parameters')
    _exact_fields(recovery, {'sessionId': payload['sessionId'], 'stage': phase,
        'noResinSpend': True, 'noFood': True, 'noRevive': True, 'noCrafting': True, 'noUpgrade': True}, 'recovery scope')
    _integer(request.get('timeoutSeconds'), 1, 60, 'recovery timeout')
    elapsed = recovery.get('elapsedMs')
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= request['timeoutSeconds'] * 1000 + 5000:
        raise ValueError('invalid recovery elapsed time')
    if recovery.get('status') in ('failed', 'cancelled', 'timeout'):
        if recovery.get('evidenceVerified') is True:
            raise ValueError('failed recovery cannot claim verified completion')
        return recovery
    _exact_fields(recovery, {'status': 'completed', 'stage': phase,
        'evidenceVerified': True, 'mainUiRestored': True, 'grounded': True, 'positionVerified': True,
        'noRevivePrompt': True, 'teamVerified': True, 'cleanupCompleted': True,
        'loadingObserved': True, 'scopeRecovered': True, 'noResinSpend': True, 'noFood': True,
        'noRevive': True, 'noCrafting': True, 'noUpgrade': True,
        'actualTeam': payload['expectedTeam']}, 'safe-hub recovery')
    position = _point(recovery.get('actualPosition'))
    if math.hypot(position['x'] + 867.7041015625, position['y'] - 2281.378173828125) > 20:
        raise ValueError('recovery actual position differs from fixed safe hub')
    return recovery


def verify_material_route_session_report(text, bettergi_dir, run_id, group, config_name, execution_outcome='running'):
    """Reconcile each native scope separately; a session return cannot merge budgets or successes."""
    analysis = {'schemaVersion': 1, 'outcome': 'unknown', 'tasks': [], 'rewards': {}, 'resinEvents': [],
        'warnings': [], 'flowEnded': False, 'cultivation': None,
        'materialRoute': {'mode': SESSION_MODE, 'reportVerified': False, 'routeCompleted': False,
            'materialGainsVerified': False, 'targetReached': False, 'segments': []}}
    try:
        payload = _session_payload(group)
        _exact_fields(payload, {'sessionId': run_id}, 'session')
        lines = text.splitlines()
        references = [v for line in lines if (v := _config_reference(line))]
        groups = [(i, m) for i, line in enumerate(lines) if (m := _GROUP_MARKER_RE.search(line))]
        if not references or set(references) != {config_name} or len(groups) != 1 or groups[0][1].groups() != ('1', '1'):
            raise ValueError('session requires unique config and one JS group')
        scoped_ids = {run_id, *(row['runId'] for row in payload['segments'])}
        allowed = {TASK_NAME, MODE, SESSION_MODE, 'material-route-fight', 'material-route-shield-cast',
            'material-route-inventory', 'material-route-recovery', 'material-route-segment', 'material-route-team', 'material-route-party-health'}
        events = []
        for i, line in enumerate(lines):
            event = _event_from_line(line)
            if event is None and '[AUTO_GAME_EVENT]' in line:
                raise ValueError('malformed session event')
            if event is None:
                continue
            if event.get('task') not in allowed or event.get('runId') not in scoped_ids or i <= groups[0][0]:
                raise ValueError('foreign or unscoped session event')
            if event.get('task') == 'material-route-party-health' and event.get('runId') == run_id:
                raise ValueError('party health must identify one independent route segment')
            if (event.get('rewardClaimed') is True or event.get('resinSpendEnabled') is True
                    or event.get('rewards') not in (None, {}) or event.get('resinEvents') not in (None, [])
                    or any(event.get(k) not in (None, 0) for k in ('originalResinSpent', 'condensedResinSpent', 'fragileResinUsed', 'transientResinUsed'))):
                raise ValueError('session contains forbidden resource evidence')
            events.append((i, event))
        if _parse_rewards(lines) or _parse_resin_events(lines) or any(_MARKER_RE.search(line) for line in lines):
            raise ValueError('session includes other tasks or resources')
        path = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('session report missing or too large')
        report = _object(_json_file(path), 'session report')
        _exact_fields(report, {'schemaVersion': 1, 'runId': run_id, 'sessionId': run_id, 'mode': SESSION_MODE,
            'gameDate': payload['gameDate'], 'noResinSpend': True, 'noCrafting': True, 'noUpgrade': True,
            'rewards': {}, 'resinEvents': []}, 'session report')
        started, finished = (_timestamp(report.get(key), key) for key in ('startedAt', 'finishedAt'))
        wall = report.get('wallSeconds')
        if (type(wall) not in (int, float) or not math.isfinite(wall) or not 0 <= wall <= 16 * 60 + 5
                or abs(wall - (finished - started).total_seconds()) > 2
                or game_date_at(started) != payload['gameDate'] or game_date_at(finished) != payload['gameDate']):
            raise ValueError('session timing exceeds runner budget or crosses game day')
        terminals = [(i, e) for i, e in events if e['task'] == SESSION_MODE and e.get('status') != 'started']
        if len(terminals) != 1:
            raise ValueError('session needs exactly one terminal event')
        terminal_i, terminal = terminals[0]
        _exact_fields(terminal, {'runId': run_id, 'sessionId': run_id, 'gameDate': payload['gameDate'],
            'reportRelativePath': 'record/' + run_id + '.json', 'status': report['status'], 'evidenceVerified': True}, 'session terminal')
        summaries = report.get('segments')
        if not isinstance(summaries, list) or len(summaries) != 2:
            raise ValueError('session report needs two segment summaries')
        initial_boundaries = [i for i, e in events if e['task'] == 'material-route-segment']
        if not initial_boundaries:
            raise ValueError('session has no segment boundaries')
        initial = _verify_recovery(events, {'runId': run_id}, payload, 'startup', groups[0][0], initial_boundaries[0])
        analysis['materialRoute']['startupRecovery'] = initial
        prior_end = groups[0][0]
        previous_success = initial.get('status') == 'completed'
        gains = {key: 0 for key in MATERIAL_IDS}
        for row, summary in zip(payload['segments'], summaries):
            _exact_fields(summary, {'runId': row['runId'], 'segmentId': row['segmentId']}, 'segment summary')
            boundaries = [(i, e) for i, e in events if e['task'] == 'material-route-segment' and e.get('runId') == row['runId']]
            actual_events = [(i, e) for i, e in events if e.get('runId') == row['runId'] and e['task'] not in {'material-route-segment', 'material-route-recovery'}]
            segment = {'runId': row['runId'], 'segmentId': row['segmentId'], 'route': row['route'],
                'outcome': 'unknown', 'reportVerified': False, 'routeCompleted': False}
            analysis['materialRoute']['segments'].append(segment)
            if summary.get('status') == 'not-started':
                if (Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (row['runId'] + '.json')).exists():
                    raise ValueError('not-started segment has a native/plugin record')
                if previous_success or actual_events or any(e['task'] == 'material-route-recovery' and e.get('runId') == row['runId'] for _, e in events):
                    raise ValueError('segment not-started contradicts preceding success or native evidence')
                if len(boundaries) != 1 or boundaries[0][1].get('status') != 'not-started' or not prior_end < boundaries[0][0] < terminal_i:
                    raise ValueError('not-started segment lacks explicit ordered evidence')
                _exact_fields(boundaries[0][1], {'sessionId': run_id, 'segmentId': row['segmentId'], 'evidenceVerified': True}, 'not-started boundary')
                segment.update(outcome='cancelled', reportVerified=True, noAttemptVerified=True, farmingSeconds=0)
                analysis['tasks'].append({'name': TASK_NAME + ':' + row['segmentId'], 'status': 'skipped', 'reason': 'preceding segment did not complete; no native attempt verified', 'evidence': []})
                prior_end = boundaries[0][0]
                continue
            if not previous_success:
                raise ValueError('second segment began after non-success')
            if len(boundaries) != 2 or [e.get('status') for _, e in boundaries] != ['started', 'finished']:
                raise ValueError('segment needs ordered start/finish boundaries')
            begin, end = [i for i, _ in boundaries]
            if not prior_end < begin < end < terminal_i or any(not begin < i < end for i, _ in actual_events):
                raise ValueError('segment events escaped independent boundaries')
            for _, boundary in boundaries:
                _exact_fields(boundary, {'sessionId': run_id, 'segmentId': row['segmentId']}, 'segment boundary')
            segment_group = build_route_group(row['runId'], payload, row['route'], game_date=payload['gameDate'],
                max_minutes=max(1, math.ceil(row['timeoutSeconds'] / 60)), timeout_seconds=row['timeoutSeconds'])
            isolated = '\n'.join([f'参数指定的一条龙配置：{config_name}', '配置组任务执行: 1/1',
                *[lines[i] for i, _ in actual_events], '一条龙和配置组任务结束'])
            verified = verify_material_route_report(isolated, bettergi_dir, row['runId'], segment_group, config_name, 'exited', inventory_only=True)
            segment.update(verified['materialRoute'], outcome=verified['outcome'])
            segment['report'] = verified.get('materialRouteReport')
            _exact_fields(_object(segment.get('report'), 'segment report'), {'sessionId': run_id, 'segmentId': row['segmentId']}, 'segment report association')
            if segment.get('materialGainsVerified'):
                report_start, report_end = (_timestamp(segment['report'][key], key) for key in ('startedAt', 'finishedAt'))
                for phase in ('before', 'after'):
                    observations = segment['report'].get('inventoryObservations', {}).get(phase)
                    if not isinstance(observations, list) or len(observations) != 2:
                        raise ValueError('session needs two stable actual inventory observations per phase')
                    expected_counts = segment['actualInventory'][phase]
                    stamps = []
                    for observation in observations:
                        if _counts(observation.get('inventory')) != expected_counts:
                            raise ValueError('session inventory observation disagrees with scoped counts')
                        stamp = _timestamp(observation.get('observedAt'), 'inventory observedAt')
                        if not report_start <= stamp <= report_end:
                            raise ValueError('session inventory observation is outside segment report')
                        stamps.append(stamp)
                    if stamps[1] <= stamps[0]:
                        raise ValueError('session inventory observations are not ordered distinct frames')
                    scans = [e for _, e in actual_events if e['task'] == 'material-route-inventory' and e.get('phase') == phase]
                    if len(scans) != 1 or scans[0].get('observationCount') != 2 or type(scans[0].get('observationCount')) is not int:
                        raise ValueError('session inventory scan does not verify two observations')
            analysis['warnings'].extend(verified['warnings'])
            task = copy.deepcopy(verified['tasks'][0])
            task['name'] += ':' + row['segmentId']
            analysis['tasks'].append(task)
            native_ends = [(i, e) for i, e in actual_events if e['task'] == MODE and e.get('status') != 'started']
            if not native_ends:
                raise ValueError('segment has no native end')
            segment['afterRecovery'] = _verify_recovery(events, row, payload, 'after', native_ends[-1][0], end)
            segment['recoveryVerified'] = segment['afterRecovery'].get('status') == 'completed'
            if verified['outcome'] == 'completed':
                if not segment['recoveryVerified']:
                    segment.update(routeOutcome='completed', outcome='failed')
                    task.update(status='failed', reason='route and inventory verified; safe-hub recovery did not complete')
            previous_success = segment['outcome'] == 'completed'
            if summary.get('status') != segment.get('report', {}).get('status'):
                raise ValueError('session summary contradicts segment evidence')
            if segment.get('materialGainsVerified'):
                for key in MATERIAL_IDS:
                    gains[key] += segment['materialGains'][key]
            prior_end = end
        completed = all(row['outcome'] == 'completed' for row in analysis['materialRoute']['segments'])
        if report['status'] == 'success' and not completed or report['status'] not in ('success', 'failed', 'unknown', 'cancelled', 'timeout'):
            raise ValueError('session success does not match both segments')
        endings = [i for i, line in enumerate(lines) if '一条龙和配置组任务结束' in line]
        analysis['flowEnded'] = len(endings) == 1 and endings[0] > terminal_i
        analysis['materialRoute'].update(reportVerified=True, routeCompleted=completed,
            materialGainsVerified=completed, materialGains=gains,
            farmingSeconds=sum(row.get('farmingSeconds', row['route'].get('reservedSeconds', 0)) for row in analysis['materialRoute']['segments']))
        analysis['materialRouteReport'] = report
        analysis['outcome'] = ('completed' if completed and analysis['flowEnded'] and execution_outcome == 'exited'
            else 'partial' if any(row['outcome'] == 'completed' for row in analysis['materialRoute']['segments'])
            else 'failed' if initial.get('status') == 'failed' or any(row['outcome'] == 'failed' for row in analysis['materialRoute']['segments']) else 'unknown')
        analysis['tasks'].insert(0, {'name': TASK_NAME,
            'status': 'success' if completed else 'failed' if analysis['outcome'] == 'failed' else 'unknown',
            'reason': 'both independent segments, inventories and safe-hub recoveries verified' if completed
                else 'session did not complete both independently verified segments', 'evidence': []})
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration) as error:
        analysis['warnings'].append('刀镡会话证据尚未核验：' + str(error))
        analysis['materialRoute'].update(reportVerified=False, routeCompleted=False, materialGainsVerified=False)
        analysis['outcome'] = 'unknown'
    return analysis


def _session_no_attempt_receipt(root, entry, directory, bettergi_dir, segments):
    plugin = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME)
    sources = [Path(directory) / 'material-route-group.json', Path(directory) / 'bettergi.log',
        plugin / 'record' / (entry['sessionId'] + '.json'), Path(bettergi_dir) / 'BetterGI.dll']
    sources.extend(plugin / 'record' / (attempted['runId'] + '.json')
        for attempted in segments if not attempted.get('noAttemptVerified') and attempted.get('report'))
    sources.extend(p for p in plugin.iterdir() if p.is_file() and p.suffix in ('.js', '.json'))
    hashes = {}
    for source in sources:
        source = _safe_path(source)
        if not source.is_relative_to(_safe_path(root)):
            raise ValueError('no-attempt source outside workspace')
        hashes[str(source.relative_to(_safe_path(root))).replace('\\', '/')] = hashlib.sha256(source.read_bytes()).hexdigest()
    return {'schemaVersion': 1, 'runId': entry['runId'], 'sessionId': entry['sessionId'],
        'gameDate': entry['gameDate'], 'route': entry['route'], 'bettergiDirectory': str(_safe_path(bettergi_dir)),
        'sourceSha256': hashes, 'verdict': 'no-native-segment-attempt'}


def _verified_session_no_attempt(root, entry):
    if not entry.get('sessionId'):
        return False
    path = _safe_path(Path(root) / 'logs/runs' / entry['runId'] / 'material-route-session-no-attempt-review.json')
    if not path.is_file():
        return False
    try:
        receipt = _json_file(path)
        if receipt.get('runId') != entry['runId'] or receipt.get('route') != entry['route']:
            return False
        for relative, digest in receipt['sourceSha256'].items():
            source = _safe_path(Path(root) / relative)
            if not source.is_relative_to(_safe_path(root)) or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                return False
        directory = _safe_path(Path(root) / 'logs/runs' / entry['sessionId'])
        group = _json_file(directory / 'material-route-group.json')
        result = _json_file(directory / 'result.json')
        _exact_fields(result, {'runId': entry['sessionId'], 'gameDate': entry['gameDate'],
            'mode': SESSION_MODE, 'expectedTasks': [TASK_NAME]}, 'no-attempt parent result')
        if result.get('outcome') not in ('failed', 'partial', 'unknown') or result.get('executionOutcome') not in (
                'exited', 'cancelled', 'timeout', 'stage_timeout', 'network_guard_failed', 'resource_pressure', 'blocked_or_failed'):
            return False
        verified = verify_material_route_session_report((directory / 'bettergi.log').read_text(encoding='utf-8'),
            receipt['bettergiDirectory'], entry['sessionId'], group, 'AutoGame_' + entry['sessionId'], result['executionOutcome'])
        return (verified['materialRoute']['reportVerified'] and any(
            row['runId'] == entry['runId'] and row.get('noAttemptVerified') for row in verified['materialRoute']['segments'])
            and receipt == _session_no_attempt_receipt(root, entry, directory, receipt['bettergiDirectory'], verified['materialRoute']['segments']))
    except (OSError, ValueError, TypeError, KeyError):
        return False


def finalize_route_session_day(root, lease, analysis, *, directory, bettergi_dir, wall_seconds):
    output = copy.deepcopy(lease)
    output['wallSeconds'] = wall_seconds
    segments = analysis.get('segments', [])
    for i, row in enumerate(lease['segments']):
        matches = [e for e in segments if e.get('runId') == row['runId']]
        evidence = matches[0] if len(matches) == 1 else {}
        outcome = evidence.get('outcome', 'unknown') if analysis.get('reportVerified') and evidence.get('reportVerified') else 'unknown'
        if outcome not in ('completed', 'partial', 'failed', 'unknown', 'cancelled', 'timeout'):
            outcome = 'unknown'
        output['segments'][i] = finalize_route_day(root, lease['gameDate'], row['runId'], outcome,
            evidence={k: v for k, v in evidence.items() if k != 'report'},
            wall_seconds=evidence.get('report', {}).get('wallSeconds'),
            farming_seconds=evidence.get('farmingSeconds') if analysis.get('reportVerified') and evidence.get('reportVerified') else None)
        segment_dir = _safe_path(Path(root) / 'logs/runs' / row['runId'])
        _atomic(segment_dir / 'result.json', {'schemaVersion': 1, 'runId': row['runId'], 'sessionId': lease['sessionId'],
            'segmentId': row['segmentId'], 'gameDate': lease['gameDate'], 'mode': MODE, 'outcome': outcome,
            'materialRoute': {k: v for k, v in evidence.items() if k != 'report'}})
        if evidence.get('report'):
            _atomic(segment_dir / 'material-route-report.json', evidence['report'])
        if analysis.get('reportVerified') and evidence.get('inventoryOnly') and evidence.get('materialGainsVerified'):
            _atomic(segment_dir / 'material-route-inventory-only-review.json', {'schemaVersion': 1,
                'runId': row['runId'], 'sessionId': lease['sessionId'], 'segmentId': row['segmentId'],
                'gameDate': lease['gameDate'], 'route': row['route'], 'outcome': outcome,
                'inventoryVerified': True, 'actualInventory': evidence['actualInventory'],
                'materialGains': evidence['materialGains'], 'doesNotConfirmRouteCompletion': True})
        if analysis.get('reportVerified') and evidence.get('noAttemptVerified'):
            _atomic(segment_dir / 'material-route-session-no-attempt-review.json',
                _session_no_attempt_receipt(root, row, directory, bettergi_dir, segments))
    return output
