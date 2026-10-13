"""Pure and fake two-segment session checks. No game processes or resources."""
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
from tests.test_material_route import route_fixture, report_fixture
from tests import test_material_route as material_tests
from tests.test_workflow import FakeHost, FakeProcess, FixedClock, wf

TEAM = ['钟离', '雷电将军', '优菈', '罗莎莉亚']
DAY = '2026-10-09'


def config_fixture():
    first = route_fixture()
    second = copy.deepcopy(first)
    second.update(relativePath=first['relativePath'].replace('sample', 'second'), sha256='c' * 64,
        fightPoints=[{'x': 1000, 'y': 2000}])
    return {'partyName': 'Test party', 'expectedTeam': TEAM, 'strategyName': route.STRATEGY_NAME,
        'requireZhongliShield': True, 'safeHub': 'mondstadt-city',
        'segments': [{'route': first, 'timeoutSeconds': 120}, {'route': second, 'timeoutSeconds': 150}]}


def event_line(event):
    return '[AUTO_GAME_EVENT] ' + json.dumps(event, ensure_ascii=False)


def recovery_fixture(run_id, session_id, phase='after'):
    request = {'runId': run_id, 'sessionId': session_id, 'stage': phase,
        'expectedTeam': TEAM, 'partyName': 'Test party', 'safeHub': 'mondstadt-city', 'timeoutSeconds': 60}
    return {'task': 'material-route-recovery', 'runId': run_id, 'sessionId': session_id, 'stage': phase,
        'status': 'completed', 'parameterEvidence': request, 'evidenceVerified': True, 'mainUiRestored': True,
        'grounded': True, 'positionVerified': True, 'noRevivePrompt': True, 'teamVerified': True,
        'cleanupCompleted': True, 'loadingObserved': True, 'scopeRecovered': True,
        'noResinSpend': True, 'noFood': True, 'noRevive': True, 'noCrafting': True, 'noUpgrade': True,
        'actualTeam': TEAM, 'actualPosition': {'x': -867.7041015625, 'y': 2281.378173828125}, 'elapsedMs': 5000}


def session_fixture(bgi, session_id, group, *, first_failed=False, skipped=False):
    payload = route._session_payload(group)
    rows = []
    initial = recovery_fixture(session_id, session_id, 'startup')
    events = [{**initial, 'status': 'started'}, initial]
    for i, row in enumerate(payload['segments']):
        scope = {'task': 'material-route-segment', 'runId': row['runId'], 'sessionId': session_id,
            'segmentId': row['segmentId']}
        if i == 1 and skipped:
            events.append({**scope, 'status': 'not-started', 'evidenceVerified': True})
            rows.append({'runId': row['runId'], 'segmentId': row['segmentId'], 'status': 'not-started'})
            continue
        single = route.build_route_group(row['runId'], payload, row['route'], game_date=payload['gameDate'],
            max_minutes=3 if row['timeoutSeconds'] == 150 else 2, timeout_seconds=row['timeoutSeconds'])
        path, report, _, segment_events = report_fixture(bgi, row['runId'], single)
        report.update(sessionId=session_id, segmentId=row['segmentId'])
        report['inventoryObservations'] = {}
        for phase in ('before', 'after'):
            report['inventoryObservations'][phase] = [
                {'observedAt': payload['gameDate'] + 'T00:00:' + ('01.000Z' if n == 0 else '01.180Z'),
                 'inventory': copy.deepcopy(report[phase + 'Inventory'])} for n in range(2)]
        for scan in segment_events:
            if scan['task'] == 'material-route-inventory':
                scan['observationCount'] = 2
        if i == 0 and first_failed:
            report.update(status='failed', nativeReturnCompleted=False)
            report['nativeResult'].update(status='failed', cleanupCompleted=False)
            segment_events[-3].update(status='failed', cleanupCompleted=False)
            segment_events[-1]['status'] = 'failed'
        path.write_text(json.dumps(report), encoding='utf-8')
        events.append({**scope, 'status': 'started'})
        events.extend(segment_events)
        recovery = recovery_fixture(row['runId'], session_id)
        events.extend([{**recovery, 'status': 'started'}, recovery])
        events.append({**scope, 'status': 'finished'})
        rows.append({'runId': row['runId'], 'segmentId': row['segmentId'], 'status': report['status']})
    report = {'schemaVersion': 1, 'runId': session_id, 'sessionId': session_id, 'gameDate': payload['gameDate'],
        'mode': route.SESSION_MODE, 'status': 'failed' if first_failed else 'success', 'noResinSpend': True,
        'noCrafting': True, 'noUpgrade': True, 'rewards': {}, 'resinEvents': [], 'segments': rows}
    report.update(startedAt=payload['gameDate'] + 'T00:00:00Z', finishedAt=payload['gameDate'] + 'T00:03:00Z', wallSeconds=180)
    path = bgi / 'User/JsScript/AutoGameMaterialRoute/record' / (session_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding='utf-8')
    events.append({'task': route.SESSION_MODE, 'runId': session_id, 'sessionId': session_id, 'gameDate': payload['gameDate'],
        'status': report['status'], 'reportRelativePath': 'record/' + session_id + '.json', 'evidenceVerified': True})
    text = '\n'.join(['参数指定的一条龙配置：AutoGame_' + session_id, '配置组任务执行: 1/1',
        *[event_line(event) for event in events], '一条龙和配置组任务结束'])
    return report, text, events


class SessionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / 'tests/.artifacts' / ('material-session-' + uuid4().hex[:10])
        self.bgi = self.root / 'BetterGI'
        self.config = config_fixture()
        self.group = route.build_route_session_group('test-session', self.config, game_date=DAY)
        self.report, self.text, self.events = session_fixture(self.bgi, 'test-session', self.group)

    def verify(self, text=None):
        return route.verify_material_route_session_report(text or self.text, self.bgi, 'test-session',
            self.group, 'AutoGame_test-session', 'exited')

    def test_two_separate_scopes_and_fractional_native_seconds(self):
        result = self.verify()
        self.assertEqual(result['outcome'], 'completed', result['warnings'])
        self.assertEqual([r['runId'] for r in result['materialRoute']['segments']], ['test-session-s1', 'test-session-s2'])
        self.assertEqual(result['materialRoute']['farmingSeconds'], 80)
        self.assertEqual(result['materialRoute']['materialGains']['112044'], 2)
        self.assertEqual(len(self.group['Projects']), 1)

    def test_single_after_recovery_missing_or_ungrounded_cannot_complete(self):
        for key in ('grounded', 'positionVerified', 'mainUiRestored', 'noRevivePrompt', 'teamVerified'):
            events = copy.deepcopy(self.events)
            next(e for e in events if e['task'] == 'material-route-recovery' and e['status'] != 'started')[key] = False
            text = self.text
            for old, new in zip(self.events, events):
                text = text.replace(event_line(old), event_line(new))
            self.assertEqual(self.verify(text)['outcome'], 'unknown', key)

    def test_no_enemy_is_never_cleared(self):
        events = copy.deepcopy(self.events)
        next(e for e in events if e['task'] == 'material-route-fight')['enemyObserved'] = False
        text = self.text
        for old, new in zip(self.events, events):
            text = text.replace(event_line(old), event_line(new))
        self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_exact_team_event_cannot_accept_swapped_slots_or_one_frame(self):
        for change in ({'slots': [2, 1, 3, 4]}, {'actualTeam': TEAM[::-1]}, {'twoFrames': False}, {'skipPartyMenu': 'true'}):
            events = copy.deepcopy(self.events)
            next(e for e in events if e['task'] == 'material-route-team').update(change)
            text = self.text
            for old, new in zip(self.events, events):
                text = text.replace(event_line(old), event_line(new))
            self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_second_segment_cannot_follow_first_failed(self):
        _, text, _ = session_fixture(self.bgi, 'test-session', self.group, first_failed=True)
        result = self.verify(text)
        self.assertEqual(result['outcome'], 'unknown')
        self.assertTrue(any('second segment began' in message for message in result['warnings']))

    def test_explicit_unattempted_second_segment_is_kept_separate(self):
        self.bgi = self.root / 'fresh-failure-bgi'
        _, text, _ = session_fixture(self.bgi, 'test-session', self.group, first_failed=True, skipped=True)
        result = self.verify(text)
        self.assertEqual(result['outcome'], 'failed', result['warnings'])
        self.assertTrue(result['materialRoute']['segments'][1]['noAttemptVerified'])
        self.assertFalse(result['materialRoute']['routeCompleted'])
        self.assertTrue(result['materialRoute']['segments'][0]['inventoryOnly'])
        self.assertEqual(result['materialRoute']['materialGains']['112044'], 1)

    def test_no_attempt_receipt_releases_only_skipped_scope_and_hash_changes_revoke_it(self):
        self.bgi = self.root / 'fresh-receipt-bgi'
        _, text, _ = session_fixture(self.bgi, 'test-session', self.group, first_failed=True, skipped=True)
        directory = self.root / 'logs/runs/test-session'
        wf.atomic_json(directory / 'material-route-group.json', self.group)
        wf.atomic_json(directory / 'result.json', {'executionOutcome': 'exited', 'outcome': 'failed',
            'runId': 'test-session', 'gameDate': DAY, 'mode': route.SESSION_MODE, 'expectedTasks': [route.TASK_NAME]})
        (directory / 'bettergi.log').write_text(text, encoding='utf-8')
        (self.bgi / 'BetterGI.dll').write_bytes(b'fake reviewed dll')
        now = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)
        lease = route.assign_route_session_day(self.root, DAY, self.config, 'test-session', now=now)
        verified = self.verify(text)
        self.assertTrue(verified['materialRoute']['reportVerified'], verified['warnings'])
        finalized = route.finalize_route_session_day(self.root, lease, verified['materialRoute'],
            directory=directory, bettergi_dir=self.bgi, wall_seconds=180)
        second = finalized['segments'][1]
        ledger_path = self.root / 'state' / route.LEDGER_NAME
        original_ledger = ledger_path.read_bytes()
        self.assertTrue(route._verified_session_no_attempt(self.root, second))
        eligibility = route.constrain_route_day(self.root, DAY, self.config['segments'][1]['route'], now=now, budget_seconds=150)
        self.assertEqual(eligibility['dailyUsedSeconds'], 40)
        with self.assertRaisesRegex(ValueError, 'already reserved'):
            route.constrain_route_day(self.root, DAY, self.config['segments'][0]['route'], now=now, budget_seconds=120)
        fresh = copy.deepcopy(self.config['segments'][1]['route'])
        fresh.update(relativePath=fresh['relativePath'].replace('second', 'fresh'), sha256='e' * 64,
            fightPoints=[{'x': 3000, 'y': 4000}])
        self.assertEqual(route.constrain_route_day(self.root, DAY, fresh, now=now, budget_seconds=60)['dailyUsedSeconds'], 40)
        receipt_path = self.root / 'logs/runs/test-session-s2/material-route-session-no-attempt-review.json'
        for source in (self.bgi / 'BetterGI.dll', directory / 'bettergi.log', receipt_path):
            original = source.read_bytes()
            if source == receipt_path:
                receipt = wf.read_json(source)
                receipt['sourceSha256'][next(iter(receipt['sourceSha256']))] = '0' * 64
                wf.atomic_json(source, receipt)
            else:
                source.write_bytes(original + b'\nstale audit source')
            self.assertFalse(route._verified_session_no_attempt(self.root, second))
            self.assertEqual(route.constrain_route_day(self.root, DAY, fresh, now=now, budget_seconds=60)['dailyUsedSeconds'], 190)
            with self.assertRaisesRegex(ValueError, 'already reserved'):
                route.constrain_route_day(self.root, DAY, self.config['segments'][1]['route'], now=now, budget_seconds=150)
            self.assertEqual(ledger_path.read_bytes(), original_ledger)
            source.write_bytes(original)
            self.assertTrue(route._verified_session_no_attempt(self.root, second))
        self.assertEqual(ledger_path.read_bytes(), original_ledger)

    def test_real_attempt_zero_seconds_keeps_existing_charge_semantics(self):
        attempted = {'reservedSeconds': 150, 'farmingSeconds': 0, 'evidence': {'nativeStarted': True}}
        self.assertEqual(route._charged_route_native_seconds(attempted), 0)
        unattempted = {'reservedSeconds': 150, 'farmingSeconds': 0, 'evidence': {'noAttemptVerified': True}}
        self.assertEqual(route._charged_route_native_seconds(unattempted), 150)

    def test_full_session_budget_is_combined_and_routes_cannot_overlap(self):
        now = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)
        prior = copy.deepcopy(self.config['segments'][0]['route'])
        prior.update(relativePath=prior['relativePath'].replace('sample', 'prior'), sha256='d' * 64,
            fightPoints=[{'x': -5000, 'y': -6000}])
        wf.atomic_json(self.root / 'state' / route.LEDGER_NAME,
            {'schemaVersion': 1, 'days': {DAY: [{'runId': 'prior', 'gameDate': DAY, 'route': prior,
                'status': 'unknown', 'farmingSeconds': 1462.89, 'reservedSeconds': 480}]}})
        self.assertEqual(route.constrain_route_session_day(self.root, DAY, self.config, now=now)['reservedSeconds'], 270)
        config = copy.deepcopy(self.config)
        config['segments'][1]['timeoutSeconds'] = 240
        with self.assertRaisesRegex(ValueError, 'combined'):
            route.constrain_route_session_day(self.root, DAY, config, now=now)
        config = copy.deepcopy(self.config)
        config['segments'][1]['route'] = config['segments'][0]['route']
        with self.assertRaisesRegex(ValueError, 'overlap'):
            route.constrain_route_session_day(self.root, DAY, config, now=now)

    def test_atomic_reservation_and_unknown_farming_freezes_both_routes(self):
        now = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)
        lease = route.assign_route_session_day(self.root, DAY, self.config, 'test-session', now=now)
        self.assertEqual([r['reservedSeconds'] for r in lease['segments']], [120, 150])
        with self.assertRaisesRegex(ValueError, 'already reserved'):
            route.constrain_route_session_day(self.root, DAY, self.config, now=now)
        result = route.finalize_route_session_day(self.root, lease, {}, directory=self.root / 'logs/runs/test-session',
            bettergi_dir=self.bgi, wall_seconds=60)
        self.assertEqual([r['status'] for r in result['segments']], ['unknown', 'unknown'])
        self.assertTrue((self.root / 'logs/runs/test-session-s1/result.json').is_file())

    def test_initial_recovery_failure_skips_both_without_farming_success(self):
        self.bgi = self.root / 'initial-failed-bgi'
        recovery = recovery_fixture('test-session', 'test-session', 'startup')
        recovery.update(status='failed', evidenceVerified=False, grounded=False)
        rows, events = [], [{**recovery, 'status': 'started'}, recovery]
        for row in route._session_payload(self.group)['segments']:
            rows.append({'runId': row['runId'], 'segmentId': row['segmentId'], 'status': 'not-started'})
            events.append({'task': 'material-route-segment', 'runId': row['runId'], 'sessionId': 'test-session',
                'segmentId': row['segmentId'], 'status': 'not-started', 'evidenceVerified': True})
        report = copy.deepcopy(self.report)
        report.update(status='failed', segments=rows)
        path = self.bgi / 'User/JsScript/AutoGameMaterialRoute/record/test-session.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding='utf-8')
        events.append({**self.events[-1], 'status': 'failed'})
        text = '\n'.join(['参数指定的一条龙配置：AutoGame_test-session', '配置组任务执行: 1/1',
            *[event_line(e) for e in events], '一条龙和配置组任务结束'])
        result = self.verify(text)
        self.assertEqual(result['outcome'], 'failed', result['warnings'])
        self.assertTrue(result['materialRoute']['reportVerified'])
        self.assertTrue(all(r['noAttemptVerified'] for r in result['materialRoute']['segments']))

    def test_native_success_and_recovery_failure_keeps_gains_and_stops_session(self):
        self.bgi = self.root / 'after-failed-bgi'
        _, text, events = session_fixture(self.bgi, 'test-session', self.group, first_failed=True, skipped=True)
        path = self.bgi / 'User/JsScript/AutoGameMaterialRoute/record/test-session-s1.json'
        report = wf.read_json(path)
        report.update(status='success', nativeReturnCompleted=True)
        report['nativeResult'].update(status='completed', cleanupCompleted=True)
        wf.atomic_json(path, report)
        parent = self.bgi / 'User/JsScript/AutoGameMaterialRoute/record/test-session.json'
        parent_report = wf.read_json(parent)
        parent_report['segments'][0]['status'] = 'success'
        wf.atomic_json(parent, parent_report)
        updated = copy.deepcopy(events)
        next(e for e in updated if e['task'] == route.MODE and e['status'] != 'started').update(status='completed', cleanupCompleted=True)
        next(e for e in updated if e['task'] == route.TASK_NAME)['status'] = 'success'
        next(e for e in updated if e['task'] == 'material-route-recovery' and e['stage'] == 'after' and e['status'] != 'started').update(status='failed', evidenceVerified=False)
        for old, new in zip(events, updated):
            text = text.replace(event_line(old), event_line(new))
        result = self.verify(text)
        self.assertEqual(result['outcome'], 'failed', result['warnings'])
        first = result['materialRoute']['segments'][0]
        self.assertTrue(first['routeCompleted'])
        self.assertTrue(first['materialGainsVerified'])
        self.assertEqual(first['routeOutcome'], 'completed')
        self.assertFalse(first['recoveryVerified'])

    def test_one_inventory_observation_cannot_be_counted_as_actual_verification(self):
        path = self.bgi / 'User/JsScript/AutoGameMaterialRoute/record/test-session-s1.json'
        report = wf.read_json(path)
        report['inventoryObservations']['after'] = report['inventoryObservations']['after'][:1]
        wf.atomic_json(path, report)
        self.assertEqual(self.verify()['outcome'], 'unknown')


class FakeSessionHost(FakeHost):
    def launch(self, exe, config_name):
        self.launch_calls = getattr(self, 'launch_calls', 0) + 1
        self.launched = True
        runtime = wf.read_json(exe.parent / 'User/OneDragon' / (config_name + '.json'))
        group_name = next(v for k, v in runtime['TaskDefinitions'].items() if runtime['TaskEnabledList'][k])
        group = wf.read_json(exe.parent / 'User/ScriptGroup' / (group_name + '.json'))
        session_id = config_name.replace('AutoGame_', '', 1)
        _, text, _ = session_fixture(exe.parent, session_id, group)
        path = self.root / 'BetterGI/log/test.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        self.process = FakeProcess()
        return self.process


class SessionWorkflowTests(unittest.TestCase):
    def setUp(self):
        material_tests.MaterialWorkflowTests.setUp(self)
        self.session_config = config_fixture()
        entries = []
        for row in self.session_config['segments']:
            path = self.root / 'BetterGI/User/AutoPathing' / row['route']['relativePath']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'positions': [{'action': 'fight', **p} for p in row['route']['fightPoints']]}), encoding='utf-8')
            row['route']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append({'path': row['route']['relativePath'], 'sha256': row['route']['sha256']})
        wf.atomic_json(self.root / 'BetterGI/User/AutoPathing/auto_game_handguard/manifest.json', {'routes': entries})
        wf.atomic_json(self.root / 'config/material-route-session.json', self.session_config)

    def run_session(self, dry=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=None, profile=route.SESSION_MODE,
            timeout_minutes=0, no_delay=True, allow_repeat=False, keep_game=False,
            allow_existing_game=False, graphics_check=False)
        stream = io.StringIO()
        host = FakeSessionHost(self.root)
        with contextlib.redirect_stdout(stream), patch.object(wf, 'datetime', FixedClock), \
                patch('checkin_hoyolab.execute_hoyolab_checkin', side_effect=AssertionError('must not check in')):
            code = wf.execute(args, host)
        return code, wf.read_json(json.loads(stream.getvalue())['resultPath']), host

    def test_session_preview_does_not_launch_or_assign_day_budget(self):
        code, result, host = self.run_session(dry=True)
        self.assertEqual(code, 0, result)
        self.assertFalse(host.launched)
        self.assertEqual(result['materialRouteEligibility']['reservedSeconds'], 270)
        self.assertFalse((self.root / 'state' / route.LEDGER_NAME).exists())

    def test_one_launch_and_independent_segment_archives(self):
        code, result, host = self.run_session()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'completed', result)
        self.assertEqual(host.launch_calls, 1)
        self.assertEqual(len(result['materialRouteLease']['segments']), 2)
        for row in result['materialRouteLease']['segments']:
            self.assertEqual(row['status'], 'completed')
            self.assertTrue((self.root / 'logs/runs' / row['runId'] / 'result.json').is_file())
