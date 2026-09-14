import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from plan_resin import PlanError, _crafting_suggestions, _read_inventory, build_plan, load_json  # noqa: E402


ARTIFACTS = ROOT / "tests" / ".artifacts" / "planner-fixtures-20260912-225249"


def goals(*characters, allow=False):
    return {"allowBookCrafting": allow, "avgGoldBooksPerRun": 1.5,
            "characters": list(characters)}


def character(name="甲", series="黄金", current=8, target=9, artifact="冰河"):
    return {"name": name, "talentSeries": series,
            "talents": [{"slot": "普攻", "current": current, "target": target}],
            "talentParty": "队伍", "artifactDomain": artifact, "artifactParty": "圣遗物队"}


def calendar(*, days=(3, 6, 0), selector=None):
    domain = {"name": "太山府", "series": "黄金", "days": list(days), "_verified": True}
    if selector is not None:
        domain.update(selector)
    return {"domains": [domain]}


def progress(books=None, verified=False):
    return {"books": books or {}, "inventoryVerified": verified}


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Kept deliberately: test inputs are inspectable and never deleted.
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / "bom.json").write_bytes(b"\xef\xbb\xbf{\"ok\": true}\n")
        (ARTIFACTS / "broken.json").write_text('{"broken": ', encoding="utf-8")

    def test_load_json_accepts_bom_and_rejects_damage(self):
        self.assertEqual(load_json(ARTIFACTS / "bom.json"), {"ok": True})
        with self.assertRaises(PlanError):
            load_json(ARTIFACTS / "broken.json")

    def test_artifact_only_plan_does_not_need_talent_files(self):
        artifact_goals = {
            "characters": [{"name": "圣遗物目标", "artifactDomain": "冰河",
                            "artifactParty": ""}]
        }

        plan = build_plan(artifact_goals, None, None, datetime(2026, 9, 14, 12))

        self.assertEqual(plan["decision"]["type"], "artifact-domain")
        self.assertEqual(plan["configPatch"]["DomainName"], "冰河")
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["blockers"], [])

    def test_completed_talent_goal_does_not_need_talent_files(self):
        completed = goals(character(current=9, target=9, artifact="冰河"))

        plan = build_plan(completed, None, None, datetime(2026, 9, 14, 12))

        self.assertEqual(plan["decision"]["type"], "artifact-domain")
        self.assertEqual(plan["configPatch"]["DomainName"], "冰河")
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["blockers"], [])

    def test_talent_goal_still_requires_calendar_and_progress(self):
        with self.assertRaises(PlanError):
            build_plan(goals(character()), None, progress(), datetime(2026, 9, 14, 12))
        with self.assertRaises(PlanError):
            build_plan(goals(character()), calendar(), None, datetime(2026, 9, 14, 12))

    def test_sunday_reset_boundary_and_verified_selector(self):
        # Naive input is server time: 03:59 belongs to Saturday, 04:00 to Sunday.
        before = build_plan(goals(character()), calendar(), progress(), datetime(2026, 9, 13, 3, 59))
        self.assertEqual(before["gameWeekday"], "周六")
        self.assertEqual(before["decision"]["type"], "talent-domain")
        after = build_plan(goals(character()), calendar(selector={"sundaySelectionVerified": True,
                                                                 "sundaySelectedValue": 2}), progress(),
                           datetime(2026, 9, 13, 4, 0))
        self.assertEqual(after["gameWeekday"], "周日")
        self.assertEqual(after["configPatch"]["SundayEverySelectedValue"], "2")

    def test_unverified_inventory_does_not_apply_lower_tier_crafting(self):
        books = {"「黄金」的哲学": 2, "「黄金」的指引": 25, "「黄金」的教导": 26}
        plan = build_plan(goals(character(), allow=True), calendar(), progress(books, verified=False),
                          datetime(2026, 9, 12, 12))
        self.assertEqual(plan["decision"]["type"], "talent-domain")
        self.assertEqual(plan["decision"]["shortage"]["gold"], 10)
        self.assertTrue(plan["craftingSuggestions"][0]["actions"])
        self.assertTrue(any("inventoryVerified" in warning for warning in plan["warnings"]))

    def test_unverified_inventory_warns_even_when_crafting_is_disabled(self):
        plan = build_plan(goals(character(), allow=False), calendar(), progress(), datetime(2026, 9, 12, 12))
        self.assertTrue(any("库存未经" in warning for warning in plan["warnings"]))

    def test_verified_inventory_can_plan_with_reserved_lower_tier_crafting(self):
        books = {"「黄金」的哲学": 2, "「黄金」的指引": 25, "「黄金」的教导": 26}
        plan = build_plan(goals(character(), allow=True), calendar(), progress(books, verified=True),
                          datetime(2026, 9, 12, 12))
        self.assertEqual(plan["decision"]["type"], "artifact-domain")
        self.assertTrue(plan["craftingSuggestions"][0]["requiresManualOrSeparateCrafting"])
        self.assertIn("材料可通过建议合成满足，尚未执行", plan["decision"]["reason"])

    def test_crafting_meets_direct_purple_before_using_surplus_for_gold(self):
        suggestion = _crafting_suggestions(
            "黄金", {"blue": 0, "purple": 6, "gold": 2},
            {"blue": 27, "purple": 1, "gold": 0},
        )
        self.assertEqual(suggestion["remainingShortageAfterSuggestedCrafting"],
                         {"blue": 0, "purple": 0, "gold": 1})
        self.assertEqual(suggestion["actions"][0]["from"], "「黄金」的教导")
        self.assertEqual(suggestion["actions"][0]["inputCount"], 24)
        self.assertEqual(suggestion["actions"][0]["outputCount"], 8)
        self.assertEqual(suggestion["actions"][1]["from"], "「黄金」的指引")
        self.assertEqual(suggestion["actions"][1]["inputCount"], 3)

    def test_empty_progress_and_boolean_calendar_day_are_rejected_safely(self):
        self.assertEqual(_read_inventory({}), {})
        invalid_calendar = calendar(days=(True,))
        with self.assertRaises(PlanError):
            build_plan(goals(character()), invalid_calendar, progress(), datetime(2026, 9, 12, 12))

    def test_same_series_goals_are_aggregated_before_inventory_comparison(self):
        books = {"「黄金」的哲学": 12}
        plan = build_plan(goals(character("甲"), character("乙")), calendar(), progress(books),
                          datetime(2026, 9, 12, 12))
        self.assertEqual(plan["decision"]["shortage"]["gold"], 12)
        self.assertEqual(plan["decision"]["character"], ["甲", "乙"])

    def test_sunday_without_verified_selector_blocks_even_with_artifact_fallback(self):
        plan = build_plan(goals(character()), calendar(), progress(), datetime(2026, 9, 13, 12))
        self.assertIsNone(plan["decision"])
        self.assertIsNone(plan["configPatch"])
        self.assertTrue(plan["blockers"])

    def test_aware_datetime_is_converted_to_configured_server_timezone(self):
        # 20:30 UTC is 04:30 Sunday in UTC+8.
        plan = build_plan(goals(character()), calendar(selector={"sundaySelectionVerified": True,
                                                                 "sundaySelectedValue": "1"}), progress(),
                          datetime(2026, 9, 12, 20, 30, tzinfo=timezone.utc))
        self.assertEqual(plan["gameWeekday"], "周日")


if __name__ == "__main__":
    unittest.main()
