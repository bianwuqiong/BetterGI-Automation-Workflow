"""Retained fake route evidence; none of these tests run a game."""
import argparse
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import material_route as route
from tests import test_workflow as workflow_tests
from tests.test_workflow import FakeHost, FakeProcess, FixedClock, wf

ROOT = Path(__file__).resolve().parents[1]


def route_fixture():
    return {'relativePath': 'auto_game_handguard/' + 'a' * 40 + '/sample.json', 'sha256': 'b' * 64,
        'catalogCommit': 'a' * 40, 'name': 'sample', 'fightPoints': [{'x': 100, 'y': 200}, {'x': 115, 'y': 210}]}


def report_fixture(bgi, run_id, group, config_name='AutoGame_test', *, gains=1):
    settings = group['Projects'][0]['JsScriptSettingsObject']
    request = route._native_parameters(settings)
    points = settings['route']['fightPoints']
    ids = [request['sha256'] + ':' + str(p['x']) + ',' + str(p['y']) for p in points]
    native = {'task': 'material-route', 'status': 'completed', **request, 'parameterEvidence': request,
        'fightPointCount': len(points), 'completedFightPoints': ids, 'observedHoldCasts': 1,
        'shieldEvidence': 'hold_skill_cooldown_observed', 'cleanupCompleted': True,
        'noResinSpend': True, 'noCrafting': True, 'noUpgrade': True, 'noFood': True,
        'noRevive': True, 'ordinaryPick': True, 'mainUiRestored': True, 'elapsedMs': 40000,
        'actualTeam': ['钟离', '雷电将军', '优菈', '罗莎莉亚']}
    before = {key: {'count': 0, 'status': 'exact'} for key in route.MATERIAL_IDS}
    after = copy.deepcopy(before)
    after['112044']['count'] = gains
    report = {'schemaVersion': 1, 'runId': run_id, 'gameDate': settings['gameDate'], 'mode': route.MODE,
        'status': 'success', 'route': settings['route'], 'partyName': settings['partyName'],
        'strategyName': route.STRATEGY_NAME, 'requireZhongliShield': True, 'noResinSpend': True,
        'noCrafting': True, 'noUpgrade': True, 'targetReached': False, 'rewards': {}, 'resinEvents': [],
        'startedAt': settings['gameDate'] + 'T00:00:00Z', 'finishedAt': settings['gameDate'] + 'T00:01:00Z',
        'wallSeconds': 60, 'beforeInventory': before, 'afterInventory': after,
        'materialGains': {'112044': gains, '112045': 0, '112046': 0}, 'materialGainsVerified': True,
        'nativeReturnCompleted': True, 'parameterEvidence': request, 'nativeResult': native}
    path = bgi / 'User/JsScript/AutoGameMaterialRoute/record' / (run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding='utf-8')
    before_event = {'task': 'material-route-inventory', 'runId': run_id, 'gameDate': settings['gameDate'],
        'phase': 'before', 'status': 'exact', 'counts': {k: 0 for k in route.MATERIAL_IDS}}
    after_event = {**before_event, 'phase': 'after', 'counts': {k: after[k]['count'] for k in route.MATERIAL_IDS}}
    start_event = {'task': 'material-route', 'status': 'started', **request, 'parameterEvidence': request}
    shield = {'task': 'material-route-shield-cast', 'status': 'cast_observed', 'runId': run_id,
        'routePath': request['routePath'], 'sha256': request['sha256'], 'evidence': 'hold_skill_cooldown_observed'}
    fights = [{'task': 'material-route-fight', 'status': 'cleared', 'runId': run_id,
        'routePath': request['routePath'], 'sha256': request['sha256'], 'pointId': ids[i], **point,
        'enemyObserved': True, 'battleEndDetected': True,
        'evidence': 'enemy_bloodbar_observed_then_party_setup_progress_white_yellow_detected_and_pickup_returned'}
        for i, point in enumerate(points)]
    plugin = {'task': route.TASK_NAME, 'runId': run_id, 'gameDate': settings['gameDate'], 'mode': route.MODE,
        'status': 'success', 'reportRelativePath': f'record/{run_id}.json', 'evidenceVerified': True}
    events = [before_event, start_event, shield, *fights, native, after_event, plugin]
    if 'expectedTeam' in settings:
        events.insert(2, {'task': 'material-route-team', 'status': 'verified', 'runId': run_id,
            'expectedTeam': settings['expectedTeam'], 'actualTeam': settings['expectedTeam'],
            'slots': [1, 2, 3, 4], 'twoFrames': True, 'skipPartyMenu': True})
    text = '\n'.join([f'参数指定的一条龙配置：{config_name}', '配置组任务执行: 1/1',
        *['[AUTO_GAME_EVENT] ' + json.dumps(e) for e in events], '一条龙和配置组任务结束'])
    return path, report, text, events


class RouteEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('material-route-' + uuid4().hex[:10])
        self.bgi = self.root / 'fake-bgi'
        self.group = route.build_route_group('test-run', {'partyName': 'Test party'}, route_fixture(), game_date='2026-10-09')
        self.path, self.report, self.text, self.events = report_fixture(self.bgi, 'test-run', self.group)

    def verify(self, text=None, execution='exited'):
        return route.verify_material_route_report(text or self.text, self.bgi, 'test-run', self.group, 'AutoGame_test', execution)

    def save(self, report):
        self.path.write_text(json.dumps(report), encoding='utf-8')

    def test_native_point_cleanup_and_actual_inventory_are_separate(self):
        result = self.verify()
        self.assertEqual(result['outcome'], 'completed', result['warnings'])
        self.assertTrue(result['materialRoute']['routeCompleted'])
        self.assertTrue(result['materialRoute']['materialGainsVerified'])
        self.assertEqual(result['materialRoute']['materialGains']['112044'], 1)
        self.assertEqual(result['rewards'], {})
        self.assertEqual(result['resinEvents'], [])
        self.assertEqual(self.verify(execution='running')['outcome'], 'partial')
        self.path, self.report, self.text, self.events = report_fixture(self.bgi, 'test-run', self.group, gains=0)
        self.assertTrue(self.verify()['materialRoute']['zeroGains'])

    def test_native_return_and_js_success_without_native_end_cannot_complete(self):
        native = '[AUTO_GAME_EVENT] ' + json.dumps(self.events[-3])
        for text in (self.text.replace(native + '\n', ''), self.text.replace(native, native + '\n' + native)):
            self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_elapsed_json_integer_float_transport_is_lossless_only(self):
        native = '[AUTO_GAME_EVENT] ' + json.dumps(self.events[-3])
        event = copy.deepcopy(self.events[-3])
        event['elapsedMs'] = 40000.0
        text = self.text.replace(native, '[AUTO_GAME_EVENT] ' + json.dumps(event))
        self.assertEqual(self.verify(text)['outcome'], 'completed')
        # An equal Python bool or a rounded/different numeric value cannot pass.
        for value in (True, None, '40000', 39999.999, -1, float('nan'), float('inf'), 486000):
            event = copy.deepcopy(self.events[-3])
            event['elapsedMs'] = value
            report = copy.deepcopy(self.report)
            if value != 39999.999:
                report['nativeResult']['elapsedMs'] = value
            self.save(report)
            text = self.text.replace(native, '[AUTO_GAME_EVENT] ' + json.dumps(event))
            self.assertEqual(self.verify(text)['outcome'], 'unknown', value)
        self.save(self.report)

    def test_scope_resource_claim_and_missing_point_fail_closed(self):
        variants = [self.text.replace('AutoGame_test', 'AutoGame_other'),
            self.text.replace('配置组任务执行: 1/1', '配置组任务执行: 1/2'),
            self.text.replace('"runId": "test-run"', '"runId": "other"', 1),
            self.text.replace('"enemyObserved": true', '"enemyObserved": false', 1),
            self.text.replace('"cleanupCompleted": true', '"cleanupCompleted": false'),
            self.text.replace('"actualTeam": [', '"actualTeam": null, "unusedTeam": ['),
            self.text + '\n奖励领取成功', self.text + '\n已使用1个脆弱树脂',
            self.text + '\n[AUTO_GAME_EVENT] {broken']
        for text in variants:
            with self.subTest(text=text):
                self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_inventory_unknown_negative_missing_and_forged_delta_stay_unknown(self):
        variants = []
        for value in (None, -1, True):
            report = copy.deepcopy(self.report)
            report['afterInventory']['112044']['count'] = value
            variants.append(report)
        report = copy.deepcopy(self.report)
        del report['afterInventory']['112045']
        variants.append(report)
        variants.extend([{**self.report, 'materialGains': {'112044': 20, '112045': 0, '112046': 0}},
            {**self.report, 'rewards': {'破旧的刀镡': 1}}, {**self.report, 'targetReached': True}])
        for report in variants:
            self.save(report)
            self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_cancelled_preserves_exact_before_and_after_points_without_success(self):
        report = copy.deepcopy(self.report)
        report.update(status='cancelled', nativeReturnCompleted=False)
        report['nativeResult'].update(status='cancelled', completedFightPoints=[])
        events = copy.deepcopy(self.events)
        events[-3] = report['nativeResult']
        events[-1]['status'] = 'cancelled'
        self.save(report)
        text = '\n'.join(['参数指定的一条龙配置：AutoGame_test', '配置组任务执行: 1/1',
            *['[AUTO_GAME_EVENT] ' + json.dumps(e) for e in events], '一条龙和配置组任务结束'])
        result = self.verify(text)
        self.assertEqual(result['outcome'], 'failed', result['warnings'])
        self.assertEqual(result['materialRoute']['actualInventory']['before']['112044'], 0)
        self.assertFalse(result['materialRoute']['materialGainsVerified'])

    def test_completed_route_with_unknown_after_inventory_does_not_claim_gains(self):
        report = copy.deepcopy(self.report)
        report.update(status='unknown', afterInventory=None, materialGainsVerified=False, materialGains={})
        events = copy.deepcopy(self.events)
        events[-1]['status'] = 'unknown'
        self.save(report)
        text = '\n'.join(['参数指定的一条龙配置：AutoGame_test', '配置组任务执行: 1/1',
            *['[AUTO_GAME_EVENT] ' + json.dumps(e) for e in events], '一条龙和配置组任务结束'])
        result = self.verify(text)
        self.assertEqual(result['outcome'], 'unknown', result['warnings'])
        self.assertTrue(result['materialRoute']['routeCompleted'])
        self.assertTrue(result['materialRoute']['reportVerified'])
        self.assertFalse(result['materialRoute']['materialGainsVerified'])
        self.assertEqual(result['materialRoute']['actualInventory']['before']['112044'], 0)

    def test_package_scope_hash_and_partial_deployment_are_rejected(self):
        for relative in ('../other.json', '/other.json', 'auto_game_handguard/../../outside.json', 'other/x.json'):
            with self.assertRaises(ValueError):
                route.normalize_route({**route_fixture(), 'relativePath': relative})
        source = self.root / 'source'
        deployed = self.bgi / 'User/JsScript/AutoGameMaterialRoute'
        source.mkdir(parents=True)
        for name in ('manifest.json', 'main.js'):
            (source / name).write_text('{}', encoding='utf-8')
            (deployed / name).write_text('{}', encoding='utf-8')
        route.prepare_material_route_plugin(source, self.bgi)
        (deployed / 'main.js').write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            route.prepare_material_route_plugin(source, self.bgi)


class RouteDayTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('route-day-' + uuid4().hex[:10])
        self.now = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
        self.route = route_fixture()

    def test_game_day_four_am_boundary_and_stale_claim(self):
        self.assertEqual(route.game_date_at(datetime(2026, 10, 8, 19, 59, tzinfo=timezone.utc)), '2026-10-08')
        self.assertEqual(route.game_date_at(datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)), '2026-10-09')
        with self.assertRaises(ValueError):
            route.assign_route_day(self.root, '2026-10-08', self.route, 'run1', now=self.now)

    def test_started_unknown_failed_and_cancelled_are_never_replayed_by_hash_change(self):
        for status in ('unknown', 'failed', 'cancelled'):
            root = self.root / status
            route.assign_route_day(root, '2026-10-09', self.route, 'run1', now=self.now)
            route.finalize_route_day(root, '2026-10-09', 'run1', status, now=self.now)
            with self.assertRaises(ValueError):
                route.constrain_route_day(root, '2026-10-09', {**self.route, 'sha256': 'c' * 64})
        root = self.root / 'started'
        route.assign_route_day(root, '2026-10-09', self.route, 'run1', now=self.now)
        with self.assertRaises(ValueError):
            route.assign_route_day(root, '2026-10-09', self.route, 'run2', now=self.now)

    def test_cross_file_nearby_fight_is_conservatively_blocked_but_next_day_is_eligible(self):
        route.assign_route_day(self.root, '2026-10-09', self.route, 'run1', now=self.now)
        other = {**self.route, 'relativePath': self.route['relativePath'].replace('sample', 'other'),
                 'sha256': 'c' * 64, 'fightPoints': [{'x': 125, 'y': 210}]}
        with self.assertRaisesRegex(ValueError, 'potentially overlap'):
            route.constrain_route_day(self.root, '2026-10-09', other)
        self.assertTrue(route.constrain_route_day(self.root, '2026-10-10', other)['eligible'])

    def test_daily_budget_does_not_refund_unknown_runtime_or_expand_to_full_day(self):
        route.assign_route_day(self.root, '2026-10-09', self.route, 'run1', now=self.now)
        other = {**self.route, 'relativePath': self.route['relativePath'].replace('sample', 'other'),
            'sha256': 'c' * 64, 'fightPoints': [{'x': 500, 'y': 500}]}
        route.assign_route_day(self.root, '2026-10-09', other, 'run2', now=self.now)
        third = {**other, 'relativePath': other['relativePath'].replace('other', 'third'),
            'sha256': 'd' * 64, 'fightPoints': [{'x': 900, 'y': 900}]}
        route.assign_route_day(self.root, '2026-10-09', third, 'run3', now=self.now)
        fourth = {**third, 'relativePath': third['relativePath'].replace('third', 'fourth'),
            'sha256': 'e' * 64, 'fightPoints': [{'x': 1300, 'y': 1300}]}
        with self.assertRaisesRegex(ValueError, '30 minutes'):
            route.constrain_route_day(self.root, '2026-10-09', fourth)


class RouteNoAttemptAuditTests(unittest.TestCase):
    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        self.run_id = 'preworld-run'
        self.day = '2026-10-09'
        self.now = datetime(2026, 10, 9, tzinfo=timezone.utc)
        self.route = route_fixture()
        self.directory = self.root / 'logs/runs' / self.run_id
        self.directory.mkdir(parents=True)
        self.bgi = self.root / 'BetterGI'
        self.group = route.build_route_group(self.run_id, {'partyName': 'Test party'}, self.route, game_date=self.day)
        group_path = self.bgi / 'User/ScriptGroup' / (self.group['Name'] + '.json')
        wf.atomic_json(group_path, self.group)
        wf.atomic_json(self.directory / 'material-route-group.json', self.group)
        template = route.inject_material_route_task(wf.read_json(self.base_path))
        dragon = wf.make_config(template, [route.TASK_ID], 'AutoGame_' + self.run_id, {}, skip_final_reward_check=True)
        dragon['TaskDefinitions'][route.TASK_ID] = self.group['Name']
        config_path = self.bgi / 'User/OneDragon' / ('AutoGame_' + self.run_id + '.json')
        wf.atomic_json(config_path, dragon)
        wf.atomic_json(self.directory / 'one-dragon.json', dragon)
        (self.bgi / 'BetterGI.dll').write_bytes(b'fake retained executable evidence')
        controller = self.root / 'src/bettergi-custom/BetterGenshinImpact/ViewModel/Pages/OneDragonFlowViewModel.cs'
        gate = self.root / 'src/bettergi-custom/BetterGenshinImpact/Service/ScriptService.cs'
        controller.parent.mkdir(parents=True)
        gate.parent.mkdir(parents=True)
        controller.write_text('await ScriptService.StartGameTask();\n配置组任务执行:', encoding='utf-8')
        gate.write_text('StartGameTask(bool waitForMainUi = true)\n当前不在游戏主界面，等待进入主界面后执行任务', encoding='utf-8')
        self.raw = self.bgi / 'log/no-attempt.log'
        messages = ['实例 IPC v2 已启动：Primary', '主窗体实例化',
            '参数指定的一条龙配置：AutoGame_' + self.run_id, '启用一条龙配置：AutoGame_' + self.run_id,
            '当前不在游戏主界面，等待进入主界面后执行任务...',
            '启动等待中尝试前台鼠标点击，等待已进行 20s',
            '启动等待中尝试前台鼠标点击，等待已进行 35s', '主窗体退出']
        seconds = [0, 1, 2, 3, 4, 24, 39, 59]
        self.text = ''.join(f'[08:00:{seconds[i]:02}.000] [INF] [Primary:S1:P1234:T1]\n{m}\n\n' for i, m in enumerate(messages))
        self.raw.write_bytes(self.text.encode('utf-8'))
        self.archive = self.directory / 'bettergi.log'
        self.archive.write_text(self.text, encoding='utf-8')
        wf.atomic_json(self.directory / 'log-offsets.json', {str(self.raw.resolve()): 0})
        self.result = {'schemaVersion': 2, 'runId': self.run_id, 'gameDate': self.day, 'mode': route.MODE,
            'outcome': 'unknown', 'executionOutcome': 'cancelled', 'expectedTasks': [route.TASK_NAME],
            'launchedAt': '2026-10-09T00:00:00Z', 'finishedAt': '2026-10-09T00:01:00Z', 'bettergiPid': 1234,
            'runtimeConfig': str(config_path.resolve()), 'runtimeMaterialRouteGroup': str(group_path.resolve())}
        wf.atomic_json(self.directory / 'result.json', self.result)
        route.assign_route_day(self.root, self.day, self.route, self.run_id, now=self.now)
        route.finalize_route_day(self.root, self.day, self.run_id, 'unknown', now=self.now)

    def review(self):
        with wf.RunLock(self.root / 'state/workflow.lock'):
            return route.write_route_no_attempt_review(self.root, self.run_id)

    def test_complete_positive_preworld_audit_releases_only_unattempted_lease(self):
        ledger_before = (self.root / 'state' / route.LEDGER_NAME).read_bytes()
        result_before = (self.directory / 'result.json').read_bytes()
        with self.assertRaises(ValueError):
            route.constrain_route_day(self.root, self.day, self.route)
        proof = self.review()
        self.assertEqual(proof['verdict'], 'no-route-attempt')
        self.assertTrue(route.constrain_route_day(self.root, self.day, self.route)['eligible'])
        self.assertEqual((self.root / 'state' / route.LEDGER_NAME).read_bytes(), ledger_before)
        self.assertEqual((self.directory / 'result.json').read_bytes(), result_before)
        with self.assertRaisesRegex(ValueError, 'runId already'):
            route.assign_route_day(self.root, self.day, self.route, self.run_id, now=self.now)
        # Another route which actually started remains reserved independently.
        other = {**self.route, 'sha256': 'c' * 64, 'relativePath': self.route['relativePath'].replace('sample', 'other'),
            'fightPoints': [{'x': 500, 'y': 500}]}
        route.assign_route_day(self.root, self.day, other, 'actual-run', now=self.now)
        with self.assertRaises(ValueError):
            route.constrain_route_day(self.root, self.day, other)

    def test_changed_source_hash_restores_conservative_reservation(self):
        self.review()
        self.assertTrue(route.constrain_route_day(self.root, self.day, self.route)['eligible'])
        (self.bgi / 'BetterGI.dll').write_bytes(b'changed executable')
        with self.assertRaises(ValueError):
            route.constrain_route_day(self.root, self.day, self.route)

    def test_fake_absence_by_removing_archived_native_event_is_rejected(self):
        self.raw.write_bytes((self.text + '[08:00:08.000] [INF] [Primary:S1:P1234:T1]\n[AUTO_GAME_EVENT] {"task":"material-route"}\n').encode())
        with self.assertRaisesRegex(ValueError, 'complete owned raw log'):
            self.review()

    def test_matching_full_log_with_group_or_native_start_is_rejected(self):
        for marker in ('配置组任务执行: 1/1', '[AUTO_GAME_EVENT] {"task":"material-route","status":"started"}'):
            text = self.text.replace('主窗体退出', marker + '\n主窗体退出')
            self.raw.write_bytes(text.encode('utf-8'))
            self.archive.write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'downstream'):
                self.review()

    def test_wrong_run_scope_or_incomplete_log_never_releases(self):
        wf.atomic_json(self.directory / 'result.json', {**self.result, 'runId': 'other-run'})
        with self.assertRaises(ValueError):
            self.review()
        wf.atomic_json(self.directory / 'result.json', self.result)
        text = self.text.replace('主窗体退出', 'last record is incomplete')
        self.raw.write_bytes(text.encode('utf-8'))
        self.archive.write_text(text, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'lifecycle incomplete'):
            self.review()

    def test_route_record_or_world_gate_absence_blocks_release(self):
        record = self.bgi / 'User/JsScript/AutoGameMaterialRoute/record' / (self.run_id + '.json')
        record.parent.mkdir(parents=True)
        record.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'record/checkpoint exists'):
            self.review()


class MaterialFakeHost(FakeHost):
    def launch(self, exe, name):
        self.launched = True
        self.process = FakeProcess()
        generated = wf.read_json(exe.parent / 'User/OneDragon' / (name + '.json'))
        group_name = next(v for k, v in generated['TaskDefinitions'].items() if generated['TaskEnabledList'][k])
        group = wf.read_json(exe.parent / 'User/ScriptGroup' / (group_name + '.json'))
        run_id = group['Projects'][0]['JsScriptSettingsObject']['runId']
        _, _, text, _ = report_fixture(exe.parent, run_id, group, name)
        (exe.parent / 'log/new.log').write_text(text, encoding='utf-8')
        return self.process


class FailedMaterialHost(MaterialFakeHost):
    def launch(self, exe, name):
        process = super().launch(exe, name)
        generated = wf.read_json(exe.parent / 'User/OneDragon' / (name + '.json'))
        group_name = next(v for k, v in generated['TaskDefinitions'].items() if generated['TaskEnabledList'][k])
        group = wf.read_json(exe.parent / 'User/ScriptGroup' / (group_name + '.json'))
        run_id = group['Projects'][0]['JsScriptSettingsObject']['runId']
        path, report, text, events = report_fixture(exe.parent, run_id, group, name)
        report.update(status='failed', nativeReturnCompleted=False)
        report['nativeResult'].update(status='failed', completedFightPoints=[])
        path.write_text(json.dumps(report), encoding='utf-8')
        events[-3] = report['nativeResult']
        events[-1]['status'] = 'failed'
        text = '\n'.join([f'参数指定的一条龙配置：{name}', '配置组任务执行: 1/1',
            *['[AUTO_GAME_EVENT] ' + json.dumps(e) for e in events], '一条龙和配置组任务结束'])
        (exe.parent / 'log/new.log').write_text(text, encoding='utf-8')
        return process


class CancelMaterialHost(MaterialFakeHost):
    def launch(self, exe, name):
        self.launched = True
        self.process = FakeProcess(stuck=True)
        (exe.parent / 'log/new.log').write_text(f'参数指定的一条龙配置：{name}\n配置组任务执行: 1/1\n', encoding='utf-8')
        run_id = name.removeprefix('AutoGame_')
        wf.atomic_json(self.root / 'logs/runs' / run_id / 'stop-request.json', {'reason': 'synthetic explicit stop'})
        return self.process


class MaterialWorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        self.route = route_fixture()
        fixed = self.root / 'BetterGI/User/AutoPathing' / self.route['relativePath']
        fixed.parent.mkdir(parents=True, exist_ok=True)
        fixed.write_text(json.dumps({'positions': [{'action': 'fight', **p} for p in self.route['fightPoints']]}), encoding='utf-8')
        self.route['sha256'] = hashlib.sha256(fixed.read_bytes()).hexdigest()
        wf.atomic_json(self.root / 'BetterGI/User/AutoPathing/auto_game_handguard/manifest.json',
            {'routes': [{'path': self.route['relativePath'], 'sha256': self.route['sha256']}]})
        wf.atomic_json(self.root / 'config/material-route.json', {'partyName': 'Test party', 'strategyName': route.STRATEGY_NAME,
            'requireZhongliShield': True, 'timeoutSeconds': 480, 'route': self.route})
        for base in (self.root / 'bgi-scripts/AutoGameMaterialRoute', self.root / 'BetterGI/User/JsScript/AutoGameMaterialRoute'):
            base.mkdir(parents=True, exist_ok=True)
            (base / 'manifest.json').write_text('{}', encoding='utf-8')
            (base / 'main.js').write_text('// fake retained package', encoding='utf-8')

    def run_route(self, dry=False, host_type=MaterialFakeHost):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=None, profile='material-route', timeout_minutes=0,
            no_delay=True, allow_repeat=False, keep_game=False, allow_existing_game=False, graphics_check=False)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), patch.object(wf, 'datetime', FixedClock), \
                patch('checkin_hoyolab.execute_hoyolab_checkin', side_effect=AssertionError('must not check in')):
            code = wf.execute(args, host_type(self.root))
        return code, wf.read_json(json.loads(stream.getvalue())['resultPath'])

    def test_preview_is_one_route_and_never_assigns_lease_or_changes_resin_authorization(self):
        receipt = self.root / 'state/cultivation-authorization.json'
        wf.atomic_json(receipt, {'originalResinCap': 60, 'unknownReservation': 40})
        code, result = self.run_route(dry=True)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['expectedTasks'], ['刀镡路线'])
        self.assertEqual(result['timeBudget']['maximumMinutes'], 16)
        generated = wf.read_json(result['plannedConfig'])
        self.assertTrue(generated['SkipFinalRewardCheck'])
        self.assertEqual(sum(generated['TaskEnabledList'].values()), 1)
        self.assertNotIn('hoyolabCheckin', result)
        self.assertNotIn('cultivationAuthorization', result)
        self.assertFalse((self.root / 'state' / route.LEDGER_NAME).exists())
        self.assertEqual(wf.read_json(receipt)['unknownReservation'], 40)
        self.assertEqual(self.base_path.read_bytes(), self.before)

    def test_fake_live_route_archives_evidence_reserves_points_and_blocks_same_day_replay(self):
        code, result = self.run_route()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'completed')
        self.assertTrue(result['materialRoute']['materialGainsVerified'])
        self.assertEqual(result['rewards'], {})
        self.assertEqual(result['materialRouteLease']['status'], 'completed')
        self.assertTrue((Path(result['logArchive']) / 'material-route-report.json').is_file())
        self.assertEqual(self.base_path.read_bytes(), self.before)
        code, result = self.run_route()
        self.assertNotEqual(code, 0)
        self.assertTrue(any('already reserved' in e for e in result['errors']))

    def test_timeout_cannot_expand_past_sixteen_minutes(self):
        with self.assertRaises(wf.WorkflowError):
            wf.time_budget(self.cfg, None, 'material-route', 17)

    def test_failed_native_keeps_inventory_points_and_consumed_day_lease(self):
        code, result = self.run_route(host_type=FailedMaterialHost)
        self.assertNotEqual(code, 0)
        self.assertEqual(result['outcome'], 'failed', result)
        self.assertTrue(result['materialRoute']['fightPointEvidence'])
        self.assertEqual(result['materialRoute']['actualInventory']['before']['112044'], 0)
        self.assertEqual(result['materialRouteLease']['status'], 'failed')
        with self.assertRaises(ValueError):
            route.constrain_route_day(self.root, result['gameDate'], self.route)

    def test_explicit_stop_uses_owned_cleanup_and_keeps_unknown_reservation(self):
        code, result = self.run_route(host_type=CancelMaterialHost)
        self.assertEqual(code, 9, result)
        self.assertEqual(result['executionOutcome'], 'cancelled')
        self.assertFalse(result['materialRoute']['reportVerified'])
        self.assertEqual(result['materialRouteLease']['status'], 'unknown')
        self.assertNotIn('farmingSeconds', result['materialRouteLease'])
        with self.assertRaises(ValueError):
            route.constrain_route_day(self.root, result['gameDate'], self.route)


if __name__ == '__main__':
    unittest.main()
