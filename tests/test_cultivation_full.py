"""Pure fake supervisor tests. No game, production config or resource ledger writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from scripts import cultivation_full as full
from scripts.analyze_run import analyze_log

DAY = '2026-10-10'
TEAM = ['桑多涅', '奥黛塔', '八重神子', '钟离']
MIZUKI_TARGET = {'characterName': '梦见月瑞希', 'targetLevel': 90,
    'talentTargets': {'normal': 9, 'skill': 9, 'burst': 9}, 'includeEquippedWeapon': True, 'weaponTargetLevel': 90}
OTHER_TARGET = {'characterName': '香菱', 'targetLevel': 80,
    'talentTargets': {'normal': 6, 'skill': 8, 'burst': 8}, 'includeEquippedWeapon': False, 'weaponTargetLevel': None}


def verified_dispatch_fixture():
    """Future verifier contract only; the current engine emits no such proof."""
    return {'status': 'verified', 'evidenceVerified': True,
            'collectionStatus': 'completed', 'reassignmentStatus': 'completed',
            'postStateStatus': 'completed'}


def child_fixture(profile='cultivation', outcome='completed', identifier='20261010T000001-12345678', target=None):
    result = {'runId': identifier, 'gameDate': DAY, 'profile': profile, 'outcome': outcome,
              'executionOutcome': 'not_started' if outcome == 'planned' else 'exited',
              'exitCode': 0 if outcome in {'planned', 'completed'} else 4,
              'finishedAt': '2026-10-10T00:02:00+00:00',
              'requestedProfileTasks': ['领取邮件', '培养材料', '领取每日奖励'] if profile == 'cultivation' else ['队伍免费恢复'] if profile == 'party-preparation' else ['刀镡路线'],
              'cultivationTarget': deepcopy(target or MIZUKI_TARGET), 'cultivationMode': 'execute'}
    if profile == 'cultivation':
        result['cultivation'] = {'reportVerified': outcome == 'completed', 'runId': identifier}
        claim_status = 'success' if outcome == 'completed' else 'unknown'
        result['tasks'] = [{'name': '领取每日奖励', 'status': claim_status,
            'dailyRewardClaim': {'status': claim_status, 'evidence': [
                {'line': 1, 'text': '检查每日奖励结果：今日奖励已领取'}] if outcome == 'completed' else []}}]
        if outcome == 'completed':
            result['tasks'][0]['successScope'] = 'daily-reward-claim-only'
            result['dispatchVerification'] = verified_dispatch_fixture()
            result['fullDailyScopeVerified'] = True
    if profile == 'party-preparation':
        native = {'task': 'party-preparation', 'runId': identifier, 'status': 'completed',
                  'evidenceVerified': True, 'teamObservationCount': 2, 'actualTeam': TEAM,
                  'slotHealthEvidence': [{'slot': i, 'name': name, 'hp': 90, 'maxHp': 100, 'ratio': .9,
                      'observations': 2, 'identityVerified': True, 'identityObservations': 2,
                      'ocrMatchingObservations': 2} for i, name in enumerate(TEAM, 1)]}
        result['partyPreparation'] = {'mode': 'party-preparation', 'nativeResult': native,
            **dict.fromkeys(('reportVerified', 'preparationCompleted', 'allowStatueRevival',
                'noRouteExecution', 'noItemConsumption', 'noRevivalItemConsumption',
                'noResinSpend', 'noFood', 'noCrafting', 'noUpgrade'), True)}
    bundle = {'result': result, 'resultPath': f'logs/runs/{identifier}/result.json',
            'recordingPath': f'logs/runs/{identifier}/recording.json',
            'recording': {'complete': True, 'frameCoveragePassed': True}}
    if profile == 'cultivation':
        bundle['cultivationReport'] = {'runId': identifier, 'mode': 'execute', 'readOnly': False,
            'status': 'success' if outcome == 'completed' else 'unknown', 'targetReached': False,
            'target': deepcopy(target or MIZUKI_TARGET)}
    return bundle


class FakeHost:
    def __init__(self, children=(), elapsed=(), start=None, target=None):
        self.start = start or datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        self.elapsed = 0
        self.children = list(children)
        self.durations = list(elapsed)
        self.calls, self.resource_checks, self.resumes = [], [], {}
        self.scope_checks = []
        self.preparation_checks = []
        self.gate_error = None
        self.target = deepcopy(target or MIZUKI_TARGET)

    def load_target(self):
        return deepcopy(self.target)

    def now(self):
        return self.start + timedelta(seconds=self.elapsed)

    def monotonic(self):
        return self.elapsed

    def run_phase(self, phase, minutes, dry_run, deadline, day):
        self.calls.append((deepcopy(phase), minutes, dry_run, deadline, day))
        self.elapsed += self.durations.pop(0) if self.durations else 60
        child = self.children.pop(0) if self.children else child_fixture(phase['profile'], 'planned' if dry_run else 'completed',
            identifier=f'20261010T0000{len(self.calls):02d}-{len(self.calls):08x}', target=self.target)
        return deepcopy(child)

    def read_bundle(self, identifier):
        return deepcopy(self.resumes[identifier])

    def verify_resume_scope(self, bundle, phase, target):
        assert target == self.target
        self.scope_checks.append(phase['name'])

    def verify_preparation_scope(self, bundle, phase):
        self.preparation_checks.append(phase['name'])

    def validate_resource_gate(self, day, target):
        assert target == self.target
        self.resource_checks.append(day)
        if self.gate_error:
            raise ValueError(self.gate_error)
        return {'originalResinCap': 60, 'priorReservedOriginal': 40,
                'runtimeOriginalResinBudget': 20, 'condensedResinCap': 0}


class FullSupervisorTests(unittest.TestCase):
    def test_replacement_target_generates_its_own_plan_and_bound_children_without_upgrade_claim(self):
        host = FakeHost(target=OTHER_TARGET)
        report = full.supervise(host, dry_run=True)
        self.assertEqual(report['outcome'], 'planned')
        self.assertEqual(report['target'], OTHER_TARGET)
        self.assertEqual(report['targetSha256'], full.target_identity(OTHER_TARGET))
        self.assertNotEqual(report['targetSha256'], full.target_identity(MIZUKI_TARGET))
        self.assertTrue(all(child['parentTarget'] == OTHER_TARGET for child in report['phases']))
        self.assertFalse(report['targetReached'])
        self.assertIsNone(report['fullDailyScopeVerified'])
        self.assertEqual(host.resource_checks, [])

    def test_old_mizuki_child_and_resume_cannot_complete_replacement_target(self):
        old = child_fixture(target=MIZUKI_TARGET)
        host = FakeHost([child_fixture('party-preparation'), old], target=OTHER_TARGET)
        report = full.supervise(host, authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        self.assertFalse(report['fullDailyScopeVerified'])
        self.assertEqual(len(report['phases']), 1)
        self.assertIn('requested cultivation target', report['errors'][0])
        host = FakeHost(target=OTHER_TARGET)
        host.resumes[old['result']['runId']] = old
        report = full.supervise(host, authorized=True, resume_ids=[old['result']['runId']])
        self.assertEqual(report['outcome'], 'unknown')
        self.assertEqual(host.calls, [])
        self.assertEqual(host.resource_checks, [])
        self.assertEqual(host.scope_checks, [])

    def test_target_config_change_during_parent_stops_before_next_resource_gate(self):
        class ChangingHost(FakeHost):
            def run_phase(self, *args):
                bundle = super().run_phase(*args)
                self.target = deepcopy(MIZUKI_TARGET)
                return bundle
        host = ChangingHost(target=OTHER_TARGET)
        report = full.supervise(host, authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual(report['target'], OTHER_TARGET)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(host.resource_checks, [])
        self.assertIn('target changed', report['errors'][0])

    def test_old_archive_cannot_be_relabelled_as_a_new_target_by_result_summary(self):
        child = child_fixture(target=OTHER_TARGET)
        child['cultivationReport']['target'] = deepcopy(MIZUKI_TARGET)
        host = FakeHost([child_fixture('party-preparation'), child], target=OTHER_TARGET)
        report = full.supervise(host, authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        self.assertFalse(report['fullDailyScopeVerified'])
        self.assertIn('requested parent target', report['errors'][0])
        host = FakeHost(target=OTHER_TARGET)
        host.resumes[child['result']['runId']] = child
        self.assertEqual(full.supervise(host, authorized=True, resume_ids=[child['result']['runId']])['outcome'], 'unknown')
        self.assertEqual(host.calls, [])

    def test_replacement_target_keeps_authorization_day_and_dispatch_gates(self):
        with self.assertRaises(ValueError):
            full.supervise(FakeHost(target=OTHER_TARGET))
        child = child_fixture(target=OTHER_TARGET)
        child['result']['dispatchVerification']['postStateStatus'] = 'unknown'
        report = full.supervise(FakeHost([child_fixture('party-preparation'), child], target=OTHER_TARGET), authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        self.assertFalse(report['fullDailyScopeVerified'])
        child['result']['gameDate'] = '2026-10-09'
        report = full.supervise(FakeHost([child_fixture('party-preparation'), child], target=OTHER_TARGET), authorized=True)
        self.assertNotEqual(report['outcome'], 'completed')
    def test_preview_only_calls_plans_and_never_resource_gate(self):
        host = FakeHost()
        report = full.supervise(host, dry_run=True, with_routes=True, route_session_config='config/session.json')
        self.assertEqual(report['outcome'], 'planned')
        self.assertFalse(report['targetReached'])
        self.assertEqual(len(host.calls), 4)
        self.assertTrue(all(c[2] for c in host.calls))
        self.assertEqual(host.resource_checks, [])

    def test_real_requires_explicit_authorization(self):
        host = FakeHost()
        with self.assertRaises(ValueError):
            full.supervise(host)
        self.assertEqual(host.calls, [])

    def test_routes_require_explicit_config(self):
        with self.assertRaises(ValueError):
            full.supervise(FakeHost(), authorized=True, with_routes=True)

    def test_core_supported_scope_and_budget(self):
        host = FakeHost()
        report = full.supervise(host, authorized=True)
        self.assertEqual(report['outcome'], 'completed')
        self.assertEqual(report['maximumMinutes'], 25)
        self.assertEqual(report['resourceGate']['runtimeOriginalResinBudget'], 20)
        self.assertEqual(report['resourceGate']['priorReservedOriginal'], 40)
        self.assertFalse(report['targetReached'])
        self.assertEqual([c[0]['profile'] for c in host.calls], ['party-preparation', 'cultivation'])
        self.assertIs(report['fullDailyScopeVerified'], True)
        self.assertIs(report['phases'][1]['dispatchScopeVerified'], True)

    def test_missing_dispatch_keeps_completed_claim_but_supported_daily_partial(self):
        for only_flag in (False, True):
            with self.subTest(only_flag=only_flag):
                child = child_fixture()
                child['result'].pop('dispatchVerification')
                if not only_flag:
                    child['result'].pop('fullDailyScopeVerified')
                before = deepcopy(child)
                host = FakeHost([child_fixture('party-preparation', identifier='20261010T000000-00000000'), child])
                report = full.supervise(host, authorized=True)
                self.assertEqual(report['outcome'], 'partial')
                self.assertIs(report['fullDailyScopeVerified'], False)
                phase = report['phases'][1]
                self.assertEqual(phase['outcome'], 'partial')
                self.assertEqual(phase['claimedOutcome'], 'completed')
                self.assertEqual(phase['completionBlocker'], 'dispatch_unverified')
                self.assertIn('dispatchVerification is missing', phase['reason'])
                self.assertEqual(phase['tasks'], child['result']['tasks'])
                self.assertEqual(phase['tasks'][0]['dailyRewardClaim']['status'], 'success')
                self.assertEqual(child, before)
                self.assertEqual(len(host.calls), 2)
                self.assertEqual(len(host.resource_checks), 1)

    def test_current_claim_only_parser_result_cannot_complete_full_daily(self):
        parsed = analyze_log('一条龙任务执行: 1/1\n探索派遣：再次派遣\n探索派遣：完成\n'
                             '检查每日奖励结果：今日奖励已领取\n一条龙和配置组任务结束',
                             ['领取每日奖励'])
        self.assertEqual(parsed['outcome'], 'completed')
        child = child_fixture()
        child['result'].update({key: parsed[key] for key in
                               ('tasks', 'dispatchVerification', 'fullDailyScopeVerified')})
        report = full.supervise(FakeHost([child_fixture('party-preparation', identifier='20261010T000000-00000000'), child]), authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        phase = report['phases'][1]
        self.assertEqual(phase['dispatchVerification'], parsed['dispatchVerification'])
        self.assertIs(phase['fullDailyScopeVerified'], False)
        self.assertIs(phase['dispatchScopeVerified'], False)
        self.assertEqual(phase['tasks'][0]['status'], 'success')
        self.assertEqual(phase['tasks'][0]['dailyRewardClaim']['status'], 'success')
        self.assertIn('dispatchVerification.status', '\n'.join(report['errors']))

    def test_dispatch_requires_every_independent_status_and_strict_boolean(self):
        changes = [('status', 'completed'), ('status', 'unknown'),
                   ('collectionStatus', 'unknown'), ('collectionStatus', 'skipped'),
                   ('reassignmentStatus', 'unknown'), ('postStateStatus', None),
                   ('evidenceVerified', False), ('evidenceVerified', 1),
                   ('evidenceVerified', 'true')]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                child = child_fixture()
                child['result']['dispatchVerification'][field] = value
                report = full.supervise(FakeHost([child_fixture('party-preparation', identifier='20261010T000000-00000000'), child]), authorized=True)
                self.assertEqual(report['outcome'], 'partial')
                self.assertIn(field, report['phases'][1]['reason'])
                self.assertIs(report['fullDailyScopeVerified'], False)
        for value in (None, False, 1, 'true'):
            with self.subTest(fullDailyScopeVerified=value):
                child = child_fixture()
                child['result']['fullDailyScopeVerified'] = value
                report = full.supervise(FakeHost([child_fixture('party-preparation', identifier='20261010T000000-00000000'), child]), authorized=True)
                self.assertEqual(report['outcome'], 'partial')
                self.assertIn('fullDailyScopeVerified', report['phases'][1]['reason'])
        for value in ([], 'verified', True):
            with self.subTest(dispatchVerification=value):
                child = child_fixture()
                child['result']['dispatchVerification'] = value
                report = full.supervise(FakeHost([child_fixture('party-preparation', identifier='20261010T000000-00000000'), child]), authorized=True)
                self.assertEqual(report['outcome'], 'partial')
                self.assertEqual(report['phases'][1]['completionBlocker'], 'dispatch_unverified')

    def test_old_completed_resume_without_dispatch_is_retained_and_never_replayed(self):
        identifier = '20261010T000001-12345678'
        for missing in (False, True):
            with self.subTest(missing=missing):
                child = child_fixture()
                if missing:
                    child['result'].pop('dispatchVerification')
                    child['result'].pop('fullDailyScopeVerified')
                else:
                    child['result']['dispatchVerification']['reassignmentStatus'] = 'unknown'
                host = FakeHost()
                host.resumes[identifier] = child
                report = full.supervise(host, authorized=True, resume_ids=[identifier])
                self.assertEqual(report['outcome'], 'partial')
                self.assertEqual(host.calls, [])
                self.assertEqual(host.scope_checks, [])
                self.assertEqual(host.resource_checks, [])
                rejected = report['phases'][0]
                self.assertIs(rejected['resumeRejected'], True)
                self.assertFalse(rejected['resumed'])
                self.assertEqual(rejected['claimedOutcome'], 'completed')
                self.assertEqual(rejected['tasks'][0]['dailyRewardClaim']['status'], 'success')
                self.assertIn('resume rejected', report['errors'][0])
                self.assertIn('cultivation-daily', report['pendingPhases'])
                self.assertIs(report['fullDailyScopeVerified'], False)

    def test_preview_does_not_require_or_certify_real_dispatch_proof(self):
        child = child_fixture(outcome='planned')
        child['result']['dispatchVerification'] = {'status': 'unknown', 'evidenceVerified': False}
        child['result']['fullDailyScopeVerified'] = False
        host = FakeHost([child_fixture('party-preparation', 'planned', identifier='20261010T000000-00000000'), child])
        report = full.supervise(host, dry_run=True)
        self.assertEqual(report['outcome'], 'planned')
        self.assertEqual(host.resource_checks, [])
        self.assertIsNone(report['fullDailyScopeVerified'])
        phase = report['phases'][1]
        self.assertEqual(phase['dispatchVerification'], child['result']['dispatchVerification'])
        self.assertIs(phase['fullDailyScopeVerified'], False)
        self.assertIsNone(phase['dispatchScopeVerified'])
        self.assertIsNone(phase['completionBlocker'])

    def test_full_defaults_to_separate_preparations_routes35_core_target20(self):
        host = FakeHost(elapsed=[120, 540, 120, 900])
        report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json')
        self.assertEqual(report['outcome'], 'completed')
        self.assertEqual(report['maximumMinutes'], 35)
        self.assertEqual(report['coreTargetMinutes'], 20)
        self.assertTrue(report['materialRoutesMeasuredSeparately'])
        self.assertEqual([c[1] for c in host.calls], [5, 10, 5, 20])
        self.assertEqual(report['wallSeconds'], 1680)
        self.assertEqual(len(host.preparation_checks), 2)

    def test_route_failure_partial_unknown_never_retries_or_starts_resources(self):
        for outcome in ('failed', 'partial', 'unknown'):
            with self.subTest(outcome=outcome):
                host = FakeHost(children=[child_fixture('party-preparation'), child_fixture('material-route-session', outcome,
                    identifier='20261010T000002-22222222')])
                report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json')
                self.assertNotEqual(report['outcome'], 'completed')
                self.assertEqual(len(host.calls), 2)
                self.assertEqual(host.resource_checks, [])
                self.assertEqual(report['pendingPhases'], ['party-preparation-before-cultivation', 'cultivation-daily'])

    def test_successful_extra_insufficient_time_preserves_partial(self):
        host = FakeHost(elapsed=[120, 600, 60])
        report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json', maximum_minutes=25)
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual(len(host.calls), 3)
        self.assertEqual(host.resource_checks, [])

    def test_resource_gate_failure_stops_after_routes(self):
        host = FakeHost()
        host.gate_error = 'continuation missing or cumulative gate consumed'
        report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json')
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual(len(host.calls), 3)

    def test_wrong_day_profile_nonterminal_or_recording_rejected(self):
        for field, value in [('gameDate', '2026-10-09'), ('profile', 'core'), ('outcome', 'running'), ('finishedAt', None)]:
            host = FakeHost()
            child = child_fixture('party-preparation')
            child['result'][field] = value
            host.children = [child]
            self.assertEqual(full.supervise(host, authorized=True)['outcome'], 'unknown')
        for field in ('complete', 'frameCoveragePassed'):
            child = child_fixture('party-preparation')
            child['recording'][field] = False
            self.assertEqual(full.supervise(FakeHost([child]), authorized=True)['outcome'], 'unknown')

    def test_scan_or_wrong_target_not_promoted_to_completed(self):
        for field, value in [('cultivationMode', 'scan'), ('cultivationTarget', {})]:
            child = child_fixture()
            child['result'][field] = value
            self.assertEqual(full.supervise(FakeHost([child_fixture('party-preparation'), child]), authorized=True)['outcome'], 'partial')

    def test_preview_success_never_accepted_as_actual_or_actual_as_preview(self):
        self.assertEqual(full.supervise(FakeHost([child_fixture('party-preparation', outcome='planned')]), authorized=True)['outcome'], 'failed')
        self.assertEqual(full.supervise(FakeHost([child_fixture('party-preparation')]), dry_run=True)['outcome'], 'unknown')

    def test_game_reset_budget_blocks_child_before_launch(self):
        start = datetime(2026, 10, 10, 19, 55, tzinfo=timezone.utc)
        host = FakeHost(start=start)
        report = full.supervise(host, authorized=True)
        self.assertNotEqual(report['outcome'], 'completed')
        self.assertEqual(host.calls, [])

    def test_game_day_change_after_child_stops_next_phase(self):
        host = FakeHost(start=datetime(2026, 10, 10, 19, 40, tzinfo=timezone.utc), elapsed=[1300])
        report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json')
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(host.resource_checks, [])

    def test_resume_only_verified_same_day_and_scope(self):
        identifier = '20261010T000001-12345678'
        host = FakeHost()
        host.resumes[identifier] = child_fixture()
        report = full.supervise(host, authorized=True, resume_ids=[identifier])
        self.assertEqual(report['outcome'], 'completed')
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(host.calls[0][0]['profile'], 'party-preparation')
        self.assertTrue(report['phases'][1]['resumed'])
        self.assertEqual(host.scope_checks, ['cultivation-daily'])
        for outcome in ('failed', 'unknown', 'partial', 'planned'):
            host.resumes[identifier] = child_fixture(outcome=outcome)
            self.assertEqual(full.supervise(host, authorized=True, resume_ids=[identifier])['outcome'], 'unknown')
        host.resumes[identifier] = child_fixture()
        host.resumes[identifier]['result']['gameDate'] = '2026-10-09'
        self.assertEqual(full.supervise(host, authorized=True, resume_ids=[identifier])['outcome'], 'unknown')

    def test_verified_cultivation_resume_cannot_certify_failed_fresh_preparation(self):
        identifier = '20261010T000001-12345678'
        for outcome in ('failed', 'unknown'):
            with self.subTest(outcome=outcome):
                host = FakeHost([child_fixture('party-preparation', outcome,
                                               identifier='20261010T000000-00000000')])
                host.resumes[identifier] = child_fixture()
                report = full.supervise(host, authorized=True, resume_ids=[identifier])
                self.assertNotEqual(report['outcome'], 'completed')
                self.assertIs(report['fullDailyScopeVerified'], False)
                self.assertEqual(host.scope_checks, ['cultivation-daily'])
                self.assertEqual(len(host.calls), 1)
                self.assertEqual(host.calls[0][0]['profile'], 'party-preparation')
                self.assertEqual(host.resource_checks, [])
                self.assertIn('child was not verified complete', report['errors'][0])

    def test_completed_cultivation_phase_does_not_certify_partial_parent_after_reset(self):
        # Both child receipts are valid, but the parent's current-day contract
        # fails after the last child. Child dispatch proof alone is insufficient.
        host = FakeHost(start=datetime(2026, 10, 10, 19, 0, tzinfo=timezone.utc),
                        elapsed=[60, 3600])
        report = full.supervise(host, authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual(report['phases'][1]['outcome'], 'completed')
        self.assertIs(report['phases'][1]['dispatchScopeVerified'], True)
        self.assertIs(report['fullDailyScopeVerified'], False)
        self.assertIn('child crossed the game-day boundary', report['errors'])

    def test_argv_uses_exact_supported_profiles_no_repeat_budget_or_shell(self):
        root = Path('E:/project space')
        for dry_run in (True, False):
            for phase in full.phases(True, 'config/session with spaces.json'):
                argv = full.child_command(root, phase, 10, dry_run)
                self.assertIsInstance(argv, list)
                self.assertIn('-File', argv)
                self.assertIn(phase['profile'], argv)
                self.assertNotIn('core', argv)
                self.assertNotIn('-AllowRepeat', argv)
                self.assertNotIn('--original-resin-budget', argv)
                self.assertEqual('-DryRun' in argv, dry_run)
                if phase.get('routeSessionConfig'):
                    self.assertIn('config/session with spaces.json', argv)

    def test_global_limit_and_duplicate_resume_rejected(self):
        for minutes in (0, 19, 36, 100, True):
            with self.assertRaises(ValueError):
                full.supervise(FakeHost(), authorized=True, maximum_minutes=minutes)
        identifier = '20261010T000001-12345678'
        host = FakeHost()
        host.resumes[identifier] = child_fixture()
        self.assertEqual(full.supervise(host, authorized=True, resume_ids=[identifier, identifier])['outcome'], 'unknown')

    def test_preparation_failure_prevents_all_combat(self):
        for outcome in ('failed', 'partial', 'unknown'):
            host = FakeHost([child_fixture('party-preparation', outcome)])
            report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json')
            self.assertNotEqual(report['outcome'], 'completed')
            self.assertEqual(len(host.calls), 1)
            self.assertEqual(host.resource_checks, [])

    def test_new_preparation_required_after_routes(self):
        host = FakeHost([child_fixture('party-preparation'),
            child_fixture('material-route-session', identifier='20261010T000002-22222222'),
            child_fixture('party-preparation', 'failed', identifier='20261010T000003-33333333')])
        report = full.supervise(host, authorized=True, with_routes=True, route_session_config='config/session.json')
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual([row[0]['profile'] for row in host.calls],
            ['party-preparation', 'material-route-session', 'party-preparation'])
        self.assertEqual(host.resource_checks, [])

    def test_low_dead_unknown_identity_single_frame_and_item_revive_rejected(self):
        for key, value in [('ratio', .07), ('hp', 0), ('observations', 1),
                           ('identityVerified', False), ('identityObservations', 1), ('ocrMatchingObservations', 1)]:
            child = child_fixture('party-preparation')
            child['result']['partyPreparation']['nativeResult']['slotHealthEvidence'][1][key] = value
            report = full.supervise(FakeHost([child]), authorized=True)
            self.assertEqual(report['outcome'], 'unknown')
            self.assertEqual(report['phases'], [])
        for key, value in [('allowStatueRevival', False), ('noItemConsumption', False),
                           ('noRevivalItemConsumption', False), ('noRevive', True)]:
            child = child_fixture('party-preparation')
            child['result']['partyPreparation'][key] = value
            self.assertEqual(full.supervise(FakeHost([child]), authorized=True)['outcome'], 'unknown')

    def test_old_preparation_is_not_reusable_fresh_health(self):
        identifier = '20261010T000001-12345678'
        host = FakeHost()
        host.resumes[identifier] = child_fixture('party-preparation')
        report = full.supervise(host, authorized=True, resume_ids=[identifier])
        self.assertEqual(report['outcome'], 'unknown')
        self.assertEqual(host.calls, [])

    def test_duplicate_child_id_across_preparations_is_rejected(self):
        identifier = '20261010T000001-12345678'
        host = FakeHost([child_fixture('party-preparation', identifier=identifier),
                         child_fixture(identifier=identifier)])
        report = full.supervise(host, authorized=True)
        self.assertEqual(report['outcome'], 'partial')
        self.assertEqual(len(report['phases']), 1)


class LocalHostFakeTests(unittest.TestCase):
    """Exercise process binding, scoped stop and archive reads with fake processes."""
    def fixture(self, dry_run=False):
        root = Path(__file__).resolve().parent / '.artifacts' / ('cultivation-full-' + uuid4().hex)
        (root / 'logs/runs').mkdir(parents=True)
        (root / 'state').mkdir()
        parent = root / 'logs/cultivation-full/parent'
        parent.mkdir(parents=True)
        host = full.LocalHost(root, parent)
        # Keep fake game-day tests independent of the computer's current date.
        host.now = lambda: datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
        phase = full.phases()[-1]
        bundle = child_fixture(outcome='planned' if dry_run else 'completed')
        identifier = bundle['result']['runId']
        result = bundle['result']
        result['triggeredAt'] = host.now().isoformat()
        result['runnerPid'] = 333
        directory = root / 'logs/runs' / identifier

        class Process:
            pid = 222
            returncode = 0
            polls = 0

            def poll(self):
                self.polls += 1
                return None if self.polls == 1 else self.returncode

        def launch(argv, **kwargs):
            self.argv, self.spawn_kwargs = argv, kwargs
            directory.mkdir()
            (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
            if not dry_run:
                (directory / 'cultivation-report.json').write_text(json.dumps(bundle['cultivationReport']), encoding='utf-8')
            if dry_run:
                kwargs['stdout'].write(json.dumps({'runId': identifier, 'outcome': 'planned'}) + '\n')
                kwargs['stdout'].flush()
            else:
                video = directory / 'genshin-window.mkv'
                video.write_bytes(b'fake retained video; no actual game')
                recording = dict(bundle['recording'], file=str(video))
                (directory / 'recording.json').write_text(json.dumps(recording), encoding='utf-8')
                (root / 'state/current-run.json').write_text(json.dumps(result), encoding='utf-8')
            return Process()
        return host, phase, result, launch

    def test_actual_binds_owned_runner_and_recording(self):
        host, phase, result, launch = self.fixture()
        with patch.object(full.subprocess, 'Popen', side_effect=launch), patch.object(full.time, 'sleep'), patch.object(host, 'owns_runner', return_value=True) as owns:
            bundle = host.run_phase(phase, 20, False, host.monotonic() + 1200, DAY)
        self.assertEqual(bundle['result']['runId'], result['runId'])
        self.assertFalse(self.spawn_kwargs['shell'])
        owns.assert_called_with(333, 222)

    def test_unrelated_current_runner_never_accepted(self):
        host, phase, result, launch = self.fixture()
        with patch.object(full.subprocess, 'Popen', side_effect=launch), patch.object(full.time, 'sleep'), patch.object(host, 'owns_runner', return_value=False), patch.object(full.subprocess, 'run') as stop:
            with self.assertRaises(ValueError):
                host.run_phase(phase, 20, False, host.monotonic() + 1200, DAY)
        stop.assert_not_called()

    def test_preview_identifies_process_owned_summary_without_current(self):
        host, phase, result, launch = self.fixture(True)
        with patch.object(full.subprocess, 'Popen', side_effect=launch), patch.object(full.time, 'sleep'), patch.object(host, 'owns_runner') as owns:
            bundle = host.run_phase(phase, 20, True, host.monotonic() + 1200, DAY)
        self.assertEqual(bundle['result']['outcome'], 'planned')
        self.assertIn('-DryRun', self.argv)
        self.assertFalse((host.root / 'state/current-run.json').exists())
        owns.assert_not_called()

    def test_deadline_requests_only_exact_owned_workflow_stop(self):
        host, phase, result, launch = self.fixture()
        with patch.object(full.subprocess, 'Popen', side_effect=launch), patch.object(full.time, 'sleep'), patch.object(host, 'owns_runner', return_value=True), patch.object(full.subprocess, 'run') as stop:
            with self.assertRaises(RuntimeError):
                host.run_phase(phase, 20, False, host.monotonic() - 1, DAY)
        argv = stop.call_args.args[0]
        self.assertEqual(argv[-3:], ['stop', '--run-id', result['runId']])
        self.assertFalse(stop.call_args.kwargs['shell'])
        self.assertEqual(host.last_child_reference['runId'], result['runId'])

    def test_real_resource_gate_rejects_config_or_ledger_expansion(self):
        host, _, _, _ = self.fixture()
        (host.root / 'config').mkdir()
        config = {'target': deepcopy(MIZUKI_TARGET), 'executionEnabled': True,
                  'policy': {'maxSteps': 1, 'originalResinBudget': 20, 'condensedResinBudget': 0,
                             'allowDomain': True, 'allowBoss': False, 'allowCrafting': False,
                             'validationMode': True, 'validationScopeId': 'mizuki-first-validation-20261008',
                             'requireZhongliShieldCast': True, 'domainResin': 'original'}}
        gate = {'scopeId': 'mizuki-first-validation-20261008', 'gameDate': DAY,
                'originalResinCap': 60, 'condensedResinCap': 0, 'priorReservedOriginal': 40,
                'runtimeOriginalResinBudget': 20, 'alreadyAttemptedSources': ['boss']}
        path = host.root / 'config/cultivation.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        (host.root / 'config/settings.json').write_text(json.dumps({'bettergiExe': 'BetterGI_custom/BetterGI.exe'}), encoding='utf-8')
        with patch('scripts.cultivation_validation.constrain_validation', return_value=(config, gate)) as constrain:
            self.assertEqual(host.validate_resource_gate(DAY, MIZUKI_TARGET)['runtimeOriginalResinBudget'], 20)
            self.assertFalse(constrain.call_args.kwargs['assign'])
        for key, value in [('originalResinCap', 80), ('priorReservedOriginal', 0), ('runtimeOriginalResinBudget', 60), ('alreadyAttemptedSources', ['boss', 'domain'])]:
            changed = dict(gate, **{key: value})
            with patch('scripts.cultivation_validation.constrain_validation', return_value=(config, changed)):
                with self.assertRaises(ValueError):
                    host.validate_resource_gate(DAY, MIZUKI_TARGET)
        for key, value in [('allowBoss', True), ('allowCrafting', True), ('originalResinBudget', 40), ('maxSteps', 2), ('requireZhongliShieldCast', False)]:
            changed = deepcopy(config)
            changed['policy'][key] = value
            path.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaises(ValueError):
                host.validate_resource_gate(DAY, MIZUKI_TARGET)

    def test_local_target_is_loaded_from_config_and_old_identity_gate_is_rejected(self):
        host, _, _, _ = self.fixture()
        (host.root / 'config').mkdir()
        path = host.root / 'config/cultivation.json'
        path.write_text(json.dumps({'target': OTHER_TARGET}), encoding='utf-8')
        self.assertEqual(host.load_target(), OTHER_TARGET)
        old = child_fixture(target=MIZUKI_TARGET)
        with self.assertRaisesRegex(ValueError, 'target/mode mismatch'):
            host.verify_resume_scope(old, full.phases()[-1], OTHER_TARGET)
        with self.assertRaisesRegex(ValueError, 'local cultivation config'):
            host.verify_resume_scope(old, full.phases()[-1], MIZUKI_TARGET)


if __name__ == '__main__':
    unittest.main()
