"""Bounded cultivation configuration and independent, read-only evidence checks."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

if __package__:
    from .weapon_guide_evidence import verify_weapon_guide_inventory
    from .backpack_inventory_evidence import verify_backpack_inventory
else:
    from weapon_guide_evidence import verify_weapon_guide_inventory
    from backpack_inventory_evidence import verify_backpack_inventory


TASK_ID = "auto-game-cultivation"
TASK_NAME = "培养材料"
PLUGIN_NAME = "AutoGameCultivation"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
_FLAGS = ("allowDomain", "domainValidated", "domainSingleAttemptVerified", "allowBoss",
          "bossValidated", "allowCrafting", "craftingValidated", "validationMode", "allowRoutes", "allowWeekly",
          "requireZhongliShieldCast", "dailyMode", "dailyDomainReady")
_TARGET_KEYS = {"characterName", "targetLevel", "talentTargets", "includeEquippedWeapon", "weaponTargetLevel"}
_SOURCE_COMMIT = "3f1e938a6dcd5a34642dad03a91488db8d2da40c"


def _integer(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a JSON boolean")
    return value


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _text(value: Any, name: str, maximum: int = 100, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{name} must be a bounded string")
    return value.strip()


def _mode(mode: str) -> str:
    if mode not in ("scan", "execute"):
        raise ValueError("mode must be scan or execute")
    return mode


def _run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid runId")
    return run_id


def _timestamp(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _target(value: Any) -> dict:
    target = _object(value, "target")
    if set(target) != _TARGET_KEYS:
        raise ValueError("target must contain only the five documented fields")
    talents = _object(target.get("talentTargets"), "talentTargets")
    if set(talents) != {"normal", "skill", "burst"}:
        raise ValueError("all three talent targets are required")
    include = _boolean(target.get("includeEquippedWeapon"), "includeEquippedWeapon")
    weapon = target.get("weaponTargetLevel")
    if include:
        weapon = _integer(weapon, 1, 90, "weaponTargetLevel")
    elif weapon is not None:
        _integer(weapon, 1, 90, "weaponTargetLevel")
        weapon = None
    return {
        "characterName": _text(target.get("characterName"), "characterName"),
        "targetLevel": _integer(target.get("targetLevel"), 1, 90, "targetLevel"),
        "talentTargets": {name: _integer(talents[name], 1, 10, name) for name in ("normal", "skill", "burst")},
        "includeEquippedWeapon": include, "weaponTargetLevel": weapon,
    }


def _json_file(path: Path) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))


def load_cultivation_config(path, mode) -> dict:
    """Read a whitelist config; scan never needs resource execution permission."""
    return _normalize_config(_json_file(Path(path)), mode)


def _normalize_config(raw, mode) -> dict:
    _mode(mode)
    raw = _object(raw, "config")
    if set(raw) - {"target", "policy", "executionEnabled"}:
        raise ValueError("unsupported cultivation configuration field")
    enabled = _boolean(raw.get("executionEnabled", False), "executionEnabled")
    if mode == "execute" and not enabled:
        raise ValueError("execute requires executionEnabled=true")
    supplied = _object(raw.get("policy", {}), "policy")
    allowed = set(_FLAGS) | {"maxSteps", "maxMinutes", "reserveOriginalResin", "actualOriginalResin",
        "originalResinBudget", "condensedResinBudget", "domainResin", "resinObservedAt",
        "domainPartyName", "bossPartyName", "strategyName", "fragileResinBudget", "transientResinBudget",
        "allowFragileResin", "allowTransientResin", "bossTimeoutSeconds", "bossTeamName",
        "craftingCountry", "validationScopeId", "validationAttemptedSources"}
    if set(supplied) - allowed:
        raise ValueError("unsupported cultivation policy field")
    policy = {name: _boolean(supplied.get(name, False), name) for name in _FLAGS}
    # The runner derives this fact from the actual global BGI configuration.
    policy["domainSingleAttemptVerified"] = False
    for name in ("allowRoutes", "allowWeekly"):
        if policy[name]:
            raise ValueError(f"{name} is disabled until live validation")
    for name in ("fragileResinBudget", "transientResinBudget"):
        _integer(supplied.get(name, 0), 0, 0, name)
    for name in ("allowFragileResin", "allowTransientResin"):
        if _boolean(supplied.get(name, False), name):
            raise ValueError("fragile/transient resin is forbidden")
    policy["maxSteps"] = _integer(supplied.get("maxSteps", 1), 1, 20, "maxSteps")
    policy["maxMinutes"] = _integer(supplied.get("maxMinutes", 15), 1, 15, "maxMinutes")
    policy["bossTimeoutSeconds"] = _integer(supplied.get("bossTimeoutSeconds", 180), 120, 180, "bossTimeoutSeconds")
    policy["reserveOriginalResin"] = _integer(supplied.get("reserveOriginalResin", 0), 0, 200, "reserveOriginalResin")
    for name, high in (("originalResinBudget", 200), ("condensedResinBudget", 5), ("actualOriginalResin", 200)):
        value = supplied.get(name)
        if value is None and mode == "execute" and name != "actualOriginalResin":
            raise ValueError(f"execute requires an explicit {name}; use 0 when unused")
        policy[name] = None if value is None else _integer(value, 0, high, name)
    resin = supplied.get("domainResin", "original")
    if resin not in ("original", "condensed"):
        raise ValueError("domainResin must be original or condensed")
    policy["domainResin"] = resin
    policy["craftingCountry"] = supplied.get("craftingCountry", "蒙德")
    if policy["craftingCountry"] not in ("蒙德", "璃月"):
        raise ValueError("unsupported crafting country")
    scope = _text(supplied.get("validationScopeId", ""), "validationScopeId", 80, empty=True)
    if scope and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", scope):
        raise ValueError("invalid validationScopeId")
    attempted = supplied.get("validationAttemptedSources", [])
    if not isinstance(attempted, list) or any(item not in ("boss", "domain") for item in attempted) or len(attempted) != len(set(attempted)):
        raise ValueError("invalid validationAttemptedSources")
    policy.update(validationScopeId=scope, validationAttemptedSources=list(attempted))
    if not policy["validationMode"] and not policy["dailyMode"] and (scope or attempted):
        raise ValueError("validation scope is only allowed in validationMode")
    if policy["dailyMode"] and (policy["validationMode"] or not scope or attempted
            or policy["originalResinBudget"] is None or policy["condensedResinBudget"] != 0
            or resin != "original" or policy["allowBoss"] or policy["allowCrafting"] or not policy['requireZhongliShieldCast']):
        raise ValueError("daily scope requires original-only domain claims, no initial-validation/boss/crafting")
    if not policy["dailyMode"] and policy["dailyDomainReady"]:
        raise ValueError("dailyDomainReady requires dailyMode")
    if policy["validationMode"] and (policy["originalResinBudget"] is None or policy["originalResinBudget"] > 60
            or policy["condensedResinBudget"] != 0 or resin != "original"
            or policy["maxSteps"] > 2 or policy["allowCrafting"]):
        raise ValueError("initial validation requires at most 60 original, zero condensed, two steps and no crafting")
    observed = supplied.get("resinObservedAt")
    if observed is not None:
        _timestamp(observed, "resinObservedAt")
    policy["resinObservedAt"] = observed
    for name in ("domainPartyName", "bossPartyName", "strategyName"):
        policy[name] = _text(supplied.get(name, ""), name, empty=True)
    if "bossTeamName" in supplied:
        alias = _text(supplied["bossTeamName"], "bossTeamName", empty=True)
        if policy["bossPartyName"] and policy["bossPartyName"] != alias:
            raise ValueError("conflicting boss team names")
        policy["bossPartyName"] = alias
    return {"target": _target(raw.get("target")), "policy": policy, "executionEnabled": enabled}


def inject_cultivation_task(template) -> dict:
    """Copy the runner template and insert its logical JS task after mail."""
    result = copy.deepcopy(_object(template, "template"))
    definitions = _object(result.get("TaskDefinitions"), "TaskDefinitions")
    enabled = _object(result.get("TaskEnabledList"), "TaskEnabledList")
    order = result.get("TaskOrder")
    if not isinstance(order, list) or any(not isinstance(key, str) for key in order) or len(order) != len(set(order)) or any(key not in definitions or key not in enabled for key in order):
        raise ValueError("invalid TaskOrder")
    if TASK_ID in definitions and definitions[TASK_ID] != TASK_NAME:
        raise ValueError("cultivation task ID collision")
    if any(name == TASK_NAME and key != TASK_ID for key, name in definitions.items()):
        raise ValueError("cultivation task name collision")
    definitions[TASK_ID] = TASK_NAME
    enabled[TASK_ID] = True
    if TASK_ID not in order:
        mail = [index for index, key in enumerate(order) if definitions[key] == "领取邮件"]
        order.insert(mail[0] + 1 if len(mail) == 1 else 0, TASK_ID)
    return result


def build_cultivation_group(run_id, config, mode, global_config) -> dict:
    _run_id(run_id)
    _mode(mode)
    config = _normalize_config(config, mode)
    target = config["target"]
    policy = copy.deepcopy(config["policy"])
    global_config = _object(global_config, "global_config")
    retries = _object(global_config.get("autoDomainConfig", {}), "autoDomainConfig").get("reviveRetryCount")
    policy["domainSingleAttemptVerified"] = type(retries) is int and retries == 1
    return {"Name": "AutoGameCultivation_" + run_id, "Projects": [{
        "Name": TASK_NAME, "FolderName": PLUGIN_NAME, "Type": "Javascript", "Status": "Enabled",
        "Schedule": "Daily", "RunNum": 1, "AllowJsNotification": False,
        "JsScriptSettingsObject": {"runId": run_id, "mode": mode,
            "targetConfigJson": json.dumps(target, ensure_ascii=False),
            "policyJson": json.dumps(policy, ensure_ascii=False)},
    }]}


def _safe_path(path) -> Path:
    """Reject symlinks and Windows junction/reparse ancestors before resolving."""
    absolute = Path(os.path.abspath(path))
    for part in reversed((absolute, *absolute.parents)):
        if os.path.lexists(part):
            stat = part.lstat()
            if part.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
                raise ValueError("symlink/junction/reparse paths are forbidden")
    return absolute.resolve()


def _package_files(root: Path) -> dict[str, bytes]:
    result = {}
    for folder, directories, filenames in os.walk(root, followlinks=False):
        for name in directories:
            _safe_path(Path(folder) / name)
        directories[:] = [name for name in directories if name.lower() != "record"]
        for name in filenames:
            path = _safe_path(Path(folder) / name)
            if not path.is_file() or not path.is_relative_to(root):
                raise ValueError("plugin file is outside package")
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def install_cultivation_plugin(source_dir, bettergi_dir) -> dict:
    """Install once under a caller-held lock; an upgrade needs a prior backup."""
    source = _safe_path(source_dir)
    bettergi = _safe_path(bettergi_dir)
    if not source.is_dir() or not bettergi.is_dir():
        raise ValueError("source and BetterGI directories must exist")
    destination = _safe_path(bettergi / "User" / "JsScript" / PLUGIN_NAME)
    if not destination.is_relative_to(bettergi) or source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("invalid plugin destination")
    files = _package_files(source)
    if "manifest.json" not in files or "main.js" not in files:
        raise ValueError("plugin package requires manifest.json and main.js")
    if destination.exists():
        if not destination.is_dir() or _package_files(destination) != files:
            raise ValueError("plugin upgrade requires a recoverable backup; existing files were not changed")
        return {"installed": False, "unchanged": True, "pluginDirectory": str(destination), "filesCopied": 0}
    for relative, content in files.items():
        path = _safe_path(destination / relative)
        if not path.is_relative_to(destination):
            raise ValueError("plugin file escaped destination")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    return {"installed": True, "unchanged": False, "pluginDirectory": str(destination), "filesCopied": len(files)}


def normalize_calculator_material(material) -> dict:
    """Normalize a supplied response fragment, never fetch an account API."""
    item = _object(material, "material")
    identifier = _integer(item.get("id"), 1, 999999999, "id")
    needed = _integer(item.get("num"), 0, 999999999, "num")
    lacking = _integer(item.get("lack_num"), 0, needed, "lack_num")
    return {"id": identifier, "count": needed - lacking,
            "status": "exact" if lacking > 0 else "lower_bound"}


def _inventory(value: Any) -> dict:
    result = {}
    for identifier, row in _object(value, "inventory").items():
        if not isinstance(identifier, str) or not re.fullmatch(r"[1-9][0-9]{0,8}", identifier):
            raise ValueError("inventory keys must be material IDs")
        row = _object(row, "inventory row")
        status = row.get("status")
        if status not in ("exact", "lower_bound", "unknown"):
            raise ValueError("invalid inventory status")
        count = row.get("count")
        if status == "unknown":
            if count is not None:
                raise ValueError("unknown inventory must have count=null")
        else:
            _integer(count, 0, 999999999, "inventory count")
        clean = {"name": _text(row.get("name"), "material name"), "count": count, "status": status}
        if "reason" in row:
            clean["reason"] = _text(row["reason"], "inventory reason", 1000, empty=True)
        result[identifier] = clean
    return result


def _profile(value: Any, target: dict) -> dict:
    profile = _object(value, "profile")
    if profile.get("characterName") != target["characterName"]:
        raise ValueError("profile character mismatch")
    def progress(raw):
        raw = _object(raw, "progress")
        level = _integer(raw.get("level"), 1, 90, "level")
        limit = _integer(raw.get("limit"), level, 90, "limit")
        if limit not in (20, 40, 50, 60, 70, 80, 90):
            raise ValueError("invalid ascension limit")
        limits = (20, 40, 50, 60, 70, 80, 90)
        index = limits.index(limit)
        if index and level < limits[index - 1]:
            raise ValueError("level contradicts its ascension limit")
        return {"level": level, "limit": limit}
    talents = _object(profile.get("talents"), "talents")
    clean_talents = {}
    for name in ("normal", "skill", "burst"):
        raw = _object(talents.get(name), name)
        display = _integer(raw.get("display"), 1, 13, "display")
        bonus = _boolean(raw.get("hasBonus"), "hasBonus")
        base = _integer(raw.get("base"), 1, 10, "base")
        if base != display - (3 if bonus else 0):
            raise ValueError("talent bonus evidence mismatch")
        clean_talents[name] = {"display": display, "hasBonus": bonus, "base": base}
    weapon = profile.get("weapon")
    if target["includeEquippedWeapon"]:
        weapon = _object(weapon, "weapon")
        weapon = {"name": _text(weapon.get("name"), "weapon name"), **progress(weapon)}
    elif weapon is not None:
        raise ValueError("unexpected weapon scope")
    return {"characterName": target["characterName"], "character": progress(profile.get("character")),
            "talents": clean_talents, "weapon": weapon}


def _public_data(value):
    """Do not propagate arbitrary account/credential fields from a saved file."""
    if isinstance(value, dict):
        return {key: _public_data(item) for key, item in value.items()
                if not any(token in key.lower() for token in ("uid", "cookie", "token", "account", "password", "email"))}
    if isinstance(value, list):
        return [_public_data(item) for item in value]
    return value


def _boss_evidence(step: dict, plugin: Path, policy: dict, material_ids: set[str]) -> None:
    parameters = _object(step.get("parameterEvidence"), "boss parameterEvidence")
    required = {"SpecifyRunCount": True, "RunCount": 1, "UseFragileResin": False,
        "UseTransientResin": False, "ReviveRetryCount": 0, "ReturnToStatueAfterEachRound": False,
        "RewardRecognitionEnabled": True, "Timeout": policy["bossTimeoutSeconds"]}
    for name, value in required.items():
        if type(parameters.get(name)) is not type(value) or parameters[name] != value:
            raise ValueError("boss single-claim parameters differ from safe policy")
    mapping = _object(step.get("mappingEvidence"), "boss mappingEvidence")
    ids = mapping.get("materialIds")
    if not isinstance(ids, list) or any(not isinstance(identifier, str) for identifier in ids) or len(ids) != len(set(ids)) or set(ids) != material_ids:
        raise ValueError("boss material mapping coverage mismatch")
    if mapping.get("source") != "upstream/data/materials.json" or mapping.get("sourceCommit") != _SOURCE_COMMIT or mapping.get("bossName") != step["bossName"]:
        raise ValueError("boss mapping source mismatch")
    materials_path = _safe_path(plugin / "upstream/data/materials.json")
    catalog_path = _safe_path(plugin / "upstream/data/bettergi-boss-catalog.json")
    for path in (materials_path, catalog_path):
        if not path.is_relative_to(plugin) or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("boss static mapping unavailable")
    materials = _object(_json_file(materials_path), "boss material rules")
    catalog = _object(_json_file(catalog_path), "boss catalog")
    if step["bossName"] not in catalog.get("bosses", []):
        raise ValueError("boss is outside supported catalog")
    for identifier in material_ids:
        rule = _object(materials.get(identifier), "boss material rule")
        if rule.get("executionType") != "boss" or rule.get("bossName") != step["bossName"]:
            raise ValueError("boss name does not match unique static material mapping")


def _static_data(plugin: Path, filename: str) -> dict:
    path = _safe_path(plugin / "upstream/data" / filename)
    if not path.is_relative_to(plugin) or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("static material/recipe evidence unavailable")
    return _object(_json_file(path), filename)


def _recipe_chain(identifier: str, recipes: dict) -> set[str]:
    neighbors: dict[str, set[str]] = {}
    for output, recipe in recipes.items():
        for item in recipe.get("inputs", []):
            low = str(item["id"])
            neighbors.setdefault(output, set()).add(low)
            neighbors.setdefault(low, set()).add(output)
    result, pending = set(), [identifier]
    while pending:
        current = pending.pop()
        if current not in result:
            result.add(current)
            pending.extend(neighbors.get(current, ()))
    return result


def _domain_evidence(step: dict, plugin: Path, policy: dict, ids: set[str]) -> None:
    materials = _static_data(plugin, "materials.json")
    recipes = _static_data(plugin, "crafting-recipes.json")
    selected = step.get("sundaySelectedValue", "")
    family = {identifier for identifier, rule in materials.items()
              if rule.get("executionType") == "domain" and rule.get("domainName") == step["domainName"]
              and str(rule.get("sundaySelectedValue", "")) == selected}
    if not family or not ids <= family or any(_recipe_chain(identifier, recipes) != ids for identifier in ids):
        raise ValueError("domain static mapping or complete material chain mismatch")
    start = _timestamp(step.get("startedAt"), "startedAt")
    from datetime import timedelta, timezone
    weekday = (start.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).isoweekday() % 7
    if any(weekday not in materials[identifier].get("openDays", []) for identifier in ids):
        raise ValueError("domain is not open on this game day")
    if weekday == 0 and not re.fullmatch(r"[1-9][0-9]*", selected):
        raise ValueError("Sunday reward selection unverified")
    parameters = step.get("parameterEvidence")
    if parameters is None and not policy["validationMode"] and not policy["dailyMode"] and not policy["requireZhongliShieldCast"]:
        return  # Legacy ordinary reports retain their existing parameter contract.
    parameters = _object(parameters, "domain parameterEvidence")
    required = {"DomainRoundNum": 1, "SpecifyResinUse": True, "AutoArtifactSalvage": False,
                "RewardRecognitionEnabled": True, "DomainName": step["domainName"],
                "PartyName": policy["domainPartyName"], "SundaySelectedValue": selected}
    if policy["requireZhongliShieldCast"]:
        required.update(RequireZhongliShieldCast=True, CombatOnly=False)
    for name in ("OriginalResinUseCount", "OriginalResin20UseCount", "OriginalResin40UseCount",
                 "CondensedResinUseCount", "TransientResinUseCount", "FragileResinUseCount"):
        required[name] = int((name == "OriginalResin20UseCount" and step["resin"] == "original")
                             or (name == "CondensedResinUseCount" and step["resin"] == "condensed"))
    for name, value in required.items():
        if type(parameters.get(name)) is not type(value) or parameters[name] != value:
            raise ValueError("domain parameters differ from single-claim policy")


def _resin_evidence(step: dict, cost: int) -> dict:
    snapshots = []
    for name, reference in (("resinBefore", "startedAt"), ("resinAfter", "finishedAt")):
        raw = _object(step.get(name), name)
        observed = _timestamp(raw.get("observedAt"), "resin observedAt")
        age = (_timestamp(step.get(reference), reference) - observed).total_seconds()
        if raw.get("mainUiRestored") is not True or not 0 <= age <= 120:
            raise ValueError("resin observation stale or main UI not restored")
        clean = {}
        for kind, high in (("original", 200), ("condensed", 5)):
            value = raw.get(kind + "Resin")
            flag = raw.get(kind + "Verified", raw.get("verified"))
            if flag is not True:
                if value is not None:
                    raise ValueError("unverified resin must be null")
                clean[kind] = None
            else:
                clean[kind] = _integer(value, 0, high, kind + "Resin")
        if raw.get("verified") is not (all(value is not None for value in clean.values())):
            raise ValueError("resin overall verification flag mismatch")
        snapshots.append((observed, clean))
    if snapshots[1][0] < snapshots[0][0]:
        raise ValueError("resin observation timestamps reversed")
    delta = {kind: None if snapshots[0][1][kind] is None or snapshots[1][1][kind] is None
             else snapshots[0][1][kind] - snapshots[1][1][kind] for kind in ("original", "condensed")}
    reported = _object(step.get("actualResinDelta"), "actualResinDelta")
    if set(reported) != set(delta) or any(type(reported[k]) is not type(delta[k]) or reported[k] != delta[k] for k in delta):
        raise ValueError("actual resin delta contradicts observed snapshots")
    if step["resin"] == "original":
        valid = delta["original"] is not None and cost - 2 <= delta["original"] <= cost and delta["condensed"] in (None, 0)
    else:
        valid = delta["condensed"] == 1 and (delta["original"] is None or -2 <= delta["original"] <= 0)
    if not valid:
        raise ValueError("actual resin usage differs from configured claim")
    return delta


def _inventory_read_metadata(raw: dict, policy: dict, run_id: str, mode: str) -> list[dict]:
    """Check optional actual same-run snapshots; legacy reports retain their contract."""
    steps = raw['steps']
    present = 'initialInventoryRead' in raw or any(isinstance(s,dict) and ('beforeInventoryRead' in s or 'afterInventoryRead' in s) for s in steps)
    if not present:
        return []
    if (mode!='execute' or not policy['dailyMode'] or policy['domainResin']!='original'
            or any(policy[k] for k in ('allowBoss','allowCrafting','allowRoutes','allowWeekly'))):
        raise ValueError('inventory snapshot reuse metadata is restricted to nonmutating daily original domains')
    report_start=_timestamp(raw.get('startedAt'),'inventory report startedAt')
    report_finish=_timestamp(raw.get('finishedAt'),'inventory report finishedAt')
    def game_day(moment):
        return (moment.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).date()
    authorized_day = game_day(report_start)
    initial=_object(raw.get('initialInventoryRead'),'initialInventoryRead')
    if initial.get('runId')!=run_id:
        raise ValueError('initial inventory snapshot belongs to another run')
    initial_start=_timestamp(initial.get('startedAt'),'initial read startedAt')
    initial_finish=_timestamp(initial.get('finishedAt'),'initial read finishedAt')
    initial_rows=_object(initial.get('inventory'),'initial actual inventory')
    _inventory(initial_rows)
    def evidence_window(rows, first, last):
        def timestamps(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in ('observedAt','clickedAt') and type(item) in (int,float): yield item
                    else: yield from timestamps(item)
            elif isinstance(value,list):
                for item in value: yield from timestamps(item)
        for row in rows.values():
            for observed in timestamps(row.get('evidence')):
                if not first.timestamp()*1000<=observed<=last.timestamp()*1000:
                    raise ValueError('raw inventory frame precedes or exceeds its declared read window')
    if not report_start<=initial_start<=initial_finish<=report_finish:
        raise ValueError('initial inventory read window outside report')
    evidence_window(initial_rows,initial_start,initial_finish)
    for index,step in enumerate(steps):
        step=_object(step,'inventory read step')
        if (step.get('type')!='domain' or step.get('resin')!='original'
                or type(step.get('maxClaims')) is not int or step['maxClaims']!=1):
            raise ValueError('inventory snapshot reuse is not a single original domain claim')
        before=_object(step.get('before'),'actual before inventory')
        read=_object(step.get('beforeInventoryRead'),'beforeInventoryRead')
        started=_timestamp(step.get('startedAt'),'step startedAt')
        used=_timestamp(read.get('usedAt'),'inventory usedAt')
        first=_timestamp(read.get('readStartedAt'),'before read startedAt')
        last=_timestamp(read.get('readFinishedAt'),'before read finishedAt')
        if read.get('runId')!=run_id or not report_start<=first<=last<=used==started<=report_finish:
            raise ValueError('before inventory metadata scope/window/claim time mismatch')
        if any(game_day(moment) != authorized_day for moment in (first, last, used)):
            raise ValueError('before inventory or claim crosses the UTC+8 04:00 game-day boundary')
        source=read.get('source')
        if source=='initial-current-run':
            if index!=0 or first!=initial_start or last!=initial_finish:
                raise ValueError('initial before inventory must be the first current-run read')
            actual=initial_rows
        elif source=='previous-step-after':
            if index==0:
                raise ValueError('previous after inventory is unavailable for first step')
            previous=steps[index-1]
            previous_read=_object(previous.get('afterInventoryRead'),'previous actual after read')
            if (read.get('previousStepId')!=previous.get('stepId') or previous.get('status')!='success'
                    or previous.get('type')!='domain' or previous.get('resin')!='original' or previous.get('maxClaims')!=1
                    or previous.get('domainName')!=step.get('domainName') or previous.get('sundaySelectedValue')!=step.get('sundaySelectedValue')
                    or first!=_timestamp(previous_read.get('startedAt'),'previous read startedAt')
                    or last!=_timestamp(previous_read.get('finishedAt'),'previous read finishedAt')
                    or _timestamp(previous.get('finishedAt'),'previous step finish')>used):
                raise ValueError('before inventory does not come from the adjacent successful original-domain after')
            actual=_object(previous.get('after'),'previous actual after inventory')
            if set(actual)!=set(before):
                raise ValueError('previous actual after does not cover the same complete material family')
        elif source=='fresh-current-run':
            actual=before
            if index and first<_timestamp(steps[index-1].get('finishedAt'),'prior step finish'):
                raise ValueError('fresh before inventory predates preceding step')
        else:
            raise ValueError('before inventory read source unknown')
        if source!='previous-step-after' and 'previousStepId' in read:
            raise ValueError('nonprevious inventory read contains a previous step reference')
        if not before or any(row.get('status')!='exact' for row in before.values()):
            raise ValueError('declared current-run before snapshot is incomplete')
        if source!='fresh-current-run':
            if (used-first).total_seconds()>120:
                raise ValueError('reused inventory oldest observation exceeds120 seconds')
            if any(identifier not in actual or actual[identifier]!=row for identifier,row in before.items()):
                raise ValueError('before raw counts/source differ from the actual same-run snapshot')
        evidence_window(before,first,last)
        after=step.get('after')
        if isinstance(after,dict):
            after_read=_object(step.get('afterInventoryRead'),'afterInventoryRead')
            after_start=_timestamp(after_read.get('startedAt'),'after read startedAt')
            after_finish=_timestamp(after_read.get('finishedAt'),'after read finishedAt')
            if (after_read.get('runId')!=run_id or not started<=after_start<=after_finish<=_timestamp(step.get('finishedAt'),'step finish')<=report_finish):
                raise ValueError('after inventory read scope/window mismatch')
            evidence_window(after,after_start,after_finish)
        elif 'afterInventoryRead' in step or step.get('status')=='success':
            raise ValueError('after inventory read metadata lacks actual observed after inventory')
    return [initial_rows]


def _crafting_evidence(step: dict, plugin: Path, policy: dict, ids: set[str], delta: dict) -> None:
    materials = _static_data(plugin, "materials.json")
    recipes = _static_data(plugin, "crafting-recipes.json")
    identifier = _text(step.get("materialId"), "materialId")
    recipe = _object(recipes.get(identifier), "static recipe")
    q = _integer(step.get("craftCount"), 1, 999999999, "craftCount")
    inputs = recipe.get("inputs")
    if recipe.get("resultCount") != 1 or not isinstance(inputs, list) or len(inputs) != 1 or inputs[0].get("count") != 3:
        raise ValueError("unsupported crafting recipe")
    input_id = str(inputs[0]["id"])
    expected_recipe = {"resultCount": 1, "inputs": [{"id": input_id, "count": 3}]}
    if json.dumps(step.get("recipeEvidence"), sort_keys=True) != json.dumps(expected_recipe, sort_keys=True) or _recipe_chain(identifier, recipes) != ids:
        raise ValueError("crafting static recipe or complete chain mismatch")
    bases = 0
    outputs = {}
    for member in ids:
        if member not in recipes:
            bases += 1
            continue
        member_recipe = recipes[member]
        member_inputs = member_recipe.get('inputs')
        if member_recipe.get('resultCount') != 1 or not isinstance(member_inputs, list) or len(member_inputs) != 1 or member_inputs[0].get('count') != 3:
            raise ValueError("crafting chain contains an unsupported recipe")
        low = str(member_inputs[0]['id'])
        outputs[low] = outputs.get(low, 0) + 1
    if bases != 1 or any(count > 1 for count in outputs.values()):
        raise ValueError("crafting chain is not a finite linear 3:1 chain")
    name = materials.get(identifier, {}).get("name")
    if not name or step.get("materialName") != name or step.get("craftingCountry") != policy["craftingCountry"] or "materialType" not in step or step["materialType"] is not None:
        raise ValueError("crafting target/country mismatch")
    if "confirmedConfiguredResinCost" in step and (type(step["confirmedConfiguredResinCost"]) is not int or step["confirmedConfiguredResinCost"] != 0):
        raise ValueError("crafting must not claim resin spending")
    if delta.get(input_id) != -3*q or not q <= delta.get(identifier, -1) <= 2*q or any(delta[i] != 0 for i in ids - {identifier, input_id}):
        raise ValueError("crafting actual input/output delta mismatch")
    expected = {"Success": True, "MaterialName": name, "TargetQuantity": q, "ActualQuantity": q, "MainUiRestored": True}
    result = _object(step.get("resultEvidence"), "resultEvidence")
    if any(type(result.get(k)) is not type(v) or result[k] != v for k, v in expected.items()) or step.get("materialsSpent") != {input_id: 3*q}:
        raise ValueError("crafting result or materials spent mismatch")
    if not str(step.get("moraCostStatus", "")).startswith("unverified"):
        raise ValueError("unobserved Mora cost cannot be verified")


def verify_cultivation_report(event, bettergi_dir, run_id, mode, expected_target, run_directory, *, expected_policy=None) -> dict:
    """Validate the actual plugin report without writing or declaring target completion."""
    unknown = {"status": "unknown", "reason": "cultivation report unverified", "cultivation": None, "report": None}
    try:
        _run_id(run_id)
        _mode(mode)
        event = _object(event, "event")
        claimed = event.get("claimedStatus", event.get("status"))
        if claimed not in ("success", "failed", "unknown", "blocked"):
            raise ValueError("invalid claimedStatus")
        if event.get("status", claimed) != claimed or event.get("runId") != run_id or event.get("mode") != mode:
            raise ValueError("event scope/status mismatch")
        if event.get("evidenceVerified") is not True or event.get("readOnly") is not (mode == "scan"):
            raise ValueError("event evidence/readOnly mismatch")
        if event.get("reportRelativePath") != f"record/{run_id}.json":
            raise ValueError("report relative path mismatch")
        target = _target(expected_target)
        root = _safe_path(bettergi_dir)
        plugin = _safe_path(root / "User" / "JsScript" / PLUGIN_NAME)
        path = _safe_path(plugin / "record" / f"{run_id}.json")
        archive = _safe_path(run_directory)
        if not plugin.is_relative_to(root) or not path.is_relative_to(plugin) or not archive.is_dir():
            raise ValueError("report/archive path escaped its scope")
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("report missing or too large")
        raw = _object(_json_file(path), "report")
        required = {"schemaVersion", "runId", "mode", "target", "profile", "inventory", "plan",
                    "blockers", "warnings", "steps", "status", "readOnly"}
        if not required <= set(raw) or type(raw["schemaVersion"]) is not int or raw["schemaVersion"] != 1:
            raise ValueError("report schema mismatch")
        if raw["runId"] != run_id or raw["mode"] != mode or raw["status"] != claimed or raw["readOnly"] is not (mode == "scan"):
            raise ValueError("report scope/status mismatch")
        if _target(raw["target"]) != target:
            raise ValueError("report target mismatch")
        policy = _object(raw.get("policy"), "report policy")
        validated_policy = _normalize_config({"target": target, "policy": policy,
            "executionEnabled": mode == "execute"}, mode)["policy"]
        validated_policy["domainSingleAttemptVerified"] = _boolean(policy.get("domainSingleAttemptVerified", False), "domainSingleAttemptVerified")
        if mode == 'execute' and validated_policy['dailyMode'] and not validated_policy['dailyDomainReady'] and (validated_policy['maxSteps'] != 1 or validated_policy['originalResinBudget'] > 20):
            raise ValueError('daily first claim exceeds strict single20 mode')
        if expected_policy is not None:
            expected_policy = _object(expected_policy, "expected_policy")
            canonical_expected = _normalize_config({"target": target, "policy": expected_policy,
                "executionEnabled": mode == "execute"}, mode)["policy"]
            canonical_expected["domainSingleAttemptVerified"] = _boolean(expected_policy.get("domainSingleAttemptVerified", False), "domainSingleAttemptVerified")
            if validated_policy != canonical_expected:
                raise ValueError("report policy differs from this run's policy")
        for name in ("blockers", "warnings", "steps"):
            if not isinstance(raw[name], list):
                raise ValueError(f"report {name} must be an array")
        profile = None if raw["profile"] is None else _profile(raw["profile"], target)
        inventory = _inventory(raw["inventory"])
        plan = raw["plan"]
        if plan is not None:
            plan = _object(plan, "plan")
            requirements = _object(plan.get("requirements"), "requirements")
            for identifier, count in requirements.items():
                if not re.fullmatch(r"[1-9][0-9]{0,8}", identifier):
                    raise ValueError("invalid requirement ID")
                _integer(count, 0, 999999999, "required count")
            crafting = _object(plan.get("crafting"), "crafting")
            if crafting.get("suggestionsOnly") is not True or crafting.get("executed") is not False:
                raise ValueError("crafting must remain suggestions only")
            for name in ("shortages", "manualResources", "domains"):
                if not isinstance(plan.get(name), list):
                    raise ValueError(f"plan {name} must be an array")
        inventories = [raw["inventory"], *_inventory_read_metadata(raw, validated_policy, run_id, mode)]
        for step in raw["steps"]:
            if isinstance(step, dict):
                inventories.extend(step[key] for key in ("before", "after") if isinstance(step.get(key), dict))
        if any(isinstance(row, dict) and row.get('source') == 'backpack_selected_stack' for packet in inventories for row in packet.values()):
            materials = _object(_json_file(plugin / 'upstream/data/materials.json'), 'material data')
            for packet in inventories:
                verify_backpack_inventory(packet, materials=materials, started_at=raw.get('startedAt'), finished_at=raw.get('finishedAt'))
        if any(isinstance(row, dict) and row.get("source") == "character_weapon_guide_tooltip"
               for packet in inventories for row in packet.values()):
            if profile is None or plan is None:
                raise ValueError("weapon guide inventory requires actual profile and plan context")
            materials = _object(_json_file(plugin / "upstream/data/materials.json"), "material data")
            for packet in inventories:
                verify_weapon_guide_inventory(packet, profile=profile, target=target,
                    requirements=requirements, materials=materials,
                    started_at=raw.get("startedAt"), finished_at=raw.get("finishedAt"))
        required_scan_ids = raw.get("requiredScanIds")
        manual_ids = raw.get("manualInventoryIds")
        for identifiers in (required_scan_ids, manual_ids):
            if not isinstance(identifiers, list) or any(not isinstance(item, str) or not re.fullmatch(r"[1-9][0-9]{0,8}", item) for item in identifiers) or len(identifiers) != len(set(identifiers)):
                raise ValueError("scan/manual material IDs must be unique arrays")
        if set(required_scan_ids) & set(manual_ids):
            raise ValueError("scan and manual material scopes overlap")
        if any(identifier not in set(required_scan_ids) | set(manual_ids) for identifier in inventory):
            raise ValueError("inventory is outside declared scan/manual scope")
        status = "failed" if claimed == "failed" else "unknown"
        reason = "verified report retains uncertain or blocked outcome"
        gains: dict[str, int] = {}
        original = condensed = 0
        actual = {"original": 0, "condensed": 0}
        materials_spent = {}
        steps = raw["steps"]
        verified_step_ids = []
        if mode == "scan" and steps:
            raise ValueError("read-only scan contains execution steps")
        if claimed == "success" or mode == "execute" and steps:
            if profile is None or plan is None:
                raise ValueError("scan success or execution steps require profile and plan evidence")
            if mode == "scan":
                uncertain = any(inventory.get(identifier, {}).get("status") != "exact" for identifier in required_scan_ids)
                missing = any(identifier not in set(required_scan_ids) | set(manual_ids) for identifier, count in plan["requirements"].items() if count > 0)
                blocked = any(row.get("code") in ("inventory_unknown", "material_rule_missing") for row in raw["blockers"] if isinstance(row, dict))
                if not uncertain and not missing and not blocked:
                    status, reason = "success", "verified read-only scan export; cultivation target completion not asserted"
            elif steps:
                all_verified = True
                last_after = {}
                attempted = set(validated_policy["validationAttemptedSources"])
                for index, step in enumerate(steps, 1):
                    step = _object(step, "step")
                    kind = step.get("type")
                    if step.get("stepId") != f"{run_id}:step-{index}" or kind not in ("domain", "boss", "crafting") or type(step.get("maxClaims")) is not int or step["maxClaims"] != 1:
                        raise ValueError("unbounded or unrecognized execution step")
                    validation = _boolean(step.get("validationAttempt", False), "validationAttempt")
                    if validation is not validated_policy["validationMode"]:
                        raise ValueError("step initial-validation marker differs from policy")
                    if validation:
                        if kind not in ("boss", "domain") or kind in attempted:
                            raise ValueError("initial-validation source replay forbidden")
                        attempted.add(kind)
                    if step.get("status") != "success":
                        # The operator stops at an uncertain attempt. A later
                        # success would be an unsupported replay across it.
                        if index != len(steps):
                            raise ValueError("execution continued after an uncertain step")
                        all_verified = False
                        continue
                    if kind == "domain":
                        if not validated_policy["allowDomain"] or not validated_policy["domainSingleAttemptVerified"] or not (validated_policy["domainValidated"] or validation or validated_policy["dailyMode"]):
                            raise ValueError("execution policy lacks domain validation")
                        _text(validated_policy["domainPartyName"], "domainPartyName")
                        _text(step.get("domainName"), "domainName")
                    elif kind == "boss":
                        if not validated_policy["allowBoss"] or not (validated_policy["bossValidated"] or validation):
                            raise ValueError("execution policy lacks boss validation")
                        _text(validated_policy["bossPartyName"], "bossPartyName")
                        _text(step.get("bossName"), "bossName")
                    elif not validated_policy["allowCrafting"] or not validated_policy["craftingValidated"] or validation:
                        raise ValueError("execution policy lacks crafting validation")
                    before, after = _inventory(step.get("before")), _inventory(step.get("after"))
                    delta = _object(step.get("delta"), "delta")
                    if not before or set(before) != set(after) or set(before) != set(delta):
                        raise ValueError("step inventory/delta coverage mismatch")
                    if not set(before) <= set(required_scan_ids):
                        raise ValueError("step contains material outside scan scope")
                    if kind == "boss":
                        _boss_evidence(step, plugin, validated_policy, set(before))
                    elif kind == "domain":
                        _domain_evidence(step, plugin, validated_policy, set(before))
                    verified_delta = {}
                    for identifier in before:
                        if before[identifier]["status"] != "exact" or after[identifier]["status"] != "exact":
                            all_verified = False
                            continue
                        difference = after[identifier]["count"] - before[identifier]["count"]
                        _integer(delta[identifier], -999999999 if kind == "crafting" else 0, 999999999, "delta")
                        if (difference < 0 and kind != "crafting") or delta[identifier] != difference:
                            raise ValueError("step gain contradicts before/after")
                        if identifier in last_after and before[identifier] != last_after[identifier]:
                            raise ValueError("execution inventory continuity mismatch")
                        verified_delta[identifier] = difference
                    if len(verified_delta) != len(before) or not any(verified_delta.values()):
                        all_verified = False
                        continue
                    if _timestamp(step.get("finishedAt"), "finishedAt") < _timestamp(step.get("startedAt"), "startedAt"):
                        raise ValueError("step timestamps reversed")
                    resin = step.get("resin")
                    if kind == "domain" and resin != validated_policy["domainResin"] or kind == "boss" and resin != "original":
                        raise ValueError("step resin does not match policy")
                    if kind == "crafting":
                        if resin != "none":
                            raise ValueError("crafting resin must be none")
                        _crafting_evidence(step, plugin, validated_policy, set(before), verified_delta)
                        for identifier, count in verified_delta.items():
                            if count > 0:
                                gains[identifier] = gains.get(identifier, 0) + count
                            elif count < 0:
                                materials_spent[identifier] = materials_spent.get(identifier, 0) - count
                        last_after.update(after)
                        verified_step_ids.append(step["stepId"])
                        continue
                    cost = 40 if kind == "boss" and resin == "original" else 20 if resin == "original" else 1 if resin == "condensed" else None
                    if cost is None or type(step.get("confirmedConfiguredResinCost")) is not int or step["confirmedConfiguredResinCost"] != cost:
                        raise ValueError("step resin evidence mismatch")
                    _text(step.get("resinCostEvidence"), "resinCostEvidence", 1000)
                    observed_delta = _resin_evidence(step, cost)
                    for resin_kind, value in observed_delta.items():
                        actual[resin_kind] = None if value is None or actual[resin_kind] is None else actual[resin_kind] + value
                    original += cost if resin == "original" else 0
                    condensed += cost if resin == "condensed" else 0
                    for identifier, count in verified_delta.items():
                        if count > 0:
                            gains[identifier] = gains.get(identifier, 0) + count
                    last_after.update(after)
                    verified_step_ids.append(step["stepId"])
                if len(steps) > validated_policy["maxSteps"] or original > validated_policy["originalResinBudget"] or condensed > validated_policy["condensedResinBudget"]:
                    raise ValueError("step totals exceed hard execution limits")
                if all_verified and any(inventory.get(identifier) != row for identifier, row in last_after.items()):
                    raise ValueError("final inventory does not match execution evidence")
                if all_verified and claimed == "success":
                    status, reason = "success", "verified bounded step gains; cultivation target completion not asserted"
                elif verified_step_ids:
                    reason = "verified step subtotal retained; uncertain or failed overall outcome is not upgraded"
                spending = raw.get("spending")
                if spending is not None and all_verified:
                    spending = _object(spending, "spending")
                    if spending.get("configuredConfirmedClaims") != {"original": original, "condensed": condensed} or spending.get("actualResinDelta") != actual:
                        raise ValueError("report spending totals contradict independently verified steps")
        if event.get("targetReached", False) is not False or raw.get("targetReached", False) is not False:
            raise ValueError("target completion cannot be asserted by this operator")
        if "completedSteps" in event:
            completed = sum(isinstance(step, dict) and step.get("status") == "success" for step in steps)
            if type(event["completedSteps"]) is not int or event["completedSteps"] != completed:
                raise ValueError("completed step count contradicts report")
        clean_report = _public_data(raw)
        clean_report.update(target=target, profile=profile, inventory=inventory)
        cultivation = {"scope": mode, "mode": mode, "readOnly": mode == "scan", "reportVerified": True,
            "reportPath": str(path), "reportRelativePath": event["reportRelativePath"], "runId": run_id,
            "claimedStatus": claimed, "targetReached": False, "observedGains": gains,
            "configuredConfirmedClaims": {"original": original, "condensed": condensed},
            "actualResinDelta": actual if mode == "execute" and status == "success" else None,
            "confirmedSubtotalOnly": mode == "execute" and status != "success",
            "verifiedStepResinDelta": actual if mode == "execute" and verified_step_ids else None,
            "verifiedStepIds": verified_step_ids,
            "unverifiedStepIds": [step.get("stepId") for step in steps if step.get("stepId") not in verified_step_ids],
            "materialsSpent": materials_spent, "steps": clean_report["steps"]}
        return {"status": status, "reason": reason, "cultivation": cultivation, "report": clean_report}
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as error:
        return {**unknown, "reason": f"cultivation report verification failed: {error}"}


def main(argv=None):
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='检查培养配置；不启动游戏或访问账号')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check-config')
    check.add_argument('config', type=Path)
    check.add_argument('--mode', choices=['scan', 'execute'], default='scan')
    args = parser.parse_args(argv)
    try:
        result = load_cultivation_config(args.config, args.mode)
        print(json.dumps({'ready': True, 'mode': args.mode, 'target': result['target'],
                          'executionEnabled': result['executionEnabled']}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'ready': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 4


if __name__ == '__main__':
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
