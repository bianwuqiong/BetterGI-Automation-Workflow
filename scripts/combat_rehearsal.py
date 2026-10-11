"""One bounded combat diagnostic; independently verify combat, never material gains."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import re

try:
    from cultivation import _integer, _json_file, _object, _package_files, _run_id, _safe_path, _text, _timestamp
    from analyze_run import _config_reference, _event_from_line, _FAILURE_RE, _GROUP_MARKER_RE, _MARKER_RE, _parse_rewards, _parse_resin_events
except ImportError:
    from scripts.cultivation import _integer, _json_file, _object, _package_files, _run_id, _safe_path, _text, _timestamp
    from scripts.analyze_run import _config_reference, _event_from_line, _FAILURE_RE, _GROUP_MARKER_RE, _MARKER_RE, _parse_rewards, _parse_resin_events


TASK_ID = 'auto-game-combat-rehearsal'
TASK_NAME = '战斗演练'
PLUGIN_NAME = 'AutoGameCombatRehearsal'
DOMAIN_NAME = '逆悬的冰河'
STRATEGY_NAME = '木偶星超导'
MODE = 'combat-rehearsal'


def inject_combat_rehearsal_task(template):
    result = copy.deepcopy(_object(template, 'template'))
    definitions = _object(result.get('TaskDefinitions'), 'TaskDefinitions')
    enabled = _object(result.get('TaskEnabledList'), 'TaskEnabledList')
    order = result.get('TaskOrder')
    if not isinstance(order, list) or len(order) != len(set(order)) or any(key not in definitions or key not in enabled for key in order):
        raise ValueError('invalid rehearsal TaskOrder')
    if (TASK_ID in definitions and definitions[TASK_ID] != TASK_NAME
            or any(name == TASK_NAME and key != TASK_ID for key, name in definitions.items())):
        raise ValueError('combat rehearsal task ID/name collision')
    definitions[TASK_ID] = TASK_NAME
    enabled[TASK_ID] = True
    if TASK_ID not in order:
        order.append(TASK_ID)
    return result


def build_combat_rehearsal_group(run_id, private_config, *, max_minutes=5):
    _run_id(run_id)
    max_minutes = _integer(max_minutes, 1, 5, 'rehearsal maxMinutes')
    policy = _object(_object(private_config, 'private config').get('policy', {}), 'private policy')
    party = _text(policy.get('domainPartyName', ''), 'domainPartyName', empty=True)
    return {'Name': PLUGIN_NAME + '_' + run_id, 'Projects': [{
        'Name': TASK_NAME, 'FolderName': PLUGIN_NAME, 'Type': 'Javascript', 'Status': 'Enabled',
        'Schedule': 'Daily', 'RunNum': 1, 'AllowJsNotification': False,
        'JsScriptSettingsObject': {'runId': run_id, 'domainName': DOMAIN_NAME, 'partyName': party,
            'strategyName': STRATEGY_NAME, 'maxMinutes': max_minutes}}]}


def verify_rehearsal_plugin(source_dir, bettergi_dir):
    """Read-only identity gate. Deployment remains an explicit separate operation."""
    source = _safe_path(source_dir)
    destination = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME)
    if not source.is_dir() or not destination.is_dir():
        raise ValueError('combat rehearsal plugin must already be deployed')
    files = _package_files(source)
    if not {'manifest.json', 'main.js'} <= set(files) or files != _package_files(destination):
        raise ValueError('combat rehearsal deployed plugin differs from reviewed source')
    return {'verified': True, 'pluginDirectory': str(destination),
            'sourceSha256': {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}}


def _report(bettergi_dir, run_id, settings):
    path = _safe_path(Path(bettergi_dir) / 'User/JsScript' / PLUGIN_NAME / 'record' / (run_id + '.json'))
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('combat rehearsal report missing or too large')
    report = _object(_json_file(path), 'combat rehearsal report')
    required = {'schemaVersion': 1, 'runId': run_id, 'mode': MODE,
                'noRewardClaim': True, 'targetReached': False, 'rewards': {}}
    if any(type(report.get(key)) is not type(value) or report[key] != value for key, value in required.items()):
        raise ValueError('combat rehearsal report scope/no-claim mismatch')
    if report.get('status') not in ('success', 'failed', 'unknown', 'blocked'):
        raise ValueError('invalid combat rehearsal report status')
    if report['status'] == 'success' and report.get('nativeReturnCompleted') is not True:
        raise ValueError('combat rehearsal native return is unverified')
    start, finish = (_timestamp(report.get(key), key) for key in ('startedAt', 'finishedAt'))
    if not 0 <= (finish - start).total_seconds() <= settings['maxMinutes'] * 60 + 5:
        raise ValueError('combat rehearsal report interval exceeds bound')
    parameters = _object(report.get('parameterEvidence'), 'parameterEvidence')
    fixed = {'DomainRoundNum': 1, 'DomainName': settings['domainName'], 'PartyName': settings['partyName'],
        'CombatOnly': True, 'RequireZhongliShieldCast': True, 'SpecifyResinUse': True,
        'ResinPriorityList': [], 'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 0,
        'OriginalResin40UseCount': 0, 'CondensedResinUseCount': 0, 'FragileResinUseCount': 0,
        'TransientResinUseCount': 0, 'AutoArtifactSalvage': False, 'RewardRecognitionEnabled': False}
    if any(type(parameters.get(key)) is not type(value) or parameters[key] != value for key, value in fixed.items()):
        raise ValueError('combat rehearsal native parameters differ from no-spend policy')
    expected_strategy = _safe_path(Path(bettergi_dir) / 'User/AutoFight' / (settings['strategyName'] + '.txt'))
    supplied_strategy = parameters.get('CombatStrategyPath')
    if not isinstance(supplied_strategy, str) or os.path.normcase(os.path.abspath(supplied_strategy)) != os.path.normcase(str(expected_strategy)):
        raise ValueError('combat rehearsal strategy path mismatch')
    for name in ('materialGains', 'resinEvents', 'resinSpent', 'originalResinSpent', 'condensedResinSpent'):
        if report.get(name) not in (None, {}, [], 0):
            raise ValueError('combat rehearsal report contains resource claims')
    return report, path


def verify_combat_rehearsal_analysis(text, bettergi_dir, run_id, group, config_name, execution_outcome='running'):
    """Require one scoped group, JS claim, native challenge/exit proof, and actual parameters."""
    _run_id(run_id)
    settings = _object(group['Projects'][0]['JsScriptSettingsObject'], 'rehearsal settings')
    expected_group = build_combat_rehearsal_group(run_id, {'policy': {'domainPartyName': settings.get('partyName')}},
                                                max_minutes=settings.get('maxMinutes'))
    if group != expected_group:
        raise ValueError('combat rehearsal generated group changed')
    lines = text.splitlines()
    analysis = {'schemaVersion': 1, 'outcome': 'unknown', 'tasks': [
        {'name': TASK_NAME, 'status': 'unknown', 'reason': 'combat evidence not independently verified', 'evidence': []}],
        'rewards': {}, 'resinEvents': [], 'warnings': [], 'flowEnded': False, 'cultivation': None,
        'combatRehearsal': {'mode': MODE, 'reportVerified': False, 'targetReached': False}}
    try:
        references = [name for line in lines if (name := _config_reference(line))]
        groups = [(index, match) for index, line in enumerate(lines) if (match := _GROUP_MARKER_RE.search(line))]
        ends = [index for index, line in enumerate(lines) if '一条龙和配置组任务结束' in line]
        if not references or set(references) != {config_name} or len(groups) != 1 or groups[0][1].groups() != ('1', '1') or any(_MARKER_RE.search(line) for line in lines):
            raise ValueError('combat rehearsal requires a unique current config and one JS group')
        events = []
        for index, line in enumerate(lines):
            event = _event_from_line(line)
            if event is None and '[AUTO_GAME_EVENT]' in line:
                raise ValueError('malformed combat rehearsal machine event')
            if event is not None:
                events.append((index, event))
                if event.get('task') not in (TASK_NAME, 'domain-combat-rehearsal', 'domain-shield-cast'):
                    raise ValueError('combat rehearsal log contains another task event')
                if (event.get('rewardClaimed') is True or event.get('resinSpendEnabled') is True
                        or event.get('rewards') not in (None, {}) or event.get('gains') not in (None, {})
                        or any(event.get(key) not in (None, 0) for key in ('originalResinSpent', 'condensedResinSpent', 'fragileResinUsed', 'transientResinUsed'))):
                    raise ValueError('combat rehearsal log contains resource claim evidence')
        if (_parse_rewards(lines) or _parse_resin_events(lines)
                or any(re.search(r'已进入.*领奖|奖励领取成功|获得奖励|成功分解圣遗物|已使用.*树脂', line) for line in lines)):
            raise ValueError('combat rehearsal log contains reward/resin markers')
        plugin_events = [(index, event) for index, event in events if event.get('task') == TASK_NAME]
        native_events = [(index, event) for index, event in events if event.get('task') == 'domain-combat-rehearsal']
        if len(plugin_events) != 1:
            raise ValueError('combat rehearsal needs exactly one scoped plugin event')
        plugin_index, plugin = plugin_events[0]
        if (plugin.get('runId') != run_id or plugin.get('mode') != MODE or plugin.get('evidenceVerified') is not True
                or plugin.get('reportRelativePath') != f'record/{run_id}.json'
                or plugin.get('status') not in ('success', 'failed', 'unknown', 'blocked')
                or plugin.get('noRewardClaim') is not True or plugin.get('targetReached') is not False
                or plugin_index <= groups[0][0]):
            raise ValueError('combat rehearsal plugin event scope mismatch')
        report, report_path = _report(bettergi_dir, run_id, settings)
        if report['status'] != plugin['status']:
            raise ValueError('combat rehearsal report and plugin status disagree')
        if report['status'] != 'success':
            if native_events:
                raise ValueError('combat rehearsal failed report contradicts native completion')
            analysis['tasks'][0].update(status='failed' if report['status'] in ('failed', 'blocked') else 'unknown',
                                       reason='combat rehearsal did not complete')
        else:
            if any(_FAILURE_RE.search(line) for line in lines[groups[0][0]:]):
                raise ValueError('combat rehearsal native completion contradicts a terminal failure')
            if len(native_events) != 1:
                raise ValueError('combat rehearsal needs exactly one native completion event')
            native_index, native = native_events[0]
            fixed = {'status': 'combat_completed', 'evidenceVerified': True, 'challengeCompleted': True,
                'rewardClaimed': False, 'resinSpendEnabled': False, 'shieldEvidence': 'hold_skill_cooldown_observed'}
            if (not groups[0][0] < native_index < plugin_index
                    or native.get('runId') not in (None, run_id)
                    or any(type(native.get(key)) is not type(value) or native[key] != value for key, value in fixed.items())
                    or type(native.get('observedHoldCasts')) is not int or native['observedHoldCasts'] < 1):
                raise ValueError('combat rehearsal native challenge/exit/shield evidence mismatch')
            analysis['tasks'][0].update(status='success', reason='native combat, exit, and Zhongli hold cast independently verified',
                evidence=[{'line': native_index + 1, 'text': lines[native_index]}])
        analysis['flowEnded'] = len(ends) == 1 and ends[0] > plugin_index
        if len(ends) > 1:
            raise ValueError('multiple combat rehearsal flow endings')
        analysis['combatRehearsal'].update(reportVerified=True, reportPath=str(report_path),
            noRewardClaim=True, challengeCompleted=report['status'] == 'success',
            observedHoldCasts=native_events[0][1]['observedHoldCasts'] if report['status'] == 'success' else None)
        analysis['combatRehearsalReport'] = report
        status = analysis['tasks'][0]['status']
        analysis['outcome'] = ('completed' if status == 'success' and analysis['flowEnded'] and execution_outcome == 'exited'
                               else 'partial' if status == 'success' else 'failed' if status == 'failed' else 'unknown')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        analysis['tasks'][0].update(status='unknown', reason='combat evidence not independently verified', evidence=[])
        analysis['warnings'].append('战斗演练证据尚未核验：' + str(exc))
    return analysis
