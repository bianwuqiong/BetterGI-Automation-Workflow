from __future__ import annotations

import sys
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
