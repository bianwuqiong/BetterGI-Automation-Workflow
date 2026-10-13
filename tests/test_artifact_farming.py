"""Artifact evidence, authorization, and fake shared-host tests; never launch a game."""
import argparse
import contextlib
import copy
import hashlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import artifact_farming as artifact
from tests import test_workflow as workflow_tests
from tests.test_workflow import wf, FakeHost, FixedClock

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 16, tzinfo=timezone.utc)


def model_fixture(bgi):
    path = bgi / 'Assets/Model/ItemV2/item.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('item_class_id,item_name\nrelic:fake,梦中的铁花\ncurrency:mora,摩拉\n', encoding='utf-8')


def configuration():
    raw = json.loads((ROOT / 'config/artifact-farming.example.json').read_text(encoding='utf-8'))
    raw['executionEnabled'] = True
    raw['policy'].update(domainValidated=True, maxClaims=2, originalResinBudget=100,
        condensedResinBudget=5, maxCrafts=1, craftingValidated=True,
        craftOriginalResinCost=60, condensedCapacity=5)
    return artifact.normalize_config(raw)


def snapshot(original, condensed, at):
    return {'originalResin': original, 'condensedResin': condensed,
        'originalVerified': True, 'condensedVerified': True, 'mainUiRestored': True, 'observedAt': at}


def fixture(bgi, run_id, group):
    settings = group['Projects'][0]['JsScriptSettingsObject']
    config = json.loads(settings['configJson'])
    params = {'DomainRoundNum': 1, 'DomainName': config['target']['domainName'], 'PartyName': config['target']['partyName'],
        'SpecifyResinUse': True, 'CombatOnly': False, 'RequireZhongliShieldCast': True,
        'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 0, 'OriginalResin40UseCount': 0,
        'CondensedResinUseCount': 1, 'FragileResinUseCount': 0, 'TransientResinUseCount': 0,
        'AutoArtifactSalvage': False, 'RewardRecognitionEnabled': True, 'ResinPriorityList': ['浓缩树脂'],
        'ArtifactRunId': run_id, 'ArtifactStepId': run_id + ':step-1',
        'CombatStrategyPath': str(bgi / 'User/AutoFight' / (config['target']['strategyName'] + '.txt'))}
    step = {'stepId': run_id + ':step-1', 'type': 'claim', 'resin': 'condensed', 'status': 'success',
        'startedAt': '2026-10-11T16:00:01Z', 'finishedAt': '2026-10-11T16:02:00Z',
        'before': snapshot(95, 1, '2026-10-11T16:00:00Z'),
        'after': snapshot(95, 0, '2026-10-11T16:02:00Z'), 'parameterEvidence': params, 'rewards': {'梦中的铁花': 3}}
    report = {'schemaVersion': 1, 'runId': run_id, 'mode': artifact.MODE, 'gameDate': settings['gameDate'],
        'configSha256': settings['configSha256'], 'target': config['target'], 'policy': config['policy'],
        'startedAt': '2026-10-11T16:00:00Z', 'finishedAt': '2026-10-11T16:02:01Z', 'targetReached': False,
        'status': 'success', 'steps': [step], 'totals': {'originalResinSpent': 0, 'condensedResinSpent': 1, 'crafts': 0, 'claims': 1}}
    path = bgi / 'User/JsScript' / artifact.PLUGIN_NAME / 'record' / (run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    wf.atomic_json(path, report)
    native = {'task': 'artifact-domain-claim', 'runId': run_id, 'stepId': step['stepId'],
        'resin': 'condensed', 'evidenceVerified': True, 'rewards': step['rewards'],
        'status': 'observed', 'rewardEvidenceVerified': True, 'resinEvidenceVerified': False}
    plugin = {'task': artifact.TASK_NAME, 'runId': run_id, 'mode': artifact.MODE, 'status': 'success',
        'evidenceVerified': True, 'reportRelativePath': f'record/{run_id}.json'}
    text = '\n'.join(['参数指定的一条龙配置：AutoGame_test', '配置组任务执行: 1/1',
        '[AUTO_GAME_EVENT] ' + json.dumps(native), '[AUTO_GAME_EVENT] ' + json.dumps(plugin), '一条龙和配置组任务结束'])
    return path, report, text


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('artifact-' + uuid4().hex[:10])
        self.bgi = self.root / 'fake-bgi'
        self.config = configuration()
        model_fixture(self.bgi)
        self.group = artifact.build_artifact_group('test-run', self.config, '2026-10-11', {'autoDomainConfig': {'reviveRetryCount': 1}}, bettergi_dir=self.bgi)
        self.path, self.report, self.text = fixture(self.bgi, 'test-run', self.group)

    def verify(self):
        return artifact.verify_artifact_analysis(self.text, self.bgi, 'test-run', self.group, 'AutoGame_test', 'exited')

    def test_joint_native_rewards_and_balance_complete_bounded_batch(self):
        result = self.verify()
        self.assertEqual(result['outcome'], 'completed')
        self.assertEqual(result['artifactFarming']['condensedResinSpent'], 1)
        self.assertFalse(result['artifactFarming']['targetReached'])

    def test_balance_only_native_only_and_old_snapshot_fail_closed(self):
        for mutation in ('no-delta', 'empty-rewards', 'old-before', 'foreign-native'):
            report = copy.deepcopy(self.report)
            if mutation == 'no-delta': report['steps'][0]['after']['condensedResin'] = 1
            if mutation == 'empty-rewards': report['steps'][0]['rewards'] = {}
            if mutation == 'old-before': report['steps'][0]['before']['observedAt'] = '2026-10-10T16:00:00Z'
            if mutation == 'foreign-native': self.text = self.text.replace('artifact-domain-claim', 'foreign-receipt')
            wf.atomic_json(self.path, report)
            self.assertEqual(self.verify()['outcome'], 'unknown', mutation)

    def test_unknown_step_and_unsafe_params_never_complete(self):
        for mutation in ('unknown', 'fragile', 'multi-claim'):
            report = copy.deepcopy(self.report)
            if mutation == 'unknown': report['steps'][0]['status'] = 'unknown'
            if mutation == 'fragile': report['steps'][0]['parameterEvidence']['FragileResinUseCount'] = 1
            if mutation == 'multi-claim': report['steps'][0]['parameterEvidence']['DomainRoundNum'] = 2
            wf.atomic_json(self.path, report)
            self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_mora_only_reward_is_unknown_even_with_paid_balance_and_matching_native_receipt(self):
        self.report['steps'][0]['rewards'] = {'摩拉': 10000}
        wf.atomic_json(self.path, self.report)
        self.text = self.text.replace('"\\u68a6\\u4e2d\\u7684\\u94c1\\u82b1": 3', '"\\u6469\\u62c9": 10000')
        self.assertEqual(self.verify()['outcome'], 'unknown')

    def authorize(self):
        receipt = artifact.build_artifact_authorization(self.config, NOW.isoformat())
        wf.atomic_json(self.root / 'state/artifact-authorizations' / (self.config['policy']['scopeId'] + '.json'), receipt)

    def test_game_day_receipt_and_unknown_checkpoint_block_replay(self):
        self.authorize()
        config, lease = artifact.constrain_artifact_authorization(self.root, self.config, 'a', '2026-10-11', assign=True, now=NOW)
        with self.assertRaises(ValueError):
            artifact.constrain_artifact_authorization(self.root, self.config, 'b', '2026-10-11', now=NOW)
        artifact.finalize_artifact_checkpoint(self.root, lease, {}, launch_attempted=False)
        artifact.constrain_artifact_authorization(self.root, self.config, 'b', '2026-10-11', now=NOW)
        with self.assertRaises(ValueError):
            artifact.constrain_artifact_authorization(self.root, self.config, 'c', '2026-10-12', now=NOW)

    def test_verified_spending_reduces_same_scope_budget(self):
        self.authorize()
        _, lease = artifact.constrain_artifact_authorization(self.root, self.config, 'a', '2026-10-11', assign=True, now=NOW)
        artifact.finalize_artifact_checkpoint(self.root, lease, {'reportVerified': True, 'allStepsVerified': True,
            'originalResinSpent': 60, 'condensedResinSpent': 1, 'crafts': 1}, launch_attempted=True)
        bounded, _ = artifact.constrain_artifact_authorization(self.root, self.config, 'b', '2026-10-11', now=NOW)
        self.assertEqual(bounded['policy']['originalResinBudget'], 40)
        self.assertEqual(bounded['policy']['maxCrafts'], 0)

    def test_reset_04_and_validation_only_zero_spend(self):
        self.assertEqual(artifact.game_date(datetime(2026, 10, 11, 19, 59, tzinfo=timezone.utc)), '2026-10-11')
        self.assertEqual(artifact.game_date(datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)), '2026-10-12')
        config = copy.deepcopy(self.config)
        config['policy'].update(validationOnly=True, domainValidated=False, maxClaims=1,
            originalResinBudget=0, condensedResinBudget=0, maxCrafts=0)
        artifact.normalize_config(config)
        config['policy']['originalResinBudget'] = 20
        with self.assertRaises(ValueError): artifact.normalize_config(config)

    def test_eight_hour_explicit_window_keeps_actual_approval_and_resets_only_daily_budgets(self):
        receipt = artifact.build_artifact_authorization(self.config, NOW.isoformat(), '2026-10-12T00:00:00Z')
        path = self.root / 'state/artifact-authorizations' / (self.config['policy']['scopeId'] + '.json')
        wf.atomic_json(path, receipt)
        _, lease = artifact.constrain_artifact_authorization(self.root, self.config, 'a', '2026-10-11', assign=True, now=NOW)
        artifact.finalize_artifact_checkpoint(self.root, lease, {'reportVerified': True, 'allStepsVerified': True,
            'originalResinSpent': 60, 'condensedResinSpent': 1, 'crafts': 1}, launch_attempted=True)
        bounded, next_lease = artifact.constrain_artifact_authorization(self.root, self.config, 'b', '2026-10-12',
            now=datetime(2026, 10, 11, 21, tzinfo=timezone.utc))
        self.assertEqual(bounded['policy']['originalResinBudget'], 100)
        self.assertEqual(next_lease['approvedAtUTC'], receipt['authorizedAtUTC'])
        self.assertEqual(wf.read_json(path), receipt)
        with self.assertRaises(ValueError):
            artifact.constrain_artifact_authorization(self.root, self.config, 'c', '2026-10-12',
                now=datetime(2026, 10, 12, 1, tzinfo=timezone.utc))

    def test_prior_day_unknown_cannot_be_hidden_by_extended_window_or_new_game_day(self):
        receipt = artifact.build_artifact_authorization(self.config, NOW.isoformat(), '2026-10-12T00:00:00Z')
        wf.atomic_json(self.root / 'state/artifact-authorizations' / (self.config['policy']['scopeId'] + '.json'), receipt)
        artifact.constrain_artifact_authorization(self.root, self.config, 'a', '2026-10-11', assign=True, now=NOW)
        with self.assertRaisesRegex(ValueError, 'prior-day'):
            artifact.constrain_artifact_authorization(self.root, self.config, 'b', '2026-10-12',
                now=datetime(2026, 10, 11, 21, tzinfo=timezone.utc))

    def test_validation_requires_independent_recipe_probe_and_no_claim_combat(self):
        config = copy.deepcopy(self.config)
        config['policy'].update(validationOnly=True, domainValidated=False, maxClaims=1,
            originalResinBudget=0, condensedResinBudget=0, maxCrafts=0)
        self.group = artifact.build_artifact_group('test-run', config, '2026-10-11',
            {'autoDomainConfig': {'reviveRetryCount': 1}}, bettergi_dir=self.bgi)
        self.path, report, text = fixture(self.bgi, 'test-run', self.group)
        step = report['steps'][0]
        step.update(type='validation', rewards={})
        step['after']['condensedResin'] = 1
        step['parameterEvidence'].update(CombatOnly=True, CondensedResinUseCount=0,
            RewardRecognitionEnabled=False, ResinPriorityList=[])
        step['parameterEvidence'].pop('ArtifactRunId')
        step['parameterEvidence'].pop('ArtifactStepId')
        report['totals'] = {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0}
        report['recipeInspection'] = {'Status': 'skipped', 'MainUiRestored': True, 'OriginalResinSpent': 0,
            'CondensedResinCreated': 0, 'RecipeCostVerified': True, 'RecipeOriginalResinCost': 60,
            'SafeCondensedCapacity': 5, 'CondensedCapacityObserved': False}
        native = {'task': 'domain-combat-rehearsal', 'status': 'combat_completed', 'evidenceVerified': True,
            'challengeCompleted': True, 'rewardClaimed': False, 'resinSpendEnabled': False,
            'shieldEvidence': 'hold_skill_cooldown_observed', 'observedHoldCasts': 2}
        probe = {'task': 'artifact-condensed-craft', 'status': 'skipped', 'evidenceVerified': True,
            'recipeCostVerified': True, 'recipeOriginalResinCost': 60, 'safeCondensedCapacity': 5,
            'condensedCapacityObserved': False, 'originalResinSpent': 0, 'condensedResinCreated': 0}
        lines = text.splitlines()
        lines[2] = '[AUTO_GAME_EVENT] ' + json.dumps(probe) + '\n[AUTO_GAME_EVENT] ' + json.dumps(native)
        self.text = '\n'.join(lines)
        wf.atomic_json(self.path, report)
        self.assertEqual(self.verify()['outcome'], 'completed')
        self.assertTrue(self.verify()['artifactFarming']['domainCombatValidated'])
        self.assertFalse(self.verify()['artifactFarming']['recipeInspection']['CondensedCapacityObserved'])
        self.text = self.text.replace('"recipeCostVerified": true', '"recipeCostVerified": false')
        self.assertEqual(self.verify()['outcome'], 'unknown')

    def craft_fixture(self, requested, created=None, *, legacy=False):
        created = requested if created is None else created
        config = copy.deepcopy(self.config)
        config['policy'].update(maxCrafts=requested, originalResinBudget=200, maxClaims=2)
        self.group = artifact.build_artifact_group('test-run', config, '2026-10-11',
            {'autoDomainConfig': {'reviveRetryCount': 1}}, bettergi_dir=self.bgi)
        self.path, report, text = fixture(self.bgi, 'test-run', self.group)
        before = snapshot(200, 0, '2026-10-11T16:00:00Z')
        after = snapshot(200 - created*60, created, '2026-10-11T16:01:00Z')
        native = {'Status': 'success', 'MainUiRestored': True, 'CondensedResinCreated': created,
            'OriginalResinSpent': created*60, 'OriginalResinBefore': 200, 'OriginalResinAfter': after['originalResin'],
            'CondensedResinBefore': 0, 'CondensedResinAfter': created}
        craft = {'stepId': 'test-run:step-1', 'type': 'craft', 'status': 'success',
            'startedAt': '2026-10-11T16:00:01Z', 'finishedAt': '2026-10-11T16:01:00Z',
            'before': before, 'after': after, 'nativeResult': native}
        if not legacy:
            craft.update(requestedCount=requested, craftBudget=requested*60, actualCreated=created, partialQuantity=created<requested)
        claim = report['steps'][0]
        claim.update(stepId='test-run:step-2', startedAt='2026-10-11T16:01:01Z', before=after,
            after=snapshot(after['originalResin'], created-1, '2026-10-11T16:02:00Z'))
        claim['parameterEvidence']['ArtifactStepId'] = claim['stepId']
        report['steps'] = [craft, claim]
        report['totals'].update(originalResinSpent=created*60, crafts=created)
        receipt = {'task': 'artifact-condensed-craft', 'status': 'success', 'evidenceVerified': True,
            'condensedResinCreated': created, 'originalResinSpent': created*60,
            'originalResinBefore': 200, 'originalResinAfter': after['originalResin'],
            'condensedResinBefore': 0, 'condensedResinAfter': created}
        lines = text.replace('test-run:step-1', 'test-run:step-2').splitlines()
        lines.insert(2, '[AUTO_GAME_EVENT] ' + json.dumps(receipt))
        wf.atomic_json(self.path, report)
        self.text, self.report = '\n'.join(lines), report

    def test_native_two_three_item_and_partial_batches_count_only_actual_created(self):
        for requested, created in ((2,2), (3,3), (3,2)):
            self.craft_fixture(requested, created)
            result = self.verify()
            self.assertEqual(result['outcome'], 'completed', result['warnings'])
            self.assertEqual(result['artifactFarming']['crafts'], created)
            self.assertEqual(result['artifactFarming']['originalResinSpent'], created*60)

    def test_batch_native_quantity_or_balance_conflicts_stay_unknown(self):
        self.craft_fixture(3)
        original = self.text
        self.text = original.replace('"condensedResinCreated": 3', '"condensedResinCreated": 2')
        self.assertEqual(self.verify()['outcome'], 'unknown')
        self.text = original
        report = copy.deepcopy(self.report)
        report['steps'][0]['after']['originalResin'] += 1
        wf.atomic_json(self.path, report)
        self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_old_single_item_record_stays_compatible_and_batch_request_cannot_exceed_budget(self):
        self.craft_fixture(1, legacy=True)
        self.assertEqual(self.verify()['outcome'], 'completed')
        self.craft_fixture(3)
        config = json.loads(self.group['Projects'][0]['JsScriptSettingsObject']['configJson'])
        config['policy']['originalResinBudget'] = 120
        self.group = artifact.build_artifact_group('test-run', config, '2026-10-11',
            {'autoDomainConfig': {'reviveRetryCount': 1}}, bettergi_dir=self.bgi)
        self.report['policy'] = config['policy']
        self.report['configSha256'] = artifact.config_hash(config)
        wf.atomic_json(self.path, self.report)
        self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_partial_verified_craft_records_subtotal_but_keeps_unknown_claim_and_budget_blocked(self):
        self.craft_fixture(1, legacy=True)
        report = copy.deepcopy(self.report)
        report['steps'][1].update(status='unknown')
        report['status'] = 'unknown'
        report['totals'].update(condensedResinSpent=0, claims=0)
        wf.atomic_json(self.path, report)
        self.text = self.text.replace('"status": "success", "evidenceVerified": true, "reportRelativePath"',
            '"status": "unknown", "evidenceVerified": true, "reportRelativePath"')
        analysis = self.verify()
        self.assertEqual(analysis['outcome'], 'unknown', analysis['warnings'])
        summary = analysis['artifactFarming']
        self.assertTrue(summary['reportVerified'])
        self.assertFalse(summary['allStepsVerified'])
        self.assertEqual(summary['verifiedStepIds'], ['test-run:step-1'])
        self.assertEqual(summary['unknownStepIds'], ['test-run:step-2'])
        directory = self.root / 'logs/runs/test-run'
        wf.atomic_json(directory / 'artifact-farming-report.json', report)
        lease = {'runId': 'test-run', 'gameDate': '2026-10-11', 'scopeId': report['policy']['scopeId'],
            'configSha256': report['configSha256'], 'status': 'unknown',
            'originalResinSpent': None, 'condensedResinSpent': None, 'crafts': None}
        ledger_path = self.root / 'state/artifact-checkpoints/2026-10-11.json'
        wf.atomic_json(ledger_path, {'schemaVersion': 1, 'gameDate': '2026-10-11', 'runs': [lease]})
        # Compatibility path: the old process summary does not yet contain step IDs.
        legacy_summary = {key: value for key, value in summary.items() if key not in ('verifiedStepIds', 'unknownStepIds')}
        row = artifact.finalize_artifact_checkpoint(self.root, lease, legacy_summary, launch_attempted=True)
        self.assertEqual(row['status'], 'unknown')
        self.assertIsNone(row['originalResinSpent'])
        self.assertIsNone(row['condensedResinSpent'])
        self.assertEqual(row['confirmedSubtotals'], {'originalResinSpent': 60, 'condensedResinSpent': 0, 'crafts': 1, 'claims': 0})
        self.assertEqual(row['unknownStepIds'], ['test-run:step-2'])
        self.assertFalse(artifact._ledger_row_resolved(self.root, row))
        with self.assertRaisesRegex(ValueError, 'cannot be refunded'):
            artifact.finalize_artifact_checkpoint(self.root, lease, {}, launch_attempted=False)


class ArtifactWorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        raw = json.loads((ROOT / 'config/artifact-farming.example.json').read_text(encoding='utf-8'))
        wf.atomic_json(self.root / 'config/artifact-farming.json', raw)
        global_path = self.root / 'BetterGI/User/config.json'
        global_config = wf.read_json(global_path)
        global_config.setdefault('autoDomainConfig', {})['reviveRetryCount'] = 1
        wf.atomic_json(global_path, global_config)
        model_fixture(self.root / 'BetterGI')

    def test_dry_run_uses_shared_host_and_never_checkin_deploy_or_authorize(self):
        args = argparse.Namespace(root=str(self.root), dry_run=True, task=None, profile='artifact-farming',
            timeout_minutes=0, no_delay=True, allow_repeat=False, keep_game=False, allow_existing_game=False,
            graphics_check=False)
        stream = io.StringIO()
        host = FakeHost(self.root)
        with contextlib.redirect_stdout(stream), patch.object(wf, 'datetime', FixedClock), \
                patch('checkin_hoyolab.execute_hoyolab_checkin', side_effect=AssertionError('must skip sign-in')):
            code = wf.execute(args, host)
        result = wf.read_json(json.loads(stream.getvalue())['resultPath'])
        self.assertEqual(code, 0, result)
        self.assertEqual(result['expectedTasks'], [artifact.TASK_NAME])
        self.assertFalse(host.launched)
        self.assertFalse((self.root / 'state/artifact-checkpoints').exists())
        self.assertFalse((self.root / 'BetterGI/User/JsScript').exists())
        self.assertEqual(self.base_path.read_bytes(), self.before)


class ExplicitNoConsumptionReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('explicit-artifact-review-' + uuid4().hex[:10])
        self.bgi = self.root / 'fake-bgi'
        self.run_id, self.probe_id = 'failed-validation', 'fresh-resin-probe'
        self.config = configuration()
        self.config['policy'].update(validationOnly=True, domainValidated=False, maxClaims=1,
            originalResinBudget=0, condensedResinBudget=0, maxCrafts=0, craftingValidated=False)
        group = artifact.build_artifact_group(self.run_id, self.config, '2026-10-11',
            {'autoDomainConfig': {'reviveRetryCount': 1}}, bettergi_dir=self.bgi)
        settings = group['Projects'][0]['JsScriptSettingsObject']
        self.directory = self.root / 'logs/runs' / self.run_id
        wf.atomic_json(self.directory / 'artifact-farming-group.json', group)
        identity = {}
        for name in ('main.js', 'operator.js'):
            content = (ROOT / 'bgi-scripts' / artifact.PLUGIN_NAME / name).read_bytes()
            for base in (self.bgi / 'User/JsScript' / artifact.PLUGIN_NAME, self.root / 'bgi-scripts' / artifact.PLUGIN_NAME):
                base.mkdir(parents=True, exist_ok=True)
                (base / name).write_bytes(content)
            identity[name] = hashlib.sha256(content).hexdigest()
        self.result_path = self.directory / 'result.json'
        wf.atomic_json(self.result_path, {'runId': self.run_id, 'gameDate': '2026-10-11', 'outcome': 'unknown',
            'finishedAt': '2026-10-11T16:00:20Z', 'artifactPlugin': {'verified': True, 'sha256': identity}})
        self.report_path = self.bgi / 'User/JsScript' / artifact.PLUGIN_NAME / 'record' / (self.run_id + '.json')
        self.report = {'schemaVersion': 1, 'runId': self.run_id, 'mode': artifact.MODE, 'gameDate': '2026-10-11',
            'configSha256': settings['configSha256'], 'target': self.config['target'], 'policy': self.config['policy'],
            'status': 'unknown', 'targetReached': False, 'steps': [], 'recipeInspection': None,
            'totals': {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0},
            'reason': "识别合成库存失败：原粹='98160' (98)，浓缩='0' (0)",
            'startedAt': '2026-10-11T16:00:00Z', 'finishedAt': '2026-10-11T16:00:20Z',
            'initialResinObservation': snapshot(98, 0, '2026-10-11T16:00:01Z')}
        wf.atomic_json(self.report_path, self.report)
        plugin = {'task': artifact.TASK_NAME, 'runId': self.run_id, 'mode': artifact.MODE, 'status': 'unknown', 'completedClaims': 0}
        self.log = '参数指定的一条龙配置：AutoGame_' + self.run_id + '\n配置组任务执行: 1/1\n[AUTO_GAME_EVENT] ' + json.dumps(plugin)
        (self.directory / 'bettergi.log').write_text(self.log, encoding='utf-8')
        self.probe_dir = self.root / 'logs/runs' / self.probe_id
        self.current = {**snapshot(98, 0, '2026-10-11T16:00:30Z'), 'verified': True, 'source': 'stable_map_ocr'}
        wf.atomic_json(self.probe_dir / 'result.json', {'runId': self.probe_id, 'gameDate': '2026-10-11',
            'finishedAt': '2026-10-11T16:00:31Z', 'cultivationResinCheck': True, 'cultivation': {'reportVerified': True}})
        wf.atomic_json(self.probe_dir / 'cultivation-report.json', {'runId': self.probe_id, 'mode': 'scan', 'readOnly': True,
            'steps': [], 'metadata': {'diagnostic': 'resin-only'}, 'resinObservation': self.current})
        (self.probe_dir / 'bettergi.log').write_text('[CULTIVATION_RESIN_OBSERVATION] ' + json.dumps(self.current), encoding='utf-8')
        self.ledger_path = self.root / 'state/artifact-checkpoints/2026-10-11.json'
        wf.atomic_json(self.ledger_path, {'schemaVersion': 1, 'gameDate': '2026-10-11', 'runs': [{
            'runId': self.run_id, 'scopeId': self.config['policy']['scopeId'], 'gameDate': '2026-10-11',
            'configSha256': settings['configSha256'], 'status': 'unknown', 'originalResinSpent': None,
            'condensedResinSpent': None, 'crafts': None}]})
        self.now = datetime(2026, 10, 11, 16, 0, 40, tzinfo=timezone.utc)

    def review(self, apply=False, now=None):
        return artifact.reconcile_validation_no_consumption(self.root, self.bgi, self.run_id, self.probe_id,
            reviewed_by='root-agent', apply=apply, now=now or self.now)

    def test_explicit_empty_validation_review_preserves_unknown_and_zero_cost_resolution(self):
        originals = {path: path.read_bytes() for path in (self.result_path, self.report_path, self.directory / 'bettergi.log')}
        before = self.ledger_path.read_bytes()
        self.assertEqual(self.review()['verdict'], 'resolved-no-consumption')
        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.review(apply=True)
        row = wf.read_json(self.ledger_path)['runs'][0]
        self.assertEqual(row['status'], 'resolved-no-consumption')
        self.assertEqual(row['originalStatus'], 'unknown')
        self.assertEqual(row['originalResinSpent'], 0)
        self.assertTrue(artifact._ledger_row_resolved(self.root, row))
        for path, content in originals.items(): self.assertEqual(path.read_bytes(), content)

    def test_paid_or_any_unknown_step_and_ambiguous_log_are_rejected(self):
        before = self.ledger_path.read_bytes()
        for change in ({'steps': [{'status': 'unknown'}]}, {'reason': 'after-submit inventory unknown'},
                       {'recipeInspection': {'Status': 'success'}}):
            wf.atomic_json(self.report_path, {**self.report, **change})
            with self.assertRaises(ValueError): self.review(apply=True)
            self.assertEqual(self.ledger_path.read_bytes(), before)
        wf.atomic_json(self.report_path, self.report)
        (self.directory / 'bettergi.log').write_text(self.log + '\n[AUTO_GAME_EVENT] {"task":"artifact-domain-claim"}', encoding='utf-8')
        with self.assertRaises(ValueError): self.review(apply=True)
        self.assertEqual(self.ledger_path.read_bytes(), before)

    def test_stale_probe_and_actual_balance_decrease_are_rejected(self):
        with self.assertRaises(ValueError):
            self.review(now=datetime(2026, 10, 11, 16, 3, 0, tzinfo=timezone.utc))
        self.current['originalResin'] = 97
        wf.atomic_json(self.probe_dir / 'cultivation-report.json', {'runId': self.probe_id, 'mode': 'scan', 'readOnly': True,
            'steps': [], 'metadata': {'diagnostic': 'resin-only'}, 'resinObservation': self.current})
        (self.probe_dir / 'bettergi.log').write_text('[CULTIVATION_RESIN_OBSERVATION] ' + json.dumps(self.current), encoding='utf-8')
        with self.assertRaises(ValueError): self.review(apply=True)

    def test_even_zero_budget_paid_mode_cannot_use_validation_only_review(self):
        path = self.directory / 'artifact-farming-group.json'
        group = wf.read_json(path)
        settings = group['Projects'][0]['JsScriptSettingsObject']
        paid = copy.deepcopy(self.config)
        paid['policy'].update(validationOnly=False, domainValidated=True)
        settings['configJson'] = json.dumps(paid)
        settings['configSha256'] = artifact.config_hash(paid)
        wf.atomic_json(path, group)
        before = self.ledger_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'only terminal unknown zero-budget validation'):
            self.review(apply=True)
        self.assertEqual(self.ledger_path.read_bytes(), before)

    def test_unreviewed_resolved_status_does_not_clear_unknown_replay_guard(self):
        row = wf.read_json(self.ledger_path)['runs'][0]
        row.update(status='resolved-no-consumption', originalStatus='unknown', originalResinSpent=0,
            condensedResinSpent=0, crafts=0)
        self.assertFalse(artifact._ledger_row_resolved(self.root, row))


class ExplicitHumanNewBatchTests(unittest.TestCase):
    def setUp(self):
        case = ArtifactTests()
        case.setUp()
        case.craft_fixture(1, legacy=True)
        self.root, self.bgi, self.source_id = case.root, case.bgi, 'test-run'
        report = copy.deepcopy(case.report)
        report.update(status='unknown')
        report['steps'][1]['status'] = 'unknown'
        report['totals'].update(condensedResinSpent=0, claims=0)
        wf.atomic_json(case.path, report)
        directory = self.root / 'logs/runs/test-run'
        self.old_config = json.loads(case.group['Projects'][0]['JsScriptSettingsObject']['configJson'])
        wf.atomic_json(directory / 'artifact-farming-report.json', report)
        wf.atomic_json(directory / 'artifact-farming-group.json', case.group)
        wf.atomic_json(directory / 'result.json', {'runId': 'test-run', 'outcome': 'unknown'})
        (directory / 'bettergi.log').write_text(case.text, encoding='utf-8')
        self.row = {'runId': 'test-run', 'gameDate': '2026-10-11', 'scopeId': report['policy']['scopeId'],
            'configSha256': report['configSha256'], 'status': 'unknown', 'originalResinSpent': None,
            'condensedResinSpent': None, 'crafts': None, 'confirmedSubtotals': report['totals'],
            'confirmedSubtotalOnly': True, 'unknownStepOutcomeUnresolved': True,
            'unknownStepIds': ['test-run:step-2']}
        self.ledger_path = self.root / 'state/artifact-checkpoints/2026-10-11.json'
        wf.atomic_json(self.ledger_path, {'schemaVersion': 1, 'gameDate': '2026-10-11', 'runs': [self.row]})
        self.until = '2026-10-12T00:05:00Z'
        wf.atomic_json(self.root / 'state/artifact-authorizations' / (report['policy']['scopeId'] + '.json'),
            artifact.build_artifact_authorization(self.old_config, '2026-10-11T16:00:00Z', self.until))
        self.probe_id = 'fresh-probe'
        probe_dir = self.root / 'logs/runs' / self.probe_id
        self.observation = {**snapshot(42, 1, '2026-10-11T16:05:00Z'), 'verified': True, 'source': 'stable_map_ocr'}
        wf.atomic_json(probe_dir / 'result.json', {'runId': self.probe_id, 'gameDate': '2026-10-11',
            'finishedAt': '2026-10-11T16:05:01Z', 'cultivationResinCheck': True, 'cultivation': {'reportVerified': True}})
        wf.atomic_json(probe_dir / 'cultivation-report.json', {'runId': self.probe_id, 'mode': 'scan', 'readOnly': True,
            'steps': [], 'metadata': {'diagnostic': 'resin-only'}, 'resinObservation': self.observation})
        event = {'task': '培养材料', 'runId': self.probe_id, 'mode': 'scan', 'readOnly': True, 'completedSteps': 0}
        (probe_dir / 'bettergi.log').write_text('参数指定的一条龙配置：AutoGame_' + self.probe_id
            + '\n[CULTIVATION_RESIN_OBSERVATION] ' + json.dumps(self.observation)
            + '\n[AUTO_GAME_EVENT] ' + json.dumps(event), encoding='utf-8')
        self.now = datetime(2026, 10, 11, 16, 5, 10, tzinfo=timezone.utc)
        self.approved = '2026-10-11T16:05:00Z'
        self.source_bytes = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}

    def new_config(self, scope='new-human-scope-a'):
        config = copy.deepcopy(self.old_config)
        config['policy'].update(scopeId=scope, originalResinBudget=200, condensedResinBudget=5, maxCrafts=3)
        return config

    def review(self, scope='new-human-scope-a', *, apply=True, **changes):
        args = {'approved_at': self.approved, 'valid_until': self.until,
            'approval_text': '允许新建批次继续，保留原未知记录', 'reviewed_by': 'root-agent', 'apply': apply, 'now': self.now}
        args.update(changes)
        return artifact.review_explicit_artifact_new_batch(self.root, self.new_config(scope), self.source_id,
            self.probe_id, **args)

    def test_distinct_new_scope_examples_bind_fresh_caps_without_touching_old_unknown(self):
        for scope in ('new-human-scope-a', 'new-human-scope-b'):
            reviewed = self.review(scope, apply=False)
            self.assertEqual(reviewed['config']['policy']['originalResinBudget'], 42)
            self.assertEqual(reviewed['config']['policy']['condensedResinBudget'], 1)
            self.assertEqual(reviewed['config']['policy']['maxCrafts'], 0)
            self.assertEqual(reviewed['continuationReview']['assignedRunId'], None)
        reviewed = self.review()
        _, lease = artifact.constrain_artifact_authorization(self.root, reviewed['config'], 'new-run-a',
            '2026-10-11', assign=True, now=self.now)
        self.assertEqual(lease['preservedUnknownRunIds'], ['test-run'])
        self.assertNotEqual(lease['runId'], 'test-run')
        self.assertNotEqual(lease['runId'] + ':step-1', 'test-run:step-2')
        self.assertEqual(wf.read_json(self.ledger_path)['runs'][0], self.row)
        for path, content in self.source_bytes.items(): self.assertEqual(path.read_bytes(), content)

    def test_missing_human_reply_expiry_extension_or_stale_balance_remain_blocked(self):
        for change in ({'approval_text': '继续'}, {'valid_until': '2026-10-12T01:11:48Z'},
                       {'now': datetime(2026, 10, 11, 16, 8, tzinfo=timezone.utc)}):
            with self.assertRaises(ValueError): self.review(**change)
        config = self.new_config()
        wf.atomic_json(self.root / 'state/artifact-authorizations' / (config['policy']['scopeId'] + '.json'),
            artifact.build_artifact_authorization(config, self.approved, self.until))
        with self.assertRaisesRegex(ValueError, 'no explicit human'):
            artifact.constrain_artifact_authorization(self.root, config, 'new-run-a', '2026-10-11', now=self.now)

    def test_permission_is_one_new_run_only_and_cannot_cover_next_unknown_or_other_scope(self):
        reviewed = self.review()
        _, lease = artifact.constrain_artifact_authorization(self.root, reviewed['config'], 'new-run-a',
            '2026-10-11', assign=True, now=self.now)
        with self.assertRaises(ValueError):
            artifact.constrain_artifact_authorization(self.root, reviewed['config'], 'new-run-b', '2026-10-11', now=self.now)
        with self.assertRaises(ValueError): self.review('new-human-scope-b')
        artifact.finalize_artifact_checkpoint(self.root, lease, {'reportVerified': True, 'allStepsVerified': True,
            'originalResinSpent': 20, 'condensedResinSpent': 1, 'crafts': 0}, launch_attempted=True)
        with self.assertRaisesRegex(ValueError, 'consumed'):
            artifact.constrain_artifact_authorization(self.root, reviewed['config'], 'new-run-b', '2026-10-11', now=self.now)
        with self.assertRaisesRegex(ValueError, 'single human permission'):
            self.review('new-human-scope-b')

    def test_source_fingerprint_change_and_reusing_unknown_run_id_are_rejected(self):
        reviewed = self.review()
        with self.assertRaises(ValueError):
            artifact.constrain_artifact_authorization(self.root, reviewed['config'], 'test-run', '2026-10-11', now=self.now)
        path = next(iter(self.source_bytes))
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            artifact.constrain_artifact_authorization(self.root, reviewed['config'], 'new-run-a', '2026-10-11', now=self.now)
