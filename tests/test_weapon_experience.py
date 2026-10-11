from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.weapon_experience import (  # noqa: E402
    ORE_IDS,
    WeaponPlanError,
    build_weapon_experience_report,
)


def curve_rows():
    # Small deterministic fixture: rarity XP per level is 100..500.
    # A deliberately huge level-90 sentinel catches accidental inclusion.
    return [
        {"level": level, "requiredExps": [100, 200, 300, 400, 500]}
        for level in range(1, 90)
    ] + [{"level": 90, "requiredExps": [111111, 222222, 333333, 444444, 555555]}]


def material_rows():
    values = {104011: 400, 104012: 2000, 104013: 10000}
    return [{
        "id": item_id,
        "materialType": "MATERIAL_WEAPON_EXP_STONE",
        "itemUse": [{"useOp": "ITEM_USE_ADD_WEAPON_EXP", "useParam": [str(value)]}],
    } for item_id, value in values.items()]


def rulebook(rarity=4):
    phases = {}
    mora = [5000, 15000, 20000, 30000, 35000, 45000]
    for phase, cost in enumerate(mora, 1):
        phases[f"ascend{phase}"] = [{"id": 202, "name": "摩拉", "count": cost}]
    return {"weapons": {"Test Weapon": {"rarity": rarity, "ascensionCosts": phases}}}


def observation(**overrides):
    result = {"weaponName": "Test Weapon", "rarity": 4, "level": 1, "cap": 20,
              "currentXPIntoLevel": 0, "targetLevel": 90}
    result.update(overrides)
    return result


class WeaponExperienceTests(unittest.TestCase):
    def test_4star_total_splits_at_ascension_caps_and_ignores_level_90_sentinel(self):
        report = build_weapon_experience_report(
            observation(), curve_rows(), material_rows(), rulebook(),
            {str(item_id): 0 for item_id in ORE_IDS})
        self.assertEqual(report["experience"]["xpNeeded"], 89 * 400)
        self.assertEqual([(s["fromLevel"], s["toLevel"], s["xp"])
                          for s in report["experience"]["segments"]],
                         [(1, 20, 7600), (20, 40, 8000), (40, 50, 4000),
                          (50, 60, 4000), (60, 70, 4000), (70, 80, 4000),
                          (80, 90, 4000)])
        self.assertTrue(report["experience"]["segments"][1]["requiresAscensionBefore"])
        self.assertEqual(report["breakthroughMora"]["mora"], 150000)
        self.assertEqual(report["levelMora"]["expDerivedSuggestion"], 3560)
        self.assertIsNone(report["levelMora"]["actualCost"])
        self.assertTrue(report["levelMora"]["needsGameFeeVerification"])

    def test_missing_within_level_progress_is_unknown_not_zero(self):
        target = observation()
        target.pop("currentXPIntoLevel")
        report = build_weapon_experience_report(target, curve_rows(), material_rows(), rulebook())
        self.assertEqual(report["status"], "unknown")
        self.assertIsNone(report["experience"]["xpNeeded"])
        self.assertIsNone(report["oreAdvice"]["grossOreSuggestion"])

    def test_current_cap_requires_ascension_before_next_segment(self):
        report = build_weapon_experience_report(
            observation(level=20, cap=20, currentXPIntoLevel=0, targetLevel=25),
            curve_rows(), material_rows(), rulebook())
        self.assertEqual(report["experience"]["xpNeeded"], 5 * 400)
        self.assertEqual(report["experience"]["segments"], [{
            "fromLevel": 20, "toLevel": 25, "xp": 2000, "requiresAscensionBefore": True}])
        self.assertEqual(report["breakthroughMora"]["steps"], [
            {"phase": 1, "fromCap": 20, "toCap": 40, "mora": 5000}])

    def test_partial_progress_is_subtracted_only_from_first_level_segment(self):
        report = build_weapon_experience_report(
            observation(level=38, cap=40, currentXPIntoLevel=150, targetLevel=60),
            curve_rows(), material_rows(), rulebook())
        self.assertEqual(report["experience"]["segments"], [
            {"fromLevel": 38, "toLevel": 40, "xp": 650, "requiresAscensionBefore": False},
            {"fromLevel": 40, "toLevel": 50, "xp": 4000, "requiresAscensionBefore": True},
            {"fromLevel": 50, "toLevel": 60, "xp": 4000, "requiresAscensionBefore": True},
        ])
        self.assertEqual(report["breakthroughMora"]["mora"], 35000)

    def test_rarity_selects_its_own_column(self):
        report = build_weapon_experience_report(
            observation(rarity=3, level=1, cap=20, targetLevel=3),
            curve_rows(), material_rows(), rulebook(rarity=3))
        self.assertEqual(report["experience"]["xpNeeded"], 600)

    def test_ore_overflow_is_separate_and_only_fixed_ore_ids_are_suggested(self):
        report = build_weapon_experience_report(
            observation(level=1, cap=20, currentXPIntoLevel=0, targetLevel=2),
            curve_rows(), material_rows(), rulebook(),
            {"104011": 0, "104012": 0, "104013": 0})
        gross = report["oreAdvice"]["grossOreSuggestion"]
        self.assertEqual(gross, {"counts": {"104011": 1, "104012": 0, "104013": 0},
                                 "xp": 400, "overflowXp": 0})
        self.assertEqual(set(gross["counts"]), {"104011", "104012", "104013"})
        self.assertEqual(report["oreAdvice"]["additionalOreSuggestion"], gross)
        self.assertEqual(report["levelMora"]["expDerivedSuggestion"], 40)

    def test_exact_inventory_is_required_for_ore_shortfall_advice(self):
        report = build_weapon_experience_report(
            observation(targetLevel=2), curve_rows(), material_rows(), rulebook(),
            {"104011": 4, "104012": 1})
        self.assertEqual(report["oreAdvice"]["status"], "unknown")
        self.assertIsNone(report["oreAdvice"]["shortfallXp"])

    def test_ore_mix_reports_overflow_without_folding_it_into_weapon_xp(self):
        report = build_weapon_experience_report(
            observation(level=1, cap=20, currentXPIntoLevel=0, targetLevel=3),
            curve_rows(), material_rows(), rulebook(),
            {"104011": 0, "104012": 0, "104013": 0})
        # 800 required XP; the exact fixed-ore recommendation is two base ores.
        self.assertEqual(report["experience"]["xpNeeded"], 800)
        self.assertEqual(report["oreAdvice"]["grossOreSuggestion"],
                         {"counts": {"104011": 2, "104012": 0, "104013": 0},
                          "xp": 800, "overflowXp": 0})

    def test_target_already_reached_does_not_require_level_xp(self):
        report = build_weapon_experience_report(
            observation(level=20, cap=20, currentXPIntoLevel=0, targetLevel=20),
            curve_rows(), material_rows(), rulebook())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["experience"]["xpNeeded"], 0)

    def test_invalid_rarity_cap_and_xp_values_fail_closed(self):
        with self.assertRaises(WeaponPlanError):
            build_weapon_experience_report(observation(rarity=6), curve_rows(), material_rows(), rulebook())
        with self.assertRaises(WeaponPlanError):
            build_weapon_experience_report(observation(level=21, cap=20), curve_rows(), material_rows(), rulebook())
        with self.assertRaises(WeaponPlanError):
            build_weapon_experience_report(observation(currentXPIntoLevel=400), curve_rows(), material_rows(), rulebook())


if __name__ == "__main__":
    unittest.main()
