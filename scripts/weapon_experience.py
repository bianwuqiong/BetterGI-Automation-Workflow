#!/usr/bin/env python3
"""Read-only weapon XP planning. This module never controls the game."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DATA = ROOT / "state" / "private-resource-data"
SOURCE_COMMIT = "792978e5503ecfba73dcb3562ed44a0d35a2abe2"
SOURCE_HASHES = {
    "WeaponLevelExcelConfigData.json": "d4c79367e957aac520957f9485e4d2cdd03f48aa58f0da44138235b83c310a0c",
    "MaterialExcelConfigData.json": "a0691209b2cfb50d2bf15fb06900740105d15901ebd7bb43da833922f0652319",
}
ORE_IDS = (104011, 104012, 104013)
LEVEL_CAPS = (20, 40, 50, 60, 70, 80, 90)
ASCENSION_OLD_CAPS = (20, 40, 50, 60, 70, 80)
MAX_LEVEL_BY_RARITY = {1: 70, 2: 70, 3: 90, 4: 90, 5: 90}


class WeaponPlanError(ValueError):
    """Invalid or inconsistent evidence; never replaced with guessed values."""


def _integer(value: Any, low: int, high: int, field: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise WeaponPlanError(f"{field} must be an integer in {low}..{high}")
    return value


def _json_bytes(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WeaponPlanError(f"cannot read valid data: {path.name}") from error


def load_private_sources(directory: Path = PRIVATE_DATA) -> tuple[list[dict], list[dict]]:
    """Load both pinned files and fail if either raw-byte hash has changed."""
    loaded = {}
    for filename, expected_hash in SOURCE_HASHES.items():
        path = directory / filename
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise WeaponPlanError(f"pinned private source is missing: {filename}") from error
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected_hash:
            raise WeaponPlanError(f"pinned private source SHA-256 mismatch: {filename}")
        try:
            loaded[filename] = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise WeaponPlanError(f"pinned private source is invalid JSON: {filename}") from error
    return loaded["WeaponLevelExcelConfigData.json"], loaded["MaterialExcelConfigData.json"]


def _curve_map(rows: list[dict], rarity: int) -> dict[int, int]:
    if not isinstance(rows, list) or len(rows) != 90:
        raise WeaponPlanError("weapon XP table must contain exactly 90 level rows")
    result = {}
    for expected_level, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("level") != expected_level:
            raise WeaponPlanError("weapon XP table levels must be unique and ordered 1..90")
        values = row.get("requiredExps")
        if not isinstance(values, list) or len(values) != 5:
            raise WeaponPlanError(f"invalid requiredExps at weapon level {expected_level}")
        amount = values[rarity - 1]
        if type(amount) is not int or amount <= 0:
            raise WeaponPlanError(f"invalid XP threshold at weapon level {expected_level}")
        result[expected_level] = amount
    # The source row for level 90 is a terminal 90->91 sentinel. It is never
    # included in a plan; its value only acts as the Lv.90 progress display cap.
    return result


def _ore_values(rows: list[dict]) -> dict[int, int]:
    if not isinstance(rows, list):
        raise WeaponPlanError("material data must be a list")
    values = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("id") not in ORE_IDS:
            continue
        item_id = row["id"]
        if row.get("materialType") != "MATERIAL_WEAPON_EXP_STONE":
            raise WeaponPlanError(f"material {item_id} is not weapon XP ore")
        uses = row.get("itemUse")
        first = uses[0] if isinstance(uses, list) and uses else {}
        params = first.get("useParam") if isinstance(first, dict) else None
        if first.get("useOp") != "ITEM_USE_ADD_WEAPON_EXP" or not isinstance(params, list) or not params:
            raise WeaponPlanError(f"material {item_id} lacks its weapon XP use rule")
        try:
            value = int(params[0])
        except (TypeError, ValueError) as error:
            raise WeaponPlanError(f"material {item_id} has invalid weapon XP value") from error
        if value <= 0 or str(value) != str(params[0]):
            raise WeaponPlanError(f"material {item_id} has invalid weapon XP value")
        values[item_id] = value
    if set(values) != set(ORE_IDS):
        raise WeaponPlanError("all three fixed weapon ore definitions are required")
    return values


def _breakthrough_costs(weapon_name: str, rarity: int, current_cap: int,
                        target_level: int, rulebook: dict) -> dict:
    weapon = rulebook.get("weapons", {}).get(weapon_name)
    if not isinstance(weapon, dict) or weapon.get("rarity") != rarity:
        return {"status": "unknown", "mora": None, "steps": [],
                "reason": "weapon ascension definition missing or rarity disagrees"}
    costs = weapon.get("ascensionCosts")
    if not isinstance(costs, dict):
        return {"status": "unknown", "mora": None, "steps": [],
                "reason": "weapon ascension costs missing"}
    steps = []
    for phase, old_cap in enumerate(ASCENSION_OLD_CAPS, 1):
        new_cap = old_cap + 20 if old_cap < 40 else old_cap + 10
        if old_cap < current_cap or old_cap >= target_level:
            continue
        raw_costs = costs.get(f"ascend{phase}")
        if not isinstance(raw_costs, list):
            return {"status": "unknown", "mora": None, "steps": [],
                    "reason": f"ascension cost ascend{phase} missing"}
        mora_rows = [row for row in raw_costs if isinstance(row, dict) and row.get("id") == 202]
        if len(mora_rows) != 1 or type(mora_rows[0].get("count")) is not int:
            return {"status": "unknown", "mora": None, "steps": [],
                    "reason": f"ascension mora ascend{phase} missing or ambiguous"}
        steps.append({"phase": phase, "fromCap": old_cap, "toCap": new_cap,
                      "mora": mora_rows[0]["count"]})
    return {"status": "exact", "mora": sum(row["mora"] for row in steps), "steps": steps}


def _experience_segments(current_level: int, current_xp: int, target_level: int,
                         current_cap: int, curve: dict[int, int]) -> tuple[list[dict], int]:
    segments = []
    cursor = current_level
    first = True
    for end_level in LEVEL_CAPS:
        if end_level <= cursor or end_level > target_level:
            continue
        exp = sum(curve[level] for level in range(cursor, end_level))
        if first:
            exp -= current_xp
            first = False
        segments.append({"fromLevel": cursor, "toLevel": end_level, "xp": exp,
                         "requiresAscensionBefore": cursor in ASCENSION_OLD_CAPS and cursor < target_level})
        cursor = end_level
    if cursor < target_level:
        exp = sum(curve[level] for level in range(cursor, target_level))
        if first:
            exp -= current_xp
        segments.append({"fromLevel": cursor, "toLevel": target_level, "xp": exp,
                         "requiresAscensionBefore": cursor in ASCENSION_OLD_CAPS and cursor < target_level})
    return segments, sum(segment["xp"] for segment in segments)


def _ore_mix(xp: int, values: dict[int, int]) -> dict:
    """Suggest fixed ore IDs only; the 400-XP ore bounds any overfill."""
    counts = {item_id: 0 for item_id in ORE_IDS}
    if xp <= 0:
        return {"counts": {str(key): 0 for key in ORE_IDS}, "xp": 0, "overflowXp": 0}
    smallest = values[104011]
    units = (xp + smallest - 1) // smallest
    for item_id in (104013, 104012, 104011):
        counts[item_id], units = divmod(units, values[item_id] // smallest)
    offered = sum(counts[key] * values[key] for key in ORE_IDS)
    return {"counts": {str(key): counts[key] for key in ORE_IDS},
            "xp": offered, "overflowXp": offered - xp}


def _ore_advice(xp: int, ore_values: dict[int, int], inventory: Any) -> dict:
    if not isinstance(inventory, dict) or any(str(item_id) not in inventory for item_id in ORE_IDS):
        return {"status": "unknown", "reason": "exact counts for all three ore IDs are required",
                "grossOreSuggestion": None, "additionalOreSuggestion": None,
                "inventoryXp": None, "shortfallXp": None}
    exact = {item_id: _integer(inventory[str(item_id)], 0, 10**9, f"oreInventory[{item_id}]")
             for item_id in ORE_IDS}
    inventory_xp = sum(exact[item_id] * ore_values[item_id] for item_id in ORE_IDS)
    shortfall = max(0, xp - inventory_xp)
    return {"status": "exact", "inventoryCounts": {str(k): exact[k] for k in ORE_IDS},
            "inventoryXp": inventory_xp, "shortfallXp": shortfall,
            "grossOreSuggestion": _ore_mix(xp, ore_values),
            "additionalOreSuggestion": _ore_mix(shortfall, ore_values),
            "note": "advisory only; preserves each ore ID and does not convert or consume items"}


def build_weapon_experience_report(observation: dict, curve_rows: list[dict],
                                   material_rows: list[dict], rulebook: dict,
                                   ore_inventory: Any = None) -> dict:
    """Calculate observed weapon level XP needs; no game access or authorization."""
    if not isinstance(observation, dict):
        raise WeaponPlanError("observation must be an object")
    name = observation.get("weaponName")
    if not isinstance(name, str) or not name.strip():
        raise WeaponPlanError("weaponName is required")
    rarity = _integer(observation.get("rarity"), 1, 5, "rarity")
    max_level = MAX_LEVEL_BY_RARITY[rarity]
    current_level = _integer(observation.get("level"), 1, max_level, "level")
    current_cap = _integer(observation.get("cap"), 20, max_level, "cap")
    target = _integer(observation.get("targetLevel"), 1, max_level, "targetLevel")
    if current_cap not in LEVEL_CAPS or current_level > current_cap:
        raise WeaponPlanError("observed current cap is invalid for this weapon level")
    if target < current_level:
        raise WeaponPlanError("target level cannot be lower than observed weapon level")
    ascension = _breakthrough_costs(name.strip(), rarity, current_cap, target, rulebook)
    if target <= current_level:
        return {"schemaVersion": 1, "status": "complete", "readOnly": True,
                "weapon": {"name": name.strip(), "rarity": rarity, "level": current_level,
                           "cap": current_cap, "targetLevel": target},
                "experience": {"status": "exact", "xpNeeded": 0, "segments": []},
                "levelMora": {"actualCost": None, "expDerivedSuggestion": 0,
                              "needsGameFeeVerification": True, "formula": "ceil(xpNeeded / 10)"},
                "breakthroughMora": ascension,
                "oreAdvice": {"status": "unknown", "reason": "target already reached"}}
    xp_into_level = observation.get("currentXPIntoLevel")
    if xp_into_level is None:
        return {"schemaVersion": 1, "status": "unknown", "readOnly": True,
                "weapon": {"name": name.strip(), "rarity": rarity, "level": current_level,
                           "cap": current_cap, "targetLevel": target},
                "experience": {"status": "unknown", "xpNeeded": None, "segments": [],
                               "reason": "currentXPIntoLevel was not observed; it cannot default to zero"},
                "levelMora": {"actualCost": None, "expDerivedSuggestion": None,
                              "needsGameFeeVerification": True, "formula": "ceil(xpNeeded / 10)"},
                "breakthroughMora": ascension,
                "oreAdvice": {"status": "unknown", "grossOreSuggestion": None,
                              "additionalOreSuggestion": None, "reason": "weapon XP is unknown"}}
    curve = _curve_map(curve_rows, rarity)
    xp_upper = 0 if current_level == current_cap else curve[current_level] - 1
    xp_into_level = _integer(xp_into_level, 0, xp_upper, "currentXPIntoLevel")
    ore_values = _ore_values(material_rows)
    segments, xp_needed = _experience_segments(current_level, xp_into_level, target,
                                                 current_cap, curve)
    return {"schemaVersion": 1, "status": "ready" if ascension["status"] == "exact" else "unknown",
            "readOnly": True,
            "weapon": {"name": name.strip(), "rarity": rarity, "level": current_level,
                       "cap": current_cap, "targetLevel": target,
                       "currentXPIntoLevel": xp_into_level,
                       "xpForNextLevel": curve[current_level]},
            "experience": {"status": "exact", "xpNeeded": xp_needed, "segments": segments,
                           "terminalSentinelExcluded": True},
            "levelMora": {"actualCost": None, "expDerivedSuggestion": math.ceil(xp_needed / 10),
                          "needsGameFeeVerification": True, "formula": "ceil(xpNeeded / 10)",
                          "note": "formula-derived advice only; game fee has not been observed"},
            "breakthroughMora": ascension,
            "oreAdvice": _ore_advice(xp_needed, ore_values, ore_inventory),
            "executionAuthorization": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview read-only weapon XP requirements")
    parser.add_argument("--weapon-name", required=True)
    parser.add_argument("--rarity", type=int, required=True)
    parser.add_argument("--level", type=int, required=True)
    parser.add_argument("--cap", type=int, required=True)
    parser.add_argument("--target-level", type=int, required=True)
    parser.add_argument("--current-xp-into-level", type=int)
    parser.add_argument("--ore-inventory-json", help="JSON object with exact counts for 104011/104012/104013")
    parser.add_argument("--source-dir", type=Path, default=PRIVATE_DATA)
    parser.add_argument("--rulebook", type=Path, default=ROOT / "bgi-scripts" / "AutoGameCultivation" /
                        "upstream" / "data" / "rulebook.json")
    args = parser.parse_args(argv)
    try:
        curves, materials = load_private_sources(args.source_dir)
        rulebook = _json_bytes(args.rulebook)
        inventory = json.loads(args.ore_inventory_json) if args.ore_inventory_json is not None else None
        observation = {"weaponName": args.weapon_name, "rarity": args.rarity,
                       "level": args.level, "cap": args.cap,
                       "currentXPIntoLevel": args.current_xp_into_level,
                       "targetLevel": args.target_level}
        report = build_weapon_experience_report(observation, curves, materials, rulebook, inventory)
    except (WeaponPlanError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "readOnly": True, "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
