from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.performance import analyze_performance


TASKS = ["领取邮件", "合成树脂", "自动秘境"]


def _record(clock: str, message: str) -> str:
    return f"[{clock}] [INF] BetterGI\n{message}"


class PerformanceTests(unittest.TestCase):
    def test_timing_phases_and_teleport_without_claiming_success(self) -> None:
        text = "\n".join(
            [
                _record("23:59:50.000", "一条龙任务执行: 1/3"),
                _record("23:59:55.000", '→ "任务结束"'),
                _record("23:59:56.000", "一条龙任务执行: 2/3"),
                _record("23:59:58.000", '→ "任务结束"'),
                _record("23:59:59.000", "一条龙任务执行: 3/3"),
                _record("00:00:01.000", "开始传送：秘境"),
                _record("00:00:11.000", "传送完成"),
                _record("00:00:12.000", '自动秘境："1. 走到钥匙处启动"'),
                _record("00:00:20.000", '自动秘境："2. 执行战斗策略"'),
                _record("00:00:46.000", '自动秘境："3. 寻找石化古树"'),
                _record("00:03:19.000", '自动秘境："4. 走到石化古树处"'),
                _record("00:03:25.000", '自动秘境："5. 领取奖励"'),
                _record("00:03:31.000", '自动秘境：本轮奖励识别结果 "摩拉 x100"'),
                _record("00:03:35.000", "一条龙和配置组任务结束"),
            ]
        )
        result = analyze_performance(text, TASKS)

        domain = result["rounds"][0]
        self.assertEqual(
            result["teleports"][0],
            {"index": 1, "elapsedSec": 10.0, "complete": True, "endedBy": "success"},
        )
        self.assertEqual(domain["phases"]["domain_fight"]["elapsedSec"], 26.0)
        self.assertEqual(domain["phases"]["tree_search"]["elapsedSec"], 159.0)
        self.assertTrue(domain["rewardObserved"])
        self.assertTrue(result["tasks"][2]["complete"])

    def test_incomplete_stage_uses_relative_now_elapsed(self) -> None:
        text = "\n".join(
            [
                _record("10:00:00.000", "一条龙任务执行: 1/1"),
                _record("10:00:10.000", '自动秘境："1. 走到钥匙处启动"'),
                _record("10:00:12.000", '自动秘境："2. 执行战斗策略"'),
            ]
        )
        result = analyze_performance(text, ["自动秘境"], now_elapsed_sec=42)

        self.assertEqual(
            result["rounds"][0]["phases"]["domain_fight"],
            {"elapsedSec": 30.0, "complete": False, "endedBy": "last_log"},
        )
        self.assertEqual(
            result["currentStage"],
            {"name": "domain_fight", "label": "执行战斗策略", "task": "自动秘境", "elapsedSec": 30.0},
        )

    def test_mixed_markers_do_not_attribute_or_cross_charge_counters(self) -> None:
        text = "\n".join(
            [
                _record("10:00:00.000", "一条龙任务执行: 1/1"),
                _record("10:00:01.000", "重试传送"),
                _record("10:00:02.000", "一条龙任务执行: 1/3"),
            ]
        )
        result = analyze_performance(text, TASKS)

        self.assertTrue(all(task["elapsedSec"] is None for task in result["tasks"]))
        self.assertEqual(result["counters"], {"deaths": 0, "retries": 0, "teleportFailures": 0})
        self.assertIn("differently sized", "\n".join(result["warnings"]))

    def test_pending_teleport_is_the_current_stage_over_task(self) -> None:
        text = "\n".join(
            [
                _record("10:00:00.000", "一条龙任务执行: 1/1"),
                _record("10:00:05.000", "开始传送：秘境"),
            ]
        )
        result = analyze_performance(text, ["自动秘境"], now_elapsed_sec=70)

        self.assertEqual(
            result["currentStage"],
            {"name": "teleport", "label": "传送", "task": "自动秘境", "elapsedSec": 65.0},
        )

    def test_teleport_retries_do_not_leave_a_ghost_pending_attempt(self) -> None:
        text = "\n".join(
            [
                _record("10:00:00.000", "一条龙任务执行: 1/1"),
                _record("10:00:05.000", "开始传送：第一次"),
                _record("10:00:07.000", "开始传送：第二次"),
                _record("10:00:08.000", "传送失败"),
                _record("10:00:10.000", "开始传送：第三次"),
                _record("10:00:15.000", "传送完成"),
                _record("10:00:16.000", '→ "任务结束"'),
            ]
        )
        result = analyze_performance(text, ["自动秘境"])

        self.assertEqual(
            result["teleports"],
            [
                {"index": 1, "elapsedSec": 2.0, "complete": True, "endedBy": "superseded"},
                {"index": 2, "elapsedSec": 1.0, "complete": True, "endedBy": "failure"},
                {"index": 3, "elapsedSec": 5.0, "complete": True, "endedBy": "success"},
            ],
        )
        self.assertIsNone(result["currentStage"])

    def test_short_fractional_timestamps_are_decimals_not_milliseconds(self) -> None:
        text = "\n".join(
            [
                _record("10:00:00.1", "一条龙任务执行: 1/1"),
                _record("10:00:00.12", '→ "任务结束"'),
            ]
        )
        result = analyze_performance(text, ["领取邮件"])

        self.assertEqual(result["tasks"][0], {"name": "领取邮件", "elapsedSec": 0.02, "complete": True, "endedBy": "task_end"})

    def test_flow_end_closes_pending_teleport(self) -> None:
        text = "\n".join(
            [
                _record("10:00:00.000", "一条龙任务执行: 1/1"),
                _record("10:00:05.000", "开始传送：秘境"),
                _record("10:00:09.000", "一条龙和配置组任务结束"),
            ]
        )
        result = analyze_performance(text, ["自动秘境"])

        self.assertEqual(
            result["teleports"],
            [{"index": 1, "elapsedSec": 4.0, "complete": True, "endedBy": "task_end"}],
        )
        self.assertIsNone(result["currentStage"])

    def test_fast_combat_and_slow_tree_rounds(self) -> None:
        text = "\n".join([
            _record("10:00:00.000", "一条龙任务执行: 1/1"),
            _record("10:00:00.500", '自动秘境："1. 走到钥匙处启动"'),
            _record("10:00:01.000", '自动秘境："2. 执行战斗策略"'),
            _record("10:00:33.393", '自动秘境："3. 寻找石化古树"'),
            _record("10:04:01.824", '自动秘境："4. 走到石化古树处"'),
            _record("10:04:01.824", '自动秘境："5. 领取奖励"'),
            _record("10:04:03.000", '自动秘境：本轮奖励识别结果 "示例材料 x1"'),
            _record("10:04:04.000", '自动秘境："1. 走到钥匙处启动"'),
            _record("10:04:05.000", '自动秘境："2. 执行战斗策略"'),
            _record("10:04:31.426", '自动秘境："3. 寻找石化古树"'),
            _record("10:09:01.084", '自动秘境："4. 走到石化古树处"'),
            _record("10:09:01.084", '自动秘境："5. 领取奖励"'),
            _record("10:09:03.000", '自动秘境：本轮奖励识别结果 "示例材料 x1"'),
            _record("10:09:04.000", '自动秘境："1. 走到钥匙处启动"'),
            _record("10:09:05.000", '自动秘境："2. 执行战斗策略"'),
            _record("10:09:25.000", '自动秘境："3. 寻找石化古树"'),
            _record("10:09:45.000", '自动秘境："4. 走到石化古树处"'),
            _record("10:09:46.000", "一条龙和配置组任务结束"),
        ])
        result = analyze_performance(text, ["自动秘境"])

        self.assertGreaterEqual(len(result["rounds"]), 3)
        self.assertAlmostEqual(result["rounds"][0]["phases"]["domain_fight"]["elapsedSec"], 32.393, places=3)
        self.assertAlmostEqual(result["rounds"][0]["phases"]["tree_search"]["elapsedSec"], 208.431, places=3)
        self.assertAlmostEqual(result["rounds"][1]["phases"]["domain_fight"]["elapsedSec"], 26.426, places=3)
        self.assertAlmostEqual(result["rounds"][1]["phases"]["tree_search"]["elapsedSec"], 269.658, places=3)

        later_text = "\n".join([
            _record("11:00:00.000", "一条龙任务执行: 1/1"),
            _record("11:00:00.500", '自动秘境："1. 走到钥匙处启动"'),
            _record("11:00:01.000", '自动秘境："2. 执行战斗策略"'),
            _record("11:00:42.821", '自动秘境："3. 寻找石化古树"'),
            _record("11:01:18.968", '自动秘境："4. 走到石化古树处"'),
            _record("11:01:18.968", '自动秘境："5. 领取奖励"'),
            _record("11:01:20.000", "一条龙和配置组任务结束"),
        ])
        later = analyze_performance(later_text, ["自动秘境"])
        self.assertAlmostEqual(later["rounds"][0]["phases"]["domain_fight"]["elapsedSec"], 41.821, places=3)
        self.assertAlmostEqual(later["rounds"][0]["phases"]["tree_search"]["elapsedSec"], 36.147, places=3)


if __name__ == "__main__":
    unittest.main()
