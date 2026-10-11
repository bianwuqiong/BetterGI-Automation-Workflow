from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.analyze_run import analyze_log


TASKS = ["领取邮件", "合成树脂", "自动秘境", "自动地脉花", "领取每日奖励", "领取尘歌壶奖励"]


def _full_markers(body: str = "") -> str:
    sections = []
    for index in range(1, len(TASKS) + 1):
        sections.append(f"一条龙任务执行: {index}/6")
        if index == 1:
            sections.append(body)
    return "\n".join(sections) + "\n一条龙和配置组任务结束"


class AnalyzeRunTests(unittest.TestCase):
    def test_serilog_wrapped_live_scan_event_retains_unknown_claim(self) -> None:
        # Sanitized event-only fixture from the 2026-10-08 live scan.
        text = (ROOT / "tests/fixtures/cultivation-serilog-event.txt").read_text(encoding="utf-8")
        result = analyze_log(text, ["培养材料"], run_id="test-run", cultivation_mode="scan")
        self.assertEqual(result["cultivation"]["claimedStatus"], "unknown")
        self.assertEqual(result["cultivation"]["reportRelativePath"], "record/test-run.json")
        self.assertIs(result["cultivation"]["reportVerified"], False)
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertEqual(result["resinEvents"], [])

    def test_serilog_wrapped_event_keeps_scope_status_and_evidence_checks(self) -> None:
        for override in ({"runId": "other-run"}, {"mode": "execute"},
                         {"readOnly": False}, {"evidenceVerified": False},
                         {"evidenceVerified": 1}, {"status": "skipped"},
                         {"reportRelativePath": "record/../test-run.json"}):
            with self.subTest(override=override):
                raw = self.cultivation_event(mode="scan", readOnly=True)
                payload = json.loads(raw.split(" ", 1)[1])
                payload.update(override)
                wrapped = "[AUTO_GAME_EVENT] " + json.dumps(json.dumps(payload, ensure_ascii=False))
                result = analyze_log(wrapped, ["培养材料"], run_id="test-run", cultivation_mode="scan")
                self.assertIsNone(result["cultivation"])
                self.assertEqual(result["tasks"][0]["status"], "unknown")

    def test_serilog_event_unwraps_once_without_searching_for_json(self) -> None:
        raw = self.cultivation_event(mode="scan", readOnly=True).split(" ", 1)[1]
        for payload in (json.dumps(json.dumps(raw)), json.dumps("prefix " + raw),
                        json.dumps(raw + " suffix"), json.dumps("not JSON"),
                        json.dumps([json.loads(raw)])):
            with self.subTest(payload=payload):
                result = analyze_log("[AUTO_GAME_EVENT] " + payload, ["培养材料"],
                                     run_id="test-run", cultivation_mode="scan")
                self.assertIsNone(result["cultivation"])
        result = analyze_log("OCR: [AUTO_GAME_EVENT] " + json.dumps(raw), ["培养材料"],
                             run_id="test-run", cultivation_mode="scan")
        self.assertIsNone(result["cultivation"])

    def test_serilog_wrapped_inline_event_uses_standard_log_header(self) -> None:
        raw = self.cultivation_event(mode="scan", readOnly=True).split(" ", 1)[1]
        text = '[12:00:00.123] [INF] [Primary:S1:P1:T1] [AUTO_GAME_EVENT] ' + json.dumps(raw)
        result = analyze_log(text, ["培养材料"], run_id="test-run", cultivation_mode="scan")
        self.assertEqual(result["cultivation"]["claimedStatus"], "success")
        self.assertEqual(result["tasks"][0]["status"], "unknown")

    def cultivation_event(self, **overrides) -> str:
        payload = {
            "task": "培养材料", "runId": "test-run", "status": "success",
            "evidenceVerified": True, "mode": "execute",
            "reportRelativePath": "record/test-run.json",
            "steps": [{"name": "菫色之庭", "status": "success"}],
            "observedGains": {"「浮世」的教导": 2},
        }
        payload.update(overrides)
        return "[AUTO_GAME_EVENT] " + json.dumps(payload, ensure_ascii=False)

    def test_mixed_builtin_and_cultivation_group_keep_separate_scopes(self) -> None:
        text = "\n".join([
            "一条龙任务执行: 1/2",
            '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}',
            "配置组任务执行: 1/1", "任务执行异常：JS首次尝试",
            self.cultivation_event(), "一条龙任务执行: 2/2",
            "检查每日奖励结果：今日奖励已领取", "一条龙和配置组任务结束",
        ])
        result = analyze_log(text, ["领取邮件", "培养材料", "领取每日奖励"], run_id="test-run")
        self.assertEqual([t["status"] for t in result["tasks"]], ["success", "unknown", "success"])
        self.assertEqual(result["outcome"], "partial")
        self.assertEqual(result["cultivation"]["claimedStatus"], "success")
        self.assertEqual(result["cultivation"]["observedGains"], {"「浮世」的教导": 2})
        self.assertEqual(result["cultivation"]["steps"][0]["name"], "菫色之庭")
        self.assertIs(result["cultivation"]["reportVerified"], False)

    def legacy_total_cultivation_log(self):
        return '\n'.join(['参数指定的一条龙配置：AutoGame_test-run',
            '启用一条龙配置：AutoGame_test-run', '一条龙任务执行: 1/3',
            '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}',
            '配置组任务执行: 1/1', '任务执行异常：培养独立范围',
            self.cultivation_event(status='unknown'), '一条龙任务执行: 2/3',
            '前往冒险家协会领取奖励执行异常：网络波动后未能恢复到游戏主界面',
            '一条龙和配置组任务结束', '游戏已退出，BetterGI 自动停止截图器'])

    def test_legacy_total_denominator_uses_builtin_ordinals_with_exact_cultivation_scope(self):
        result = analyze_log(self.legacy_total_cultivation_log(),
            ['领取邮件', '培养材料', '领取每日奖励'], run_id='test-run', config_name='AutoGame_test-run')
        self.assertTrue(result['flowEnded'])
        self.assertEqual([task['status'] for task in result['tasks']], ['success', 'unknown', 'failed'])
        self.assertEqual(result['cultivation']['claimedStatus'], 'unknown')
        self.assertFalse(result['cultivation']['reportVerified'])
        self.assertEqual(result['outcome'], 'partial')

    def test_legacy_total_denominator_requires_exact_config_run_and_group_proof(self):
        text = self.legacy_total_cultivation_log()
        variants = [(text, None, 'AutoGame_test-run'), (text, 'other', 'AutoGame_test-run'),
                    (text, 'test-run', None), (text, 'test-run', 'OtherRun'),
                    (text.replace('配置组任务执行: 1/1', ''), 'test-run', 'AutoGame_test-run'),
                    (text.replace('配置组任务执行: 1/1', '配置组任务执行: 1/2'), 'test-run', 'AutoGame_test-run'),
                    (text.replace('启用一条龙配置：AutoGame_test-run', '启用一条龙配置：OtherRun'), 'test-run', 'AutoGame_test-run')]
        for changed, run_id, config_name in variants:
            with self.subTest(run_id=run_id, config=config_name, changed=changed):
                result = analyze_log(changed, ['领取邮件', '培养材料', '领取每日奖励'],
                                     run_id=run_id, config_name=config_name)
                self.assertFalse(result['flowEnded'])
                self.assertIsNone(result['cultivation'])
                self.assertTrue(all(task['status'] == 'unknown' for task in result['tasks']))
                self.assertEqual(result['rewards'], {})

    def test_legacy_total_mixed_runs_duplicate_groups_and_wrong_group_position_are_rejected(self):
        text = self.legacy_total_cultivation_log()
        variants = [text + '\n' + text,
            text.replace('配置组任务执行: 1/1', '配置组任务执行: 1/1\n配置组任务执行: 1/1'),
            text.replace('一条龙任务执行: 2/3', '一条龙任务执行: 2/2'),
            text.replace('配置组任务执行: 1/1', '').replace('一条龙任务执行: 2/3', '一条龙任务执行: 2/3\n配置组任务执行: 1/1'),
            text.replace('一条龙任务执行: 2/3', '一条龙任务执行: 3/3')]
        for changed in variants:
            result = analyze_log(changed, ['领取邮件', '培养材料', '领取每日奖励'],
                                 run_id='test-run', config_name='AutoGame_test-run')
            self.assertFalse(result['flowEnded'])
            self.assertIsNone(result['cultivation'])
            self.assertTrue(all(task['status'] == 'unknown' for task in result['tasks']))

    def test_legacy_total_scoped_event_must_be_inside_the_unique_group(self):
        text = self.legacy_total_cultivation_log()
        for changed in (text.replace(self.cultivation_event(status='unknown'), ''),
                        text.replace(self.cultivation_event(status='unknown'), self.cultivation_event(runId='other')),
                        text.replace(self.cultivation_event(status='unknown'), '') + '\n' + self.cultivation_event(status='unknown')):
            result = analyze_log(changed, ['领取邮件', '培养材料', '领取每日奖励'],
                                 run_id='test-run', config_name='AutoGame_test-run')
            self.assertFalse(result['flowEnded'])
            self.assertIsNone(result['cultivation'])

    def test_single_scan_retains_claim_without_confirming_farming(self) -> None:
        text = "\n".join(["配置组任务执行: 1/1",
            self.cultivation_event(mode="scan", readOnly=True), "一条龙和配置组任务结束"])
        result = analyze_log(text, ["培养材料"], run_id="test-run", cultivation_mode="scan")
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertTrue(result["flowEnded"])
        self.assertIs(result["cultivation"]["readOnly"], True)
        self.assertEqual(result["cultivation"]["reportRelativePath"], "record/test-run.json")
        self.assertEqual(result["rewards"], {})

    def test_cultivation_wrong_or_missing_run_id_is_ignored(self) -> None:
        for run_id in (None, "different-run"):
            with self.subTest(run_id=run_id):
                result = analyze_log(self.cultivation_event(), ["培养材料"], run_id=run_id)
                self.assertIsNone(result["cultivation"])
                self.assertEqual(result["tasks"][0]["status"], "unknown")

    def test_cultivation_terminal_claims_wait_for_report_verification(self) -> None:
        for status in ("unknown", "blocked", "failed"):
            with self.subTest(status=status):
                result = analyze_log(self.cultivation_event(status=status), ["培养材料"], run_id="test-run")
                self.assertEqual(result["cultivation"]["claimedStatus"], status)
                self.assertEqual(result["tasks"][0]["status"], "unknown")

    def test_cultivation_mode_scope_mismatch_is_rejected(self) -> None:
        cases = [("scan", "execute", True), ("execute", "scan", False)]
        for event_mode, requested_mode, read_only in cases:
            with self.subTest(event_mode=event_mode):
                result = analyze_log(self.cultivation_event(mode=event_mode, readOnly=read_only),
                    ["培养材料"], run_id="test-run", cultivation_mode=requested_mode)
                self.assertIsNone(result["cultivation"])
                self.assertEqual(result["outcome"], "unknown")

    def test_cultivation_requires_strict_path_and_read_only_contract(self) -> None:
        cases = [
            {"reportRelativePath": "record/../other.json"},
            {"reportRelativePath": "C:/record/test-run.json"},
            {"mode": "scan", "readOnly": False},
            {"mode": "scan", "readOnly": 1},
            {"mode": "execute", "readOnly": True},
            {"mode": "execute", "readOnly": 0},
            {"evidenceVerified": False},
            {"status": "skipped"},
            {"status": []},
            {"task": {"unexpected": "object"}},
        ]
        for override in cases:
            with self.subTest(override=override):
                result = analyze_log(self.cultivation_event(**override), ["培养材料"],
                    run_id="test-run", cultivation_mode=override.get("mode", "execute"))
                self.assertIsNone(result["cultivation"])

    def test_cultivation_group_end_without_event_stays_unknown(self) -> None:
        result = analyze_log("配置组任务执行: 1/1\n培养材料任务结束\n一条龙和配置组任务结束",
            ["培养材料"], run_id="test-run")
        self.assertEqual(result["outcome"], "unknown")
        self.assertIsNone(result["cultivation"])

    def test_cultivation_event_can_precede_builtin_markers(self) -> None:
        text = "\n".join(["配置组任务执行: 1/1", self.cultivation_event(),
            "一条龙任务执行: 1/1", "检查每日奖励结果：今日奖励已领取",
            "一条龙和配置组任务结束"])
        result = analyze_log(text, ["培养材料", "领取每日奖励"], run_id="test-run")
        self.assertEqual(result["tasks"][1]["status"], "success")
        self.assertEqual(result["cultivation"]["claimedStatus"], "success")

    def test_cultivation_mixed_runs_or_wrong_config_reject_claims(self) -> None:
        for text, config_name in [
            ("一条龙任务执行: 1/1\n" + self.cultivation_event()
                + "\n一条龙任务执行: 1/1", None),
            ("参数指定的一条龙配置：OtherRun\n" + self.cultivation_event(), "ExpectedRun"),
        ]:
            with self.subTest(config_name=config_name):
                tasks = ["培养材料"] if config_name else ["培养材料", "领取每日奖励"]
                result = analyze_log(text, tasks, run_id="test-run", config_name=config_name)
                self.assertIsNone(result["cultivation"])
                self.assertTrue(all(task["status"] == "unknown" for task in result["tasks"]))

    def test_foreign_run_crafting_event_is_not_accounted(self) -> None:
        payload = {
            "task": "合成树脂", "runId": "other-run", "status": "success", "evidenceVerified": True,
            "originalResinBefore": 60, "originalResinAfter": 0,
            "condensedResinBefore": 0, "condensedResinAfter": 1,
            "condensedResinCreated": 1, "originalResinSpent": 60,
        }
        text = "一条龙任务执行: 1/1\n[AUTO_GAME_EVENT] " + json.dumps(payload) + "\n一条龙和配置组任务结束"
        result = analyze_log(text, ["合成树脂"], run_id="test-run")
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertEqual(result["resinEvents"], [])

    def test_failed_multi_task_run_is_not_completed(self) -> None:
        text = "\n".join([
            "一条龙任务执行: 1/6",
            "领取邮件执行异常：示例失败",
            "一条龙任务执行: 2/6",
            "合成树脂执行异常：示例失败",
            "一条龙任务执行: 3/6",
            '自动秘境：本轮奖励识别结果 "示例材料 x1"',
            "自动秘境执行异常：示例失败",
            "一条龙任务执行: 4/6",
            "自动地脉花执行异常：示例失败",
            "一条龙任务执行: 5/6",
            "领取每日奖励执行异常：示例失败",
            "一条龙任务执行: 6/6",
            "领取尘歌壶奖励执行异常：示例失败",
            "一条龙和配置组任务结束",
        ])
        result = analyze_log(text, TASKS)

        self.assertNotEqual(result["outcome"], "completed")
        self.assertEqual(result["tasks"][1]["status"], "failed")
        self.assertEqual(result["tasks"][2]["status"], "failed")
        self.assertEqual(result["tasks"][3]["status"], "failed")
        self.assertTrue(result["rewards"])

    def test_multiple_runs_are_not_cross_attributed(self) -> None:
        event = '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}'
        result = analyze_log(_full_markers(event) + "\n" + _full_markers(), TASKS)

        self.assertEqual(result["outcome"], "unknown")
        self.assertTrue(all(task["status"] == "unknown" for task in result["tasks"]))
        self.assertIn("multiple matching one-dragon runs", "\n".join(result["warnings"]))

    def test_verified_retry_success_overrides_earlier_warning(self) -> None:
        text = _full_markers(
            "任务执行异常：第一次失败\n重试任务\n"
            '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}'
        )
        result = analyze_log(text, TASKS)

        mail = result["tasks"][0]
        self.assertEqual(mail["status"], "success")
        self.assertEqual(mail["reason"], "verified AUTO_GAME_EVENT")
        self.assertNotIn("第一次失败", mail["reason"])

    def test_crafting_claim_is_not_success(self) -> None:
        text = "\n".join(
            [
                "一条龙任务执行: 1/6",
                "一条龙任务执行: 2/6",
                "无需合成浓缩树脂",
                "→ 任务结束",
                "一条龙任务执行: 3/6",
            ]
        )
        result = analyze_log(text, TASKS)

        self.assertEqual(result["tasks"][1]["status"], "unknown")
        self.assertIn("inventory verification", result["tasks"][1]["reason"])

    def test_verified_crafting_inventory_delta_completes_and_accounts(self) -> None:
        event = (
            '[AUTO_GAME_EVENT] {"task":"合成树脂","status":"success",'
            '"evidenceVerified":true,"originalResinBefore":180,"originalResinAfter":0,'
            '"condensedResinBefore":2,"condensedResinAfter":5,'
            '"condensedResinCreated":3,"originalResinSpent":180}'
        )
        text = "\n".join(
            ["一条龙任务执行: 1/1", event, "一条龙和配置组任务结束"]
        )
        result = analyze_log(text, ["合成树脂"], execution_outcome="exited")

        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["tasks"][0]["status"], "success")
        self.assertEqual(
            result["resinEvents"],
            [{"type": "crafted_condensed", "count": 3, "line": 2, "originalResinSpent": 180}],
        )

    def test_invalid_crafting_delta_cannot_complete_or_account(self) -> None:
        event = (
            '[AUTO_GAME_EVENT] {"task":"合成树脂","status":"success",'
            '"evidenceVerified":true,"originalResinBefore":180,"originalResinAfter":120,'
            '"condensedResinBefore":2,"condensedResinAfter":5,'
            '"condensedResinCreated":3,"originalResinSpent":180}'
        )
        result = analyze_log(
            "\n".join(["一条龙任务执行: 1/1", event, "一条龙和配置组任务结束"]),
            ["合成树脂"],
            execution_outcome="exited",
        )

        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertEqual(result["resinEvents"], [])

    def test_terminal_cancelled_task_is_failed(self) -> None:
        # Put the terminal record in the second marker section, not in the
        # first task's preamble.
        text = _full_markers().replace(
            "一条龙任务执行: 2/6", "一条龙任务执行: 2/6\n任务被取消"
        )
        result = analyze_log(text, TASKS)

        self.assertEqual(result["tasks"][1]["status"], "failed")

    def test_verified_success_does_not_overwrite_later_terminal_failure(self) -> None:
        text = _full_markers(
            '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}\n'
            "任务被取消"
        )
        result = analyze_log(text, TASKS)

        self.assertEqual(result["tasks"][0]["status"], "failed")

    def test_event_marker_inside_ocr_text_is_not_accepted(self) -> None:
        text = _full_markers(
            'OCR: [AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}'
        )
        result = analyze_log(text, TASKS)

        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertIn("ignored AUTO_GAME_EVENT", "\n".join(result["warnings"]))

    def test_different_marker_denominators_omit_cross_run_accounting(self) -> None:
        text = _full_markers(
            '自动秘境：本轮奖励识别结果 "摩拉 x100"\n'
            '自动秘境：使用 "浓缩树脂", 数量：1'
        ) + "\n一条龙任务执行: 1/1\n另一轮日志"
        result = analyze_log(text, TASKS)

        self.assertTrue(all(task["status"] == "unknown" for task in result["tasks"]))
        self.assertEqual(result["rewards"], {})
        self.assertEqual(result["resinEvents"], [])

    def test_wrong_explicit_config_rejects_machine_events(self) -> None:
        text = "参数指定的一条龙配置：OtherRun\n" + _full_markers(
            '[AUTO_GAME_EVENT] {"task":"领取邮件","status":"success","evidenceVerified":true}'
        )
        result = analyze_log(text, TASKS, config_name="ExpectedRun")

        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertIn("different configuration", "\n".join(result["warnings"]))

    def test_verified_skipped_tasks_are_compatible_with_completed(self) -> None:
        lines = []
        for index, task in enumerate(TASKS, start=1):
            status = "skipped" if task == "自动地脉花" else "success"
            if task == "合成树脂":
                event = (
                    f'[AUTO_GAME_EVENT] {{"task":"{task}","status":"{status}",'
                    '"evidenceVerified":true,"originalResinBefore":60,"originalResinAfter":0,'
                    '"condensedResinBefore":0,"condensedResinAfter":1,'
                    '"condensedResinCreated":1,"originalResinSpent":60}'
                )
            else:
                event = f'[AUTO_GAME_EVENT] {{"task":"{task}","status":"{status}","evidenceVerified":true}}'
            lines.extend(
                [
                    f"一条龙任务执行: {index}/6",
                    event,
                ]
            )
        lines.append("一条龙和配置组任务结束")
        result = analyze_log("\n".join(lines), TASKS)

        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["tasks"][3]["status"], "skipped")

    def test_domain_requires_reward_and_real_resin_exhaustion_end(self) -> None:
        text = "\n".join(
            [
                "一条龙任务执行: 1/6",
                "一条龙任务执行: 2/6",
                "一条龙任务执行: 3/6",
                '自动秘境：本轮奖励识别结果 "摩拉 x100"',
                "自动秘境：原粹树脂已用尽，退出秘境",
                "一条龙任务执行: 4/6",
                "一条龙任务执行: 5/6",
                "一条龙任务执行: 6/6",
                "一条龙和配置组任务结束",
            ]
        )
        result = analyze_log(text, TASKS)

        self.assertEqual(result["tasks"][2]["status"], "success")

    def test_domain_accepts_verified_spend_reward_and_explicit_task_end(self) -> None:
        text = "\n".join(
            [
                "一条龙任务执行: 1/1",
                '自动秘境：使用 "浓缩树脂", 数量：1',
                '自动秘境：本轮奖励识别结果 "摩拉 x100"',
                "体力耗尽或者设置轮次已达标，结束自动秘境",
                "任务结束",
                "一条龙和配置组任务结束",
            ]
        )

        result = analyze_log(text, ["自动秘境"], execution_outcome="exited")

        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["tasks"][0]["status"], "success")

    def test_daily_reward_accepts_verified_claimed_state(self) -> None:
        text = "\n".join(
            [
                "一条龙任务执行: 1/1",
                "检查每日奖励结果：今日奖励已领取",
                "一条龙和配置组任务结束",
            ]
        )

        result = analyze_log(text, ["领取每日奖励"], execution_outcome="exited")

        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["tasks"][0]["status"], "success")

    def test_insufficient_legacy_evidence_stays_unknown_and_timeout_cannot_complete(self) -> None:
        result = analyze_log(
            _full_markers("[AUTO_GAME_EVENT] {\"task\":\"领取邮件\",\"status\":\"success\"}"),
            TASKS,
            execution_outcome="timeout",
        )

        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["tasks"][0]["status"], "unknown")
        self.assertIn("evidenceVerified", "\n".join(result["warnings"]))

    def test_reward_lines_are_counted_once_and_summaries_are_ignored(self) -> None:
        text = "\n".join(
            [
                '自动秘境：本轮奖励识别结果 "摩拉 x100, 「黄金」的教导 x2"',
                '自动秘境：本轮奖励识别结果 "摩拉 x50, 「黄金」的教导 x1"',
                '本次奖励汇总 "摩拉 x150, 「黄金」的教导 x3"',
                '自动秘境：使用 "浓缩树脂", 数量：1',
            ]
        )
        result = analyze_log(text, TASKS)

        self.assertEqual(result["rewards"], {"摩拉": 150, "「黄金」的教导": 3})
        self.assertEqual(result["resinEvents"], [{"type": "used_condensed", "count": 1, "line": 4}])


if __name__ == "__main__":
    unittest.main()
