"""Synthetic diagnostic evidence and fake workflow processes, never a game run."""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import combat_rehearsal as rehearsal
from tests import test_workflow as workflow_tests
from tests.test_workflow import FakeHost, FakeProcess, FixedClock, wf

ROOT = Path(__file__).resolve().parents[1]


def report_fixture(bgi, run_id, group):
    settings = group['Projects'][0]['JsScriptSettingsObject']
    parameters = {'DomainRoundNum': 1, 'DomainName': settings['domainName'], 'PartyName': settings['partyName'],
        'CombatStrategyPath': str((bgi / 'User/AutoFight/木偶星超导.txt').resolve()),
        'CombatOnly': True, 'RequireZhongliShieldCast': True, 'SpecifyResinUse': True,
        'ResinPriorityList': [], 'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 0,
        'OriginalResin40UseCount': 0, 'CondensedResinUseCount': 0, 'FragileResinUseCount': 0,
        'TransientResinUseCount': 0, 'AutoArtifactSalvage': False, 'RewardRecognitionEnabled': False}
    report = {'schemaVersion': 1, 'runId': run_id, 'mode': 'combat-rehearsal', 'status': 'success',
        'parameterEvidence': parameters, 'startedAt': '2026-10-09T00:00:00Z',
        'finishedAt': '2026-10-09T00:01:00Z', 'noRewardClaim': True, 'targetReached': False,
        'rewards': {}, 'nativeReturnCompleted': True}
    path = bgi / 'User/JsScript/AutoGameCombatRehearsal/record' / (run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding='utf-8')
    return path, report


def event_lines(run_id):
    native = {'task': 'domain-combat-rehearsal', 'status': 'combat_completed', 'evidenceVerified': True,
        'challengeCompleted': True, 'rewardClaimed': False, 'resinSpendEnabled': False,
        'observedHoldCasts': 2, 'shieldEvidence': 'hold_skill_cooldown_observed'}
    plugin = {'task': '战斗演练', 'runId': run_id, 'status': 'success', 'evidenceVerified': True,
        'mode': 'combat-rehearsal', 'reportRelativePath': f'record/{run_id}.json',
        'noRewardClaim': True, 'targetReached': False}
    return '[AUTO_GAME_EVENT] ' + json.dumps(native), '[AUTO_GAME_EVENT] ' + json.dumps(plugin)


def log_fixture(run_id, config_name='AutoGame_test'):
    native, plugin = event_lines(run_id)
    return '\n'.join([f'参数指定的一条龙配置：{config_name}', '配置组任务执行: 1/1',
                       native, plugin, '一条龙和配置组任务结束'])


class CombatEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('combat-evidence-' + uuid4().hex[:10])
        self.bgi = self.root / 'fake-bgi'
        self.group = rehearsal.build_combat_rehearsal_group('test-run', {'policy': {'domainPartyName': 'Test party'}})
        self.path, self.report = report_fixture(self.bgi, 'test-run', self.group)
        self.text = log_fixture('test-run')

    def verify(self, text=None, outcome='exited'):
        return rehearsal.verify_combat_rehearsal_analysis(text or self.text, self.bgi, 'test-run', self.group,
                                                        'AutoGame_test', outcome)

    def test_joint_native_plugin_parameter_proof_completes_only_combat(self):
        analysis = self.verify()
        self.assertEqual(analysis['outcome'], 'completed')
        self.assertEqual(analysis['tasks'][0]['status'], 'success')
        self.assertTrue(analysis['combatRehearsal']['reportVerified'])
        self.assertFalse(analysis['combatRehearsal']['targetReached'])
        self.assertEqual(analysis['rewards'], {})
        self.assertEqual(analysis['resinEvents'], [])
        self.assertIsNone(analysis['cultivation'])
        self.assertEqual(self.verify(outcome='running')['outcome'], 'partial')

    def test_js_success_without_native_or_multiple_native_events_stays_unknown(self):
        native, _ = event_lines('test-run')
        for text in (self.text.replace(native + '\n', ''), self.text.replace(native, native + '\n' + native)):
            self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_wrong_run_config_group_and_contradictory_claim_fail_closed(self):
        native, plugin = event_lines('test-run')
        variants = [self.text.replace('AutoGame_test', 'AutoGame_foreign'),
            self.text.replace('配置组任务执行: 1/1', '配置组任务执行: 1/2'),
            self.text + '\n配置组任务执行: 1/1', self.text.replace(plugin, plugin.replace('test-run', 'other-run')),
            self.text.replace('"rewardClaimed": false', '"rewardClaimed": true'),
            self.text.replace('"resinSpendEnabled": false', '"resinSpendEnabled": true'),
            self.text.replace('"observedHoldCasts": 2', '"observedHoldCasts": 0'),
            self.text.replace('"observedHoldCasts": 2', '"observedHoldCasts": true'),
            self.text.replace('hold_skill_cooldown_observed', 'not_requested'),
            self.text + '\n已使用 1 个脆弱树脂', self.text + '\n奖励领取成功',
            self.text + '\n任务执行失败',
            self.text + '\n[AUTO_GAME_EVENT] {broken']
        for text in variants:
            with self.subTest(text=text):
                self.assertEqual(self.verify(text)['outcome'], 'unknown')

    def test_report_actual_native_parameters_and_no_reward_claim_cannot_be_faked(self):
        variants = []
        for field, value in (('CombatOnly', False), ('RequireZhongliShieldCast', False),
            ('DomainRoundNum', 2), ('SpecifyResinUse', False), ('OriginalResinUseCount', 1),
            ('FragileResinUseCount', 1), ('ResinPriorityList', ['原粹树脂']), ('AutoArtifactSalvage', True),
            ('RewardRecognitionEnabled', True), ('CombatStrategyPath', 'another-strategy.txt')):
            report = copy.deepcopy(self.report)
            report['parameterEvidence'][field] = value
            variants.append(report)
        variants.extend([{**self.report, 'runId': 'other-run'}, {**self.report, 'mode': 'scan'},
            {**self.report, 'targetReached': True}, {**self.report, 'rewards': {'Material': 1}},
            {**self.report, 'noRewardClaim': False}, {**self.report, 'nativeReturnCompleted': False},
            {**self.report, 'finishedAt': '2026-10-09T00:06:00Z'}])
        for report in variants:
            self.path.write_text(json.dumps(report), encoding='utf-8')
            self.assertEqual(self.verify()['outcome'], 'unknown')
        self.path.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.verify()['outcome'], 'unknown')

    def test_failed_report_does_not_become_combat_success(self):
        native, plugin = event_lines('test-run')
        report = {**self.report, 'status': 'failed', 'nativeReturnCompleted': False}
        self.path.write_text(json.dumps(report), encoding='utf-8')
        text = self.text.replace(native + '\n', '').replace(plugin, plugin.replace('"success"', '"failed"'))
        analysis = self.verify(text)
        self.assertEqual(analysis['outcome'], 'failed')
        self.assertFalse(analysis['combatRehearsal']['challengeCompleted'])


class RehearsalFakeHost(FakeHost):
    def launch(self, exe, name):
        self.launched = True
        self.process = FakeProcess()
        generated = wf.read_json(exe.parent / 'User/OneDragon' / (name + '.json'))
        group_name = next(value for key, value in generated['TaskDefinitions'].items() if generated['TaskEnabledList'][key])
        group = wf.read_json(exe.parent / 'User/ScriptGroup' / (group_name + '.json'))
        run_id = group['Projects'][0]['JsScriptSettingsObject']['runId']
        report_fixture(exe.parent, run_id, group)
        (exe.parent / 'log/new.log').write_text(log_fixture(run_id, name), encoding='utf-8')
        return self.process


class CombatWorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        wf.atomic_json(self.root / 'config/cultivation.json', {'policy': {'domainPartyName': 'Test party'}})
        for directory in (self.root / 'bgi-scripts/AutoGameCombatRehearsal',
                          self.root / 'BetterGI/User/JsScript/AutoGameCombatRehearsal'):
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'manifest.json').write_text('{}', encoding='utf-8')
            (directory / 'main.js').write_text('// retained fake package; never executes', encoding='utf-8')

    def run_rehearsal(self, dry=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=None, profile='combat-rehearsal',
            timeout_minutes=0, no_delay=True, allow_repeat=False, keep_game=False, allow_existing_game=False,
            graphics_check=False)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), patch.object(wf, 'datetime', FixedClock), \
                patch('checkin_hoyolab.execute_hoyolab_checkin', side_effect=AssertionError('checkin must not run')):
            code = wf.execute(args, RehearsalFakeHost(self.root))
        return code, wf.read_json(json.loads(stream.getvalue())['resultPath'])

    def test_dry_run_is_only_combat_and_preserves_original_authorization(self):
        receipt = self.root / 'state/cultivation-authorization.json'
        wf.atomic_json(receipt, {'originalResinCap': 60, 'unknownReservation': 40})
        before = receipt.read_bytes()
        code, result = self.run_rehearsal(dry=True)
        self.assertEqual(code, 0)
        self.assertEqual(result['expectedTasks'], ['战斗演练'])
        self.assertEqual(result['timeBudget']['maximumMinutes'], 8)
        self.assertNotIn('cultivationAuthorization', result)
        self.assertNotIn('hoyolabCheckin', result)
        generated = wf.read_json(result['plannedConfig'])
        self.assertTrue(generated['SkipFinalRewardCheck'])
        self.assertEqual(sum(generated['TaskEnabledList'].values()), 1)
        group = wf.read_json(Path(result['plannedConfig']).parent / 'combat-rehearsal-group.json')
        settings = group['Projects'][0]['JsScriptSettingsObject']
        self.assertEqual(settings['partyName'], 'Test party')
        self.assertEqual(settings['maxMinutes'], 5)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertEqual(self.base_path.read_bytes(), self.before)

    def test_fake_live_completion_archives_independent_combat_report(self):
        code, result = self.run_rehearsal()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'completed')
        self.assertEqual(result['mode'], 'combat-rehearsal')
        self.assertEqual(result['tasks'][0]['name'], '战斗演练')
        self.assertEqual(result['rewards'], {})
        self.assertEqual(result['resinEvents'], [])
        self.assertTrue(result['combatRehearsal']['reportVerified'])
        self.assertFalse(result['combatRehearsal']['targetReached'])
        self.assertTrue((Path(result['logArchive']) / 'combat-rehearsal-report.json').is_file())
        self.assertNotIn('cultivationAuthorization', result)
        self.assertNotIn('hoyolabCheckin', result)
        self.assertEqual(self.base_path.read_bytes(), self.before)

    def test_rehearsal_total_budget_cannot_exceed_eight_minutes(self):
        self.assertEqual(wf.time_budget(self.cfg, None, 'combat-rehearsal')['maximumMinutes'], 8)
        with self.assertRaises(wf.WorkflowError):
            wf.time_budget(self.cfg, None, 'combat-rehearsal', 9)

    def test_live_rehearsal_requires_previously_deployed_matching_package(self):
        path = self.root / 'BetterGI/User/JsScript/AutoGameCombatRehearsal/main.js'
        path.write_text('// changed fake package', encoding='utf-8')
        code, result = self.run_rehearsal()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['outcome'], 'failed')
        self.assertTrue(any('deployed plugin differs' in value for value in result['errors']))
        self.assertNotIn('runtimeCombatRehearsalGroup', result)


if __name__ == '__main__':
    unittest.main()
