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
from tests.test_material_route_session import TEAM, DAY, event_line


def config_fixture():
    return {'expectedTeam': TEAM, 'allowStatueRevival': True, 'timeoutSeconds': 120}


def report_fixture(bgi, run_id, group, *, native_status='completed'):
    settings = group['Projects'][0]['JsScriptSettingsObject']
    request = json.loads(settings['preparationJson'])
    native = {'task': 'party-preparation', 'status': native_status, 'runId': run_id,
        'parameterEvidence': request, 'statue': copy.deepcopy(material.PREPARATION_STATUE),
        'actualPosition': {'x': -1265.917, 'y': 1928.381}, 'actualTeam': TEAM,
        'slotHealthEvidence': [{'slot': i, 'name': name, 'hp': 8000, 'maxHp': 10000, 'ratio': .8,
            'observations': 2, 'identityVerified': True, 'identityObservations': 2, 'ocrMatchingObservations': 2}
            for i, name in enumerate(TEAM, 1)],
        'teamObservationCount': 2, 'activeSlotRestored': 4, 'elapsedMs': 25000.0,
        'statueProximityVerified': True, 'statueProximityObservationCount': 2, 'statueApproachPerformed': True,
        **{key: True for key in ('loadingObserved', 'positionVerified', 'mainUiRestored', 'grounded',
            'noRevivePrompt', 'teamVerified', 'cleanupCompleted', 'revivalMayHaveOccurred')},
        **material.PREPARATION_FLAGS, 'evidenceVerified': native_status == 'completed'}
    start = {'task': 'party-preparation', 'status': 'started', 'runId': run_id,
        'parameterEvidence': request, 'statue': copy.deepcopy(material.PREPARATION_STATUE)}
    report = {'schemaVersion': 1, 'runId': run_id, 'gameDate': settings['gameDate'], 'mode': 'party-preparation',
        'status': 'success' if native_status == 'completed' else native_status, 'allowStatueRevival': True,
        **material.PREPARATION_FLAGS, 'targetReached': False, 'rewards': {}, 'resinEvents': [],
        'parameterEvidence': request, 'nativeResult': copy.deepcopy(native),
        'startedAt': settings['gameDate'] + 'T00:00:00Z', 'finishedAt': settings['gameDate'] + 'T00:00:30Z', 'wallSeconds': 30}
    report['nativeResult']['elapsedMs'] = 25000
    path = bgi / 'User/JsScript/AutoGameMaterialRoute/record' / (run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    wf.atomic_json(path, report)
    plugin = {'task': material.PREPARATION_TASK_NAME, 'runId': run_id, 'gameDate': settings['gameDate'],
        'mode': material.PREPARATION_MODE, 'status': report['status'],
        'reportRelativePath': 'record/' + run_id + '.json', 'evidenceVerified': True}
    events = [start, native, plugin]
    text = '\n'.join(['参数指定的一条龙配置：AutoGame_' + run_id, '配置组任务执行: 1/1',
        *[event_line(event) for event in events], '一条龙和配置组任务结束'])
    return path, report, text, events


class PreparationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / 'tests/.artifacts' / ('party-preparation-' + uuid4().hex[:10])
        self.bgi = self.root / 'BetterGI'
        self.group = material.build_party_preparation_group('test-preparation', config_fixture(), game_date=DAY)
        self.path, self.report, self.text, self.events = report_fixture(self.bgi, 'test-preparation', self.group)

    def verify(self, text=None, execution='exited'):
        return material.verify_party_preparation_report(text or self.text, self.bgi, 'test-preparation', self.group,
            'AutoGame_test-preparation', execution)

    def mutated_native(self, change):
        events = copy.deepcopy(self.events)
        change(events[1])
        report = copy.deepcopy(self.report)
        report['nativeResult'] = copy.deepcopy(events[1])
        wf.atomic_json(self.path, report)
        return self.text.replace(event_line(self.events[1]), event_line(events[1]))

    def test_fixed_statue_four_healthy_slots_complete_without_farming_or_item_claims(self):
        result = self.verify()
        self.assertEqual(result['outcome'], 'completed', result['warnings'])
        self.assertTrue(result['partyPreparation']['noRouteExecution'])
        self.assertTrue(result['partyPreparation']['allowStatueRevival'])
        self.assertNotIn('noRevive', result['partyPreparation'])
        self.assertNotIn('materialRoute', result)
        self.assertEqual(result['rewards'], {})
        self.assertEqual(result['resinEvents'], [])
        self.assertEqual(self.verify(execution='running')['outcome'], 'partial')
        self.assertEqual(len(self.group['Projects']), 1)

    def test_config_never_accepts_coordinates_item_allowance_or_budget(self):
        for change in ({'route': {}}, {'originalResinBudget': 1}, {'safeHub': 'arbitrary'}, {'timeoutSeconds': 121},
                       {'timeoutSeconds': 120.0}, {'allowStatueRevival': 1}, {'allowStatueRevival': False}, {'expectedTeam': TEAM[:3]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                material.build_party_preparation_group('test-preparation', dict(config_fixture(), **change), game_date=DAY)

    def test_order_unique_group_current_run_config_and_native_lifecycle_are_required(self):
        texts = [self.text.replace(event_line(self.events[0]) + '\n', ''),
            self.text.replace(event_line(self.events[1]), event_line(self.events[1]) + '\n' + event_line(self.events[1])),
            self.text.replace('AutoGame_test-preparation', 'AutoGame_foreign'),
            self.text.replace('配置组任务执行: 1/1', '配置组任务执行: 2/2'),
            self.text.replace(event_line(self.events[0]), '[AUTO_GAME_EVENT] invalid'),
            self.text.replace('一条龙和配置组任务结束', ''),
            self.text.replace('配置组任务执行: 1/1', '一条龙任务执行: 1/1\n配置组任务执行: 1/1')]
        for text in texts:
            with self.subTest(text=text):
                self.assertNotEqual(self.verify(text)['outcome'], 'completed')
        events = copy.deepcopy(self.events)
        events[0]['runId'] = 'foreign'
        self.assertEqual(self.verify(self.text.replace(event_line(self.events[0]), event_line(events[0])))['outcome'], 'unknown')

    def test_dead_low_or_single_observation_hp_and_false_identity_are_unknown(self):
        changes = [{'hp': 0, 'ratio': 0}, {'hp': 7999, 'ratio': .7999}, {'hp': True}, {'maxHp': 0}, {'ratio': .9},
            {'hp': None}, {'observations': 1}, {'identityVerified': False}, {'identityObservations': 1},
            {'ocrMatchingObservations': 1}, {'name': TEAM[0]}, {'slot': True}]
        for change in changes:
            with self.subTest(change=change):
                text = self.mutated_native(lambda native: native['slotHealthEvidence'][1].update(change))
                self.assertEqual(self.verify(text)['outcome'], 'unknown')
        for field in ('slotHealthEvidence', 'actualTeam'):
            text = self.mutated_native(lambda native: native.update({field: native[field][::-1]}))
            self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_actual_loading_position_world_popup_cleanup_and_free_scope_are_strict(self):
        changes = [{key: False} for key in ('loadingObserved', 'positionVerified', 'mainUiRestored', 'grounded',
            'noRevivePrompt', 'teamVerified', 'cleanupCompleted', 'revivalMayHaveOccurred', *material.PREPARATION_FLAGS)]
        changes += [{'noRevive': True}, {'teamObservationCount': 1}, {'activeSlotRestored': 3},
            {'actualPosition': {'x': 0, 'y': 0}}, {'statue': {'id': '4'}}, {'elapsedMs': True}, {'elapsedMs': 125001}]
        for change in changes:
            with self.subTest(change=change):
                text = self.mutated_native(lambda native: native.update(change))
                self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_native_float_integer_transport_must_be_lossless(self):
        self.assertEqual(self.verify()['outcome'], 'completed')
        for value in (25000.1, True, '25000', None):
            report = copy.deepcopy(self.report)
            report['nativeResult']['elapsedMs'] = value
            wf.atomic_json(self.path, report)
            self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_proximity_requires_two_real_frames_inside_five_units_and_no_resource_claims(self):
        changes = [{'statueProximityVerified': False}, {'statueProximityVerified': 1},
            {'statueProximityObservationCount': 1}, {'statueProximityObservationCount': True},
            {'statueProximityObservationCount': 2.0}, {'statueApproachPerformed': 'true'},
            {'actualPosition': {'x': -1266.3422, 'y': 1934.3658}}, {'noItemConsumption': False},
            {'noResinSpend': False}, {'originalResinSpent': 1}, {'noRevive': None}]
        for change in changes:
            with self.subTest(change=change):
                text = self.mutated_native(lambda native: native.update(change))
                self.assertEqual(self.verify(text)['outcome'], 'unknown')
        for key in ('statueProximityVerified', 'statueProximityObservationCount'):
            text = self.mutated_native(lambda native: native.pop(key))
            self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_historical_failure_without_new_proximity_proof_stays_failed_and_unmodified(self):
        self.path, self.report, self.text, self.events = report_fixture(self.bgi, 'test-preparation', self.group, native_status='failed')
        for key in ('statueProximityVerified', 'statueProximityObservationCount', 'statueApproachPerformed'):
            self.events[1].pop(key)
        self.report['nativeResult'] = copy.deepcopy(self.events[1])
        wf.atomic_json(self.path, self.report)
        text = '\n'.join(['参数指定的一条龙配置：AutoGame_test-preparation', '配置组任务执行: 1/1',
            *[event_line(event) for event in self.events], '一条龙和配置组任务结束'])
        before = self.path.read_bytes()
        self.assertEqual(self.verify(text)['outcome'], 'failed')
        self.assertEqual(self.path.read_bytes(), before)

    def test_all_foreign_farming_reward_resin_events_are_forbidden(self):
        for task in ('material-route', 'material-route-fight', 'material-route-inventory', 'material-route-shield-cast', '培养材料'):
            text = self.text.replace(event_line(self.events[-1]), event_line({'task': task, 'runId': 'test-preparation'}) + '\n' + event_line(self.events[-1]))
            self.assertEqual(self.verify(text)['outcome'], 'unknown')
        for marker in ('获得奖励 摩拉 × 100', '已使用浓缩树脂', '使用复苏道具', '食用料理'):
            self.assertEqual(self.verify(self.text.replace(event_line(self.events[-1]), marker + '\n' + event_line(self.events[-1])))['outcome'], 'unknown')

    def test_failed_timeout_cancelled_and_js_unknown_never_become_success(self):
        for status in ('failed', 'cancelled', 'timeout'):
            self.path, self.report, text, self.events = report_fixture(self.bgi, 'test-preparation', self.group, native_status=status)
            result = self.verify(text)
            self.assertEqual(result['outcome'], 'failed', result['warnings'])
            self.assertFalse(result['partyPreparation']['preparationCompleted'])
        self.path, self.report, text, self.events = report_fixture(self.bgi, 'test-preparation', self.group)
        self.report['status'] = self.events[-1]['status'] = 'unknown'
        wf.atomic_json(self.path, self.report)
        text = self.text.replace('"status": "success"', '"status": "unknown"')
        self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_outer_five_minute_bound_same_day_and_parameters_are_not_relaxed(self):
        for change in ({'finishedAt': DAY + 'T00:05:01Z', 'wallSeconds': 301},
                       {'finishedAt': '2026-10-10T00:00:30Z'}, {'wallSeconds': True}, {'noRevive': True},
                       {'parameterEvidence': {}}, {'allowStatueRevival': False}):
            wf.atomic_json(self.path, dict(self.report, **change))
            self.assertEqual(self.verify()['outcome'], 'unknown')


class PreparationFakeHost(FakeHost):
    native_status = 'completed'

    def launch(self, exe, name):
        self.launch_calls = getattr(self, 'launch_calls', 0) + 1
        self.launched = True
        self.process = FakeProcess()
        generated = wf.read_json(exe.parent / 'User/OneDragon' / (name + '.json'))
        group_name = next(value for key, value in generated['TaskDefinitions'].items() if generated['TaskEnabledList'][key])
        group = wf.read_json(exe.parent / 'User/ScriptGroup' / (group_name + '.json'))
        run_id = group['Projects'][0]['JsScriptSettingsObject']['runId']
        _, _, text, _ = report_fixture(exe.parent, run_id, group, native_status=self.native_status)
        with (exe.parent / 'log/new.log').open('a', encoding='utf-8') as log:
            log.write(text + '\n')
        return self.process


class PreparationWorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        wf.atomic_json(self.root / 'config/party-preparation.json', config_fixture())
        for base in (self.root / 'bgi-scripts/AutoGameMaterialRoute', self.root / 'BetterGI/User/JsScript/AutoGameMaterialRoute'):
            base.mkdir(parents=True, exist_ok=True)
            (base / 'manifest.json').write_text('{}', encoding='utf-8')
            (base / 'main.js').write_text('// retained fake preparation package', encoding='utf-8')
        self.ledger_path = self.root / 'state' / material.LEDGER_NAME
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_bytes(b'opaque original ledger must never be read or changed by preparation')

    def run_preparation(self, dry=False, native_status='completed', existing=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=None, profile=material.PREPARATION_MODE,
            timeout_minutes=0, no_delay=True, allow_repeat=False, keep_game=False, allow_existing_game=False,
            graphics_check=False, preparation_config='config/party-preparation.json')
        stream = io.StringIO()
        host = PreparationFakeHost(self.root, existing=existing)
        host.native_status = native_status
        forbidden = ('constrain_route_day', 'constrain_route_session_day', 'assign_route_day', 'assign_route_session_day',
            'finalize_route_day', 'finalize_route_session_day', 'load_route_config', 'load_route_session_config', 'verify_route_file')
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(stream))
            stack.enter_context(patch.object(wf, 'datetime', FixedClock))
            stack.enter_context(patch.object(wf, 'prior_verified_tasks', side_effect=AssertionError('preparation cannot use core duplicate guard')))
            stack.enter_context(patch('checkin_hoyolab.execute_hoyolab_checkin', side_effect=AssertionError('must not check in')))
            stack.enter_context(patch('cultivation.load_cultivation_config', side_effect=AssertionError('must not read cultivation authorization')))
            for name in forbidden:
                stack.enter_context(patch.object(material, name, side_effect=AssertionError('preparation cannot select/reserve/execute a route')))
            code = wf.execute(args, host)
        return code, wf.read_json(json.loads(stream.getvalue())['resultPath']), host

    def test_preview_has_one_group_zero_budgets_no_farming_lease_and_is_never_completed(self):
        before = self.ledger_path.read_bytes()
        code, result, host = self.run_preparation(dry=True)
        self.assertEqual(code, 0, result)
        self.assertFalse(host.launched)
        self.assertEqual(result['outcome'], 'planned')
        self.assertEqual(result['expectedTasks'], [material.PREPARATION_TASK_NAME])
        self.assertEqual(result['timeBudget']['maximumMinutes'], 5)
        self.assertNotIn('materialRouteLease', result)
        self.assertNotIn('materialRouteEligibility', result)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        generated = wf.read_json(result['plannedConfig'])
        self.assertTrue(generated['SkipFinalRewardCheck'])
        self.assertEqual(sum(generated['TaskEnabledList'].values()), 1)

    def test_fake_live_launches_once_without_ledger_or_base_config_mutation(self):
        before = self.ledger_path.read_bytes()
        code, result, host = self.run_preparation()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'completed', result)
        self.assertTrue(result['partyPreparation']['noRouteExecution'])
        self.assertNotIn('materialRoute', result)
        self.assertNotIn('materialRouteLease', result)
        self.assertEqual(host.launch_calls, 1)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.assertTrue((Path(result['logArchive']) / 'party-preparation-report.json').is_file())
        self.assertEqual(self.base_path.read_bytes(), self.before)

    def test_repeated_preparation_bypasses_core_completion_guard_only(self):
        for _ in range(2):
            code, result, host = self.run_preparation()
            self.assertEqual(code, 0, result)
            self.assertEqual(host.launch_calls, 1)
        self.assertNotIn('materialRouteLease', result)

    def test_existing_game_is_rejected_without_launch_or_takeover(self):
        code, result, host = self.run_preparation(existing=True)
        self.assertNotEqual(code, 0)
        self.assertFalse(host.launched)
        self.assertEqual(host.stopped_game_pids, [])

    def test_failed_preparation_stops_without_retry(self):
        code, result, host = self.run_preparation(native_status='failed')
        self.assertNotEqual(code, 0)
        self.assertEqual(result['outcome'], 'failed', result)
        self.assertEqual(host.launch_calls, 1)

    def test_outer_budget_cannot_exceed_five_minutes(self):
        with self.assertRaises(wf.WorkflowError):
            wf.time_budget(self.cfg, None, material.PREPARATION_MODE, 5.1)

    def test_shared_lock_cannot_be_bypassed_by_preparation(self):
        with wf.RunLock(self.root / 'state/workflow.lock'):
            code, result, host = self.run_preparation()
        self.assertNotEqual(code, 0)
        self.assertFalse(host.launched)
