"""Replaceable artifact targets on the shared workflow; no game/UI calls here."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cultivation import _boolean, _integer, _json_file, _object, _package_files, _run_id, _safe_path, _text, _timestamp
    from analyze_run import _config_reference, _event_from_line, _GROUP_MARKER_RE, _MARKER_RE, _FAILURE_RE
except ImportError:
    from scripts.cultivation import _boolean, _integer, _json_file, _object, _package_files, _run_id, _safe_path, _text, _timestamp
    from scripts.analyze_run import _config_reference, _event_from_line, _GROUP_MARKER_RE, _MARKER_RE, _FAILURE_RE

TASK_ID = 'auto-game-artifact-farming'
TASK_NAME = '圣遗物刷取'
PLUGIN_NAME = 'AutoGameArtifactFarm'
MODE = 'artifact-farming'
RESOLVED_LEDGER_STATUSES = {'verified', 'resolved-no-consumption'}


def game_date(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('artifact time must include timezone')
    return (now.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).date().isoformat()


def normalize_config(raw):
    raw = _object(raw, 'artifact config')
    if set(raw) != {'target', 'policy', 'executionEnabled'}:
        raise ValueError('artifact config requires only target/policy/executionEnabled')
    target = _object(raw['target'], 'target')
    if set(target) != {'characterName', 'artifactSet', 'domainName', 'partyName', 'strategyName', 'mainStats'}:
        raise ValueError('invalid artifact target fields')
    normalized = {key: _text(target[key], key) for key in target if key != 'mainStats'}
    if any(part in normalized['strategyName'] for part in ('/', '\\', ':', '..')):
        raise ValueError('strategyName must be a local strategy basename')
    stats = _object(target['mainStats'], 'mainStats')
    if set(stats) != {'sands', 'goblet', 'circlet'}:
        raise ValueError('mainStats requires sands/goblet/circlet')
    normalized['mainStats'] = {key: _text(value, key) for key, value in stats.items()}
    supplied = _object(raw['policy'], 'policy')
    defaults = {'scopeId': '', 'maxClaims': 1, 'maxMinutes': 15, 'originalResinBudget': 0,
        'condensedResinBudget': 0, 'maxCrafts': 0, 'reserveOriginalResin': 0,
        'preferCondensed': True, 'craftOriginalResinCost': None, 'condensedCapacity': None,
        'craftingCountry': '蒙德', 'domainValidated': False, 'craftingValidated': False,
        'requireZhongliShieldCast': True, 'fragileResinBudget': 0, 'transientResinBudget': 0,
        'primogemBudget': 0, 'validationOnly': False}
    if set(supplied) - set(defaults):
        raise ValueError('unsupported artifact policy field')
    policy = {**defaults, **supplied}
    _run_id(policy['scopeId'])
    for key in ('preferCondensed', 'domainValidated', 'craftingValidated', 'requireZhongliShieldCast', 'validationOnly'):
        _boolean(policy[key], key)
    for key in ('fragileResinBudget', 'transientResinBudget', 'primogemBudget'):
        _integer(policy[key], 0, 0, key)
    for key, low, high in (('maxClaims', 1, 20), ('maxMinutes', 1, 25),
            ('originalResinBudget', 0, 200), ('condensedResinBudget', 0, 100),
            ('maxCrafts', 0, 20), ('reserveOriginalResin', 0, 200)):
        _integer(policy[key], low, high, key)
    # Costs/caps are explicit current-machine facts, not defaults from older versions.
    for key in ('craftOriginalResinCost', 'condensedCapacity'):
        if policy[key] is not None:
            _integer(policy[key], 1, 200, key)
    if policy['craftingCountry'] not in ('蒙德', '璃月'):
        raise ValueError('unsupported crafting country')
    enabled = _boolean(raw['executionEnabled'], 'executionEnabled')
    if policy['validationOnly'] and (policy['maxClaims'] != 1 or any(policy[key] for key in ('originalResinBudget', 'condensedResinBudget', 'maxCrafts'))):
        raise ValueError('artifact validation requires one round and zero budgets/crafts')
    if enabled and (not policy['domainValidated'] and not policy['validationOnly'] or not policy['requireZhongliShieldCast']):
        raise ValueError('execute requires domain validation and shield safety')
    if enabled and policy['maxCrafts'] and (not policy['craftingValidated'] or any(
            policy[key] is None for key in ('craftOriginalResinCost', 'condensedCapacity'))):
        raise ValueError('crafting needs current-machine cost/capacity and validation')
    return {'target': normalized, 'policy': policy, 'executionEnabled': enabled}


def load_artifact_config(path):
    return normalize_config(_json_file(Path(path)))


def config_hash(config):
    config = normalize_config(config)
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest()


def _ledger_row_resolved(root, row):
    if row.get('resourceState') == 'known_not_submitted':
        try:
            from .artifact_resource_review import classified_resource_zero
        except ImportError:
            from artifact_resource_review import classified_resource_zero
        return classified_resource_zero(root, row)
    if row.get('status') == 'verified':
        return True
    if row.get('status') != 'resolved-no-consumption' or row.get('originalStatus') != 'unknown' or any(
            type(row.get(key)) is not int or row[key] != 0 for key in ('originalResinSpent', 'condensedResinSpent', 'crafts')):
        return False
    relative = row.get('reconciliationPath')
    if not isinstance(relative, str) or Path(relative).is_absolute():
        return False
    path = _safe_path(Path(root) / relative)
    allowed = _safe_path(Path(root) / 'logs/runs' / row['runId'])
    if path.parent != allowed or path.name != 'no-consumption-reconciliation.json':
        return False
    audit = _json_file(path)
    return (hashlib.sha256(path.read_bytes()).hexdigest() == row.get('reconciliationSha256')
        and audit.get('runId') == row['runId'] and audit.get('gameDate') == row['gameDate']
        and audit.get('reviewedBy') == 'root-agent' and audit.get('originalStatus') == 'unknown'
        and audit.get('verdict') == 'resolved-no-consumption' and audit.get('originalOutcomePreserved') is True
        and audit.get('nativeCallProof') == {'maxCrafts': 1, 'originalResinBudget': 0, 'minResinToKeep': 200,
            'phase': 'strict-recipe-read-before-submit', 'noDomainEvent': True})


def build_artifact_authorization(config, authorized_at, valid_until=None):
    """Return a receipt for an already explicit user authorization; caller persists it."""
    config = normalize_config(config)
    at = _timestamp(authorized_at, 'authorizedAtUTC')
    receipt = {'schemaVersion': 1, 'scopeId': config['policy']['scopeId'], 'gameDate': game_date(at),
        'authorizedAtUTC': at.astimezone(timezone.utc).isoformat(),
        'authorizationSource': 'explicit-user-instruction', 'configSha256': config_hash(config),
        'originalResinCap': config['policy']['originalResinBudget'],
        'condensedResinCap': config['policy']['condensedResinBudget'],
        'craftCap': config['policy']['maxCrafts'], 'forbidFragileTransientPrimogems': True}
    if valid_until is not None:
        until = _timestamp(valid_until, 'validUntilUTC')
        if until <= at:
            raise ValueError('artifact authorization window must end after actual approval')
        receipt.update(schemaVersion=2, approvedAtUTC=receipt['authorizedAtUTC'],
            validUntilUTC=until.astimezone(timezone.utc).isoformat(), budgetWindow='per-UTC8-04-game-day')
    return receipt


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _unknown_rows(root, date, ledger):
    packets = [(date, ledger)]
    folder = _safe_path(Path(root) / 'state/artifact-checkpoints')
    for path in folder.glob('*.json'):
        if path.name != date + '.json':
            packets.append((path.stem, _json_file(_safe_path(path))))
    unknown = []
    for day, packet in packets:
        if packet.get('schemaVersion') != 1 or packet.get('gameDate') != day or not isinstance(packet.get('runs'), list):
            raise ValueError('invalid prior artifact checkpoint ledger')
        for row in packet['runs']:
            if not _ledger_row_resolved(root, row):
                unknown.append({'gameDate': day, 'runId': row.get('runId'), 'row': copy.deepcopy(row)})
    return sorted(unknown, key=lambda item: (item['gameDate'], item['runId'] or ''))


def _probe_resin_for_review(root, probe_id, date, now, capacity=None):
    _run_id(probe_id)
    directory = _safe_path(Path(root) / 'logs/runs' / probe_id)
    paths = [directory / name for name in ('result.json', 'cultivation-report.json', 'bettergi.log')]
    result, report = _json_file(paths[0]), _json_file(paths[1])
    if (result.get('runId') != probe_id or result.get('gameDate') != date or not result.get('finishedAt')
            or result.get('cultivationResinCheck') is not True or result.get('cultivation', {}).get('reportVerified') is not True
            or report.get('runId') != probe_id or report.get('mode') != 'scan' or report.get('readOnly') is not True
            or report.get('steps') != [] or report.get('metadata', {}).get('diagnostic') != 'resin-only'):
        raise ValueError('continuation requires an independently verified resin-only probe')
    observation = report.get('resinObservation')
    balances = _resin(observation, now, date, capacity)
    if observation.get('verified') is not True or observation.get('source') != 'stable_map_ocr':
        raise ValueError('continuation native balance is unverified')
    observations, refs, events = [], [], []
    for line in paths[2].read_text(encoding='utf-8-sig').splitlines():
        if _config_reference(line): refs.append(_config_reference(line))
        if '[AUTO_GAME_EVENT]' in line: events.append(_event_from_line(line))
        if line.strip().startswith('[CULTIVATION_RESIN_OBSERVATION]'):
            payload = json.loads(line.strip().split(']', 1)[1].strip())
            observations.append(json.loads(payload) if isinstance(payload, str) else payload)
    if (observations != [observation] or not refs or set(refs) != {'AutoGame_' + probe_id} or len(events) != 1
            or events[0] is None or events[0].get('task') != '培养材料' or events[0].get('runId') != probe_id
            or events[0].get('mode') != 'scan' or events[0].get('readOnly') is not True
            or events[0].get('completedSteps') != 0):
        raise ValueError('continuation probe balance/log/run scope mismatch')
    return observation, balances, paths


def _run_source_fingerprint(root, packet):
    row = packet['row']
    _run_id(packet['runId'])
    directory = _safe_path(Path(root) / 'logs/runs' / packet['runId'])
    paths = [directory / name for name in ('result.json', 'artifact-farming-report.json',
        'artifact-farming-group.json', 'bettergi.log')]
    result, report, group = _json_file(paths[0]), _json_file(paths[1]), _json_file(paths[2])
    if (row.get('status') != 'unknown' or result.get('runId') != packet['runId'] or result.get('outcome') != 'unknown'
            or any(row.get(key) is not None for key in ('originalResinSpent', 'condensedResinSpent', 'crafts'))
            or row.get('confirmedSubtotalOnly') is not True or row.get('unknownStepOutcomeUnresolved') is not True
            or not row.get('unknownStepIds') or report.get('runId') != packet['runId']
            or report.get('configSha256') != row.get('configSha256') or report.get('gameDate') != packet['gameDate']
            or report.get('totals') != row.get('confirmedSubtotals')
            or group['Projects'][0]['JsScriptSettingsObject'].get('configSha256') != row.get('configSha256')):
        raise ValueError('new-batch review requires preserved scoped unknown source and confirmed subtotals')
    return {'runId': packet['runId'], 'gameDate': packet['gameDate'], 'scopeId': row['scopeId'],
        'unknownRowSha256': _fingerprint(row), 'target': report['target'], 'confirmedSubtotals': row['confirmedSubtotals'],
        'unknownStepIds': row['unknownStepIds'], 'sourceSha256': {
            str(path.relative_to(_safe_path(root))): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}


def review_explicit_artifact_new_batch(root, new_config, source_run_id, fresh_probe_run_id, *,
        approved_at, valid_until, approval_text, reviewed_by, apply=False, now=None):
    """Explicit human-approved one-new-run exception; never resolve or replay the old unknown."""
    try:
        from workflow import RunLock, atomic_json
    except ImportError:
        from scripts.workflow import RunLock, atomic_json
    if reviewed_by != 'root-agent' or approval_text != '允许新建批次继续，保留原未知记录':
        raise ValueError('new artifact batch requires the explicit human preserve-unknown permission')
    root = _safe_path(root)
    config = normalize_config(new_config)
    approved, until = _timestamp(approved_at, 'actual human approval'), _timestamp(valid_until, 'original deadline')
    now = now or datetime.now(timezone.utc)
    date = game_date(now)
    if not approved <= now < until or not config['executionEnabled'] or config['policy']['validationOnly']:
        raise ValueError('human permission/window/paid new-batch mode invalid')
    with RunLock(root / 'state/workflow.lock'):
        ledger_path = _safe_path(root / 'state/artifact-checkpoints' / (date + '.json'))
        ledger = _json_file(ledger_path) if ledger_path.exists() else {'schemaVersion': 1, 'gameDate': date, 'runs': []}
        unknown = _unknown_rows(root, date, ledger)
        if len(unknown) != 1 or unknown[0]['runId'] != source_run_id:
            raise ValueError('human permission covers exactly the reviewed old unknown, not any later unknown')
        source = _run_source_fingerprint(root, unknown[0])
        if source['target'] != config['target'] or source['scopeId'] == config['policy']['scopeId']:
            raise ValueError('new scope must preserve the approved target and have a fresh identity')
        if any(row.get('scopeId') == config['policy']['scopeId'] for path in (root / 'state/artifact-checkpoints').glob('*.json')
               for row in _json_file(_safe_path(path)).get('runs', [])):
            raise ValueError('new-batch scope has already been used')
        old_authorization_path = _safe_path(root / 'state/artifact-authorizations' / (source['scopeId'] + '.json'))
        old_authorization = _json_file(old_authorization_path)
        if until != _timestamp(old_authorization.get('validUntilUTC'), 'original authorization end'):
            raise ValueError('new-batch permission cannot extend the original eight-hour deadline')
        observation, balances, probe_paths = _probe_resin_for_review(root, fresh_probe_run_id, date, now, config['policy']['condensedCapacity'])
        if _timestamp(observation['observedAt'], 'fresh approved balance') < approved:
            raise ValueError('new-batch balance must be observed after this actual human permission')
        bounded = copy.deepcopy(config)
        bounded['policy']['originalResinBudget'] = min(config['policy']['originalResinBudget'], balances[0])
        bounded['policy']['condensedResinBudget'] = min(config['policy']['condensedResinBudget'], balances[1])
        cost = bounded['policy']['craftOriginalResinCost']
        if cost:
            bounded['policy']['maxCrafts'] = min(bounded['policy']['maxCrafts'],
                max(0, balances[0] - bounded['policy']['reserveOriginalResin']) // cost,
                bounded['policy']['originalResinBudget'] // cost)
        bounded = normalize_config(bounded)
        authorization = build_artifact_authorization(bounded, approved_at, valid_until)
        review = {'schemaVersion': 1, 'kind': 'explicit-human-one-new-artifact-batch',
            'scopeId': bounded['policy']['scopeId'], 'gameDate': date, 'configSha256': config_hash(bounded),
            'authorizationSource': 'direct-human-reply', 'approvalText': approval_text,
            'approvedAtUTC': approved.astimezone(timezone.utc).isoformat(),
            'validUntilUTC': until.astimezone(timezone.utc).isoformat(), 'reviewedBy': reviewed_by,
            'reviewedAtUTC': now.isoformat(), 'assignedRunId': None, 'oneNewRunOnly': True,
            'preserveOldUnknown': True, 'refundOldConfirmedConsumption': False, 'replayOldStep': False,
            'sourceRuns': [source], 'freshProbeRunId': fresh_probe_run_id, 'freshResinObservation': observation,
            'freshProbeSha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in probe_paths},
            'originalAuthorizationSha256': hashlib.sha256(old_authorization_path.read_bytes()).hexdigest()}
        review['humanGrantSha256'] = _fingerprint({'approvedAtUTC': review['approvedAtUTC'],
            'approvalText': approval_text, 'validUntilUTC': review['validUntilUTC'], 'sourceRuns': [source]})
        if apply:
            review_path = _safe_path(root / 'state/artifact-continuations' / (review['scopeId'] + '.json'))
            auth_path = _safe_path(root / 'state/artifact-authorizations' / (review['scopeId'] + '.json'))
            if review_path.exists() or auth_path.exists():
                raise ValueError('existing new-batch review/authorization must not be overwritten')
            if any(_json_file(_safe_path(path)).get('humanGrantSha256') == review['humanGrantSha256']
                   for path in review_path.parent.glob('*.json')):
                raise ValueError('this single human permission is already bound to another new scope')
            atomic_json(review_path, review)
            atomic_json(auth_path, authorization)
        return {'config': bounded, 'authorization': authorization, 'continuationReview': review}


def _continuation_for_gate(root, config, run_id, date, now, unknown):
    path = _safe_path(Path(root) / 'state/artifact-continuations' / (config['policy']['scopeId'] + '.json'))
    if not path.exists():
        raise ValueError('unresolved/prior-day artifact checkpoint; no explicit human new-batch permission')
    review = _json_file(path)
    fixed = {'schemaVersion': 1, 'kind': 'explicit-human-one-new-artifact-batch',
        'scopeId': config['policy']['scopeId'], 'gameDate': date, 'configSha256': config_hash(config),
        'authorizationSource': 'direct-human-reply', 'approvalText': '允许新建批次继续，保留原未知记录',
        'reviewedBy': 'root-agent', 'oneNewRunOnly': True, 'preserveOldUnknown': True,
        'refundOldConfirmedConsumption': False, 'replayOldStep': False}
    if (any(type(review.get(key)) is not type(value) or review[key] != value for key, value in fixed.items())
            or review.get('assignedRunId') is not None or not _timestamp(review.get('approvedAtUTC'), 'human permission') <= now < _timestamp(review.get('validUntilUTC'), 'new batch deadline')
            or [_run_source_fingerprint(root, packet) for packet in unknown] != review.get('sourceRuns')
            or run_id in {packet['runId'] for packet in unknown}
            or len(unknown) != 1 or review['sourceRuns'][0]['target'] != config['target']):
        raise ValueError('human new-batch permission consumed/changed or additional unknown prevents continuation')
    grant = _fingerprint({'approvedAtUTC': review['approvedAtUTC'], 'approvalText': review['approvalText'],
        'validUntilUTC': review['validUntilUTC'], 'sourceRuns': review['sourceRuns']})
    if (review.get('humanGrantSha256') != grant or any(_json_file(_safe_path(candidate)).get('humanGrantSha256') == grant
            for candidate in path.parent.glob('*.json') if candidate != path)):
        raise ValueError('single human new-batch permission is ambiguous or duplicated')
    current_authorization = _json_file(_safe_path(Path(root) / 'state/artifact-authorizations' / (config['policy']['scopeId'] + '.json')))
    if current_authorization.get('authorizedAtUTC') != review['approvedAtUTC'] or current_authorization.get('validUntilUTC') != review['validUntilUTC']:
        raise ValueError('new scope authorization differs from the actual human permission/window')
    observation, balances, paths = _probe_resin_for_review(root, review['freshProbeRunId'], date, now, config['policy']['condensedCapacity'])
    if (observation != review.get('freshResinObservation') or config['policy']['originalResinBudget'] > balances[0]
            or config['policy']['condensedResinBudget'] > balances[1] or any(
                hashlib.sha256(probe_path.read_bytes()).hexdigest() != review['freshProbeSha256'].get(str(probe_path.relative_to(_safe_path(root)))) for probe_path in paths)):
        raise ValueError('new-batch fresh balance/source fingerprint changed')
    old_scope = review['sourceRuns'][0]['scopeId']
    old_path = _safe_path(Path(root) / 'state/artifact-authorizations' / (old_scope + '.json'))
    if hashlib.sha256(old_path.read_bytes()).hexdigest() != review.get('originalAuthorizationSha256'):
        raise ValueError('original approval window changed after new-batch review')
    return path, review


def constrain_artifact_authorization(root, config, run_id, date, *, assign=False, now=None, current_game_identity=None):
    """Called only under workflow.lock. Pending outcomes block replay, even for a new scope."""
    try:
        from workflow import atomic_json
    except ImportError:
        from scripts.workflow import atomic_json
    config = normalize_config(config)
    _run_id(run_id)
    now = now or datetime.now(timezone.utc)
    if game_date(now) != date:
        raise ValueError('artifact authorization is outside current UTC8-04 game day')
    scope = config['policy']['scopeId']
    receipt = _json_file(_safe_path(Path(root) / 'state/artifact-authorizations' / (scope + '.json')))
    expected = build_artifact_authorization(config, receipt.get('authorizedAtUTC'), receipt.get('validUntilUTC'))
    approved = _timestamp(receipt['authorizedAtUTC'], 'authorization time')
    window_valid = (approved <= now <= _timestamp(receipt['validUntilUTC'], 'authorization end')) if receipt.get('schemaVersion') == 2 else receipt['gameDate'] == date
    if receipt != expected or not window_valid or approved > now:
        raise ValueError('artifact receipt target/budget/date mismatch')
    ledger_path = _safe_path(Path(root) / 'state/artifact-checkpoints' / (date + '.json'))
    ledger = _json_file(ledger_path) if ledger_path.exists() else {'schemaVersion': 1, 'gameDate': date, 'runs': []}
    if ledger.get('schemaVersion') != 1 or ledger.get('gameDate') != date or not isinstance(ledger.get('runs'), list):
        raise ValueError('invalid artifact checkpoint ledger')
    unknown = _unknown_rows(root, date, ledger)
    stage_path = _safe_path(Path(root)/'state/artifact-stage-continuations'/(scope+'.json'))
    window_path = _safe_path(Path(root)/'state/artifact-window-stages'/(scope+'.json'))
    if window_path.exists():
        try:
            from .artifact_window_funding import window_for_gate
        except ImportError:
            from artifact_window_funding import window_for_gate
        continuation = window_for_gate(root, config, run_id, date, now, unknown,current_game_identity=current_game_identity)
    elif stage_path.exists():
        try:
            from .artifact_resource_review import stage_for_gate
        except ImportError:
            from artifact_resource_review import stage_for_gate
        continuation = stage_for_gate(root, config, run_id, date, now, unknown)
    else:
        continuation = _continuation_for_gate(root, config, run_id, date, now, unknown) if unknown else None
    if any(row.get('runId') == run_id for row in ledger['runs']):
        raise ValueError('artifact runId already consumed')
    used = {key: sum(_integer(row.get('verifiedResourceConsumption', {}).get(key) if row.get('resourceState') == 'known_not_submitted'
                             else row.get(key), 0, 10000, key) for row in ledger['runs'] if row.get('scopeId') == scope)
        for key in ('originalResinSpent', 'condensedResinSpent', 'crafts')}
    bounded = copy.deepcopy(config)
    for key, cap, spent in (('originalResinBudget', 'originalResinCap', 'originalResinSpent'),
            ('condensedResinBudget', 'condensedResinCap', 'condensedResinSpent'), ('maxCrafts', 'craftCap', 'crafts')):
        bounded['policy'][key] = max(0, receipt[cap] - used[spent])
    lease = {'runId': run_id, 'scopeId': scope, 'gameDate': date, 'status': 'unknown',
        'configSha256': config_hash(bounded), 'originalResinSpent': None,
        'condensedResinSpent': None, 'crafts': None}
    if receipt.get('schemaVersion') == 2:
        lease.update(approvedAtUTC=receipt['approvedAtUTC'], validUntilUTC=receipt['validUntilUTC'])
    if assign:
        if continuation:
            review_path, review = continuation
            review.update(assignedRunId=run_id, assignedAtUTC=now.isoformat())
            atomic_json(review_path, review)
            lease['explicitContinuationScope'] = review['scopeId']
            lease['preservedUnknownRunIds'] = [packet['runId'] for packet in unknown]
            if review.get('kind') == 'explicit-approved-batch-resource-stage':
                lease['derivedStageFundingScope'] = review['fundingScopeId']
                lease['parentResourceRunId'] = review['parentRunId']
            if review.get('kind') == 'explicit-original-window-resource-stage':
                lease['originalWindowFundingScope'] = review['originalScopeId']
                lease['originalWindowContinuationScope'] = review['continuationScopeId']
        ledger['runs'].append(lease)
        atomic_json(ledger_path, ledger)
    return bounded, lease


def finalize_artifact_checkpoint(root, lease, evidence, *, launch_attempted):
    try:
        from workflow import atomic_json
    except ImportError:
        from scripts.workflow import atomic_json
    path = _safe_path(Path(root) / 'state/artifact-checkpoints' / (lease['gameDate'] + '.json'))
    ledger = _json_file(path)
    row = next(row for row in ledger['runs'] if row['runId'] == lease['runId'])
    if not launch_attempted:
        if row.get('confirmedSubtotals') or any(row.get(key) not in (None, 0) for key in
                ('originalResinSpent', 'condensedResinSpent', 'crafts')):
            raise ValueError('known artifact consumption cannot be refunded as not-launched')
        row.update(status='verified', originalResinSpent=0, condensedResinSpent=0, crafts=0,
            verdict='explicit-not-launched')
    elif evidence.get('reportVerified') is True and evidence.get('allStepsVerified') is True:
        row.update(status='verified', **{key: _integer(evidence[key], 0, 10000, key)
            for key in ('originalResinSpent', 'condensedResinSpent', 'crafts')})
    elif evidence.get('reportVerified') is True and evidence.get('allStepsVerified') is False:
        subtotal = {key: _integer(evidence[key], 0, 10000, key)
            for key in ('originalResinSpent', 'condensedResinSpent', 'crafts', 'claims')}
        archive_path = _safe_path(Path(root) / 'logs/runs' / lease['runId'] / 'artifact-farming-report.json')
        archive = _json_file(archive_path)
        if (archive.get('runId') != lease['runId'] or archive.get('gameDate') != lease['gameDate']
                or archive.get('configSha256') != row.get('configSha256') or archive.get('totals') != subtotal):
            raise ValueError('confirmed artifact subtotal differs from the scoped archived report')
        steps = archive.get('steps')
        if not isinstance(steps, list):
            raise ValueError('artifact subtotal report steps missing')
        verified_ids = [step.get('stepId') for step in steps if step.get('status') == 'success']
        unknown_ids = [step.get('stepId') for step in steps if step.get('status') != 'success']
        if (not unknown_ids or len(set(verified_ids + unknown_ids)) != len(steps)
                or any(not isinstance(identifier, str) or not identifier.startswith(lease['runId'] + ':step-')
                       for identifier in verified_ids + unknown_ids)
                or evidence.get('verifiedStepIds', verified_ids) != verified_ids
                or evidence.get('unknownStepIds', unknown_ids) != unknown_ids):
            raise ValueError('confirmed/unknown artifact step identities mismatch')
        previous = row.get('confirmedSubtotals')
        if isinstance(previous, dict) and any(subtotal[key] < previous.get(key, 0) for key in subtotal):
            raise ValueError('confirmed artifact consumption cannot be reduced')
        row.update(status='unknown', originalResinSpent=None, condensedResinSpent=None, crafts=None,
            confirmedSubtotals=subtotal, confirmedStepIds=verified_ids, unknownStepIds=unknown_ids,
            confirmedSubtotalOnly=True, unknownStepOutcomeUnresolved=True,
            confirmedEvidencePath=str(archive_path.relative_to(_safe_path(root))),
            confirmedEvidenceSha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
    atomic_json(path, ledger)
    return row


def reconcile_validation_no_consumption(root, bettergi_dir, run_id, fresh_probe_run_id,
        *, reviewed_by, apply=False, now=None):
    """Explicit root review only. Resolve pre-submit zero-budget recipe-reader failure.

    Never called by a runner. Preserve the unknown result; reject paid settings,
    any step, a domain event, ambiguous source hashes, or stale independent reads.
    """
    try:
        from workflow import RunLock, atomic_json
    except ImportError:
        from scripts.workflow import RunLock, atomic_json
    import math
    import re
    if reviewed_by != 'root-agent':
        raise ValueError('no-consumption reconciliation requires explicit root-agent review')
    _run_id(run_id)
    _run_id(fresh_probe_run_id)
    if run_id == fresh_probe_run_id:
        raise ValueError('reconciliation needs an independent newer read-only probe')
    root, bgi = _safe_path(root), _safe_path(bettergi_dir)
    now = now or datetime.now(timezone.utc)
    with RunLock(root / 'state/workflow.lock'):
        directory = _safe_path(root / 'logs/runs' / run_id)
        result_path, group_path, log_path = (directory / name for name in
            ('result.json', 'artifact-farming-group.json', 'bettergi.log'))
        result, group = _json_file(result_path), _json_file(group_path)
        settings = group['Projects'][0]['JsScriptSettingsObject']
        config = normalize_config(json.loads(settings['configJson']))
        policy, date = config['policy'], settings['gameDate']
        if (result.get('runId') != run_id or result.get('gameDate') != date or result.get('outcome') != 'unknown'
                or not result.get('finishedAt') or settings.get('runId') != run_id
                or policy['validationOnly'] is not True or policy['maxClaims'] != 1
                or any(policy[key] for key in ('originalResinBudget', 'condensedResinBudget', 'maxCrafts'))
                or settings.get('configSha256') != config_hash(config)):
            raise ValueError('only terminal unknown zero-budget validation can be reconciled')
        live_report_path = _safe_path(bgi / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
        report = _json_file(live_report_path)
        if (report.get('runId') != run_id or report.get('mode') != MODE or report.get('gameDate') != date
                or report.get('configSha256') != config_hash(config) or report.get('target') != config['target']
                or report.get('policy') != policy or report.get('status') != 'unknown'
                or report.get('targetReached') is not False or report.get('steps') != []
                or report.get('recipeInspection') is not None
                or report.get('totals') != {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0}
                or not isinstance(report.get('reason'), str) or not report['reason'].startswith('识别合成库存失败：原粹=')):
            raise ValueError('report is not an empty pre-submit recipe-read failure; no paid/unknown step review allowed')
        finished = _timestamp(report.get('finishedAt'), 'failed validation finish')
        started = _timestamp(report.get('startedAt'), 'failed validation start')
        initial = report['initialResinObservation']
        initial_balance = _resin(initial, _timestamp(initial['observedAt'], 'initial observation'), date, policy['condensedCapacity'])
        if not started <= _timestamp(initial['observedAt'], 'initial observation') <= finished <= now:
            raise ValueError('validation observation/report interval mismatch')
        plugin_identity = result.get('artifactPlugin', {})
        if plugin_identity.get('verified') is not True:
            raise ValueError('failed validation plugin was not verified at launch')
        for name in ('main.js', 'operator.js'):
            deployed = _safe_path(bgi / 'User/JsScript' / PLUGIN_NAME / name)
            digest = hashlib.sha256(deployed.read_bytes()).hexdigest()
            if (plugin_identity.get('sha256', {}).get(name) != digest or hashlib.sha256(
                    _safe_path(root / 'bgi-scripts' / PLUGIN_NAME / name).read_bytes()).hexdigest() != digest):
                raise ValueError('zero-budget native call source differs from the launch/reviewed source')
        text = log_path.read_text(encoding='utf-8-sig')
        lines = text.splitlines()
        refs = [_config_reference(line) for line in lines if _config_reference(line)]
        groups = [_GROUP_MARKER_RE.search(line) for line in lines if _GROUP_MARKER_RE.search(line)]
        events = [_event_from_line(line) for line in lines if '[AUTO_GAME_EVENT]' in line]
        if (not refs or set(refs) != {'AutoGame_' + run_id} or len(groups) != 1
                or groups[0].groups() != ('1', '1') or len(events) != 1
                or events[0] is None or events[0].get('task') != TASK_NAME
                or events[0].get('runId') != run_id or events[0].get('status') != 'unknown'
                or events[0].get('completedClaims') != 0
                or re.search(r'一条龙任务执行|自动秘境|古树|领奖|获得奖励|已使用.*树脂|本次提交|批次核验完成|合成数量已连续', text)):
            raise ValueError('validation log contains domain/claim/commit evidence or ambiguous scope')
        probe_dir = _safe_path(root / 'logs/runs' / fresh_probe_run_id)
        probe_result_path, probe_report_path, probe_log_path = (probe_dir / name for name in
            ('result.json', 'cultivation-report.json', 'bettergi.log'))
        probe_result, probe = _json_file(probe_result_path), _json_file(probe_report_path)
        if (probe_result.get('runId') != fresh_probe_run_id or probe_result.get('gameDate') != date
                or probe_result.get('cultivationResinCheck') is not True or not probe_result.get('finishedAt')
                or probe_result.get('cultivation', {}).get('reportVerified') is not True
                or probe.get('runId') != fresh_probe_run_id or probe.get('mode') != 'scan'
                or probe.get('readOnly') is not True or probe.get('steps') != []
                or probe.get('metadata', {}).get('diagnostic') != 'resin-only'):
            raise ValueError('independent current resin-only probe is not independently verified')
        current = probe.get('resinObservation')
        current_balance = _resin(current, now, date, policy['condensedCapacity'])
        observed = _timestamp(current['observedAt'], 'current observation')
        if observed < finished or current.get('verified') is not True or current.get('source') != 'stable_map_ocr':
            raise ValueError('independent probe precedes failure or lacks native stable-map evidence')
        probe_text = probe_log_path.read_text(encoding='utf-8-sig')
        observations = []
        for line in probe_text.splitlines():
            if line.strip().startswith('[CULTIVATION_RESIN_OBSERVATION]'):
                payload = json.loads(line.strip().split(']', 1)[1].strip())
                observations.append(json.loads(payload) if isinstance(payload, str) else payload)
        if observations != [current]:
            raise ValueError('independent probe saved balance differs from its native log')
        max_growth = math.ceil((observed - _timestamp(initial['observedAt'], 'initial observation')).total_seconds() / 480) + 1
        if current_balance[1] != initial_balance[1] or not initial_balance[0] <= current_balance[0] <= min(200, initial_balance[0] + max_growth):
            raise ValueError('independent balance does not corroborate no consumption')
        ledger_path = _safe_path(root / 'state/artifact-checkpoints' / (date + '.json'))
        ledger = _json_file(ledger_path)
        matching = [row for row in ledger['runs'] if row.get('runId') == run_id]
        if len(matching) != 1 or matching[0].get('status') != 'unknown' or matching[0].get('configSha256') != config_hash(config):
            raise ValueError('unknown ledger row does not match reviewed validation')
        sources = [result_path, group_path, log_path, live_report_path, probe_result_path, probe_report_path, probe_log_path]
        audit = {'schemaVersion': 1, 'kind': 'explicit-validation-no-consumption-review', 'runId': run_id,
            'freshProbeRunId': fresh_probe_run_id, 'reviewedBy': reviewed_by, 'reviewedAtUTC': now.isoformat(),
            'gameDate': date, 'originalStatus': 'unknown', 'originalOutcomePreserved': True,
            'verdict': 'resolved-no-consumption', 'noReplayOfPaidStep': True,
            'nativeCallProof': {'maxCrafts': 1, 'originalResinBudget': 0, 'minResinToKeep': 200,
                'phase': 'strict-recipe-read-before-submit', 'noDomainEvent': True},
            'initialResinObservation': initial, 'currentResinObservation': current,
            'sourceSha256': {str(path.relative_to(root)) if path.is_relative_to(root) else 'bettergi/' + path.name:
                hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}}
        if apply:
            audit_path = directory / 'no-consumption-reconciliation.json'
            if audit_path.exists():
                raise ValueError('existing explicit reconciliation must not be overwritten')
            atomic_json(audit_path, audit)
            matching[0].update(originalStatus='unknown', status='resolved-no-consumption',
                originalResinSpent=0, condensedResinSpent=0, crafts=0,
                reconciliationPath=str(audit_path.relative_to(root)),
                reconciliationSha256=hashlib.sha256(audit_path.read_bytes()).hexdigest())
            atomic_json(ledger_path, ledger)
        return audit


def inject_artifact_task(template):
    result = copy.deepcopy(_object(template, 'template'))
    definitions, enabled, order = result['TaskDefinitions'], result['TaskEnabledList'], result['TaskOrder']
    if len(order) != len(set(order)) or any(key not in definitions or key not in enabled for key in order):
        raise ValueError('invalid artifact TaskOrder')
    if TASK_ID in definitions and definitions[TASK_ID] != TASK_NAME or any(
            name == TASK_NAME and key != TASK_ID for key, name in definitions.items()):
        raise ValueError('artifact task collision')
    definitions[TASK_ID], enabled[TASK_ID] = TASK_NAME, True
    if TASK_ID not in order:
        order.append(TASK_ID)
    return result


def artifact_reward_names(bettergi_dir):
    """Use the native recognizer's class table, never equate Mora with an artifact."""
    path = _safe_path(Path(bettergi_dir) / 'Assets/Model/ItemV2/item.csv')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = csv.DictReader(stream)
        if not {'item_class_id', 'item_name'} <= set(rows.fieldnames or []):
            raise ValueError('native artifact recognition table has unsupported columns')
        names = sorted({row['item_name'].strip() for row in rows
            if row['item_class_id'].startswith('relic:') and row['item_name'].strip()})
    if not names or len(names) > 10000:
        raise ValueError('native artifact recognition names unavailable')
    return names


def build_artifact_group(run_id, config, date, global_config, *, dry_run=False, bettergi_dir=None, authorization=None):
    _run_id(run_id)
    config = normalize_config(config)
    if not dry_run and not config['executionEnabled']:
        raise ValueError('artifact execute requires executionEnabled=true')
    retries = _object(global_config.get('autoDomainConfig', {}), 'autoDomainConfig').get('reviveRetryCount')
    if type(retries) is not int or retries != 1:
        raise ValueError('artifact domain requires global single-attempt count=1')
    names = [] if config['policy']['validationOnly'] else artifact_reward_names(bettergi_dir) if bettergi_dir else []
    if not dry_run and not config['policy']['validationOnly'] and not names:
        raise ValueError('paid artifacts require native artifact recognition names')
    return {'Name': PLUGIN_NAME + '_' + run_id, 'Projects': [{
        'Name': TASK_NAME, 'FolderName': PLUGIN_NAME, 'Type': 'Javascript', 'Status': 'Enabled',
        'Schedule': 'Daily', 'RunNum': 1, 'AllowJsNotification': False,
        'JsScriptSettingsObject': {'runId': run_id, 'gameDate': date,
            'configJson': json.dumps(config, ensure_ascii=False), 'configSha256': config_hash(config),
            'singleAttemptVerified': True, 'artifactRewardNamesJson': json.dumps(names, ensure_ascii=False),
            'validUntilUTC': (authorization or {}).get('validUntilUTC')}}]}


def verify_artifact_plugin(source_dir, bettergi_dir):
    source = _safe_path(source_dir)
    destination = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME)
    if not source.is_dir() or not destination.is_dir() or _package_files(source) != _package_files(destination):
        raise ValueError('artifact plugin must already match reviewed source; deploy with recoverable backup first')
    return {'verified': True, 'pluginDirectory': str(destination),
        'sha256': {key: hashlib.sha256(value).hexdigest() for key, value in _package_files(source).items()}}


def _resin(snapshot, when, date, capacity):
    snapshot = _object(snapshot, 'resin snapshot')
    at = _timestamp(snapshot.get('observedAt'), 'observedAt')
    if (not 0 <= (when - at).total_seconds() <= 120 or game_date(at) != date
            or snapshot.get('mainUiRestored') is not True or snapshot.get('originalVerified') is not True
            or snapshot.get('condensedVerified') is not True):
        raise ValueError('artifact resin snapshot unverified/stale/wrong day')
    return (_integer(snapshot.get('originalResin'), 0, 200, 'originalResin'),
        _integer(snapshot.get('condensedResin'), 0, capacity or 200, 'condensedResin'))


def verify_artifact_analysis(text, bettergi_dir, run_id, group, config_name, execution_outcome='running'):
    """Cross-check scoped native receipts, strict parameters, fresh balances, and checkpoint file."""
    analysis = {'schemaVersion': 1, 'outcome': 'unknown', 'tasks': [{
        'name': TASK_NAME, 'status': 'unknown', 'reason': 'artifact evidence not independently verified', 'evidence': []}],
        'rewards': {}, 'resinEvents': [], 'warnings': [], 'flowEnded': False,
        'artifactFarming': {'reportVerified': False, 'targetReached': False}}
    try:
        settings = group['Projects'][0]['JsScriptSettingsObject']
        config = normalize_config(json.loads(settings['configJson']))
        reward_names = [] if config['policy']['validationOnly'] else artifact_reward_names(bettergi_dir)
        if json.loads(settings.get('artifactRewardNamesJson', 'null')) != reward_names:
            raise ValueError('artifact native class table changed')
        if settings['runId'] != run_id or settings['configSha256'] != config_hash(config):
            raise ValueError('generated artifact settings changed')
        lines = text.splitlines()
        refs = [_config_reference(line) for line in lines if _config_reference(line)]
        groups = [(index, match) for index, line in enumerate(lines) if (match := _GROUP_MARKER_RE.search(line))]
        if not refs or set(refs) != {config_name} or len(groups) != 1 or groups[0][1].groups() != ('1', '1') or any(_MARKER_RE.search(line) for line in lines):
            raise ValueError('artifact run/config/group scope ambiguous')
        events = [(index, event) for index, line in enumerate(lines) if (event := _event_from_line(line)) is not None]
        plugin = [(index, event) for index, event in events if event.get('task') == TASK_NAME]
        if len(plugin) != 1:
            raise ValueError('exactly one artifact plugin event required')
        event_index, event = plugin[0]
        if (event.get('runId') != run_id or event.get('mode') != MODE or event.get('evidenceVerified') is not True
                or event.get('reportRelativePath') != f'record/{run_id}.json' or event_index <= groups[0][0]):
            raise ValueError('artifact plugin event mismatch')
        path = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('artifact report too large')
        report = _object(_json_file(path), 'artifact report')
        if any(report.get(key) != value for key, value in {'schemaVersion': 1, 'runId': run_id, 'mode': MODE,
                'gameDate': settings['gameDate'], 'configSha256': settings['configSha256'],
                'target': config['target'], 'policy': config['policy'], 'targetReached': False}.items()):
            raise ValueError('artifact report scope mismatch')
        start, finish = (_timestamp(report.get(key), key) for key in ('startedAt', 'finishedAt'))
        if settings.get('validUntilUTC') is not None and finish > _timestamp(settings['validUntilUTC'], 'authorization end'):
            raise ValueError('artifact authorization window expired before completion')
        policy = config['policy']
        if policy['validationOnly']:
            recipe = _object(report.get('recipeInspection'), 'recipeInspection')
            cost = _integer(recipe.get('RecipeOriginalResinCost'), 1, 200, 'recipe cost')
            safe_cap = _integer(recipe.get('SafeCondensedCapacity'), 1, 200, 'safe capacity')
            if (recipe.get('Status') != 'skipped' or recipe.get('MainUiRestored') is not True
                    or recipe.get('RecipeCostVerified') is not True or recipe.get('OriginalResinSpent') != 0
                    or recipe.get('CondensedResinCreated') != 0 or recipe.get('CondensedCapacityObserved') is not False):
                raise ValueError('zero-budget recipe inspection not verified')
            probes = [e for index, e in events if groups[0][0] < index < event_index
                and e.get('task') == 'artifact-condensed-craft' and e.get('status') == 'skipped'
                and e.get('evidenceVerified') is True and e.get('recipeCostVerified') is True
                and e.get('recipeOriginalResinCost') == cost and e.get('safeCondensedCapacity') == safe_cap
                and e.get('condensedCapacityObserved') is False and e.get('originalResinSpent') == 0
                and e.get('condensedResinCreated') == 0]
            if len(probes) != 1:
                raise ValueError('native zero-budget recipe inspection missing')
        if not 0 <= (finish-start).total_seconds() <= policy['maxMinutes'] * 60 + 10 or game_date(start) != settings['gameDate'] or game_date(finish) != settings['gameDate']:
            raise ValueError('artifact interval/day exceeds bounds')
        totals = {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0}
        reward_total = {}
        steps = report.get('steps')
        if not isinstance(steps, list) or len(steps) > policy['maxClaims'] + policy['maxCrafts']:
            raise ValueError('artifact steps exceed bounds')
        all_verified = True
        previous_finish = start
        previous_after = None
        used_native_indices = set()
        last_native_index = groups[0][0]
        for number, step in enumerate(steps, 1):
            if step.get('stepId') != f'{run_id}:step-{number}':
                raise ValueError('artifact step sequence mismatch')
            step_start = _timestamp(step.get('startedAt'), 'step startedAt')
            if not previous_finish <= step_start <= finish:
                raise ValueError('artifact step interval mismatch')
            if step.get('status') != 'success':
                if number != len(steps):
                    raise ValueError('artifact continued after unknown step')
                all_verified = False
                break
            step_finish = _timestamp(step.get('finishedAt'), 'step finishedAt')
            if not step_start <= step_finish <= finish:
                raise ValueError('invalid artifact step duration')
            before = _resin(step['before'], step_start, settings['gameDate'], policy['condensedCapacity'])
            after = _resin(step['after'], step_finish, settings['gameDate'], policy['condensedCapacity'])
            if previous_after is not None and step['before'] != previous_after:
                raise ValueError('artifact consecutive balance evidence is discontinuous')
            if _timestamp(step['before']['observedAt'], 'before') < start or _timestamp(step['after']['observedAt'], 'after') < step_start:
                raise ValueError('artifact balances reused from another run/step')
            delta = [after[i] - before[i] for i in range(2)]
            if step['type'] == 'craft':
                cost = policy['craftOriginalResinCost']
                native = step['nativeResult']
                requested = _integer(step.get('requestedCount', 1), 1, 5, 'requested craft count')
                created = _integer(native.get('CondensedResinCreated'), 1, requested, 'actual craft count')
                if cost is None or policy['condensedCapacity'] is None:
                    raise ValueError('craft current-machine cost/capacity missing')
                maximum_request = min(policy['maxCrafts'] - totals['crafts'], policy['condensedCapacity'] - before[1],
                    (before[0] - policy['reserveOriginalResin']) // cost,
                    (policy['originalResinBudget'] - totals['originalResinSpent']) // cost, 5)
                spent = created * cost
                if (requested > maximum_request or not policy['preferCondensed'] or not policy['craftingValidated']
                        or totals['condensedResinSpent'] >= policy['condensedResinBudget']
                        or step.get('craftBudget', requested * cost) != requested * cost
                        or step.get('actualCreated', created) != created or step.get('partialQuantity', created < requested) is not (created < requested)
                        or delta != [-spent, created] or native.get('Status') != 'success'
                        or native.get('MainUiRestored') is not True or native.get('OriginalResinSpent') != spent
                        or [native.get('OriginalResinBefore'), native.get('CondensedResinBefore')] != list(before)
                        or [native.get('OriginalResinAfter'), native.get('CondensedResinAfter')] != list(after)):
                    raise ValueError('artifact craft output/delta mismatch')
                matches = [(index, e) for index, e in events if last_native_index < index < event_index and index not in used_native_indices
                    and e.get('task') == 'artifact-condensed-craft' and e.get('status') == 'success'
                    and e.get('evidenceVerified') is True and e.get('condensedResinCreated') == created
                    and e.get('originalResinSpent') == spent
                    and [e.get('originalResinBefore'), e.get('condensedResinBefore')] == list(before)
                    and [e.get('originalResinAfter'), e.get('condensedResinAfter')] == list(after)]
                if len(matches) != 1:
                    raise ValueError('artifact native craft receipt missing')
                last_native_index = matches[0][0]
                used_native_indices.add(last_native_index)
                totals['originalResinSpent'] += spent
                totals['crafts'] += created
            elif step['type'] == 'validation':
                if not policy['validationOnly'] or len(steps) != 1 or delta[1] != 0 or delta[0] not in (0, 1):
                    raise ValueError('artifact validation resin changed unexpectedly')
                params = step['parameterEvidence']
                fixed = {'DomainRoundNum': 1, 'DomainName': config['target']['domainName'], 'PartyName': config['target']['partyName'],
                    'SpecifyResinUse': True, 'CombatOnly': True, 'RequireZhongliShieldCast': True,
                    'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 0, 'OriginalResin40UseCount': 0,
                    'CondensedResinUseCount': 0, 'FragileResinUseCount': 0, 'TransientResinUseCount': 0,
                    'AutoArtifactSalvage': False, 'RewardRecognitionEnabled': False, 'ResinPriorityList': []}
                if any(type(params.get(key)) is not type(value) or params[key] != value for key, value in fixed.items()):
                    raise ValueError('artifact validation unsafe parameters')
                strategy = _safe_path(Path(bettergi_dir) / 'User/AutoFight' / (config['target']['strategyName'] + '.txt'))
                if _safe_path(params['CombatStrategyPath']) != strategy or step.get('rewards') != {}:
                    raise ValueError('artifact validation strategy/reward mismatch')
                native = [e for index, e in events if groups[0][0] < index < event_index and e.get('task') == 'domain-combat-rehearsal'
                    and e.get('status') == 'combat_completed' and e.get('evidenceVerified') is True
                    and e.get('challengeCompleted') is True and e.get('rewardClaimed') is False
                    and e.get('resinSpendEnabled') is False and e.get('shieldEvidence') == 'hold_skill_cooldown_observed'
                    and type(e.get('observedHoldCasts')) is int and e['observedHoldCasts'] > 0]
                if len(native) != 1:
                    raise ValueError('artifact no-claim combat/shield evidence missing')
            elif step['type'] == 'claim':
                resin = step['resin']
                if resin not in ('original', 'condensed') or (resin == 'original' and (delta[0] < -20 or delta[0] > -19 or delta[1] != 0)) or (resin == 'condensed' and (delta[0] not in (0, 1) or delta[1] != -1)):
                    raise ValueError('artifact claim balance delta mismatch')
                params = step['parameterEvidence']
                fixed = {'DomainRoundNum': 1, 'DomainName': config['target']['domainName'], 'PartyName': config['target']['partyName'],
                    'SpecifyResinUse': True, 'CombatOnly': False, 'RequireZhongliShieldCast': True,
                    'OriginalResinUseCount': 0, 'OriginalResin20UseCount': int(resin == 'original'),
                    'OriginalResin40UseCount': 0, 'CondensedResinUseCount': int(resin == 'condensed'),
                    'FragileResinUseCount': 0, 'TransientResinUseCount': 0, 'AutoArtifactSalvage': False,
                    'RewardRecognitionEnabled': True, 'ResinPriorityList': ['原粹树脂' if resin == 'original' else '浓缩树脂']}
                fixed.update(ArtifactRunId=run_id, ArtifactStepId=step['stepId'])
                if any(type(params.get(key)) is not type(value) or params[key] != value for key, value in fixed.items()):
                    raise ValueError('artifact claim unsafe parameters')
                strategy = _safe_path(Path(bettergi_dir) / 'User/AutoFight' / (config['target']['strategyName'] + '.txt'))
                if _safe_path(params['CombatStrategyPath']) != strategy:
                    raise ValueError('artifact strategy mismatch')
                rewards = _object(step['rewards'], 'artifact rewards')
                if not rewards or any(not isinstance(key, str) or type(value) is not int or value <= 0 for key, value in rewards.items()):
                    raise ValueError('artifact actual positive rewards missing')
                if not any(name in reward_names for name in rewards):
                    raise ValueError('actual native artifact-class reward missing; Mora alone is insufficient')
                native_matches = [(index, e) for index, e in events if last_native_index < index < event_index and index not in used_native_indices
                    and e.get('task') == 'artifact-domain-claim' and e.get('stepId') == step['stepId']
                    and e.get('runId') == run_id and e.get('evidenceVerified') is True
                    and e.get('status') == 'observed' and e.get('rewardEvidenceVerified') is True
                    and e.get('resinEvidenceVerified') is False
                    and e.get('resin') == resin and e.get('rewards') == rewards]
                if len(native_matches) != 1:
                    raise ValueError('artifact native scoped reward receipt missing')
                last_native_index = native_matches[0][0]
                used_native_indices.add(last_native_index)
                for key, value in rewards.items():
                    reward_total[key] = reward_total.get(key, 0) + value
                totals['claims'] += 1
                totals['originalResinSpent' if resin == 'original' else 'condensedResinSpent'] += 20 if resin == 'original' else 1
            else:
                raise ValueError('invalid artifact step type')
            if after[0] < policy['reserveOriginalResin']:
                raise ValueError('artifact reserve breached')
            previous_finish = step_finish
            previous_after = step['after']
        if totals['originalResinSpent'] > policy['originalResinBudget'] or totals['condensedResinSpent'] > policy['condensedResinBudget'] or totals['crafts'] > policy['maxCrafts'] or totals['claims'] > policy['maxClaims']:
            raise ValueError('artifact spending exceeds authorization')
        if report.get('status') != event.get('status') or report.get('totals') != totals:
            raise ValueError('artifact report/event/totals mismatch')
        if report['status'] == 'success' and (not all_verified or any(_FAILURE_RE.search(line) for line in lines[groups[0][0]:])):
            raise ValueError('artifact success contradicts unknown/native failure')
        ends = [index for index, line in enumerate(lines) if '一条龙和配置组任务结束' in line]
        analysis['flowEnded'] = len(ends) == 1 and ends[0] > event_index
        success = report['status'] == 'success' and all_verified
        analysis['tasks'][0].update(status='success' if success else 'unknown', reason='fresh resin deltas and native reward receipts verified' if success else 'artifact outcome requires review')
        analysis['artifactFarming'].update(reportVerified=True, allStepsVerified=all_verified,
            **totals, reportPath=str(path), rewards=reward_total,
            verifiedStepIds=[step['stepId'] for step in steps if step.get('status') == 'success'],
            unknownStepIds=[step['stepId'] for step in steps if step.get('status') != 'success'])
        if policy['validationOnly']:
            analysis['artifactFarming'].update(recipeInspection=report['recipeInspection'], domainCombatValidated=success)
        analysis['artifactFarmingReport'] = report
        analysis['rewards'] = reward_total
        analysis['outcome'] = 'completed' if success and analysis['flowEnded'] and execution_outcome == 'exited' else 'partial' if success else 'unknown'
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as error:
        analysis['warnings'].append('圣遗物证据未核验：' + str(error))
    return analysis
