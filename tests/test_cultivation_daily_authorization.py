"""Independent daily grants preserve old unknowns and require same-run first20 proof."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from uuid import uuid4

from scripts.cultivation import load_cultivation_config, verify_cultivation_report
from scripts.cultivation_validation import constrain_validation
from tests import test_cultivation as cultivation_fixtures
from tests.test_cultivation import TARGET, POLICY, ROOT

MARKER = '单次原粹20提交后已安全退出到世界双帧，native不宣称已消费或发奖，交外层库存/余额验收'


class DailyAuthorizationTests(unittest.TestCase):
    def write(self, path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')

    def reference(self, path):
        return {'path': path.relative_to(self.root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('daily-authorization-' + uuid4().hex[:12])
        self.bgi = self.root / 'BetterGI_custom'
        self.bgi.mkdir(parents=True)
        self.old = self.root / 'state/cultivation-authorization.json'
        self.write(self.old, {'schemaVersion': 1, 'scopeId': 'old-first', 'purpose': 'initial-validation',
            'target': TARGET, 'assignedRunIds': ['old-unknown-domain', 'old-unknown-boss']})
        self.old_bytes = self.old.read_bytes()
        snapshot = self.root / 'state/cultivation-authorization-snapshots/parent.json'
        snapshot.write_bytes(self.old_bytes) if snapshot.parent.exists() else self.write(snapshot, json.loads(self.old_bytes))
        domain = self.root / 'src/bettergi-custom/BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.SingleOriginal20.cs'
        domain.parent.mkdir(parents=True)
        domain.write_text('retained fake protected native implementation\ninternal static bool HasProtectedLoadingBackground(ImageRegion capture) { return false; }\n// single20 singleclick and30second exit chain remain unchanged\n', encoding='utf-8')
        dll = self.bgi / 'BetterGI.dll'
        dll.write_bytes(b'fake retained DLL identity')
        self.receipt = {'schemaVersion': 1, 'scopeId': 'new-day', 'purpose': 'daily-original-domain',
            'gameDate': '2026-10-10', 'target': copy.deepcopy(TARGET), 'originalResinCap': 200, 'condensedResinCap': 0,
            'authorizedAtUTC': '2026-10-10T01:30:00Z', 'assignedRunIds': [],
            'authorizationSource': {'kind': 'explicit-user-daily-original', 'recordedBy': 'root-agent',
                                    'instruction': 'Authorize current natural original resin for today; no supplement.'},
            'parentReceipt': {**self.reference(snapshot), 'scopeId': 'old-first'},
            'runtimeIdentity': {'domainSource': self.reference(domain), 'engineDll': self.reference(dll)}}
        self.path = self.root / 'state/cultivation-daily-authorizations/new-day.json'
        self.write(self.path, self.receipt)
        self.config = {'executionEnabled': True, 'target': TARGET, 'policy': {**POLICY, 'validationMode': False,
            'dailyMode': True, 'dailyDomainReady': False, 'validationScopeId': 'new-day', 'validationAttemptedSources': [],
            'domainValidated': True, 'allowBoss': False, 'allowCrafting': False, 'maxSteps': 8, 'originalResinBudget': 200,
            'requireZhongliShieldCast': True}}

    def guard(self, run_id='new-run', **kwargs):
        return constrain_validation(self.root, self.bgi, self.config, run_id, '2026-10-10', **kwargs)

    def prior(self, *, status='success'):
        cfg, auth = self.guard('test-run', assign=True)
        helper = cultivation_fixtures.CultivationTests()
        report = helper.execution_report()
        # Saturday opens the 天光 chain, rather than the Thursday 浮世 fixture.
        report = json.loads(json.dumps(report).replace('104320', '104326').replace('104321', '104327').replace('104322', '104328'))
        report['policy'] = {**cfg['policy'], 'domainSingleAttemptVerified': True}
        step = report['steps'][0]
        step['sundaySelectedValue'] = '3'
        step['validationAttempt'] = False
        for key in ('startedAt', 'finishedAt'):
            step[key] = step[key].replace('2026-10-08', '2026-10-10')
        for key in ('resinBefore', 'resinAfter'):
            step[key]['observedAt'] = step[key]['observedAt'].replace('2026-10-08', '2026-10-10')
        step['parameterEvidence'] = {'DomainRoundNum': 1, 'SpecifyResinUse': True, 'AutoArtifactSalvage': False,
            'RewardRecognitionEnabled': True, 'DomainName': step['domainName'], 'PartyName': POLICY['domainPartyName'],
            'SundaySelectedValue': '3', 'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 1,
            'OriginalResin40UseCount': 0, 'CondensedResinUseCount': 0, 'TransientResinUseCount': 0,
            'FragileResinUseCount': 0, 'RequireZhongliShieldCast': True, 'CombatOnly': False, 'ResinPriorityList': ['原粹树脂']}
        directory = self.root / 'logs/runs/test-run'
        directory.mkdir(parents=True)
        plugin = self.bgi / 'User/JsScript/AutoGameCultivation'
        data = plugin / 'upstream/data'
        data.mkdir(parents=True)
        for filename in ('materials.json', 'crafting-recipes.json', 'bettergi-boss-catalog.json'):
            shutil.copyfile(ROOT / 'bgi-scripts/AutoGameCultivation/upstream/data' / filename, data / filename)
        self.report_path = plugin / 'record/test-run.json'
        self.write(self.report_path, report)
        verified = verify_cultivation_report(helper.event('execute'), self.bgi, 'test-run', 'execute', TARGET, directory)
        self.assertEqual(verified['status'], 'success', verified['reason'])
        result = {'runId': 'test-run', 'gameDate': '2026-10-10', 'cultivationTarget': TARGET,
            'cultivationAuthorization': auth, 'cultivationLaunchAttempted': True, 'cultivation': verified['cultivation'],
            'triggeredAt': '2026-10-10T01:00:00Z', 'finishedAt': '2026-10-10T01:01:05Z', 'gameStillRunning': False}
        self.write(directory / 'result.json', result)
        (directory / 'bettergi.log').write_text('[09:00:30.123] ' + MARKER, encoding='utf-8')
        if status != 'success':
            report['status'] = step['status'] = status
            self.write(self.report_path, report)
        return report, result, directory

    def test_first20_ignores_manual_validation_and_old_assignments(self):
        self.config['policy']['dailyDomainReady'] = True
        cfg, summary = self.guard(assign=True)
        self.assertEqual(cfg['policy']['originalResinBudget'], 20)
        self.assertEqual(cfg['policy']['maxSteps'], 1)
        self.assertFalse(cfg['policy']['domainValidated'])
        self.assertTrue(summary['strictFirst20'])
        self.assertEqual(summary['priorRuns'], [])
        self.assertEqual(self.old.read_bytes(), self.old_bytes)
        with self.assertRaisesRegex(ValueError, 'replay'):
            self.guard(assign=True)

    def test_same_scope_complete_inventory_resin_and_native_exit_unlocks_multiple_single20(self):
        self.prior()
        cfg, summary = self.guard()
        self.assertTrue(summary['dailyDomainReady'])
        self.assertEqual(cfg['policy']['originalResinBudget'], 180)
        self.assertEqual(cfg['policy']['maxSteps'], 8)
        self.assertEqual(summary['priorReservedOriginal'], 20)
        self.assertEqual(self.old.read_bytes(), self.old_bytes)

    def test_unknown_attempt_stays_reserved_and_blocks_next_claim(self):
        self.prior(status='unknown')
        cfg, summary = self.guard()
        self.assertEqual(summary['priorReservedOriginal'], 20)
        self.assertEqual(cfg['policy']['originalResinBudget'], 0)
        self.assertEqual(summary['unknownRuns'], ['test-run'])

    def test_no_missing_duplicate_stale_or_unstamped_native_exit_can_unlock(self):
        _, _, directory = self.prior()
        for log in ('', '[09:02:00.000] ' + MARKER, MARKER,
                    '[09:00:30.123] ' + MARKER + '\n[09:00:30.124] ' + MARKER):
            (directory / 'bettergi.log').write_text(log, encoding='utf-8')
            self.assertEqual(self.guard()[0]['policy']['originalResinBudget'], 0)

    def test_scope_provenance_caps_old_run_and_runtime_fingerprint_fail_closed(self):
        original = copy.deepcopy(self.receipt)
        for changes in ({'gameDate': '2026-10-09'}, {'originalResinCap': 201}, {'condensedResinCap': 1},
                        {'purpose': 'initial-validation'}, {'assignedRunIds': ['old-unknown-domain']},
                        {'authorizationSource': {'kind': 'model-recommendation'}}, {'runtimeIdentity': {}}):
            self.write(self.path, {**original, **changes})
            with self.assertRaises(ValueError):
                self.guard()
        self.write(self.path, original)
        (self.bgi / 'BetterGI.dll').write_bytes(b'changed engine')
        with self.assertRaisesRegex(ValueError, 'SHA256 changed'):
            self.guard()

    def test_legacy_snapshot_must_remain_byte_identical(self):
        self.write(self.old, {**json.loads(self.old_bytes), 'assignedRunIds': []})
        with self.assertRaisesRegex(ValueError, 'parent receipt changed'):
            self.guard()

    def test_daily_config_forbids_boss_crafting_condensed_and_initial_scope(self):
        path = self.root / 'daily-config.json'
        self.write(path, self.config)
        self.assertTrue(load_cultivation_config(path, 'execute')['policy']['dailyMode'])
        for changes in ({'allowBoss': True}, {'allowCrafting': True}, {'condensedResinBudget': 1},
                        {'validationMode': True}, {'validationAttemptedSources': ['domain']}):
            self.write(path, {**self.config, 'policy': {**self.config['policy'], **changes}})
            with self.assertRaises(ValueError):
                load_cultivation_config(path, 'execute')

    def test_prelaunch_assigned_run_is_safe_but_launched_without_checkpoint_is_rejected(self):
        _, auth = self.guard('test-run', assign=True)
        result = {'runId': 'test-run', 'gameDate': '2026-10-10', 'cultivationTarget': TARGET,
                  'cultivationAuthorization': auth, 'cultivationLaunchAttempted': False}
        path = self.root / 'logs/runs/test-run/result.json'
        self.write(path, result)
        self.assertEqual(self.guard()[1]['priorReservedOriginal'], 0)
        self.write(path, {**result, 'cultivationLaunchAttempted': True})
        with self.assertRaisesRegex(ValueError, 'missing durable report'):
            self.guard()

    def test_checkpoint_mirror_union_reserves_all_attempts_and_never_trusts_stale_success(self):
        report, _, directory = self.prior()
        expanded = copy.deepcopy(report)
        step = copy.deepcopy(expanded['steps'][0])
        step.update(stepId='test-run:step-2', status='unknown')
        expanded['steps'].append(step)
        self.write(directory / 'cultivation-report.json', expanded)
        cfg, summary = self.guard()
        self.assertEqual(summary['priorReservedOriginal'], 40)
        self.assertEqual(cfg['policy']['originalResinBudget'], 0)

    def test_changed_report_inventory_resin_or_protected_parameter_cannot_unlock(self):
        report, _, _ = self.prior()
        for field, value in (('after', {}), ('resinAfter', {}), ('parameterEvidence', {})):
            changed = copy.deepcopy(report)
            changed['steps'][0][field] = value
            self.write(self.report_path, changed)
            self.assertEqual(self.guard()[0]['policy']['originalResinBudget'], 0)

    def test_requested_lower_budget_is_respected_after_first20(self):
        self.prior()
        self.config['policy']['originalResinBudget'] = 40
        cfg, summary = self.guard()
        self.assertEqual(cfg['policy']['originalResinBudget'], 40)
        self.assertEqual(summary['priorReservedOriginal'], 20)

    def test_canonical_archive_with_stripped_top_inventory_provenance_unlocks(self):
        report, _, directory = self.prior()
        report['inventory']['104326'].update(source='verified-grid-diagnostic', verified=True,
                                             evidence={'retainedFrame': 'fake-existing-evidence'})
        self.write(self.report_path, report)
        canonical = verify_cultivation_report(cultivation_fixtures.CultivationTests().event('execute'),
            self.bgi, 'test-run', 'execute', TARGET, directory)
        self.assertEqual(canonical['status'], 'success')
        self.assertNotEqual(report, canonical['report'])
        self.write(directory / 'cultivation-report.json', canonical['report'])
        cfg, summary = self.guard()
        self.assertTrue(summary['dailyDomainReady'])
        self.assertEqual(cfg['policy']['originalResinBudget'], 180)
        self.assertEqual(self.old.read_bytes(), self.old_bytes)

    def test_canonical_archive_must_match_all_counts_and_paid_step_evidence(self):
        report, _, directory = self.prior()
        canonical = verify_cultivation_report(cultivation_fixtures.CultivationTests().event('execute'),
            self.bgi, 'test-run', 'execute', TARGET, directory)['report']
        for change in ('topCount', 'paidAfter', 'resinAfter', 'nativeParameter'):
            forged = copy.deepcopy(canonical)
            if change == 'topCount':
                forged['inventory']['104326']['count'] += 1
            elif change == 'paidAfter':
                forged['steps'][0]['after']['104326']['count'] += 1
            elif change == 'resinAfter':
                forged['steps'][0]['resinAfter']['originalResin'] -= 1
            else:
                forged['steps'][0]['parameterEvidence']['OriginalResin20UseCount'] = 2
            self.write(directory / 'cultivation-report.json', forged)
            cfg, summary = self.guard()
            self.assertFalse(summary['dailyDomainReady'])
            self.assertEqual(summary['priorReservedOriginal'], 20)
            self.assertEqual(cfg['policy']['originalResinBudget'], 0)

    def transition(self):
        parent = self.root / 'state/cultivation-authorization-snapshots/runtime-parent.json'
        parent.write_bytes(self.path.read_bytes())
        backup = self.root / 'backups/reader-only/BetterGI.dll'
        backup.parent.mkdir(parents=True)
        backup.write_bytes((self.bgi / 'BetterGI.dll').read_bytes())
        (self.bgi / 'BetterGI.dll').write_bytes(b'new reader-only engine')
        prefix = 'src/bettergi-custom/BetterGenshinImpact/'
        dispatcher = self.root / (prefix + 'Core/Script/Dependence/Dispatcher.cs')
        dispatcher.parent.mkdir(parents=True)
        dispatcher.write_text('new dispatcher reader API', encoding='utf-8')
        before = backup.parent / 'Dispatcher.cs'; before.write_text('actual old dirty dispatcher', encoding='utf-8')
        added = self.root / (prefix + 'GameTask/Common/Job/ReadBackpackInventoryTask.cs')
        added.parent.mkdir(parents=True); added.write_text('new read-only task', encoding='utf-8')
        transition = {'schemaVersion': 1, 'kind': 'reader-only-runtime-transition', 'scopeId': 'new-day',
            'gameDate': '2026-10-10', 'effectiveAtUTC': '2026-10-10T02:00:00Z', 'reviewedBy': 'root-agent',
            'reason': 'Actual source diff independently reviewed: only named backpack reader and dispatcher API.',
            'parentReceipt': self.reference(parent), 'oldDllBackup': self.reference(backup),
            'priorRuntimeIdentity': self.receipt['runtimeIdentity'],
            'currentRuntimeIdentity': {**self.receipt['runtimeIdentity'], 'engineDll': self.reference(self.bgi / 'BetterGI.dll')},
            'reviewedSourceChanges': [
                {'path': dispatcher.relative_to(self.root).as_posix(), 'before': self.reference(before), 'after': self.reference(dispatcher)},
                {'path': added.relative_to(self.root).as_posix(), 'before': None, 'after': self.reference(added)}]}
        path = self.root / 'state/cultivation-daily-runtime-transitions/new-day.json'
        self.write(path, transition)
        return path, transition

    def test_reader_only_transition_preserves_old_result_identity_and_grant(self):
        _, result, directory = self.prior()
        receipt_before = self.path.read_bytes(); result_before = (directory / 'result.json').read_bytes()
        _, transition = self.transition()
        cfg, summary = self.guard()
        self.assertTrue(summary['dailyDomainReady'])
        self.assertEqual(summary['runtimeIdentity'], transition['currentRuntimeIdentity'])
        self.assertEqual(self.path.read_bytes(), receipt_before)
        self.assertEqual((directory / 'result.json').read_bytes(), result_before)

    def test_reader_transition_rejects_unreviewed_file_changed_protection_and_missing_dirty_before(self):
        self.prior(); path, transition = self.transition()
        for mutation in ('outsideSource', 'protection', 'dispatcherBefore', 'cutoverHistory'):
            bad = copy.deepcopy(transition)
            if mutation == 'outsideSource': bad['reviewedSourceChanges'][0]['path'] = 'src/AutoDomainTask.cs'
            elif mutation == 'protection': bad['currentRuntimeIdentity']['domainSource']['sha256'] = '0' * 64
            elif mutation == 'dispatcherBefore': bad['reviewedSourceChanges'][0]['before'] = None
            else: bad['effectiveAtUTC'] = '2026-10-10T00:00:00Z'
            self.write(path, bad)
            with self.assertRaises(ValueError): self.guard()
