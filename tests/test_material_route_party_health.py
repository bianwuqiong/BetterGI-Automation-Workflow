"""New scoped engine health events, with unchanged legacy no-event fixtures."""
import copy
from pathlib import Path
import unittest
from uuid import uuid4

from scripts import material_route as route
from tests.test_material_route import report_fixture, route_fixture
from tests.test_material_route_session import TEAM, DAY, config_fixture, session_fixture, event_line


def health_fixture(run_id):
    return {'task': 'material-route-party-health', 'status': 'verified', 'runId': run_id,
        'actualTeam': TEAM, 'minimumHpRatio': .8, 'activeSlotRestored': 4, 'teamObservationCount': 2,
        'noFood': True, 'noRevive': True,
        'slotHealthEvidence': [{'slot': slot, 'name': name, 'hp': 8000, 'maxHp': 10000, 'ratio': .8,
            'observations': 2, 'identityVerified': True, 'identityObservations': 2, 'ocrMatchingObservations': 2}
            for slot, name in enumerate(TEAM, 1)]}


def add_health(events):
    result = []
    for event in events:
        result.append(copy.deepcopy(event))
        if event['task'] == 'material-route-team':
            result.append(health_fixture(event['runId']))
    return result


class RoutePartyHealthTests(unittest.TestCase):
    def setUp(self):
        self.bgi = Path(__file__).resolve().parents[1] / 'tests/.artifacts' / ('route-health-' + uuid4().hex[:10])
        self.group = route.build_route_group('test-health', {'partyName': 'Test party', 'expectedTeam': TEAM}, route_fixture(), game_date=DAY)
        _, self.report, _, legacy = report_fixture(self.bgi, 'test-health', self.group)
        self.legacy = legacy
        self.events = add_health(legacy)

    def verify(self, events=None):
        text = '\n'.join(['参数指定的一条龙配置：AutoGame_test', '配置组任务执行: 1/1',
            *[event_line(e) for e in (self.events if events is None else events)], '一条龙和配置组任务结束'])
        return route.verify_material_route_report(text, self.bgi, 'test-health', self.group, 'AutoGame_test', 'exited')

    def test_new_event_is_verified_and_legacy_evidence_stays_byte_preserved(self):
        report_path = self.bgi / 'User/JsScript/AutoGameMaterialRoute/record/test-health.json'
        before = report_path.read_bytes()
        result = self.verify()
        self.assertEqual(result['outcome'], 'completed', result['warnings'])
        self.assertTrue(result['materialRoute']['partyHealthVerified'])
        self.assertEqual(self.verify(self.legacy)['outcome'], 'completed')
        self.assertEqual(report_path.read_bytes(), before)

    def test_exact_scope_flags_team_and_cardinality_are_required_when_present(self):
        changes = [{'runId': 'foreign'}, {'status': 'completed'}, {'actualTeam': TEAM[::-1]}, {'minimumHpRatio': .7},
            {'minimumHpRatio': True}, {'activeSlotRestored': True}, {'teamObservationCount': 1}, {'noFood': False},
            {'noRevive': False}, {'slotHealthEvidence': []}]
        for change in changes:
            with self.subTest(change=change):
                events = copy.deepcopy(self.events)
                next(e for e in events if e['task'] == 'material-route-party-health').update(change)
                self.assertEqual(self.verify(events)['outcome'], 'unknown')
        duplicate = copy.deepcopy(self.events)
        duplicate.insert(3, health_fixture('test-health'))
        self.assertEqual(self.verify(duplicate)['outcome'], 'unknown')

    def test_hp_current_identity_two_frames_numeric_semantics_and_order_are_strict(self):
        for change in ({'hp': 0, 'ratio': 0}, {'hp': 7999, 'ratio': .7999}, {'hp': True}, {'maxHp': None},
            {'ratio': .9}, {'observations': True}, {'observations': 1}, {'identityVerified': False},
            {'identityObservations': 1}, {'ocrMatchingObservations': 1}, {'name': TEAM[2]}, {'slot': 1}):
            with self.subTest(change=change):
                events = copy.deepcopy(self.events)
                next(e for e in events if e['task'] == 'material-route-party-health')['slotHealthEvidence'][1].update(change)
                self.assertEqual(self.verify(events)['outcome'], 'unknown')
        for destination in (0, 2, 5, len(self.events) - 1):
            events = copy.deepcopy(self.events)
            health = next(e for e in events if e['task'] == 'material-route-party-health')
            events.remove(health)
            events.insert(destination, health)
            self.assertEqual(self.verify(events)['outcome'], 'unknown', destination)

    def test_native_failed_health_gate_without_verified_event_stays_failed(self):
        events = copy.deepcopy(self.legacy)
        native = next(e for e in events if e['task'] == route.MODE and e['status'] == 'completed')
        native.update(status='failed', cleanupCompleted=False)
        events[-1]['status'] = 'failed'
        report = copy.deepcopy(self.report)
        report.update(status='failed', nativeReturnCompleted=False, nativeResult=native)
        import json
        (self.bgi / 'User/JsScript/AutoGameMaterialRoute/record/test-health.json').write_text(json.dumps(report), encoding='utf-8')
        self.assertEqual(self.verify(events)['outcome'], 'failed')

    def test_session_accepts_health_per_segment_and_rejects_parent_or_cross_segment_scope(self):
        group = route.build_route_session_group('test-session-health', config_fixture(), game_date=DAY)
        _, _, events = session_fixture(self.bgi, 'test-session-health', group)
        healthy = add_health(events)
        def verify(rows):
            text = '\n'.join(['参数指定的一条龙配置：AutoGame_test-session-health', '配置组任务执行: 1/1',
                *[event_line(e) for e in rows], '一条龙和配置组任务结束'])
            return route.verify_material_route_session_report(text, self.bgi, 'test-session-health', group,
                'AutoGame_test-session-health', 'exited')
        result = verify(healthy)
        self.assertEqual(result['outcome'], 'completed', result['warnings'])
        self.assertTrue(all(segment['partyHealthVerified'] for segment in result['materialRoute']['segments']))
        self.assertEqual(verify(events)['outcome'], 'completed')
        for change in ({'runId': 'test-session-health'}, {'runId': 'test-session-health-s2'}, {'actualTeam': TEAM[::-1]}):
            altered = copy.deepcopy(healthy)
            next(e for e in altered if e['task'] == 'material-route-party-health').update(change)
            self.assertEqual(verify(altered)['outcome'], 'unknown')
        altered = copy.deepcopy(healthy)
        next(e for e in altered if e['task'] == 'material-route-party-health')['slotHealthEvidence'][1]['hp'] = 0
        self.assertEqual(verify(altered)['outcome'], 'unknown')
