"""Fixed-hub recovery proofs and fake runner checks; no game or route execution."""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import material_route as material
from tests import test_workflow as workflow_tests
from tests.test_workflow import FakeHost, FakeProcess, FixedClock, wf
from tests.test_material_route_session import TEAM, DAY, recovery_fixture, event_line


def config_fixture():
    return {'partyName': 'Test party', 'expectedTeam': TEAM, 'safeHub': 'mondstadt-city', 'timeoutSeconds': 60}


def report_fixture(bgi, run_id, group, *, native_status='completed'):
    settings = group['Projects'][0]['JsScriptSettingsObject']
    request = json.loads(settings['recoveryJson'])
    native = recovery_fixture(run_id, run_id, 'startup')
    native['parameterEvidence'] = request
    native['elapsedMs'] = 25000.0
    start = {'task': 'material-route-recovery', 'status': 'started', 'runId': run_id, 'sessionId': run_id,
        'stage': 'startup', 'parameterEvidence': request}
    if native_status != 'completed':
        native.update(status=native_status, evidenceVerified=False, scopeRecovered=False,
            grounded=False, positionVerified=False, actualPosition={'x': None, 'y': None})
    report = {'schemaVersion': 1, 'runId': run_id, 'sessionId': run_id,
        'gameDate': settings['gameDate'], 'mode': material.RECOVERY_MODE,
        'status': 'success' if native_status == 'completed' else native_status,
        'noResinSpend': True, 'noFood': True, 'noRevive': True, 'noCrafting': True, 'noUpgrade': True,
        'targetReached': False, 'rewards': {}, 'resinEvents': [], 'parameterEvidence': request,
        'nativeResult': copy.deepcopy(native), 'startedAt': settings['gameDate'] + 'T00:00:00Z',
        'finishedAt': settings['gameDate'] + 'T00:00:30Z', 'wallSeconds': 30}
    report['nativeResult']['elapsedMs'] = 25000
    path = bgi / 'User/JsScript/AutoGameMaterialRoute/record' / (run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    wf.atomic_json(path, report)
    plugin = {'task': material.RECOVERY_TASK_NAME, 'runId': run_id, 'gameDate': settings['gameDate'],
        'mode': material.RECOVERY_MODE, 'status': report['status'], 'reportRelativePath': 'record/' + run_id + '.json',
        'evidenceVerified': True}
    events = [start, native, plugin]
    text = '\n'.join(['参数指定的一条龙配置：AutoGame_' + run_id, '配置组任务执行: 1/1',
        *[event_line(event) for event in events], '一条龙和配置组任务结束'])
    return path, report, text, events


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / 'tests/.artifacts' / ('material-recovery-' + uuid4().hex[:10])
        self.bgi = self.root / 'BetterGI'
        self.group = material.build_route_recovery_group('test-recovery', config_fixture(), game_date=DAY)
        self.path, self.report, self.text, self.events = report_fixture(self.bgi, 'test-recovery', self.group)

    def verify(self, text=None, execution='exited'):
        return material.verify_material_recovery_report(text or self.text, self.bgi, 'test-recovery', self.group,
            'AutoGame_test-recovery', execution)

    def save(self, report):
        wf.atomic_json(self.path, report)

    def test_strict_fixed_hub_completion_is_recovery_only(self):
        result = self.verify()
        self.assertEqual(result['outcome'], 'completed', result['warnings'])
        self.assertTrue(result['materialRecovery']['noRouteExecution'])
        self.assertTrue(result['materialRecovery']['recoveryCompleted'])
        self.assertNotIn('materialRoute', result)
        self.assertEqual(result['rewards'], {})
        self.assertEqual(result['resinEvents'], [])
        self.assertEqual(self.verify(execution='running')['outcome'], 'partial')
        self.assertEqual(len(self.group['Projects']), 1)

    def test_configuration_cannot_include_route_budget_or_arbitrary_hub(self):
        for change in ({'route': {}}, {'originalResinBudget': 1}, {'safeHub': 'arbitrary'},
                       {'timeoutSeconds': 61}, {'timeoutSeconds': True}, {'expectedTeam': TEAM[:3]}):
            config = dict(config_fixture(), **change)
            with self.assertRaises(ValueError):
                material.build_route_recovery_group('test-recovery', config, game_date=DAY)

    def test_unique_scope_start_and_terminal_are_required(self):
        for text in (self.text.replace(event_line(self.events[0]) + '\n', ''),
                     self.text.replace(event_line(self.events[1]), event_line(self.events[1]) + '\n' + event_line(self.events[1])),
                     self.text.replace('AutoGame_test-recovery', 'AutoGame_foreign'),
                     self.text.replace('"sessionId": "test-recovery"', '"sessionId": "foreign"')):
            self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_grounded_team_world_position_and_all_proofs_are_strict(self):
        changes = [{key: False} for key in ('mainUiRestored', 'grounded', 'positionVerified', 'teamVerified',
            'loadingObserved', 'scopeRecovered', 'noRevivePrompt', 'cleanupCompleted', 'noFood', 'noRevive')]
        changes.extend([{'actualTeam': TEAM[::-1]}, {'actualPosition': {'x': 500, 'y': 300}},
            {'grounded': 1}, {'elapsedMs': True}, {'elapsedMs': 65001}])
        for change in changes:
            events = copy.deepcopy(self.events)
            events[1].update(change)
            report = copy.deepcopy(self.report)
            report['nativeResult'] = copy.deepcopy(events[1])
            self.save(report)
            text = self.text.replace(event_line(self.events[1]), event_line(events[1]))
            self.assertEqual(self.verify(text)['outcome'], 'unknown', change)

    def test_native_return_float_integer_transport_is_lossless_only(self):
        self.assertEqual(self.verify()['outcome'], 'completed')
        for value in (25000.1, True, '25000', None):
            report = copy.deepcopy(self.report)
            report['nativeResult']['elapsedMs'] = value
            self.save(report)
            self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_route_inventory_fight_loot_and_resin_events_are_forbidden(self):
        for task in ('material-route', 'material-route-fight', 'material-route-inventory', 'material-route-shield-cast'):
            foreign = {'task': task, 'runId': 'test-recovery', 'status': 'started'}
            text = self.text.replace(event_line(self.events[-1]), event_line(foreign) + '\n' + event_line(self.events[-1]))
            self.assertEqual(self.verify(text)['outcome'], 'unknown')
        text = self.text.replace(event_line(self.events[-1]), '获得奖励 摩拉 × 100\n' + event_line(self.events[-1]))
        self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_failed_native_keeps_failed_without_farming_success(self):
        for status in ('failed', 'cancelled', 'timeout'):
            self.path, self.report, text, self.events = report_fixture(self.bgi, 'test-recovery', self.group, native_status=status)
            result = self.verify(text)
            self.assertEqual(result['outcome'], 'failed', result['warnings'])
            self.assertTrue(result['materialRecovery']['reportVerified'])
            self.assertFalse(result['materialRecovery']['recoveryCompleted'])

    def test_four_minute_bound_and_game_day_are_not_relaxed(self):
        for change in ({'finishedAt': DAY + 'T00:05:00Z', 'wallSeconds': 300},
                       {'finishedAt': '2026-10-10T00:00:30Z'}, {'wallSeconds': True}):
            report = dict(self.report, **change)
            self.save(report)
            self.assertEqual(self.verify()['outcome'], 'unknown')


class RecoveryFakeHost(FakeHost):
    def launch(self, exe, name):
        self.launch_calls = getattr(self, 'launch_calls', 0) + 1
        self.launched = True
        self.process = FakeProcess()
        generated = wf.read_json(exe.parent / 'User/OneDragon' / (name + '.json'))
        group_name = next(value for key, value in generated['TaskDefinitions'].items() if generated['TaskEnabledList'][key])
        group = wf.read_json(exe.parent / 'User/ScriptGroup' / (group_name + '.json'))
        run_id = group['Projects'][0]['JsScriptSettingsObject']['runId']
        _, _, text, _ = report_fixture(exe.parent, run_id, group)
        with (exe.parent / 'log/new.log').open('a', encoding='utf-8') as log:
            log.write(text + '\n')
        return self.process


class RecoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        wf.atomic_json(self.root / 'config/material-recovery.json', config_fixture())
        for base in (self.root / 'bgi-scripts/AutoGameMaterialRoute', self.root / 'BetterGI/User/JsScript/AutoGameMaterialRoute'):
            base.mkdir(parents=True, exist_ok=True)
            (base / 'manifest.json').write_text('{}', encoding='utf-8')
            (base / 'main.js').write_text('// retained fake recovery package', encoding='utf-8')
        self.ledger_path = self.root / 'state' / material.LEDGER_NAME
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_bytes(b'opaque original ledger must never be read or changed by recovery')

    def run_recovery(self, dry=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=None, profile=material.RECOVERY_MODE,
            timeout_minutes=0, no_delay=True, allow_repeat=False, keep_game=False,
            allow_existing_game=False, graphics_check=False)
        stream = io.StringIO()
        host = RecoveryFakeHost(self.root)
        forbidden = ('constrain_route_day', 'constrain_route_session_day', 'assign_route_day', 'assign_route_session_day',
            'finalize_route_day', 'finalize_route_session_day', 'load_route_config', 'load_route_session_config', 'verify_route_file')
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(stream))
            stack.enter_context(patch.object(wf, 'datetime', FixedClock))
            stack.enter_context(patch('checkin_hoyolab.execute_hoyolab_checkin', side_effect=AssertionError('must not check in')))
            for name in forbidden:
                stack.enter_context(patch.object(material, name, side_effect=AssertionError('recovery cannot select/reserve/execute a route')))
            code = wf.execute(args, host)
        return code, wf.read_json(json.loads(stream.getvalue())['resultPath']), host

    def test_preview_is_fixed_hub_and_has_no_farming_lease(self):
        before = self.ledger_path.read_bytes()
        code, result, host = self.run_recovery(dry=True)
        self.assertEqual(code, 0, result)
        self.assertFalse(host.launched)
        self.assertEqual(result['expectedTasks'], [material.RECOVERY_TASK_NAME])
        self.assertEqual(result['timeBudget']['maximumMinutes'], 4)
        self.assertNotIn('materialRouteLease', result)
        self.assertNotIn('materialRouteEligibility', result)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        generated = wf.read_json(result['plannedConfig'])
        self.assertTrue(generated['SkipFinalRewardCheck'])
        self.assertEqual(sum(generated['TaskEnabledList'].values()), 1)

    def test_fake_live_recovery_launches_once_and_never_reads_or_mutates_ledger(self):
        before = self.ledger_path.read_bytes()
        code, result, host = self.run_recovery()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'completed', result)
        self.assertTrue(result['materialRecovery']['noRouteExecution'])
        self.assertNotIn('materialRoute', result)
        self.assertNotIn('materialRouteLease', result)
        self.assertEqual(host.launch_calls, 1)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.assertTrue((Path(result['logArchive']) / 'material-recovery-report.json').is_file())
        self.assertEqual(self.base_path.read_bytes(), self.before)

    def test_recovery_can_repeat_without_core_repeat_authorization_or_route_reservation(self):
        for _ in range(2):
            code, result, host = self.run_recovery()
            self.assertEqual(code, 0, result)
            self.assertEqual(host.launch_calls, 1)
        self.assertNotIn('materialRouteLease', result)

    def test_outer_budget_cannot_exceed_four_minutes(self):
        with self.assertRaises(wf.WorkflowError):
            wf.time_budget(self.cfg, None, material.RECOVERY_MODE, 4.1)
