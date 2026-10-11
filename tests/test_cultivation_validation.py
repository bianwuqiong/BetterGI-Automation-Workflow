"""Retained fake receipts/checkpoints prove resource authorization is cumulative."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from uuid import uuid4

from scripts.cultivation_validation import constrain_validation
from tests.test_cultivation import TARGET, POLICY

ROOT = Path(__file__).resolve().parents[1]


class ValidationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('validation-ledger-' + uuid4().hex[:12])
        self.bgi = self.root / 'fake-bgi'
        self.bgi.mkdir(parents=True)
        self.path = self.root / 'state/cultivation-authorization.json'
        self.receipt = {'schemaVersion': 1, 'scopeId': 'first-validation', 'gameDate': '2026-10-08',
            'target': copy.deepcopy(TARGET), 'originalResinCap': 60, 'condensedResinCap': 0,
            'purpose': 'initial-validation', 'authorizedAtUTC': '2026-10-08T00:00:00Z', 'assignedRunIds': []}
        self.config = {'target': copy.deepcopy(TARGET), 'executionEnabled': True,
            'policy': {**POLICY, 'validationMode': True, 'originalResinBudget': 60,
                       'validationScopeId': 'first-validation', 'validationAttemptedSources': []}}
        self.write(self.path, self.receipt)

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def guard(self, *, assign=False, run_id='new-run'):
        return constrain_validation(self.root, self.bgi, self.config, run_id, '2026-10-08', assign=assign)

    def prior(self, kinds, *, status='unknown', archive=False, run_id='old-run'):
        self.receipt['assignedRunIds'].append(run_id)
        self.write(self.path, self.receipt)
        report = {'runId': run_id, 'mode': 'execute', 'target': copy.deepcopy(TARGET),
            'policy': copy.deepcopy(self.config['policy']), 'status': status,
            'steps': [{'stepId': f'{run_id}:step-{index}', 'type': kind,
                       'status': status, 'validationAttempt': True, 'maxClaims': 1, 'resin': 'original'} for index, kind in enumerate(kinds, 1)]}
        path = (self.root / f'logs/runs/{run_id}/cultivation-report.json' if archive else
                self.bgi / f'User/JsScript/AutoGameCultivation/record/{run_id}.json')
        self.write(path, report)
        return path, report

    def test_initial_scope_is_registered_only_by_assign(self):
        before = self.path.read_bytes()
        config, summary = self.guard()
        self.assertEqual(config['policy']['originalResinBudget'], 60)
        self.assertEqual(summary['priorReservedOriginal'], 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.guard(assign=True)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['assignedRunIds'], ['new-run'])
        with self.assertRaisesRegex(ValueError, 'replay'):
            self.guard(assign=True)

    def test_replacing_target_cannot_reuse_old_receipt_or_unknown_budget_reservation(self):
        self.prior(['boss'])
        receipt_before = self.path.read_bytes()
        self.config['target']['characterName'] = '香菱'
        with self.assertRaisesRegex(ValueError, 'date/target/purpose mismatch'):
            self.guard(assign=True)
        self.assertEqual(self.path.read_bytes(), receipt_before)

    def test_unknown_boss_checkpoint_reserves_forty_and_disables_boss(self):
        self.prior(['boss'])
        cfg, summary = self.guard()
        self.assertEqual(cfg['policy']['originalResinBudget'], 20)
        self.assertEqual(cfg['policy']['validationAttemptedSources'], ['boss'])
        self.assertEqual(summary['priorReservedOriginal'], 40)

    def test_completed_or_failed_full_attempt_exhausts_total_cap(self):
        self.prior(['boss', 'domain'], status='failed')
        cfg, summary = self.guard()
        self.assertEqual(cfg['policy']['originalResinBudget'], 0)
        self.assertEqual(summary['alreadyAttemptedSources'], ['boss', 'domain'])

    def test_run_copy_and_plugin_copy_union_do_not_double_charge(self):
        _, report = self.prior(['boss'])
        report['steps'].append({'stepId': 'old-run:step-2', 'type': 'domain', 'status': 'unknown', 'validationAttempt': True, 'maxClaims': 1, 'resin': 'original'})
        self.write(self.root / 'logs/runs/old-run/cultivation-report.json', report)
        _, summary = self.guard()
        self.assertEqual(summary['priorReservedOriginal'], 60)

    def test_archive_only_evidence_remains_reserved(self):
        self.prior(['domain'], archive=True)
        cfg, summary = self.guard()
        self.assertEqual(cfg['policy']['originalResinBudget'], 40)
        self.assertEqual(summary['alreadyAttemptedSources'], ['domain'])

    def test_corrupt_or_conflicting_copy_never_refunds(self):
        path, report = self.prior(['boss'])
        self.write(self.root / 'logs/runs/old-run/cultivation-report.json', report)
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            self.guard()
        report['steps'][0]['type'] = 'domain'
        self.write(path, report)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            self.guard()

    def test_assigned_missing_report_requires_explicit_unlaunched_proof(self):
        self.receipt['assignedRunIds'] = ['old-run']
        self.write(self.path, self.receipt)
        with self.assertRaises(ValueError):
            self.guard()
        result = {'runId': 'old-run', 'gameDate': '2026-10-08', 'cultivationTarget': TARGET,
                  'cultivationAuthorization': {'scopeId': 'first-validation'}, 'cultivationLaunchAttempted': False}
        path = self.root / 'logs/runs/old-run/result.json'
        self.write(path, result)
        self.assertEqual(self.guard()[1]['priorReservedOriginal'], 0)
        for change in ({'cultivationLaunchAttempted': True}, {'launchedAt': '2026-10-08T00:01:00Z'}, {'gameDate': '2026-10-07'}):
            self.write(path, {**result, **change})
            with self.assertRaises(ValueError):
                self.guard()

    def test_scope_date_target_and_caps_cannot_expand_authorization(self):
        for changes in ({'scopeId': 'other'}, {'gameDate': '2026-10-07'}, {'originalResinCap': 80},
                        {'condensedResinCap': 1}, {'purpose': 'daily'}, {'authorizedAtUTC': '2026-10-07T00:00:00Z'},
                        {'target': {**TARGET, 'targetLevel': 80}}):
            with self.subTest(changes=changes):
                self.write(self.path, {**self.receipt, **changes})
                with self.assertRaises(ValueError):
                    self.guard()

    def test_requested_budget_remains_lower_bound_on_runtime_cap(self):
        self.prior(['domain'])
        self.config['policy']['originalResinBudget'] = 20
        self.assertEqual(self.guard()[0]['policy']['originalResinBudget'], 20)

    def test_nonvalidation_never_requires_or_registers_receipt(self):
        self.config['policy']['validationMode'] = False
        before = self.path.read_bytes()
        self.assertEqual(self.guard(assign=True)[1], {})
        self.assertEqual(self.path.read_bytes(), before)

    def continuation_fixture(self, game_date='2026-10-09'):
        """Synthetic independent approval; never touches the actual state folder."""
        snapshot = self.root / 'state/cultivation-authorization-snapshots' / (game_date + '-parent.json')
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(self.path.read_bytes())
        approval = {'schemaVersion': 1, 'kind': 'initial-validation-continuation',
            'scopeId': self.receipt['scopeId'], 'gameDate': game_date, 'target': copy.deepcopy(TARGET),
            'originalResinCap': 60, 'condensedResinCap': 0, 'authorizedAtUTC': game_date + 'T00:00:00Z',
            'authorizationSource': {'kind': 'explicit-user-resume', 'recordedBy': 'root-agent',
                'instruction': 'Continue the same first validation; preserve the cumulative cap and unknown reservation.'},
            'parentReceipt': {'path': snapshot.relative_to(self.root).as_posix(),
                'sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest()}}
        path = self.root / 'state/cultivation-validation-continuations' / (game_date + '.json')
        self.write(path, approval)
        return path, approval, snapshot

    def cross_day_guard(self, *, run_id='resumed-run', assign=False, game_date='2026-10-09'):
        return constrain_validation(self.root, self.bgi, self.config, run_id, game_date, assign=assign)

    def prior_result(self, identifier='old-run', game_date='2026-10-08', authorization=None):
        result = {'runId': identifier, 'gameDate': game_date, 'cultivationTarget': copy.deepcopy(TARGET),
            'cultivationAuthorization': authorization or {'scopeId': self.receipt['scopeId']},
            'cultivationLaunchAttempted': True, 'outcome': 'unknown'}
        self.write(self.root / 'logs/runs' / identifier / 'result.json', result)
        return result

    def test_cross_day_requires_separate_dated_explicit_resume(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.cross_day_guard(assign=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.continuation_fixture()
        _, summary = self.cross_day_guard()
        self.assertEqual(summary['originalGameDate'], '2026-10-08')
        self.assertEqual(summary['gameDate'], '2026-10-09')
        self.assertEqual(summary['originalResinCap'], 60)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cross_day_preserves_unknown_forty_and_snapshot_across_append(self):
        report_path, _ = self.prior(['boss'])
        prior = self.prior_result()
        approval_path, _, snapshot = self.continuation_fixture()
        immutable = [path.read_bytes() for path in (approval_path, snapshot, report_path)]
        self.config['policy']['allowBoss'] = False
        config, summary = self.cross_day_guard(assign=True)
        self.assertEqual(config['policy']['originalResinBudget'], 20)
        self.assertEqual(summary['priorReservedOriginal'], 40)
        self.assertEqual(summary['alreadyAttemptedSources'], ['boss'])
        self.assertEqual(summary['releasedNoCommitOriginal'], 0)
        self.assertNotIn('observedOriginalSpent', summary)
        current = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(current['gameDate'], '2026-10-08')
        self.assertEqual(current['authorizedAtUTC'], self.receipt['authorizedAtUTC'])
        self.assertEqual(current['assignedRunIds'], ['old-run', 'resumed-run'])
        self.prior_result('resumed-run', '2026-10-09', summary)
        self.write(self.root / 'logs/runs/resumed-run/cultivation-report.json',
            {'runId': 'resumed-run', 'mode': 'execute', 'target': copy.deepcopy(TARGET),
             'policy': copy.deepcopy(config['policy']), 'status': 'unknown', 'steps':
             [{'stepId': 'resumed-run:step-1', 'type': 'domain', 'status': 'unknown',
               'validationAttempt': True, 'maxClaims': 1, 'resin': 'original'}]})
        config, summary = self.cross_day_guard(run_id='next-run')
        self.assertEqual(config['policy']['originalResinBudget'], 0)
        self.assertEqual(summary['priorReservedOriginal'], 60)
        self.assertEqual(summary['originalResinCap'], 60)
        self.assertEqual([path.read_bytes() for path in (approval_path, snapshot, report_path)], immutable)
        self.assertEqual(json.loads((self.root / 'logs/runs/old-run/result.json').read_text(encoding='utf-8')), prior)

    def test_cross_day_requires_authoritative_result_even_with_checkpoint(self):
        self.prior(['boss'])
        self.continuation_fixture()
        with self.assertRaises(ValueError):
            self.cross_day_guard()
        self.prior_result()
        self.assertEqual(self.cross_day_guard()[1]['priorReservedOriginal'], 40)
        path = self.root / 'logs/runs/old-run/result.json'
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.cross_day_guard()

    def test_continuation_rejects_scope_cap_target_provenance_and_wrong_game_day(self):
        path, approval, _ = self.continuation_fixture()
        variants = [{**approval, 'scopeId': 'unlinked-new-scope'}, {**approval, 'originalResinCap': 20},
            {**approval, 'originalResinCap': 80}, {**approval, 'condensedResinCap': 1},
            {**approval, 'target': {**TARGET, 'targetLevel': 80}}, {**approval, 'gameDate': '2026-10-10'},
            {**approval, 'authorizedAtUTC': '2026-10-08T19:59:59Z'},
            {**approval, 'authorizationSource': {'kind': 'automatic-retry', 'recordedBy': 'root-agent', 'instruction': 'Continue'}},
            {**approval, 'authorizationSource': {**approval['authorizationSource'], 'instruction': ''}},
            {**approval, 'authorizationSource': {**approval['authorizationSource'], 'recordedBy': 'self'}}]
        before = self.path.read_bytes()
        for variant in variants:
            with self.subTest(variant=variant):
                self.write(path, variant)
                with self.assertRaises(ValueError):
                    self.cross_day_guard(assign=True)
                self.assertEqual(self.path.read_bytes(), before)

    def test_continuation_rejects_changed_or_missing_snapshot_and_prefix_removal(self):
        self.prior(['boss'])
        self.prior_result()
        path, approval, snapshot = self.continuation_fixture()
        original = snapshot.read_bytes()
        snapshot.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'SHA256 changed'):
            self.cross_day_guard()
        snapshot.write_bytes(original)
        changed = copy.deepcopy(approval)
        changed['parentReceipt']['path'] = 'state/cultivation-authorization-snapshots/missing.json'
        self.write(path, changed)
        with self.assertRaises(ValueError):
            self.cross_day_guard()
        self.write(path, approval)
        self.receipt['assignedRunIds'] = []
        self.write(self.path, self.receipt)
        with self.assertRaisesRegex(ValueError, 'prefix changed'):
            self.cross_day_guard()
        self.receipt['assignedRunIds'] = ['old-run']
        self.receipt['originalResinCap'] = 20
        self.write(self.path, self.receipt)
        changed['parentReceipt'] = approval['parentReceipt']
        changed['originalResinCap'] = 20
        self.write(path, changed)
        with self.assertRaisesRegex(ValueError, 'parent receipt changed'):
            self.cross_day_guard()

    def test_new_day_assigned_result_must_retain_exact_continuation_provenance(self):
        self.continuation_fixture()
        _, summary = self.cross_day_guard(assign=True)
        prior = self.prior_result('resumed-run', '2026-10-09', summary)
        prior['cultivationLaunchAttempted'] = False
        path = self.root / 'logs/runs/resumed-run/result.json'
        self.write(path, prior)
        self.assertEqual(self.cross_day_guard(run_id='next-run')[1]['priorReservedOriginal'], 0)
        variants = [copy.deepcopy(prior) for _ in range(4)]
        variants[0]['cultivationAuthorization'].pop('executionContinuation')
        variants[1]['cultivationAuthorization']['executionContinuation']['sha256'] = '0' * 64
        variants[2]['cultivationAuthorization']['originalResinCap'] = 20
        variants[3]['gameDate'] = '2026-10-10'
        for variant in variants:
            self.write(path, variant)
            with self.assertRaises(ValueError):
                self.cross_day_guard(run_id='next-run')

    def test_original_receipt_timestamp_cannot_be_overwritten_for_resume(self):
        self.continuation_fixture()
        self.receipt['authorizedAtUTC'] = '2026-10-09T00:00:00Z'
        self.write(self.path, self.receipt)
        with self.assertRaisesRegex(ValueError, 'timestamp outside'):
            self.cross_day_guard()

    def test_old_audit_dates_and_fixed_pre_battle_limits_survive_resume(self):
        audit_path, _, reports = self.reviewed_pre_battle_fixture()
        before = [path.read_bytes() for path in [audit_path, *reports]]
        self.continuation_fixture()
        self.config['policy']['allowBoss'] = False
        config, summary = self.cross_day_guard()
        self.assertEqual(config['policy']['originalResinBudget'], 60)
        self.assertEqual(summary['releasedNoCommitOriginal'], 40)
        self.assertEqual(summary['noCommitReviews'][0]['historicalOutcomeRetained'], 'unknown')
        self.assertEqual([path.read_bytes() for path in [audit_path, *reports]], before)
        audit = json.loads(before[0])
        audit['gameDate'] = '2026-10-09'
        self.write(audit_path, audit)
        with self.assertRaises(ValueError):
            self.cross_day_guard()

    def test_old_reader_only_abort_audit_uses_original_day(self):
        audit_path, _, _ = self.reviewed_no_attempt_fixture()
        before = audit_path.read_bytes()
        self.continuation_fixture()
        _, summary = self.cross_day_guard()
        self.assertEqual(summary['noAttemptReviews'][0]['historicalOutcomeRetained'], 'failed')
        self.assertEqual(summary['releasedNoCommitOriginal'], 0)
        self.assertEqual(audit_path.read_bytes(), before)

    def test_third_day_accounts_prior_continuation_without_rewriting_approval(self):
        self.prior(['boss'])
        self.prior_result()
        first_path, _, first_snapshot = self.continuation_fixture()
        _, summary = self.cross_day_guard(assign=True)
        self.prior_result('resumed-run', '2026-10-09', summary)
        self.write(self.root / 'logs/runs/resumed-run/cultivation-report.json',
            {'runId': 'resumed-run', 'mode': 'execute', 'target': copy.deepcopy(TARGET),
             'policy': copy.deepcopy(self.config['policy']), 'steps': []})
        first_before = [first_path.read_bytes(), first_snapshot.read_bytes()]
        self.continuation_fixture('2026-10-10')
        config, summary = self.cross_day_guard(run_id='third-day-run', game_date='2026-10-10')
        self.assertEqual(summary['priorReservedOriginal'], 40)
        self.assertEqual(config['policy']['originalResinBudget'], 20)
        self.assertEqual([first_path.read_bytes(), first_snapshot.read_bytes()], first_before)

    def reviewed_no_commit_fixture(self, *, mirrors=True):
        report_path, report = self.prior(['boss'])
        report['policy']['allowCrafting'] = False
        step = report['steps'][0]
        step.update(resinBefore={'originalResin': 149, 'originalVerified': True, 'mainUiRestored': True,
                    'observedAt': '2026-10-08T00:05:49Z'}, startedAt='2026-10-08T00:05:50Z',
                    finishedAt='2026-10-08T00:09:00Z',
                    parameterEvidence={'SpecifyRunCount': True, 'RunCount': 1, 'UseFragileResin': False,
                        'UseTransientResin': False, 'ReviveRetryCount': 0, 'ReturnToStatueAfterEachRound': False,
                        'RewardRecognitionEnabled': True, 'Timeout': 180})
        self.write(report_path, report)
        report_paths = [report_path]
        run_dir = self.root / 'logs/runs/old-run'
        if mirrors:
            report_paths.append(run_dir / 'cultivation-report.json')
            self.write(report_paths[-1], report)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / 'bettergi.log').write_text('[08:08:33.000] [INF]\n检测到复苏界面\n[08:09:01.000] [ERR]\n取消自动任务\nTpTask.SwitchArea', encoding='utf-8')
        video = run_dir / 'genshin-window.mkv'
        video.write_bytes(b'retained fake video; no game or recorder invoked')
        self.write(run_dir / 'recording.json', {'complete': True, 'frameCoveragePassed': True,
            'frameCoverage': .9956, 'file': str(video.resolve()), 'startedAt': '2026-10-08T00:00:00Z',
            'stoppedAt': '2026-10-08T00:10:00Z', 'probe': {'format': {'duration': '600'}}})
        frame_dir = self.root / 'tests/.artifacts/no-commit-audit-old'
        frame_dir.mkdir(parents=True)
        for name in ('startMap', 'endMap', 'revive'):
            (frame_dir / (name + '.png')).write_bytes(('retained fake frame ' + name).encode())
        def source(path):
            return {'path': path.relative_to(self.root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        audit = {'schemaVersion': 1, 'kind': 'historical-boss-no-commit', 'runId': 'old-run',
            'stepId': 'old-run:step-1', 'scopeId': 'first-validation', 'gameDate': '2026-10-08',
            'target': copy.deepcopy(TARGET), 'reviewId': 'historical-no-commit:old-run:step-1',
            'configuredOriginalCost': 40, 'releasedOriginalReservation': 40, 'observedOriginalSpent': 0,
            'verdict': 'no-commit', 'reviewedBy': 'root-agent', 'reviewedAtUTC': '2026-10-08T00:10:01Z',
            'reason': 'Independent retained fixture: same original resin across bounded no-supplement interval',
            'assertions': {name: True for name in ('uninterruptedVideoReviewed', 'logAndFramesReviewed', 'noSupplement', 'noRewardSubmission', 'bossAliveAtRevive')},
            'sources': {'reports': [source(path) for path in report_paths], 'log': source(run_dir / 'bettergi.log'),
                'recording': source(run_dir / 'recording.json'), 'video': source(video),
                'frames': {name: source(frame_dir / (name + '.png')) for name in ('startMap', 'endMap', 'revive')}},
            'observations': {'startMap': {'videoOffsetSeconds': 360, 'observedAtUTC': '2026-10-08T00:06:00Z', 'originalResin': 149, 'nextRestoreSeconds': 298},
                'endMap': {'videoOffsetSeconds': 565, 'observedAtUTC': '2026-10-08T00:09:25Z', 'originalResin': 149},
                'revive': {'videoOffsetSeconds': 512, 'observedAtUTC': '2026-10-08T00:08:32Z'}}}
        audit_path = self.root / 'state/cultivation-no-commit-reviews/old-run.json'
        self.write(audit_path, audit)
        return audit_path, audit, report_paths

    def test_reviewed_zero_commit_releases_only_old_reservation_without_success_or_new_cap(self):
        audit_path, audit, report_paths = self.reviewed_no_commit_fixture()
        before = [path.read_bytes() for path in report_paths]
        receipt_before = self.path.read_bytes()
        config, summary = self.guard()
        self.assertEqual(config['policy']['originalResinBudget'], 60)
        self.assertEqual(config['policy']['validationAttemptedSources'], [])
        self.assertEqual(summary['releasedNoCommitOriginal'], 40)
        self.assertEqual(summary['priorReservedOriginal'], 0)
        self.assertEqual(summary['noCommitReviews'][0]['historicalOutcomeRetained'], 'unknown')
        self.assertEqual([path.read_bytes() for path in report_paths], before)
        self.assertEqual(self.path.read_bytes(), receipt_before)
        self.assertEqual(self.guard()[1]['releasedNoCommitOriginal'], 40)  # Derived once; never adds 40 to cap.
        self.guard(assign=True)
        new_report = {'runId': 'new-run', 'mode': 'execute', 'target': TARGET, 'policy': self.config['policy'],
            'status': 'unknown', 'steps': [{'stepId': 'new-run:step-1', 'type': 'boss', 'maxClaims': 1,
                                          'resin': 'original', 'validationAttempt': True, 'status': 'unknown'}]}
        self.write(self.bgi / 'User/JsScript/AutoGameCultivation/record/new-run.json', new_report)
        config, summary = self.guard(run_id='next-run')
        self.assertEqual(config['policy']['originalResinBudget'], 20)
        self.assertEqual(config['policy']['validationAttemptedSources'], ['boss'])
        self.assertEqual(summary['releasedNoCommitOriginal'], 40)

    def test_review_rejects_wrong_scope_cost_time_and_supplement_assertions(self):
        audit_path, audit, _ = self.reviewed_no_commit_fixture()
        variants = [{**audit, 'scopeId': 'other'}, {**audit, 'runId': 'foreign'},
                    {**audit, 'releasedOriginalReservation': 60}, {**audit, 'observedOriginalSpent': 1},
                    {**audit, 'verdict': 'success'}, {**audit, 'assertions': {**audit['assertions'], 'noSupplement': False}}]
        changed = copy.deepcopy(audit)
        changed['observations']['endMap']['originalResin'] = 109
        variants.append(changed)
        changed = copy.deepcopy(audit)
        changed['observations']['endMap']['observedAtUTC'] = '2026-10-08T00:08:25Z'
        variants.append(changed)
        changed = copy.deepcopy(audit)
        changed['observations']['startMap']['nextRestoreSeconds'] = 200
        variants.append(changed)
        for variant in variants:
            self.write(audit_path, variant)
            with self.assertRaises(ValueError):
                self.guard()

    def test_review_requires_unchanged_sources_and_all_current_report_mirrors(self):
        audit_path, audit, report_paths = self.reviewed_no_commit_fixture()
        changed = copy.deepcopy(audit)
        changed['sources']['reports'].pop()
        self.write(audit_path, changed)
        with self.assertRaisesRegex(ValueError, 'every existing report'):
            self.guard()
        self.write(audit_path, audit)
        for source in (report_paths[0], report_paths[1], self.root / audit['sources']['log']['path'],
                       self.root / audit['sources']['video']['path'], self.root / audit['sources']['frames']['endMap']['path']):
            before = source.read_bytes()
            source.write_bytes(before + b' ')
            with self.assertRaises(ValueError):
                self.guard()
            source.write_bytes(before)

    def test_review_not_assigned_to_current_receipt_cannot_release_budget(self):
        self.reviewed_no_commit_fixture()
        self.receipt['assignedRunIds'] = []
        self.write(self.path, self.receipt)
        config, summary = self.guard()
        self.assertEqual(summary['releasedNoCommitOriginal'], 0)
        self.assertEqual(config['policy']['originalResinBudget'], 60)

    def test_even_rehashed_review_sources_cannot_hide_after_inventory_or_late_cancellation(self):
        audit_path, audit, report_paths = self.reviewed_no_commit_fixture()
        report_before = [path.read_bytes() for path in report_paths]
        changed = copy.deepcopy(audit)
        for path in report_paths:
            report = json.loads(path.read_text(encoding='utf-8'))
            report['steps'][0]['after'] = {'113071': {'name': '谜土的护符', 'count': 34, 'status': 'exact'}}
            self.write(path, report)
        for source in changed['sources']['reports']:
            source['sha256'] = hashlib.sha256((self.root / source['path']).read_bytes()).hexdigest()
        self.write(audit_path, changed)
        with self.assertRaisesRegex(ValueError, 'after/commit'):
            self.guard()
        for path, before in zip(report_paths, report_before):
            path.write_bytes(before)
        changed = copy.deepcopy(audit)
        log_path = self.root / changed['sources']['log']['path']
        log_path.write_text('[08:08:33.000] [INF]\n检测到复苏界面\n[08:09:59.000] [ERR]\n取消自动任务\nTpTask.SwitchArea', encoding='utf-8')
        changed['sources']['log']['sha256'] = hashlib.sha256(log_path.read_bytes()).hexdigest()
        self.write(audit_path, changed)
        with self.assertRaisesRegex(ValueError, 'native cancellation'):
            self.guard()

    def reviewed_no_attempt_fixture(self):
        self.receipt['assignedRunIds'] = ['old-run']
        self.write(self.path, self.receipt)
        run_dir = self.root / 'logs/runs/old-run'
        result = {'runId': 'old-run', 'gameDate': '2026-10-08', 'cultivationTarget': TARGET,
            'cultivationAuthorization': {'scopeId': 'first-validation'}, 'cultivationLaunchAttempted': True,
            'outcome': 'failed', 'finishedAt': '2026-10-08T00:02:06Z',
            'errors': ['[WinError 5] current-run.json.example.tmp -> current-run.json']}
        self.write(run_dir / 'result.json', result)
        log = '[08:01:40.000] [DBG]\n当前状态：MainUi\n状态转换成功：OpenCharacterList\n状态转换成功：OpenFilterPanel\n[08:01:44.000] [DBG]\n当前状态：OpenFilterPanel\n[08:01:44.040] [DBG]\n主窗体退出'
        (run_dir / 'bettergi.log').write_text(log, encoding='utf-8')
        self.write(run_dir / 'cultivation-group.json', {'Name': 'AutoGameCultivation_old-run',
            'Projects': [{'JsScriptSettingsObject': {'runId': 'old-run', 'mode': 'execute',
                'targetConfigJson': json.dumps(TARGET), 'policyJson': json.dumps(self.config['policy'])}}]})
        video = run_dir / 'genshin-window.mkv'
        video.write_bytes(b'retained fake reader-only video')
        self.write(run_dir / 'recording.json', {'complete': True, 'frameCoveragePassed': True, 'frameCoverage': .9831,
            'file': str(video.resolve()), 'startedAt': '2026-10-08T00:00:00Z', 'stoppedAt': '2026-10-08T00:02:01Z',
            'probe': {'format': {'duration': '118.6'}}})
        backup = self.root / 'backups/retained-runtime'
        backup.mkdir(parents=True)
        (backup / 'operator.js').write_text("const raw=await api.getCharacter();\nreport.steps.push(step);\nconst checkpointPath=`record/${input.runId}.json`;\nif(await api.writeText(checkpointPath,checkpoint)!==true || api.readText(checkpointPath)!==checkpoint) throw new Error('领奖前记录写入失败');\nawait api.runBoss();\nawait api.runDomain();", encoding='utf-8')
        (backup / 'main.js').write_text('getCharacter:(name,categories)=>characterDevelopmentTask.GetCharacter(name,categories)', encoding='utf-8')
        frame_dir = self.root / 'tests/.artifacts/no-attempt-audit-old'
        frame_dir.mkdir(parents=True)
        frames = []
        def source(path):
            return {'path': path.relative_to(self.root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for index in range(1, 7):
            frame = frame_dir / f'interval-{index:02}.png'
            frame.write_bytes(f'retained fake contact {index}'.encode())
            frames.append(source(frame))
        sources = {key: source(run_dir / filename) for key, filename in
            (('result', 'result.json'), ('log', 'bettergi.log'), ('group', 'cultivation-group.json'),
             ('recording', 'recording.json'), ('video', 'genshin-window.mkv'))}
        sources.update(operator=source(backup / 'operator.js'), main=source(backup / 'main.js'), frames=frames)
        audit = {'schemaVersion': 1, 'kind': 'historical-pre-resource-no-attempt', 'reviewId': 'historical-no-attempt:old-run',
            'runId': 'old-run', 'scopeId': 'first-validation', 'gameDate': '2026-10-08', 'target': TARGET,
            'verdict': 'no-resource-attempt', 'releasedOriginalReservation': 0, 'observedOriginalSpent': 0,
            'reviewedBy': 'root-agent', 'reviewedAtUTC': '2026-10-08T00:03:00Z', 'reason': 'Independently reviewed retained fake reader-only abort',
            'assertions': {name: True for name in ('uninterruptedVideoReviewed', 'noResourceEntrySeen',
                'checkpointContractReviewed', 'runtimeSourceIdentityReviewed', 'noSupplement', 'characterReaderOnly')},
            'sources': sources, 'observations': {'videoInterval': {'startOffsetSeconds': 0, 'endOffsetSeconds': 118,
                'reviewedSampleCount': 119, 'sampleIntervalSeconds': 1}, 'lastReader': {'state': 'OpenFilterPanel', 'observedAtUTC': '2026-10-08T00:01:44Z'},
                'nativeWindowExitAtUTC': '2026-10-08T00:01:44.040Z', 'roleMenu': {'videoOffsetSeconds': 110, 'observedAtUTC': '2026-10-08T00:01:50Z'}}}
        audit_path = self.root / 'state/cultivation-no-commit-reviews/old-run.json'
        self.write(audit_path, audit)
        return audit_path, audit, result

    def test_reviewed_reader_only_abort_clears_missing_report_block_without_fabricated_report(self):
        _, _, prior = self.reviewed_no_attempt_fixture()
        before = self.path.read_bytes()
        config, summary = self.guard()
        self.assertEqual(config['policy']['originalResinBudget'], 60)
        self.assertEqual(summary['releasedNoCommitOriginal'], 0)
        self.assertEqual(summary['noAttemptReviews'][0]['historicalOutcomeRetained'], 'failed')
        self.assertIs(summary['noAttemptReviews'][0]['resourceAttempted'], False)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(json.loads((self.root / 'logs/runs/old-run/result.json').read_text(encoding='utf-8')), prior)
        self.assertFalse((self.root / 'logs/runs/old-run/cultivation-report.json').exists())
        self.assertFalse((self.bgi / 'User/JsScript/AutoGameCultivation/record/old-run.json').exists())

    def test_reader_only_audit_requires_independent_review_complete_samples_and_matching_times(self):
        path, audit, _ = self.reviewed_no_attempt_fixture()
        variants = [{**audit, 'scopeId': 'other'}, {**audit, 'releasedOriginalReservation': 40},
                    {**audit, 'assertions': {**audit['assertions'], 'runtimeSourceIdentityReviewed': False}}]
        for key, value in (('reviewedSampleCount', 118), ('endOffsetSeconds', 110)):
            changed = copy.deepcopy(audit)
            changed['observations']['videoInterval'][key] = value
            variants.append(changed)
        changed = copy.deepcopy(audit)
        changed['observations']['nativeWindowExitAtUTC'] = '2026-10-08T00:01:44.050Z'
        variants.append(changed)
        for changed in variants:
            self.write(path, changed)
            with self.assertRaises(ValueError):
                self.guard()

    def test_reader_only_audit_rejects_rehashed_resource_entry_or_wrong_checkpoint_order(self):
        path, audit, _ = self.reviewed_no_attempt_fixture()
        for key, prefix in (('log', 'AutoBoss resource entered\n'), ('operator', 'await api.runBoss();\n')):
            changed = copy.deepcopy(audit)
            source = self.root / changed['sources'][key]['path']
            before = source.read_bytes()
            source.write_bytes(prefix.encode() + before)
            changed['sources'][key]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            self.write(path, changed)
            with self.assertRaises(ValueError):
                self.guard()
            source.write_bytes(before)

    def reviewed_pre_battle_fixture(self, identifier='old-run'):
        scope = 'mizuki-first-validation-20261008'
        self.receipt['scopeId'] = scope
        self.config['policy'].update(validationScopeId=scope, allowCrafting=False, allowRoutes=False, allowWeekly=False)
        report_path, report = self.prior(['boss'], run_id=identifier)
        step = report['steps'][0]
        step.update(bossName='Test Boss', startedAt='2026-10-08T00:07:08Z',
            resinBefore={'originalResin': 163, 'originalVerified': True, 'mainUiRestored': True,
                         'observedAt': '2026-10-08T00:07:06Z'},
            parameterEvidence={'BossName': 'Test Boss', 'SpecifyRunCount': True, 'RunCount': 1,
                'UseFragileResin': False, 'UseTransientResin': False, 'ReviveRetryCount': 0,
                'ReturnToStatueAfterEachRound': False, 'RewardRecognitionEnabled': True, 'Timeout': 180})
        self.write(report_path, report)
        run_dir = self.root / 'logs/runs' / identifier
        archive = run_dir / 'cultivation-report.json'
        self.write(archive, report)
        (run_dir / 'bettergi.log').write_text('[08:07:40.000] [INF]\n"自动首领讨伐"：前往 Test Boss\n'
            '[08:09:30.000] [DBG]\n主窗体退出\n粗略接近途经点', encoding='utf-8')
        video = run_dir / 'genshin-window.mkv'
        video.write_bytes(b'retained fake pre-battle video; no game launched')
        recording = {'complete': True, 'frameCoveragePassed': True, 'frameCoverage': .9964, 'gamePid': 12345,
            'file': str(video.resolve()), 'startedAt': '2026-10-08T00:00:00Z', 'stoppedAt': '2026-10-08T00:09:43Z',
            'settings': {'frameRate': 15}, 'probe': {'format': {'duration': '581.334'}}}
        self.write(run_dir / 'recording.json', recording)
        self.write(run_dir / 'result.json', {'runId': identifier, 'gameDate': '2026-10-08', 'cultivationTarget': TARGET,
            'cultivationAuthorization': {'scopeId': scope, 'originalResinCap': 60, 'condensedResinCap': 0},
            'cultivationLaunchAttempted': True, 'outcome': 'unknown', 'executionOutcome': 'cancelled',
            'finishedAt': '2026-10-08T00:09:45Z', 'gamePidsClosedByGuard': [12345], 'recording': recording})
        self.write(run_dir / 'cultivation-group.json', {'Name': 'AutoGameCultivation_' + identifier,
            'Projects': [{'JsScriptSettingsObject': {'runId': identifier, 'mode': 'execute',
                'targetConfigJson': json.dumps(TARGET), 'policyJson': json.dumps(self.config['policy'])}}]})
        backup = self.root / 'backups' / ('pre-battle-abort-source-' + identifier.split('-')[0])
        backup.mkdir(parents=True)
        (backup / 'operator.js').write_text('report.steps.push(step);\nconst checkpointPath=`record/${input.runId}.json`;\n'
            "if(await api.writeText(checkpointPath,checkpoint)!==true || api.readText(checkpointPath)!==checkpoint) throw new Error('failure');\nawait api.runBoss(taskParam,remainingMilliseconds);", encoding='utf-8')
        (backup / 'main.js').write_text('async runBoss(){return dispatcher.RunAutoBossTask(param,cts.Token);}', encoding='utf-8')
        (backup / 'AutoBossTask.cs').write_text('private async Task RunBossLoop() {\nawait NavigateToBoss();\n'
            'await RunAutoFight();\nawait NavigateToReward();\nawait TakeReward();\n}\n'
            '    private async Task RunAutoFight() {\n_logger.LogInformation("{Name}：执行战斗策略", Name);\n}', encoding='utf-8')
        (backup / 'BetterGI.dll').write_bytes(b'retained fake executed DLL')
        def source(path):
            return {'path': path.relative_to(self.root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        sources = {k: source(run_dir / name) for k, name in (('result', 'result.json'), ('group', 'cultivation-group.json'),
            ('log', 'bettergi.log'), ('video', 'genshin-window.mkv'), ('recording', 'recording.json'))}
        sources.update({k: source(backup / name) for k, name in (('operator', 'operator.js'), ('main', 'main.js'),
            ('autoBoss', 'AutoBossTask.cs'), ('dll', 'BetterGI.dll'))})
        sources['reports'] = [source(report_path), source(archive)]
        identity = {'schemaVersion': 1, 'runId': identifier, 'gameDate': '2026-10-08', 'gamePid': 12345,
            'reviewedBy': 'live-operator', 'reviewedAtUTC': '2026-10-08T00:10:00Z', 'sourceMatchesExecutedBinary': True,
            'sources': {k: copy.deepcopy(sources[k]) for k in ('operator', 'main', 'autoBoss', 'dll')}}
        self.write(backup / 'runtime-deployment-attestation.json', identity)
        sources['runtimeIdentity'] = source(backup / 'runtime-deployment-attestation.json')
        frame_dir = self.root / 'tests/.artifacts' / ('no-commit-audit-' + identifier.split('-')[0])
        frame_dir.mkdir(parents=True)
        frames = []
        for index in range(1, 10):
            frame = frame_dir / f'sheet-{index:02}.png'
            frame.write_bytes(f'retained fake contact {index}; padding excluded'.encode())
            frames.append(frame)
        sources['frames'] = [source(p) for p in frames]
        metadata = {'RunId': identifier, 'SampleFps': 1, 'ReviewedSampleCount': 161, 'ContactSheets': 9,
            'PaddedCellsExcluded': True, 'RequestedOffsetStart': 420, 'RecordingDuration': 581.334,
            'FirstEncodedPts': 420, 'LastEncodedPts': 581.267, 'EncodedFrames': 2416, 'MaximumEncodedGapSeconds': .134,
            'ObservedBeforeOriginal': 163, 'BeforeObservedAt': step['resinBefore']['observedAt'],
            'BalanceAtStop': 'not_observed', 'NoRefillOrRewardUiObserved': True, 'NoBattleStrategyOrClaimEntryObserved': True,
            'FileHashes': [{'Path': str(p.resolve()), 'Hash': hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in (video, run_dir / 'bettergi.log', report_path, archive, *frames)]}
        self.write(frame_dir / 'review-metadata.json', metadata)
        sources['metadata'] = source(frame_dir / 'review-metadata.json')
        audit = {'schemaVersion': 1, 'kind': 'pre-battle-boss-no-commit', 'runId': identifier,
            'stepId': identifier + ':step-1', 'reviewId': 'pre-battle-no-commit:' + identifier + ':step-1',
            'scopeId': scope, 'gameDate': '2026-10-08', 'target': TARGET,
            'configuredOriginalCost': 40, 'releasedOriginalReservation': 40, 'observedOriginalSpent': 0,
            'verdict': 'no-commit', 'reviewedBy': 'root-agent', 'reviewedAtUTC': '2026-10-08T00:10:01Z',
            'reason': 'Reviewed retained fake pre-battle source and continuous video, without an after balance',
            'immutableProofChecks': {k: True for k in ('runtimeDeploymentIdentityReviewed', 'checkpointBeforeBossEntryReviewed',
                'navigationBeforeFightBeforeClaimReviewed', 'completeIntervalReviewed', 'noBattleEntry', 'noRewardEntry',
                'noSupplement', 'bossAliveAtStop')}, 'sources': sources}
        audit_path = self.root / 'state/cultivation-no-commit-reviews' / (identifier + '.json')
        self.write(audit_path, audit)
        return audit_path, audit, [report_path, archive]

    def test_pre_battle_no_after_balance_releases_exactly_one_reservation_and_retains_unknown(self):
        _, _, reports = self.reviewed_pre_battle_fixture()
        before = [p.read_bytes() for p in reports]
        receipt = self.path.read_bytes()
        for _ in range(2):
            config, summary = self.guard()
            self.assertEqual(summary['originalResinCap'], 60)
            self.assertEqual(summary['priorReservedOriginal'], 0)
            self.assertEqual(summary['releasedNoCommitOriginal'], 40)
            self.assertEqual(config['policy']['originalResinBudget'], 60)
            self.assertEqual(summary['noCommitReviews'][0]['historicalOutcomeRetained'], 'unknown')
            self.assertEqual(summary['noCommitReviews'][0]['balanceAfterStop'], 'not_observed')
        self.assertEqual([p.read_bytes() for p in reports], before)
        self.assertEqual(self.path.read_bytes(), receipt)

    def test_pre_battle_rejects_scope_target_refill_retry_missing_hash_and_duplicate_assignment(self):
        path, audit, _ = self.reviewed_pre_battle_fixture()
        variants = [{**audit, 'scopeId': 'other'}, {**audit, 'gameDate': '2026-10-07'},
            {**audit, 'target': {**TARGET, 'targetLevel': 80}}, {**audit, 'stepId': 'old-run:step-2'},
            {**audit, 'releasedOriginalReservation': 60}, {**audit, 'reviewedBy': 'self'},
            {**audit, 'immutableProofChecks': {**audit['immutableProofChecks'], 'noBattleEntry': False}}]
        missing = copy.deepcopy(audit)
        missing['sources']['dll'].pop('sha256')
        variants.append(missing)
        for variant in variants:
            self.write(path, variant)
            with self.assertRaises(ValueError):
                self.guard()
        self.write(path, audit)
        self.receipt['assignedRunIds'].append('old-run')
        self.write(self.path, self.receipt)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.guard()

    def test_pre_battle_even_rehashed_sources_cannot_hide_commit_refill_or_entry_marker(self):
        path, audit, reports = self.reviewed_pre_battle_fixture()
        for changes in ({'after': {}}, {'resinAfter': {'originalResin': 123}},
                        {'parameterEvidence': {**json.loads(reports[0].read_text(encoding='utf-8'))['steps'][0]['parameterEvidence'], 'ReviveRetryCount': 1}},
                        {'parameterEvidence': {**json.loads(reports[0].read_text(encoding='utf-8'))['steps'][0]['parameterEvidence'], 'UseFragileResin': True}}):
            original = [p.read_bytes() for p in reports]
            changed = copy.deepcopy(audit)
            for report in reports:
                data = json.loads(report.read_text(encoding='utf-8'))
                data['steps'][0].update(changes)
                self.write(report, data)
            for source in changed['sources']['reports']:
                source['sha256'] = hashlib.sha256((self.root / source['path']).read_bytes()).hexdigest()
            self.write(path, changed)
            with self.assertRaises(ValueError):
                self.guard()
            for report, content in zip(reports, original):
                report.write_bytes(content)
        for marker in ('执行战斗策略', '已进入征讨之花领奖界面', '首领奖励领取成功', '已使用 1 个脆弱树脂'):
            changed = copy.deepcopy(audit)
            log = self.root / changed['sources']['log']['path']
            original = log.read_bytes()
            log.write_bytes(original + marker.encode('utf-8'))
            changed['sources']['log']['sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
            self.write(path, changed)
            with self.assertRaisesRegex(ValueError, 'log contains'):
                self.guard()
            log.write_bytes(original)

    def test_pre_battle_rejects_uncertain_video_coverage_or_fabricated_stop_balance(self):
        path, audit, _ = self.reviewed_pre_battle_fixture()
        metadata_path = self.root / audit['sources']['metadata']['path']
        original = metadata_path.read_bytes()
        for field, value in (('ReviewedSampleCount', 162), ('MaximumEncodedGapSeconds', 1),
                             ('LastEncodedPts', 570), ('PaddedCellsExcluded', False), ('BalanceAtStop', 164),
                             ('NoBattleStrategyOrClaimEntryObserved', False)):
            metadata = json.loads(original)
            metadata[field] = value
            self.write(metadata_path, metadata)
            changed = copy.deepcopy(audit)
            changed['sources']['metadata']['sha256'] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
            self.write(path, changed)
            with self.assertRaises(ValueError):
                self.guard()
        metadata_path.write_bytes(original)

    def test_pre_battle_rejects_changed_deployed_dll_and_missing_report_mirror(self):
        path, audit, _ = self.reviewed_pre_battle_fixture()
        changed = copy.deepcopy(audit)
        changed['sources']['reports'].pop()
        self.write(path, changed)
        with self.assertRaisesRegex(ValueError, 'every existing report'):
            self.guard()
        self.write(path, audit)
        dll = self.root / audit['sources']['dll']['path']
        dll.write_bytes(dll.read_bytes() + b'changed binary')
        with self.assertRaisesRegex(ValueError, 'SHA256 changed'):
            self.guard()


if __name__ == '__main__':
    unittest.main()
