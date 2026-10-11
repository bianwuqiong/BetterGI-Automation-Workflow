"""Offline tests for the runner/plugin evidence boundary; fixtures are retained."""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests import test_workflow as tw
from tests import test_cultivation as tc
import cultivation as helper
import checkin_hoyolab as checkin_module

wf = tw.wf
ROOT = Path(__file__).resolve().parents[1]


class CultivationFakeHost(tw.FakeHost):
    def __init__(self, root, report_factory, *, report_change=None, missing=False, mixed=False):
        super().__init__(root)
        self.report_factory = report_factory
        self.report_change = report_change
        self.missing = missing
        self.mixed = mixed
        self.group = None

    def launch(self, exe, name):
        self.launched = True
        self.process = tw.FakeProcess()
        runtime = wf.read_json(exe.parent / "User/OneDragon" / (name + ".json"))
        group_name = runtime["TaskDefinitions"]["auto-game-cultivation"]
        self.group = wf.read_json(exe.parent / "User/ScriptGroup" / (group_name + ".json"))
        settings = self.group["Projects"][0]["JsScriptSettingsObject"]
        run_id, mode = settings["runId"], settings["mode"]
        report = self.report_factory(mode)
        if settings.get('resinDiagnosticOnly'):
            report.update(profile=None, inventory={}, plan=None, blockers=[], warnings=[], steps=[],
                requiredScanIds=[], manualInventoryIds=[], status='unknown',
                resinObservation={'originalResin': None, 'condensedResin': None,
                                  'verified': False, 'mainUiRestored': False})
        report.update(runId=run_id, target=json.loads(settings["targetConfigJson"]),
                      policy=json.loads(settings["policyJson"]))
        for index, step in enumerate(report["steps"], 1):
            step["stepId"] = f"{run_id}:step-{index}"
        if self.report_change:
            self.report_change(report)
        if not self.missing:
            report_path = exe.parent / "User/JsScript/AutoGameCultivation/record" / (run_id + ".json")
            wf.atomic_json(report_path, report)
        event = {"task": "培养材料", "runId": run_id, "mode": mode, "status": "success",
            "evidenceVerified": True, "readOnly": mode == "scan", "targetReached": False,
            "reportRelativePath": "record/" + run_id + ".json",
            "completedSteps": len(report["steps"])}
        if settings.get('resinDiagnosticOnly'):
            event['status'] = 'unknown'
        lines = ["参数指定的一条龙配置：" + name]
        if self.mixed:
            lines.extend(["一条龙任务执行: 1/2",
                '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}'])
        lines.extend(["配置组任务执行: 1/1", "[AUTO_GAME_EVENT] " + json.dumps(event, ensure_ascii=False)])
        if self.mixed:
            lines.extend(["一条龙任务执行: 2/2", "检查每日奖励结果：今日奖励已领取"])
        lines.append("一条龙和配置组任务结束")
        (exe.parent / "log/new.log").write_text("\n".join(lines), encoding="utf-8")
        return self.process


class CultivationWorkflowTests(unittest.TestCase):
    def test_evidence_packet_retains_partial_subtotal_and_uncertain_total(self):
        cultivation = {'configuredConfirmedClaims': {'original': 20, 'condensed': 0},
            'actualResinDelta': None, 'confirmedSubtotalOnly': True,
            'verifiedStepResinDelta': {'original': 20, 'condensed': 0},
            'verifiedStepIds': ['test-run:step-1'], 'unverifiedStepIds': ['test-run:step-2'],
            'observedGains': {'104320': 2}}
        packet = wf.packet_for({'runId': 'test-run', 'outcome': 'unknown', 'cultivation': cultivation})
        for key, value in cultivation.items():
            self.assertEqual(packet['cultivation'][key], value)

    def setUp(self):
        # Composition keeps the original 47 tests out of this test case.
        self.fixture = tw.WorkflowTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.cfg = copy.deepcopy(self.fixture.cfg)
        self.cfg.update(checkpointOnly=False, resumeVerifiedTasks=False)
        wf.atomic_json(self.root / "config/settings.json", self.cfg)
        self.config = {"target": copy.deepcopy(tc.TARGET), "policy": {}, "executionEnabled": False}
        wf.atomic_json(self.root / "config/cultivation.json", self.config)
        self.global_path = self.root / "BetterGI/User/config.json"
        global_config = wf.read_json(self.global_path)
        global_config["autoDomainConfig"]["reviveRetryCount"] = 1
        wf.atomic_json(self.global_path, global_config)
        self.global_before = self.global_path.read_bytes()
        self.report_fixture = tc.CultivationTests()

    def source_package(self):
        destination = self.root / "bgi-scripts/AutoGameCultivation"
        shutil.copytree(ROOT / "bgi-scripts/AutoGameCultivation", destination)
        return destination

    def make_report(self, mode):
        return (self.report_fixture.report(mode) if mode == "scan"
                else self.report_fixture.execution_report())

    def run_flow(self, *, dry=False, mode="scan", profile="cultivation", task=None, host=None, resin_check=False, graphics_check=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=task, profile=profile,
            cultivation_mode=mode, timeout_minutes=1, no_delay=True, allow_repeat=False,
            keep_game=False, allow_existing_game=False, graphics_check=graphics_check,
            cultivation_resin_check=resin_check)
        host = host or CultivationFakeHost(self.root, self.make_report)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(wf, "datetime", tw.FixedClock):
            code = wf.execute(args, host)
        summary = json.loads(output.getvalue())
        return code, wf.read_json(summary["resultPath"]), host

    def test_dry_scan_has_no_checkin_install_or_production_mutation(self):
        host = CultivationFakeHost(self.root, self.make_report)
        with patch.object(checkin_module, "execute_hoyolab_checkin") as checkin, patch.object(helper, "install_cultivation_plugin") as install:
            code, result, _ = self.run_flow(dry=True, host=host)
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "planned")
        self.assertEqual(result["expectedTasks"], ["培养材料"])
        self.assertFalse(host.launched)
        checkin.assert_not_called()
        install.assert_not_called()
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)
        self.assertEqual(self.global_path.read_bytes(), self.global_before)
        self.assertEqual(len(list(self.fixture.base_path.parent.glob("*.json"))), 1)
        self.assertFalse((self.root / "BetterGI/User/JsScript/AutoGameCultivation").exists())
        self.assertFalse((self.root / "BetterGI/User/ScriptGroup").exists())
        planned = wf.read_json(result["plannedConfig"])
        self.assertIs(planned["SkipFinalRewardCheck"], True)
        group = wf.read_json(Path(result["resultPath"]).parent / "cultivation-group.json")
        self.assertEqual(planned["TaskDefinitions"]["auto-game-cultivation"], group["Name"])
        self.assertEqual(group["Projects"][0]["JsScriptSettingsObject"]["mode"], "scan")

    def test_resin_probe_dry_run_is_single_read_only_node_and_no_persistent_mutation(self):
        before = (self.root / 'config/cultivation.json').read_bytes()
        with patch.object(checkin_module, 'execute_hoyolab_checkin') as checkin, patch.object(helper, 'install_cultivation_plugin') as install:
            code, result, host = self.run_flow(dry=True, resin_check=True)
        self.assertEqual(code, 0)
        self.assertFalse(host.launched)
        self.assertIs(result['cultivationResinCheck'], True)
        self.assertEqual(result['expectedTasks'], ['培养材料'])
        planned = wf.read_json(result['plannedConfig'])
        self.assertIs(planned['SkipFinalRewardCheck'], True)
        self.assertEqual(planned['CompletionAction'], '关闭游戏和软件')
        enabled = [key for key, value in planned['TaskEnabledList'].items() if value]
        self.assertEqual(enabled, ['auto-game-cultivation'])
        group = wf.read_json(Path(result['resultPath']).parent / 'cultivation-group.json')
        settings = group['Projects'][0]['JsScriptSettingsObject']
        self.assertIs(settings['resinDiagnosticOnly'], True)
        self.assertEqual(settings['mode'], 'scan')
        self.assertEqual((self.root / 'config/cultivation.json').read_bytes(), before)
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)
        self.assertFalse((self.root / 'state/cultivation-authorization.json').exists())
        checkin.assert_not_called()
        install.assert_not_called()

    def test_resin_probe_live_fake_archives_unknown_scan_without_claiming_material_success(self):
        self.source_package()
        with patch.object(checkin_module, 'execute_hoyolab_checkin') as checkin:
            code, result, host = self.run_flow(resin_check=True, task='培养材料', profile='core')
        self.assertTrue(host.launched)
        self.assertNotEqual(code, 0)
        self.assertEqual(result['outcome'], 'unknown')
        self.assertEqual(result['expectedTasks'], ['培养材料'])
        self.assertEqual(result['cultivation']['scope'], 'scan')
        self.assertIs(result['cultivation']['readOnly'], True)
        self.assertIs(result['cultivation']['reportVerified'], True)
        self.assertIs(result['cultivation']['targetReached'], False)
        report = wf.read_json(Path(result['resultPath']).parent / 'cultivation-report.json')
        self.assertIsNone(report['profile'])
        self.assertIsNone(report['plan'])
        self.assertEqual(report['steps'], [])
        self.assertEqual(report['inventory'], {})
        self.assertIn('resinObservation', report)
        self.assertEqual(result['resinEvents'], [])
        self.assertEqual(self.global_path.read_bytes(), self.global_before)
        checkin.assert_not_called()

    def test_resin_probe_rejects_execute_unrelated_tasks_and_graphics_check(self):
        self.config.update(executionEnabled=True, policy=copy.deepcopy(tc.POLICY))
        wf.atomic_json(self.root / 'config/cultivation.json', self.config)
        for options in ({'mode': 'execute'}, {'profile': 'core'}, {'task': '领取邮件'}, {'graphics_check': True}):
            with self.subTest(options=options):
                code, result, host = self.run_flow(dry=True, resin_check=True, **options)
                self.assertNotEqual(code, 0)
                self.assertFalse(host.launched)
                self.assertEqual(result['outcome'], 'failed')
                self.assertIn('只读探针', ' '.join(result['errors']))

    def test_execution_and_normal_profiles_keep_final_reward_check_without_mutating_template(self):
        self.config.update(executionEnabled=True, policy=copy.deepcopy(tc.POLICY))
        wf.atomic_json(self.root / "config/cultivation.json", self.config)
        for mode, profile, task in (("execute", "cultivation", None),
                                    ("scan", "core", None),
                                    ("scan", "configured", "合成树脂")):
            with self.subTest(mode=mode, profile=profile, task=task):
                code, result, host = self.run_flow(dry=True, mode=mode, profile=profile, task=task)
                self.assertEqual(code, 0)
                self.assertFalse(host.launched)
                self.assertIs(wf.read_json(result["plannedConfig"])["SkipFinalRewardCheck"], False)
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)

    def test_single_execute_cultivation_omits_mail_daily_and_keeps_twenty_original_budget(self):
        self.source_package()
        self.config.update(executionEnabled=True, policy={**tc.POLICY,
            'originalResinBudget': 20, 'condensedResinBudget': 0, 'maxSteps': 1})
        wf.atomic_json(self.root / 'config/cultivation.json', self.config)
        with patch.object(checkin_module, 'execute_hoyolab_checkin', return_value={'status': 'disabled'}):
            code, result, host = self.run_flow(mode='execute', task='培养材料')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'completed')
        self.assertEqual(result['expectedTasks'], ['培养材料'])
        self.assertEqual([task['name'] for task in result['tasks']], ['培养材料'])
        self.assertEqual(result['cultivation']['configuredConfirmedClaims'], {'original': 20, 'condensed': 0})
        self.assertFalse(result['cultivation']['targetReached'])
        policy = json.loads(host.group['Projects'][0]['JsScriptSettingsObject']['policyJson'])
        self.assertEqual(policy['originalResinBudget'], 20)
        self.assertEqual(policy['condensedResinBudget'], 0)
        self.assertEqual(policy['maxSteps'], 1)
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)

    def test_recorded_entry_limits_task_binding_to_cultivation_without_starting_game(self):
        source = ROOT / 'scripts/run_daily_recorded.ps1'
        command = ('$tokens=$null;$errors=$null;'
            f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{source}',[ref]$tokens,[ref]$errors);"
            'if($errors){throw $errors};'
            '$task=$ast.ParamBlock.Parameters|Where-Object {$_.Name.VariablePath.UserPath -eq "Task"};'
            '$validation=$task.Attributes|Where-Object {$_.TypeName.Name -eq "ValidateSet"};'
            '$validation.PositionalArguments.Value|ConvertTo-Json -Compress')
        parsed = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, timeout=15)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        self.assertEqual(json.loads(parsed.stdout.decode('utf-8-sig')), '培养材料')

    def test_bound_scan_report_completes_only_read_only_export(self):
        self.source_package()
        with patch.object(checkin_module, "execute_hoyolab_checkin") as checkin:
            code, result, host = self.run_flow()
        checkin.assert_not_called()
        self.assertEqual(code, 0)
        self.assertTrue(host.launched)
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["mode"], "cultivation-scan")
        self.assertEqual(result["executionOutcome"], "exited")
        self.assertEqual(result["cultivation"]["scope"], "scan")
        self.assertTrue(result["cultivation"]["readOnly"])
        self.assertFalse(result["cultivation"]["targetReached"])
        self.assertEqual(result["rewards"], {})
        self.assertEqual(result["resinEvents"], [])
        self.assertEqual(result["expectedTasks"], ["培养材料"])
        archived = wf.read_json(Path(result["resultPath"]).parent / "cultivation-report.json")
        self.assertEqual(archived["runId"], result["runId"])
        self.assertEqual(archived["target"], result["cultivationTarget"])
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)
        self.assertEqual(self.global_path.read_bytes(), self.global_before)

    def test_missing_report_never_promotes_successful_machine_claim(self):
        self.source_package()
        host = CultivationFakeHost(self.root, self.make_report, missing=True)
        with patch.object(checkin_module, "execute_hoyolab_checkin") as checkin:
            code, result, _ = self.run_flow(host=host)
        checkin.assert_not_called()
        self.assertNotEqual(code, 0)
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertFalse((Path(result["resultPath"]).parent / "cultivation-report.json").exists())

    def test_wrong_run_report_is_not_archived_or_promoted(self):
        self.source_package()
        host = CultivationFakeHost(self.root, self.make_report,
            report_change=lambda report: report.update(runId="foreign-run"))
        code, result, _ = self.run_flow(host=host)
        self.assertNotEqual(code, 0)
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertIsNone(result.get("cultivation"))
        self.assertFalse((Path(result["resultPath"]).parent / "cultivation-report.json").exists())

    def test_execute_is_disabled_before_launch_or_install(self):
        host = CultivationFakeHost(self.root, self.make_report)
        with patch.object(helper, "install_cultivation_plugin") as install, patch.object(checkin_module, "execute_hoyolab_checkin") as checkin:
            code, result, _ = self.run_flow(mode="execute", host=host)
        self.assertNotEqual(code, 0)
        self.assertFalse(host.launched)
        self.assertEqual(result["outcome"], "failed")
        self.assertIn("executionEnabled", " ".join(result["errors"]))
        install.assert_not_called()
        checkin.assert_not_called()
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)

    def test_validation_ledger_is_required_before_any_launch(self):
        self.source_package()
        self.config.update(executionEnabled=True, policy={**tc.POLICY, 'validationMode': True,
            'domainValidated': False, 'originalResinBudget': 60, 'validationScopeId': 'first-validation'})
        wf.atomic_json(self.root / 'config/cultivation.json', self.config)
        code, result, host = self.run_flow(mode='execute', task='培养材料')
        self.assertNotEqual(code, 0)
        self.assertFalse(host.launched)
        self.assertIn('initial-validation evidence', ' '.join(result['errors']))

    def test_validation_assigns_before_launch_and_unknown_attempt_limits_next_runtime(self):
        self.source_package()
        self.config.update(executionEnabled=True, policy={**tc.POLICY, 'validationMode': True,
            'domainValidated': False, 'originalResinBudget': 60, 'validationScopeId': 'first-validation'})
        wf.atomic_json(self.root / 'config/cultivation.json', self.config)
        receipt_path = self.root / 'state/cultivation-authorization.json'
        wf.atomic_json(receipt_path, {'schemaVersion': 1, 'scopeId': 'first-validation',
            'gameDate': '2026-09-12', 'target': tc.TARGET, 'originalResinCap': 60,
            'condensedResinCap': 0, 'authorizedAtUTC': '2026-09-12T11:00:00Z',
            'purpose': 'initial-validation', 'assignedRunIds': []})
        def unknown(report):
            report['steps'][0].update(validationAttempt=True, status='unknown')
            report['status'] = 'unknown'
        host = CultivationFakeHost(self.root, self.make_report, report_change=unknown)
        ordinary_launch = host.launch
        def checked_launch(exe, name):
            receipt = wf.read_json(receipt_path)
            self.assertEqual(len(receipt['assignedRunIds']), 1)
            evidence = wf.read_json(self.root / 'logs/runs' / receipt['assignedRunIds'][0] / 'result.json')
            self.assertIs(evidence['cultivationLaunchAttempted'], True)
            return ordinary_launch(exe, name)
        host.launch = checked_launch
        code, first, _ = self.run_flow(mode='execute', task='培养材料', host=host)
        self.assertNotEqual(code, 0)
        self.assertEqual(first['cultivationAuthorization']['runtimeOriginalResinBudget'], 60)
        code, second, second_host = self.run_flow(mode='execute', task='培养材料')
        self.assertTrue(second_host.launched)
        self.assertEqual(second['cultivationAuthorization']['priorReservedOriginal'], 20)
        self.assertEqual(second['cultivationAuthorization']['runtimeOriginalResinBudget'], 40)
        settings = second_host.group['Projects'][0]['JsScriptSettingsObject']
        policy = json.loads(settings['policyJson'])
        self.assertEqual(policy['validationAttemptedSources'], ['domain'])
        self.assertEqual(policy['originalResinBudget'], 40)
        self.assertFalse(policy['domainValidated'])
        self.assertNotEqual(code, 0)  # The fake's forbidden repeated domain report is rejected.

    def test_mixed_mail_cultivation_daily_completes_with_bound_execution_report(self):
        self.source_package()
        self.config.update(executionEnabled=True, policy=copy.deepcopy(tc.POLICY))
        wf.atomic_json(self.root / "config/cultivation.json", self.config)
        host = CultivationFakeHost(self.root, self.make_report, mixed=True)
        with patch.object(checkin_module, "execute_hoyolab_checkin", return_value={"status": "disabled"}):
            code, result, _ = self.run_flow(mode="execute", host=host)
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["expectedTasks"], ["领取邮件", "培养材料", "领取每日奖励"])
        self.assertEqual([task["status"] for task in result["tasks"]], ["success", "success", "success"])
        self.assertEqual(result["cultivation"]["scope"], "execute")
        self.assertFalse(result["cultivation"]["readOnly"])
        self.assertFalse(result["cultivation"]["targetReached"])
        self.assertEqual(result["cultivation"]["observedGains"], {"104320": 2})
        self.assertEqual(result["cultivation"]["configuredConfirmedClaims"], {"original": 20, "condensed": 0})
        self.assertEqual(result["profileCompletion"]["status"], "completed")
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)

    def test_generated_policy_is_bound_and_running_analysis_cannot_complete(self):
        self.source_package()
        host = CultivationFakeHost(self.root, self.make_report,
            report_change=lambda report: report["policy"].update(domainSingleAttemptVerified=False))
        code, result, _ = self.run_flow(host=host)
        self.assertNotEqual(code, 0)
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        # This assertion uses the same real report + runner glue with the
        # bound policy instead of changing the workflow implementation.
        run_id = result["runId"]
        directory = Path(result["resultPath"]).parent
        group = wf.read_json(result["runtimeCultivationGroup"])
        settings = group["Projects"][0]["JsScriptSettingsObject"]
        report = self.report_fixture.report("scan")
        report.update(runId=run_id, policy=json.loads(settings["policyJson"]))
        wf.atomic_json(self.root / "BetterGI/User/JsScript/AutoGameCultivation/record" / (run_id + ".json"), report)
        event = {"task": "培养材料", "runId": run_id, "mode": "scan", "status": "success",
            "claimedStatus": "success", "evidenceVerified": True, "readOnly": True,
            "reportRelativePath": "record/" + run_id + ".json", "targetReached": False}
        analysis = {"cultivation": event, "tasks": [{"name": "培养材料", "status": "unknown"}],
            "flowEnded": True, "outcome": "unknown"}
        verified = wf.verify_cultivation_analysis(analysis, self.root / "BetterGI/BetterGI.exe", run_id,
            "scan", tc.TARGET, directory, execution_outcome="running", expected_policy=json.loads(settings["policyJson"]))
        self.assertEqual(verified["tasks"][0]["status"], "success")
        self.assertEqual(verified["outcome"], "partial")

    @unittest.skipUnless(sys.platform == "win32", "Windows compatibility version guard")
    def test_scan_stale_graphics_profile_stops_before_launch_and_plugin_install(self):
        import winreg
        profile = wf.read_json(ROOT / "config/genshin-compat-profile.json")
        profile["graphicsData"]["volatileVersion"] = "OSRELWin7.1.0"
        wf.atomic_json(self.root / "config/stale-graphics.json", profile)
        fake_registry = json.dumps({
            "graphicsData": json.dumps({"currentVolatielGrade": 1, "customVolatileGrades": [],
                "volatileVersion": "OSRELWin7.0.0"}), "globalPerfData": "{}"},
            separators=(",", ":")).encode("utf-8") + b"\0"
        self.cfg.update(gameGraphicsProfile="config/stale-graphics.json",
            gameDisplaySettings={"width": 1920, "height": 1080, "windowed": True},
            verifyAutomationGraphicsAfterStart=True, restoreManualGraphicsAfterRun=True)
        wf.atomic_json(self.root / "config/settings.json", self.cfg)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(wf, "begin_graphics_lease", return_value={"runId": "fake"}))
            stack.enter_context(patch.object(wf, "finish_graphics_lease", return_value={"restored": True}))
            opened = stack.enter_context(patch.object(winreg, "OpenKey"))
            stack.enter_context(patch.object(winreg, "QueryValueEx", return_value=(fake_registry, winreg.REG_BINARY)))
            written = stack.enter_context(patch.object(winreg, "SetValueEx"))
            install = stack.enter_context(patch.object(helper, "install_cultivation_plugin"))
            code, result, host = self.run_flow()
        self.assertNotEqual(code, 0)
        self.assertFalse(host.launched)
        self.assertTrue(result["graphicsVerification"]["required"])
        self.assertIn("版本", " ".join(result["errors"]))
        self.assertIn("7.0", " ".join(result["errors"]))
        opened.assert_called_once()
        written.assert_not_called()
        install.assert_not_called()
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)

    def test_execute_and_common_task_keep_prelaunch_graphics_guard(self):
        self.config.update(executionEnabled=True, policy=copy.deepcopy(tc.POLICY))
        wf.atomic_json(self.root / "config/cultivation.json", self.config)
        self.cfg.update(gameGraphicsProfile="config/graphics-profile.json",
            gameDisplaySettings={"width": 1920, "height": 1080, "windowed": True},
            verifyAutomationGraphicsAfterStart=True, restoreManualGraphicsAfterRun=True)
        wf.atomic_json(self.root / "config/settings.json", self.cfg)
        for mode, task, profile in (("scan", None, "cultivation"), ("execute", None, "cultivation"), ("scan", "合成树脂", "configured")):
            with self.subTest(mode=mode, task=task), contextlib.ExitStack() as stack:
                lease = stack.enter_context(patch.object(wf, "begin_graphics_lease", return_value={"runId": "fake"}))
                ensure = stack.enter_context(patch.object(wf, "ensure_genshin_graphics_profile", return_value={}))
                stack.enter_context(patch.object(wf, "ensure_genshin_display_settings", return_value={}))
                verify = stack.enter_context(patch.object(wf, "verify_genshin_automation_graphics", return_value={"allMatched": False}))
                stack.enter_context(patch.object(wf, "finish_graphics_lease", return_value={"restored": True}))
                host = CultivationFakeHost(self.root, self.make_report)
                code, result, _ = self.run_flow(mode=mode, task=task, profile=profile, host=host)
            self.assertNotEqual(code, 0)
            self.assertFalse(host.launched)
            lease.assert_called_once()
            ensure.assert_called_once()
            verify.assert_called_once()
            self.assertTrue(result["graphicsVerification"]["required"])
            self.assertIn("未启动游戏", " ".join(result["errors"]))

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell CLI encoding")
    def test_powershell_dry_run_preserves_chinese_cultivation_task(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("run_cultivation.ps1", "workflow.py", "plan_resin.py", "analyze_run.py",
                     "performance.py", "checkin_hoyolab.py", "cultivation.py", "weapon_guide_evidence.py", "backpack_inventory_evidence.py"):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)
        self.cfg.update(pythonExe=sys.executable, maximumRunMinutes=30,
            bettergiProcessNames=["FakeNeverRealBettergi"], gameProcessNames=["FakeNeverRealGenshin"],
            gameGraphicsProfile="config/fake-graphics.json",
            gameDisplaySettings={"width": 1920, "height": 1080, "windowed": True})
        wf.atomic_json(self.root / "config/fake-graphics.json", wf.read_json(ROOT / "config/genshin-compat-profile.json"))
        wf.atomic_json(self.root / "config/settings.json", self.cfg)
        self.assertTrue((scripts / "run_cultivation.ps1").read_bytes().startswith(b"\xef\xbb\xbf"))
        completed = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(scripts / "run_cultivation.ps1"), "-DryRun"],
            cwd=self.root, capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 0,
            completed.stdout.decode("utf-8", errors="replace") + completed.stderr.decode("utf-8", errors="replace"))
        results = list((self.root / "logs/runs").glob("*/result.json"))
        self.assertEqual(len(results), 1)
        result = wf.read_json(results[0])
        self.assertEqual(result["outcome"], "planned")
        self.assertEqual(result["expectedTasks"], ["培养材料"])
        self.assertEqual(result["cultivationMode"], "scan")
        self.assertEqual(result["executionOutcome"], "not_started")
        self.assertTrue(result["graphicsVerification"]["required"])
        self.assertEqual(self.fixture.base_path.read_bytes(), self.fixture.before)
        self.assertFalse((self.root / "BetterGI/User/ScriptGroup").exists())
        self.assertFalse((self.root / "BetterGI/User/JsScript/AutoGameCultivation").exists())


if __name__ == "__main__":
    unittest.main()
