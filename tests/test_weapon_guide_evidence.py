from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.weapon_guide_evidence import verify_weapon_guide_inventory

BASE = 1791475200000
MATERIAL = "高塔孤王的碎梦"


def ocr(text, x=110, y=120, width=100, height=20):
    return dict(text=text, x=x, y=y, width=width, height=height)


def fixture(count=0, combined=False):
    def context(offset):
        return {"observedAt": BASE + offset, "contextRows": {
            "characterName": [ocr("梦见月瑞希")], "weaponName": [ocr("讨龙英杰谭")],
            "targetLevel": [ocr("升级至Lv.90")],
        }}
    def tooltip(offset):
        rows = [ocr(MATERIAL)]
        rows += ([ocr(f"培养需求{count}/9", y=220)] if combined else
                 [ocr("培养需求", y=220), ocr(f"{count}/9", x=250, y=220)])
        rows += [ocr("可合成数量", y=300), ocr("2", x=250, y=300)]
        return {"observedAt": BASE + offset,
                "tooltipRegion": dict(x=100, y=100, width=400, height=400), "tooltipRows": rows}
    evidence = {"session": {"before": [context(100), context(300)],
                           "after": [context(1000), context(1200)],
                           "characterName": "梦见月瑞希", "weaponName": "讨龙英杰谭", "targetLevel": 90},
                "tooltip": [tooltip(500), tooltip(700)], "materialId": "114004", "required": 9}
    row = {"name": MATERIAL, "count": count, "status": "exact", "verified": True,
           "source": "character_weapon_guide_tooltip", "evidence": evidence}
    return {"raw_inventory": {"114004": row},
            "profile": {"characterName": "梦见月瑞希", "weapon": {"name": "讨龙英杰谭"}},
            "target": {"weaponTargetLevel": 90}, "requirements": {"114004": 9},
            "materials": {"114004": {"name": MATERIAL}}, "started_at": BASE, "finished_at": BASE + 2000}


class WeaponGuideEvidenceTests(unittest.TestCase):
    def verify(self, data):
        return verify_weapon_guide_inventory(**data)

    def test_zero_and_positive_combined_and_separate_ratios(self):
        for count in (0, 15):
            for combined in (False, True):
                with self.subTest(count=count, combined=combined):
                    data = fixture(count, combined)
                    original = copy.deepcopy(data)
                    self.assertIsNone(self.verify(data))
                    self.assertEqual(data, original)

    def test_flags_are_not_evidence(self):
        data = fixture()
        row = data["raw_inventory"]["114004"]
        row["verified"] = False
        self.verify(data)
        row["verified"] = True
        row["count"] = 2
        with self.assertRaises(ValueError):
            self.verify(data)
        row["count"] = 0
        row["evidence"] = {}
        with self.assertRaises(ValueError):
            self.verify(data)

    def test_unknown_and_other_sources_are_not_promoted_or_changed(self):
        data = fixture()
        row = data["raw_inventory"]["114004"]
        row.update(status="unknown", count=None, evidence=None)
        self.verify(data)
        row["count"] = 0
        with self.assertRaises(ValueError):
            self.verify(data)
        row["source"] = "old_bag_scan"
        original = copy.deepcopy(data)
        self.verify(data)
        self.assertEqual(data, original)

    def test_material_requirement_and_session_identity_mismatches(self):
        mutations = [lambda d, r: r["evidence"].update(materialId="114003"),
                     lambda d, r: r["evidence"].update(required=8),
                     lambda d, r: d["requirements"].update({"114004": 8}),
                     lambda d, r: d["materials"]["114004"].update(name="其他材料"),
                     lambda d, r: r.update(name="其他材料"),
                     lambda d, r: r["evidence"]["session"].update(weaponName="其他武器"),
                     lambda d, r: r["evidence"]["session"].update(characterName="钟离"),
                     lambda d, r: r["evidence"]["session"].update(targetLevel=80),
                     lambda d, r: r.update(mainUiRestored=False)]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                data = fixture()
                mutate(data, data["raw_inventory"]["114004"])
                with self.assertRaises(ValueError):
                    self.verify(data)

    def test_character_weapon_and_target_changes_in_each_context_frame(self):
        for group in ("before", "after"):
            for index in (0, 1):
                for field in ("characterName", "weaponName", "targetLevel"):
                    with self.subTest(group=group, index=index, field=field):
                        data = fixture()
                        frame = data["raw_inventory"]["114004"]["evidence"]["session"][group][index]
                        frame["contextRows"][field][0]["text"] = "错误上下文"
                        with self.assertRaises(ValueError):
                            self.verify(data)

    def test_timestamp_bounds_order_duration_and_independence(self):
        for location, value in (("before0", BASE - 1), ("before1", BASE + 150),
                                ("before1", BASE + 5101), ("after0", BASE + 600),
                                ("after1", BASE + 1050), ("after1", BASE + 6101),
                                ("tooltip0", BASE + 200), ("tooltip1", BASE + 550),
                                ("tooltip1", BASE + 5501), ("after1", BASE + 2001)):
            with self.subTest(location=location, value=value):
                data = fixture()
                e = data["raw_inventory"]["114004"]["evidence"]
                group, index = location[:-1], int(location[-1])
                (e["tooltip"] if group == "tooltip" else e["session"][group])[index]["observedAt"] = value
                with self.assertRaises(ValueError):
                    self.verify(data)
        data = fixture()
        data["finished_at"] = BASE + 130000
        after = data["raw_inventory"]["114004"]["evidence"]["session"]["after"]
        after[0]["observedAt"], after[1]["observedAt"] = BASE + 120100, BASE + 120300
        with self.assertRaises(ValueError):
            self.verify(data)

    def test_iso_report_interval(self):
        data = fixture()
        from datetime import datetime, timezone
        data["started_at"] = datetime.fromtimestamp(BASE / 1000, timezone.utc).isoformat()
        data["finished_at"] = datetime.fromtimestamp((BASE + 2000) / 1000, timezone.utc).isoformat()
        self.verify(data)
        data["started_at"] = "2026-10-09T00:00:00"
        with self.assertRaises(ValueError):
            self.verify(data)

    def test_craft_count_is_ignored_and_ambiguous_demand_rejected(self):
        for mutation in ("missing", "multi", "baseline", "left", "changed", "wrong_required", "duplicate_label"):
            with self.subTest(mutation=mutation):
                data = fixture()
                frames = data["raw_inventory"]["114004"]["evidence"]["tooltip"]
                rows = frames[0]["tooltipRows"]
                if mutation == "missing":
                    rows.pop(2)
                elif mutation == "multi":
                    rows.append(ocr("2/9", x=350, y=220))
                elif mutation == "baseline":
                    rows[2]["y"] = 260
                elif mutation == "left":
                    rows[2]["x"] = 100
                elif mutation == "changed":
                    rows[2]["text"] = "2/9"
                elif mutation == "wrong_required":
                    rows[2]["text"] = "0/8"
                else:
                    rows.append(ocr("培养需求", y=350))
                with self.assertRaises(ValueError):
                    self.verify(data)

    def test_material_title_uniqueness_full_name_and_above_demand(self):
        for mode in ("duplicate", "partial", "lower"):
            data = fixture()
            rows = data["raw_inventory"]["114004"]["evidence"]["tooltip"][0]["tooltipRows"]
            if mode == "duplicate":
                rows.append(ocr(MATERIAL, y=150))
            elif mode == "partial":
                rows[0]["text"] = MATERIAL[:-1]
            else:
                rows[0]["y"] = 220
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.verify(data)

    def test_popover_title_can_be_below_search_roi_upper_quarter(self):
        data = fixture()
        for frame in data["raw_inventory"]["114004"]["evidence"]["tooltip"]:
            frame["tooltipRegion"]["height"] = 840
            for row in frame["tooltipRows"]:
                row["y"] += 300
        self.verify(data)

    def test_nonfinite_boolean_and_invalid_geometry_are_rejected(self):
        for value in (True, float("nan"), float("inf"), -1):
            for field in ("count", "required", "observedAt", "x", "width"):
                with self.subTest(value=value, field=field):
                    data = fixture()
                    row = data["raw_inventory"]["114004"]
                    if field == "count":
                        row[field] = value
                    elif field == "required":
                        row["evidence"][field] = value
                    elif field == "observedAt":
                        row["evidence"]["tooltip"][0][field] = value
                    else:
                        row["evidence"]["tooltip"][0]["tooltipRows"][0][field] = value
                    with self.assertRaises(ValueError):
                        self.verify(data)
        data = fixture()
        data["raw_inventory"]["114004"]["evidence"]["tooltip"][0]["tooltipRows"][0]["x"] = 499
        with self.assertRaises(ValueError):
            self.verify(data)

    def test_unicode_normalization_and_extra_fields(self):
        data = fixture()
        row = data["raw_inventory"]["114004"]
        row["mainUiRestored"] = True
        row["extra"] = {"diagnostic": True}
        for frame in row["evidence"]["tooltip"]:
            frame["tooltipRows"][2]["text"] = "０ ／ ９"
        self.verify(data)


if __name__ == "__main__":
    unittest.main()
