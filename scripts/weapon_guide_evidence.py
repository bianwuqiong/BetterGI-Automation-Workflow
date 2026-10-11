"""Independent, read-only validation of weapon-guide OCR inventory evidence."""
from __future__ import annotations

from datetime import datetime
import math
import re
import unicodedata

SOURCE = "character_weapon_guide_tooltip"
_SAFE_INTEGER = 9007199254740991


def _fail(message):
    raise ValueError("weapon guide evidence: " + message)


def _object(value, label):
    if not isinstance(value, dict):
        _fail(label + " must be an object")
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(label + " must be finite numeric")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        _fail(label + " must be finite numeric")
    return value


def _integer(value, label, minimum=0, maximum=_SAFE_INTEGER):
    value = _number(value, label)
    if value != int(value) or not minimum <= value <= maximum:
        _fail(label + " is outside integer bounds")
    return int(value)


def _text(value):
    if not isinstance(value, str):
        _fail("OCR/expected text must be a string")
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _rect(value):
    value = _object(value, "rectangle")
    x, y, w, h = (_number(value.get(key), key) for key in ("x", "y", "width", "height"))
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        _fail("invalid rectangle bounds")
    _number(x + w, "rectangle right bound")
    _number(y + h, "rectangle bottom bound")
    return x, y, w, h


def _rows(value, region=None):
    if not isinstance(value, list) or not value:
        _fail("OCR rows must be a nonempty array")
    for row in value:
        _text(_object(row, "OCR row").get("text"))
        x, y, w, h = _rect(row)
        if region is not None:
            rx, ry, rw, rh = region
            if x < rx or y < ry or x + w > rx + rw or y + h > ry + rh:
                _fail("OCR row exceeds tooltip region")
    return value


def _ratio(text):
    match = re.fullmatch(r"([0-9]+)/([0-9]+)", _text(text))
    if not match:
        return None
    # Bound digit lengths before converting untrusted OCR text to integers.
    if any(len(part.lstrip("0")) > 16 for part in match.groups()):
        _fail("ratio exceeds safe integer range")
    return tuple(_integer(int(part), "ratio") for part in match.groups())


def _tooltip(frame, name, required):
    region = _rect(frame.get("tooltipRegion"))
    rows = _rows(frame.get("tooltipRows"), region)
    titles = [row for row in rows if _text(row["text"]) == _text(name)]
    if len(titles) != 1:
        _fail("material title missing or ambiguous")
    labels = [row for row in rows if re.fullmatch(r"培养需求:?(?:[0-9]+/[0-9]+)?", _text(row["text"]))]
    if len(labels) != 1:
        _fail("cultivation demand label missing or ambiguous")
    label = labels[0]
    if titles[0]["y"] + titles[0]["height"] > label["y"]:
        _fail("material title must precede the cultivation demand row")
    parsed = _ratio(re.sub(r"^培养需求:?", "", _text(label["text"])))
    if parsed is None:
        candidates = [row for row in rows if _ratio(row["text"]) is not None
                      and row["x"] >= label["x"] + label["width"]
                      and abs(row["y"] + row["height"] / 2 - label["y"] - label["height"] / 2)
                      <= min(row["height"], label["height"]) * .75]
        if len(candidates) != 1:
            _fail("demand ratio missing or ambiguous on demand baseline")
        parsed = _ratio(candidates[0]["text"])
    if parsed[1] != required:
        _fail("tooltip required quantity mismatch")
    return parsed[0]


def _context(frame, character, weapon, level):
    rows = _object(frame.get("contextRows"), "contextRows")
    for key, expected in (("characterName", character), ("weaponName", weapon)):
        values = _rows(rows.get(key))
        if sum(_text(row["text"]) == _text(expected) for row in values) != 1:
            _fail(key + " context mismatch or ambiguity")
    values = sorted(_rows(rows.get("targetLevel")), key=lambda row: (row["y"], row["x"]))
    text = _text("".join(row["text"] for row in values))
    if not re.fullmatch(r"升级至(?:Lv\.?)?" + str(level) + r"(?:级)?", text, re.IGNORECASE):
        _fail("target level context mismatch")


def _report_time(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                _fail("report timestamp needs timezone")
            return _number(parsed.timestamp() * 1000, "report timestamp")
        except (ValueError, OverflowError) as error:
            _fail("invalid report timestamp: " + str(error))
    return _number(value, "report timestamp")


def verify_weapon_guide_inventory(raw_inventory, *, profile, target, requirements,
                                 materials, started_at, finished_at) -> None:
    """Raise ValueError for unsupported guide claims; leave all input data untouched.

    Other inventory sources remain the responsibility of their existing verifier.
    Epoch values use milliseconds; report limits may also be timezone-aware ISO dates.
    """
    rows = _object(raw_inventory, "inventory")
    guide_rows = [(identifier, row) for identifier, row in rows.items()
                  if isinstance(row, dict) and row.get("source") == SOURCE]
    if not guide_rows:
        return
    for identifier, row in guide_rows:
        if row.get("status") == "unknown":
            if row.get("count") is not None:
                _fail("unknown inventory cannot contain a count")
            continue
        if row.get("status") != "exact":
            _fail("unsupported guide inventory status")
        if "mainUiRestored" in row and row["mainUiRestored"] is not True:
            _fail("main UI restoration is unverified")
        profile = _object(profile, "profile")
        target = _object(target, "target")
        character = profile.get("characterName")
        weapon = _object(profile.get("weapon"), "weapon").get("name")
        if not _text(character) or not _text(weapon):
            _fail("empty profile context")
        level = _integer(target.get("weaponTargetLevel"), "weaponTargetLevel", 1, 90)
        required = _integer(_object(requirements, "requirements").get(identifier), "required")
        material = _object(_object(materials, "materials").get(identifier), "material")
        name = material.get("name")
        if not _text(name) or row.get("name") != name:
            _fail("inventory material name mismatch")
        evidence = _object(row.get("evidence"), "evidence")
        if evidence.get("materialId") != identifier or _integer(evidence.get("required"), "evidence required") != required:
            _fail("material identity or required quantity mismatch")
        session = _object(evidence.get("session"), "session")
        if session.get("characterName") != character or session.get("weaponName") != weapon:
            _fail("session character or weapon mismatch")
        if _integer(session.get("targetLevel"), "session target", 1, 90) != level:
            _fail("session target mismatch")
        groups = [session.get("before"), evidence.get("tooltip"), session.get("after")]
        if any(not isinstance(group, list) or len(group) != 2 for group in groups):
            _fail("two independent before, tooltip, and after frames required")
        start, finish = _report_time(started_at), _report_time(finished_at)
        if finish < start:
            _fail("report time interval reversed")
        times = []
        for group in groups:
            pair = [_number(_object(frame, "frame").get("observedAt"), "observedAt") for frame in group]
            if not 100 <= pair[1] - pair[0] <= 5000:
                _fail("independent frame interval outside 100..5000 ms")
            if any(value < start or value > finish for value in pair):
                _fail("frame timestamp outside this report")
            times.extend(pair)
        if times != sorted(times) or times[-1] - times[0] > 120000:
            _fail("session frame order or duration invalid")
        for frame in groups[0] + groups[2]:
            _context(frame, character, weapon, level)
        counts = [_tooltip(frame, name, required) for frame in groups[1]]
        count = _integer(row.get("count"), "inventory count")
        if counts[0] != counts[1] or count != counts[0]:
            _fail("inventory count disagrees with independent tooltips")
