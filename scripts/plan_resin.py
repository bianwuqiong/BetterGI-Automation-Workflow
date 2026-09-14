#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure, fail-closed resin planning for the BetterGI daily runner.

The command line only previews a plan (or writes that report). It never
changes BetterGI's OneDragon configuration. The runner applies configPatch.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

ROOT = Path(__file__).resolve().parent.parent
LEVEL_COSTS = {2: {"blue": 3}, 3: {"purple": 2}, 4: {"purple": 4},
               5: {"purple": 6}, 6: {"purple": 9}, 7: {"gold": 4},
               8: {"gold": 6}, 9: {"gold": 12}, 10: {"gold": 16}}
TIERS = ("blue", "purple", "gold")
TIER_BOOK = {"blue": "的教导", "purple": "的指引", "gold": "的哲学"}
WEEKDAY_NAMES = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")


class PlanError(ValueError):
    pass


def _server_time(now: datetime, utc_offset_hours: int) -> datetime:
    if not isinstance(now, datetime):
        raise PlanError("now must be a datetime")
    try:
        offset = int(utc_offset_hours)
    except (TypeError, ValueError) as exc:
        raise PlanError("utc_offset_hours must be an integer") from exc
    tz = timezone(timedelta(hours=offset))
    return now.replace(tzinfo=tz) if now.tzinfo is None else now.astimezone(tz)


def game_weekday(now: datetime, *, reset_hour: int = 4,
                 utc_offset_hours: int = 8) -> Tuple[int, datetime]:
    """Return (Sunday=0 weekday, effective server datetime)."""
    if not isinstance(reset_hour, int) or not 0 <= reset_hour <= 23:
        raise PlanError("reset_hour must be in 0..23")
    server_now = _server_time(now, utc_offset_hours)
    effective = server_now - timedelta(days=1) if server_now.hour < reset_hour else server_now
    return (effective.weekday() + 1) % 7, effective


def talent_needs(talents: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Return direct book requirements for the supplied talent upgrades."""
    need = {tier: 0 for tier in TIERS}
    for talent in talents or []:
        if not isinstance(talent, dict):
            raise PlanError("each talent must be an object")
        current = _integer(talent.get("current", 1), "talent current")
        target = _integer(talent.get("target", current), "talent target")
        if not 1 <= current <= 10 or not 1 <= target <= 10 or target < current:
            raise PlanError("talent levels must satisfy 1 <= current <= target <= 10")
        for level in range(current + 1, target + 1):
            for tier, amount in LEVEL_COSTS.get(level, {}).items():
                need[tier] += amount
    return need


def _series(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value[1:-1].strip() if value.startswith("「") and value.endswith("」") else value


def _book_name(series: str, tier: str) -> str:
    return "「{}」{}".format(series, TIER_BOOK[tier])


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise PlanError("{} must be an integer".format(label))
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PlanError("{} must be an integer".format(label)) from exc
    if isinstance(value, float) and result != value:
        raise PlanError("{} must be an integer".format(label))
    return result


def _read_inventory(progress: Dict[str, Any]) -> Dict[str, int]:
    if not isinstance(progress, dict):
        raise PlanError("progress must be an object")
    books = progress.get("books", {})
    if not isinstance(books, dict):
        raise PlanError("progress.books must be an object")
    checked = {}
    for name, count in books.items():
        quantity = _integer(count, "inventory for {!r}".format(name))
        if quantity < 0:
            raise PlanError("inventory for {!r} cannot be negative".format(name))
        checked[name] = quantity
    return checked


def _crafting_suggestions(series: str, need: Dict[str, int], have: Dict[str, int]) -> Dict[str, Any]:
    """Suggest only conversions of books not reserved for direct demand."""
    direct = {tier: max(0, need[tier] - have[tier]) for tier in TIERS}
    spare_blue = max(0, have["blue"] - need["blue"])
    # Meet direct purple demand first. This reserves lower tiers required by
    # other goals before suggesting any conversion for gold.
    direct_purple_from_blue = min(direct["purple"], spare_blue // 3)
    spare_blue -= direct_purple_from_blue * 3
    remaining_purple_shortage = direct["purple"] - direct_purple_from_blue
    spare_purple = max(0, have["purple"] + direct_purple_from_blue - need["purple"])
    gold_to_make = min(direct["gold"], (spare_purple + spare_blue // 3) // 3)
    purple_from_stock = min(spare_purple, gold_to_make * 3)
    purple_from_blue_for_gold = gold_to_make * 3 - purple_from_stock
    total_purple_from_blue = direct_purple_from_blue + purple_from_blue_for_gold
    actions = []
    if total_purple_from_blue:
        actions.append({"from": _book_name(series, "blue"), "to": _book_name(series, "purple"),
                        "inputCount": total_purple_from_blue * 3, "outputCount": total_purple_from_blue})
    if gold_to_make:
        actions.append({"from": _book_name(series, "purple"), "to": _book_name(series, "gold"),
                        "inputCount": gold_to_make * 3, "outputCount": gold_to_make})
    remaining = dict(direct)
    remaining["purple"] = remaining_purple_shortage
    remaining["gold"] -= gold_to_make
    return {"series": series, "directShortage": direct,
            "remainingShortageAfterSuggestedCrafting": remaining, "actions": actions,
            "requiresManualOrSeparateCrafting": bool(actions)}


def _valid_domains(calendar: Dict[str, Any], series: str, weekday: int) -> list[Dict[str, Any]]:
    if not isinstance(calendar, dict) or not isinstance(calendar.get("domains", []), list):
        raise PlanError("calendar.domains must be a list")
    found = []
    for domain in calendar["domains"]:
        if not isinstance(domain, dict) or domain.get("_verified") is not True:
            continue
        days = domain.get("days", [])
        if not isinstance(days, list) or any(not isinstance(day, int) or isinstance(day, bool) or day < 0 or day > 6 for day in days):
            raise PlanError("verified calendar domain days must contain integers in 0..6")
        if _series(domain.get("series")) != series:  # exact, not substring matching
            continue
        if weekday not in days:
            continue
        if isinstance(domain.get("name"), str) and domain["name"].strip():
            found.append(domain)
    return found


def _estimated_runs(shortage: Dict[str, int], average_gold: Any) -> int:
    try:
        average = max(0.5, float(average_gold))
    except (TypeError, ValueError):
        average = 1.5
    if shortage["gold"]:
        return int(math.ceil(shortage["gold"] / average))
    if shortage["purple"]:
        return int(math.ceil(shortage["purple"] / 3.0))
    return int(math.ceil(shortage["blue"] / 3.0)) if shortage["blue"] else 0


def build_plan(goals: Dict[str, Any], calendar: Dict[str, Any], progress: Dict[str, Any], now: datetime,
               *, reset_hour: int = 4, utc_offset_hours: int = 8) -> Dict[str, Any]:
    """Build a side-effect-free daily plan.

    A nonempty ``blockers`` list means the runner must not retain an older
    domain. Suggested crafting changes planning only when both trust flags are
    explicitly true; suggestions never alter inventory.
    """
    if not isinstance(goals, dict):
        raise PlanError("goals must be an object")
    if not isinstance(calendar, dict) or not isinstance(calendar.get("domains", []), list):
        raise PlanError("calendar.domains must be a list")
    for domain in calendar["domains"]:
        if not isinstance(domain, dict) or domain.get("_verified") is not True:
            continue
        if not _series(domain.get("series")) or not isinstance(domain.get("name"), str) or not domain["name"].strip():
            raise PlanError("verified calendar domains require nonempty name and series")
        days = domain.get("days")
        if not isinstance(days, list) or any(not isinstance(day, int) or isinstance(day, bool) or day < 0 or day > 6 for day in days):
            raise PlanError("verified calendar domain days must contain integers in 0..6")
    inventory = _read_inventory(progress)
    weekday, effective = game_weekday(now, reset_hour=reset_hour, utc_offset_hours=utc_offset_hours)
    warnings, blockers, suggestions = [], [], []
    plan = {"gameDate": effective.date().isoformat(), "gameWeekday": WEEKDAY_NAMES[weekday],
            "decision": None, "warnings": warnings, "blockers": blockers,
            "craftingSuggestions": suggestions, "configPatch": None}
    characters = goals.get("characters", [])
    if not isinstance(characters, list):
        raise PlanError("goals.characters must be a list")

    # Aggregate each book series in first-seen order, preventing double use of stock.
    grouped: Dict[str, Dict[str, Any]] = {}
    for character in characters:
        if not isinstance(character, dict):
            raise PlanError("each character must be an object")
        series, talents = _series(character.get("talentSeries")), character.get("talents") or []
        if not series or not talents:
            continue
        group = grouped.setdefault(series, {"need": {tier: 0 for tier in TIERS}, "characters": [], "party": ""})
        needed = talent_needs(talents)
        for tier in TIERS:
            group["need"][tier] += needed[tier]
        group["characters"].append(character.get("name") or series)
        if not group["party"] and isinstance(character.get("talentParty"), str):
            group["party"] = character["talentParty"]

    allow_craft = goals.get("allowBookCrafting") is True
    verified_inventory = progress.get("inventoryVerified") is True
    if not verified_inventory:
        warnings.append("库存未经 inventoryVerified=true 核验；直接库存仅作保守计划依据，合成建议不会影响本次选本。")

    eligible, sunday_problem, unknown_schedule, craft_satisfied = None, None, [], []
    for series, group in grouped.items():
        have = {tier: inventory.get(_book_name(series, tier), 0) for tier in TIERS}
        suggestion = _crafting_suggestions(series, group["need"], have)
        if suggestion["actions"]:
            suggestions.append(suggestion)
        shortage = suggestion["remainingShortageAfterSuggestedCrafting"] if allow_craft and verified_inventory else suggestion["directShortage"]
        if suggestion["actions"]:
            warnings.append("「{}」存在建议合成；{}本次选本使用该折算。".format(series, "已核实库存，" if allow_craft and verified_inventory else "未用于"))
        if not any(shortage.values()):
            if allow_craft and verified_inventory and suggestion["actions"]:
                craft_satisfied.append(series)
            continue
        has_verified_schedule = any(
            isinstance(domain, dict) and domain.get("_verified") is True
            and _series(domain.get("series")) == series
            for domain in calendar.get("domains", [])
        )
        if not has_verified_schedule:
            unknown_schedule.append(series)
            continue
        candidates = _valid_domains(calendar, series, weekday)
        if not candidates:
            continue
        selected, sunday_value = candidates[0], "0"
        if weekday == 0:
            selected = next((d for d in candidates if d.get("sundaySelectionVerified") is True
                             and str(d.get("sundaySelectedValue")) in {"1", "2", "3"}), None)
            if selected is None:
                sunday_problem = "周日「{}」缺书，但缺少已核实的 sundaySelectedValue(1..3)；禁止沿用旧秘境。".format(series)
                continue
            sunday_value = str(selected["sundaySelectedValue"])
        eligible = (series, group, shortage, selected, sunday_value)
        break

    if eligible:
        series, group, shortage, domain, sunday_value = eligible
        plan["decision"] = {"type": "talent-domain", "domain": domain["name"], "party": group["party"],
                            "character": group["characters"], "series": series, "shortage": shortage,
                            "estimatedRunsNeeded": _estimated_runs(shortage, goals.get("avgGoldBooksPerRun", 1.5)),
                            "estimatedRunsAreAdvisory": True,
                            "reason": "「{}」仍有缺口，今天（{}）掉落".format(series, WEEKDAY_NAMES[weekday])}
        plan["configPatch"] = {"DomainName": domain["name"], "PartyName": group["party"],
                               "WeeklyDomainEnabled": False, "SundayEverySelectedValue": sunday_value}
        return plan
    if sunday_problem:
        blockers.append(sunday_problem)
        return plan
    if unknown_schedule:
        blockers.append("缺少仍有需求书系的已核实日历：{}；无法确认今日是否掉落，禁止改刷圣遗物或沿用旧秘境。".format("、".join(unknown_schedule)))
        return plan

    # No runnable talent book today (or all needs met): first configured artifact fallback.
    for character in characters:
        if isinstance(character, dict) and isinstance(character.get("artifactDomain"), str) and character["artifactDomain"].strip():
            domain = character["artifactDomain"].strip()
            party = character.get("artifactParty") if isinstance(character.get("artifactParty"), str) else ""
            reason = "天赋需求已满足或今日不掉落，使用推荐圣遗物本"
            if craft_satisfied:
                reason = "{}材料可通过建议合成满足，尚未执行；{}".format("、".join("「{}」".format(s) for s in craft_satisfied), reason)
            plan["decision"] = {"type": "artifact-domain", "domain": domain, "party": party,
                                "character": character.get("name") or domain,
                                "reason": reason,
                                "estimatedRunsAreAdvisory": True}
            plan["configPatch"] = {"DomainName": domain, "PartyName": party,
                                   "WeeklyDomainEnabled": False, "SundayEverySelectedValue": "0"}
            return plan
    blockers.append("没有可安全执行的天赋本或圣遗物本决策；禁止沿用旧秘境配置。")
    return plan


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError("无法读取 {}: {}".format(path, exc)) from exc
    if not isinstance(value, dict):
        raise PlanError("{} 顶层必须是 JSON object".format(path))
    return value


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlanError("--now 必须为 ISO-8601 时间") from exc


def main(argv: list[str] | None = None) -> int:
    # Windows console code pages otherwise corrupt JSON Chinese text. Keep this
    # in CLI only so callers of build_plan/tests do not mutate host streams.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="预览 BetterGI 树脂计划；不修改一条龙配置")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--now", help="ISO-8601 时间；无时区时按服务器时区解释")
    parser.add_argument("--output", type=Path, help="可选 JSON 报告输出路径")
    parser.add_argument("--reset-hour", type=int, default=4)
    parser.add_argument("--utc-offset-hours", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        plan = build_plan(load_json(root / "config" / "goals.json"),
                          load_json(root / "config" / "domain-calendar.json"),
                          load_json(root / "config" / "book-progress.json"), _parse_now(args.now),
                          reset_hour=args.reset_hour, utc_offset_hours=args.utc_offset_hours)
        rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 3 if plan["blockers"] else 0
    except PlanError as exc:
        sys.stderr.write("[plan_resin] 配置错误: {}\n".format(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
