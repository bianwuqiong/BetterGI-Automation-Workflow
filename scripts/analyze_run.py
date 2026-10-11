"""Conservatively turn a BetterGI one-dragon log into structured evidence.

``analyze_log`` is intentionally an *evidence reporter*, rather than a parser
which assumes that an action completed because BetterGI moved to its next
step.  Its result has this stable, JSON-serialisable shape::

    {
      "schemaVersion": 1,
      "outcome": "completed|partial|failed|unknown",
      "tasks": [{"name", "status", "reason", "evidence"}],
      "rewards": {"item name": positive_int},
      "resinEvents": [{"type", "count", "line"}],
      "warnings": [str],
      "flowEnded": bool,
      "cultivation": None | {"claimedStatus", "mode", "readOnly", "reportRelativePath", ...},
    }

Legacy BetterGI text is accepted only as narrow negative evidence, plus the
two-part domain completion proof (a per-round reward recognition and an
unambiguous normal/end-of-resin message).  In particular, ``任务结束``, a
process exit, click/intention logs, and ``无需合成浓缩树脂`` never prove a
successful task.  The latter has been observed after interacting with the
wrong NPC.  A reported resin shortage is retained as a warning because OCR can
misread it; it is not a domain success proof.

New runners may write one JSON object per line starting with
``[AUTO_GAME_EVENT]`` (or append it to a standard BetterGI log header). It must contain a task name from ``expected_tasks``, a
supported ``status`` (``success``, ``failed``, ``skipped``, or ``unknown``),
and ``evidenceVerified: true`` (``evidence_verified`` is also accepted).  Only
then can it establish a task status.  This distinguishes checked machine
events from old, intent-only log prose.  A future runner should emit the event
only after it has performed the relevant inventory/UI verification.

Builtin task attribution relies on ``一条龙任务执行: i/n`` markers. Normally the
denominator counts builtins excluding the JS task ``培养材料``. Legacy mixed
cultivation runs used the total including that group while keeping builtin
ordinals. That alternate denominator requires one exact run/configuration,
one 1/1 group, and its matching scoped cultivation event. More than one complete or
started matching run, or markers with different denominators, is mixed input:
task statuses remain unknown and rewards/resin events are omitted rather than
cross-charged to an arbitrary run. ``config_name`` rejects a segment only when
an exact BetterGI ``参数指定的一条龙配置：NAME`` or
``启用一条龙配置：NAME`` record names a different configuration.

Cultivation events require the caller's ``run_id`` and ``cultivation_mode``
scope. They remain unknown until the runner independently validates the saved
report. All plugin evidence is retained in ``cultivation`` with
``claimedStatus`` and ``reportVerified: false``; scan success is never proof of
material farming.

The module uses only the Python standard library and never calls an AI service.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
_MARKER_RE = re.compile(r"一条龙任务执行\s*:\s*(\d+)\s*/\s*(\d+)")
_GROUP_MARKER_RE = re.compile(r"配置组任务执行\s*:\s*(\d+)\s*/\s*(\d+)")
_CULTIVATION_TASK = "培养材料"
_EVENT_PREFIX = "[AUTO_GAME_EVENT]"
_EVENT_STATUSES = {"success", "failed", "skipped", "unknown"}
_FAILURE_RE = re.compile(r"(?:执行异常|执行失败|任务(?:执行)?失败|任务已取消|任务被取消|任务取消|已取消任务|连续战斗失败\d+次，任务终止)")
_REWARD_RE = re.compile(r"\s*([^,，]+?)\s*[x×]\s*(\d+)\s*(?:[,，]|$)")
_CONFIG_RE = re.compile(r"(?:参数指定|启用)(?:的)?一条龙配置\s*[：:]\s*([A-Za-z0-9_-]+)\s*$")
_BGI_INLINE_EVENT_RE = re.compile(
    r"^\[\d{2}:\d{2}:\d{2}\.\d+\]\s+\[(?:TRC|DBG|INF|WRN|ERR|FTL)\].*?(\[AUTO_GAME_EVENT\]\s*.*)$"
)


def _evidence(line_number: int, text: str) -> dict[str, Any]:
    return {"line": line_number, "text": text.strip()}


def _config_reference(text: str) -> str | None:
    match = _CONFIG_RE.search(text.strip())
    return match.group(1) if match else None


def _event_from_line(line: str) -> dict[str, Any] | None:
    stripped = line.lstrip()
    if stripped.startswith(_EVENT_PREFIX):
        payload = stripped[len(_EVENT_PREFIX) :].strip()
    else:
        inline = _BGI_INLINE_EVENT_RE.match(stripped)
        if not inline:
            return None
        payload = inline.group(1)[len(_EVENT_PREFIX) :].strip()
    if not payload:
        return None
    try:
        event = json.loads(payload)
        # Serilog quotes a JS JSON argument as a JSON string. Unwrap that
        # transport layer once; nested strings and non-object payloads stay invalid.
        if isinstance(event, str):
            event = json.loads(event)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _valid_crafting_event(event: dict[str, Any], status: str) -> bool:
    fields = {
        name: event.get(name)
        for name in (
            "originalResinBefore",
            "originalResinAfter",
            "condensedResinBefore",
            "condensedResinAfter",
            "condensedResinCreated",
            "originalResinSpent",
        )
    }
    if any(not isinstance(value, int) or isinstance(value, bool) for value in fields.values()):
        return False
    original_before = fields["originalResinBefore"]
    original_after = fields["originalResinAfter"]
    condensed_before = fields["condensedResinBefore"]
    condensed_after = fields["condensedResinAfter"]
    crafted = fields["condensedResinCreated"]
    spent = fields["originalResinSpent"]
    if not (0 <= original_after <= original_before <= 200):
        return False
    if not (0 <= condensed_before <= condensed_after <= 5):
        return False
    if crafted < 0 or spent < 0 or spent != crafted * 60:
        return False
    if original_before - original_after != spent or condensed_after - condensed_before != crafted:
        return False
    return (status == "success" and crafted > 0) or (status == "skipped" and crafted == 0)


def _verified_event_status(event: dict[str, Any], expected: set[str]) -> str | None:
    task = event.get("task", event.get("taskName"))
    status = event.get("status")
    verified = event.get("evidenceVerified", event.get("evidence_verified"))
    if not isinstance(task, str) or not isinstance(status, str):
        return None
    if task not in expected or status not in _EVENT_STATUSES or verified is not True:
        return None
    if task == "合成树脂" and status in {"success", "skipped"} and not _valid_crafting_event(event, status):
        return None
    return str(status)


def _cultivation_event(
    event: dict[str, Any], run_id: str | None, mode: str,
) -> dict[str, Any] | None:
    """Retain a scoped claim for the runner to verify against its saved report.

    A machine event does not prove the referenced file exists or contains the
    same evidence. In particular, a successful scan proves no material farming.
    """
    if (
        not isinstance(run_id, str)
        or not run_id
        or event.get("runId") != run_id
        or event.get("task") != _CULTIVATION_TASK
        or not isinstance(event.get("status"), str)
        or event.get("status") not in {"success", "failed", "unknown", "blocked"}
        or event.get("evidenceVerified") is not True
        or event.get("mode") != mode
        or event.get("reportRelativePath") != f"record/{run_id}.json"
        or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id)
    ):
        return None
    if mode == "scan":
        if event.get("readOnly") is not True:
            return None
    elif mode == "execute":
        if event.get("readOnly") is not None and event.get("readOnly") is not False:
            return None
    else:
        return None
    # Preserve all plugin evidence (steps, gains, inventory and warnings), but
    # reserve reportVerified for the runner's independent file validation.
    return {**event, "claimedStatus": event["status"], "reportVerified": False}


def _matching_runs(lines: list[str], task_count: int) -> list[list[tuple[int, int]]]:
    """Return marker groups that begin with 1/n, including incomplete runs."""
    if not task_count:
        return []
    markers = [
        (index, int(match.group(1)), int(match.group(2)))
        for index, line in enumerate(lines)
        if (match := _MARKER_RE.search(line)) and int(match.group(2)) == task_count
    ]
    runs: list[list[tuple[int, int]]] = []
    pos = 0
    while pos < len(markers):
        _, ordinal, _ = markers[pos]
        if ordinal != 1:
            pos += 1
            continue
        group: list[tuple[int, int]] = [(markers[pos][0], 1)]
        expected_ordinal = 2
        pos += 1
        while pos < len(markers):
            line_index, ordinal, _ = markers[pos]
            if ordinal == 1:
                break
            if ordinal == expected_ordinal:
                group.append((line_index, ordinal))
                expected_ordinal += 1
            elif ordinal > expected_ordinal:
                # A missing section makes later attribution unsafe.
                break
            pos += 1
        runs.append(group)
        # Do not consume a new 1/n marker: it starts the next candidate run.
    return runs


def _segment_bounds(run: list[tuple[int, int]], line_count: int) -> dict[int, tuple[int, int]]:
    bounds: dict[int, tuple[int, int]] = {}
    for position, (start, ordinal) in enumerate(run):
        end = run[position + 1][0] if position + 1 < len(run) else line_count
        bounds[ordinal] = (start, end)
    return bounds


def _legacy_cultivation_total_run(lines: list[str], expected: list[str], run_id: str | None,
                                config_name: str | None, mode: str) -> list[list[tuple[int, int]]]:
    """Recognize only the fixed, uniquely scoped builtin+one cultivation group case."""
    if (expected.count(_CULTIVATION_TASK) != 1 or len(expected) < 2
            or len(set(expected)) != len(expected) or not run_id
            or config_name != f"AutoGame_{run_id}"):
        return []
    markers = [(index, int(match[1]), int(match[2])) for index, line in enumerate(lines)
               if (match := _MARKER_RE.search(line))]
    builtin_count = len(expected) - 1
    if not markers or any(total != len(expected) or not 1 <= ordinal <= builtin_count
                          for _, ordinal, total in markers):
        return []
    candidates = _matching_runs(lines, len(expected))
    if len(candidates) != 1 or len(candidates[0]) != len(markers):
        return []
    references = [(index, reference) for index, line in enumerate(lines)
                  if (reference := _config_reference(line))]
    groups = [(index, int(match[1]), int(match[2])) for index, line in enumerate(lines)
              if (match := _GROUP_MARKER_RE.search(line))]
    if (not references or any(reference != config_name for _, reference in references)
            or len(groups) != 1 or groups[0][1:] != (1, 1)
            or references[-1][0] >= min(groups[0][0], markers[0][0])):
        return []
    group_start = groups[0][0]
    cultivation_index = expected.index(_CULTIVATION_TASK)
    preceding = sum(name != _CULTIVATION_TASK for name in expected[:cultivation_index])
    run = candidates[0]
    if preceding and (len(run) < preceding or group_start <= run[preceding - 1][0]):
        return []
    if len(run) > preceding and group_start >= run[preceding][0]:
        return []
    group_end = next((index for index, _, _ in markers if index > group_start), len(lines))
    plugin_events = [(index, event) for index, line in enumerate(lines)
                     if (event := _event_from_line(line)) is not None
                     and event.get('task', event.get('taskName')) == _CULTIVATION_TASK]
    if (len(plugin_events) != 1 or not group_start < plugin_events[0][0] < group_end
            or _cultivation_event(plugin_events[0][1], run_id, mode) is None):
        return []
    return candidates


def _parse_rewards(lines: list[str]) -> dict[str, int]:
    rewards: defaultdict[str, int] = defaultdict(int)
    for line in lines:
        marker = line.find("本轮奖励识别结果")
        if marker < 0:
            continue
        # One physical recognition line is parsed once.  Deliberately do not
        # inspect later reward summaries, which duplicate these quantities.
        payload = line[marker + len("本轮奖励识别结果") :].strip().strip('"“”')
        for match in _REWARD_RE.finditer(payload):
            item = match.group(1).strip().strip('"“”')
            if item:
                rewards[item] += int(match.group(2))
    return dict(rewards)


def _parse_resin_events(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for number, text in enumerate(lines, start=1):
        machine_event = _event_from_line(text)
        if (
            machine_event
            and machine_event.get("task", machine_event.get("taskName")) == "合成树脂"
            and machine_event.get("evidenceVerified", machine_event.get("evidence_verified")) is True
            and machine_event.get("status") in {"success", "skipped"}
            and _valid_crafting_event(machine_event, str(machine_event.get("status")))
        ):
            crafted = machine_event.get("condensedResinCreated")
            spent = machine_event.get("originalResinSpent")
            if isinstance(crafted, int) and not isinstance(crafted, bool) and crafted >= 0:
                event = {"type": "crafted_condensed", "count": crafted, "line": number}
                if isinstance(spent, int) and not isinstance(spent, bool) and spent >= 0:
                    event["originalResinSpent"] = spent
                events.append(event)
        condensed = re.search(r'使用\s*["“]?浓缩树脂["”]?\s*[,，]?\s*数量\s*[：:]\s*(\d+)', text)
        original = re.search(r'使用\s*["“]?原粹树脂["”]?\s*[,，]?\s*数量\s*[：:]\s*(\d+)', text)
        if condensed:
            events.append({"type": "used_condensed", "count": int(condensed.group(1)), "line": number})
        if original:
            events.append({"type": "used_original", "count": int(original.group(1)), "line": number})
        if "树脂不足" in text or "原粹树脂不足" in text:
            events.append({"type": "reported_insufficient", "count": 0, "line": number})
    return events


def _domain_legacy_success(segment: list[str]) -> bool:
    has_reward = any("本轮奖励识别结果" in line for line in segment)
    if not has_reward:
        return False
    has_verified_spend = any(
        re.search(r'使用\s*["“]?(?:浓缩树脂|原粹树脂)["”]?\s*[,，]?\s*数量\s*[：:]\s*\d+', line)
        for line in segment
    )
    # "用尽所有...后结束" at task start describes configuration, not outcome.
    normal_end = any(
        re.search(r"(?:自动)?秘境.*(?:正常结束|完成).*(?:树脂(?:已)?耗尽|树脂已用尽)", line)
        or re.search(r"(?:树脂(?:已)?耗尽|树脂已用尽|已用尽.*树脂).*(?:自动)?秘境.*(?:结束|完成)", line)
        or re.search(r"(?:自动)?秘境.*(?:树脂(?:已)?耗尽|树脂已用尽|原粹树脂已用尽).*(?:退出|结束|完成)", line)
        for line in segment
    )
    configured_or_exhausted_end = has_verified_spend and any(
        "体力耗尽或者设置轮次已达标，结束自动秘境" in line
        for line in segment
    )
    return bool(normal_end or configured_or_exhausted_end)


def _legacy_task_status(name: str, segment: list[str], offset: int) -> tuple[str, str, list[dict[str, Any]]]:
    failures = [
        (offset + index, line)
        for index, line in enumerate(segment)
        if _FAILURE_RE.search(line)
    ]

    if "每日奖励" in name:
        claimed = [
            (offset + index, line)
            for index, line in enumerate(segment)
            if "检查每日奖励结果" in line and "今日奖励已领取" in line
        ]
        last_failure = failures[-1] if failures else None
        if claimed and (last_failure is None or claimed[-1][0] > last_failure[0]):
            return "success", "verified daily reward claimed state", [_evidence(claimed[-1][0] + 1, claimed[-1][1])]
        if failures:
            line, text = failures[-1]
            return "failed", "explicit terminal failure in this task section", [_evidence(line + 1, text)]
        uncertain = [
            _evidence(offset + index + 1, line)
            for index, line in enumerate(segment)
            if "未完成或者已领取" in line or "未领取" in line
        ]
        if uncertain:
            return "unknown", "daily reward log is ambiguous", uncertain
        return "unknown", "no verified daily reward state", []

    if failures:
        line, text = failures[-1]
        return "failed", "explicit terminal failure in this task section", [_evidence(line + 1, text)]

    if "合成" in name:
        for index, line in enumerate(segment):
            if "无需合成浓缩树脂" in line:
                return (
                    "unknown",
                    "crafting claim has no inventory verification",
                    [_evidence(offset + index + 1, line)],
                )
        return "unknown", "no verified crafting inventory result", []

    if "秘境" in name:
        reward_lines = [
            _evidence(offset + index + 1, line)
            for index, line in enumerate(segment)
            if "本轮奖励识别结果" in line
        ]
        if _domain_legacy_success(segment):
            return "success", "reward recognition and explicit normal resin-exhaustion end", reward_lines
        if reward_lines:
            return "unknown", "reward observed without verified normal completion", reward_lines
        return "unknown", "no verified domain reward and completion evidence", []

    # Mail, teapot and other old text lack a durable receipt/inventory proof.
    return "unknown", "no verified completion evidence", []


def analyze_log(
    text: str,
    expected_tasks: list[str],
    *,
    execution_outcome: str = "exited",
    config_name: str | None = None,
    run_id: str | None = None,
    cultivation_mode: str = "execute",
) -> dict[str, Any]:
    """Analyze one supplied log slice without making completion assumptions."""
    lines = text.splitlines()
    expected = list(expected_tasks)
    expected_set = set(expected)
    warnings: list[str] = []
    task_results = [
        {"name": name, "status": "unknown", "reason": "no verified completion evidence", "evidence": []}
        for name in expected
    ]

    if len(expected_set) != len(expected):
        warnings.append("expected_tasks contains duplicate names; event attribution is ambiguous")

    builtin_indexes = [index for index, name in enumerate(expected) if name != _CULTIVATION_TASK]
    runs = _matching_runs(lines, len(builtin_indexes))
    if not runs:
        runs = _legacy_cultivation_total_run(lines, expected, run_id, config_name, cultivation_mode)
        if runs:
            warnings.append("legacy mixed cultivation markers use total task denominator; builtin ordinals mapped with exact run/config/group evidence")
    marker_denominators = {
        int(match.group(2)) for line in lines if (match := _MARKER_RE.search(line))
    }
    legacy_total_rejected = (not runs and bool(builtin_indexes)
                             and expected.count(_CULTIVATION_TASK) == 1
                             and marker_denominators == {len(expected)})
    mixed_input = len(runs) > 1 or len(marker_denominators) > 1 or legacy_total_rejected
    selected_run: list[tuple[int, int]] | None = None
    config_rejected = False
    if mixed_input:
        if legacy_total_rejected:
            warnings.append("legacy mixed cultivation denominator lacks unique exact run/config/group proof; refusing attribution")
        elif len(marker_denominators) > 1:
            warnings.append("one-dragon markers have different denominators; refusing mixed-run attribution")
        else:
            warnings.append("multiple matching one-dragon runs in one log slice; refusing cross-run attribution")
    elif len(runs) == 1:
        candidate = runs[0]
        if config_name:
            first, last = candidate[0][0], candidate[-1][0]
            # BetterGI writes its selected configuration immediately before the
            # first 1/n marker, so include that short setup preamble too.
            scoped = "\n".join(lines[max(0, first - 100) : last + 1])
            references = [name for line in scoped.splitlines() if (name := _config_reference(line))]
            if references and config_name not in references:
                warnings.append("matching one-dragon section names a different configuration")
                config_rejected = True
            else:
                selected_run = candidate
        else:
            selected_run = candidate
    elif expected:
        if any(_MARKER_RE.search(line) for line in lines):
            warnings.append("one-dragon marker denominator does not match expected_tasks")
        else:
            warnings.append("no one-dragon markers; legacy task prose was not attributed")

    if not builtin_indexes and config_name:
        references = [name for line in lines if (name := _config_reference(line))]
        if references and config_name not in references:
            warnings.append("cultivation group names a different configuration")
            config_rejected = True

    event_by_task: dict[str, tuple[str, int, str]] = {}
    cultivation: dict[str, Any] | None = None
    rejected_events = 0
    for number, line in enumerate(lines, start=1):
        event = _event_from_line(line)
        if event is None:
            if _EVENT_PREFIX in line:
                rejected_events += 1
            continue
        task = str(event.get("task", event.get("taskName")))
        if task == _CULTIVATION_TASK:
            candidate = _cultivation_event(event, run_id, cultivation_mode)
            if task not in expected_set or candidate is None:
                rejected_events += 1
                continue
            cultivation = {**candidate, "line": number}
            status = event["status"]
            event_by_task[task] = (status, number, line)
            continue
        if run_id is not None and event.get("runId") not in (None, run_id):
            rejected_events += 1
            continue
        status = _verified_event_status(event, expected_set)
        if status is None:
            rejected_events += 1
            continue
        event_by_task[task] = (status, number, line)
    if rejected_events:
        warnings.append("ignored AUTO_GAME_EVENT without supported task, status, or evidenceVerified=true")

    if selected_run is not None:
        for ordinal, (start, end) in _segment_bounds(selected_run, len(lines)).items():
            builtin_index = ordinal - 1
            if builtin_index >= len(builtin_indexes):
                continue
            index = builtin_indexes[builtin_index]
            name = expected[index]
            # A JS group is a separate execution scope and may occur between
            # builtins. Its failure prose must not contaminate the prior task.
            group_start = next(
                (pos for pos in range(start + 1, end) if _GROUP_MARKER_RE.search(lines[pos])),
                end,
            )
            status, reason, evidence = _legacy_task_status(name, lines[start:group_start], start)
            task_results[index].update(status=status, reason=reason, evidence=evidence)

    # Exact machine events can establish a task without legacy prose, but they
    # cannot bypass mixed input or an explicitly different configuration.
    selected_bounds = None
    if selected_run is not None:
        selected_bounds = (selected_run[0][0] + 1, len(lines))
    if not mixed_input and not config_rejected:
        for item in task_results:
            if item["name"] in event_by_task:
                status, number, line = event_by_task[item["name"]]
                if item["name"] != _CULTIVATION_TASK and selected_bounds and not (selected_bounds[0] <= number <= selected_bounds[1]):
                    continue
                failure_lines = [
                    evidence["line"] for evidence in item.get("evidence", [])
                    if item.get("status") == "failed" and isinstance(evidence.get("line"), int)
                ]
                if status == "success" and failure_lines and max(failure_lines) > number:
                    warnings.append(
                        f"line {number}: verified success predates a terminal failure for {item['name']}; failure retained"
                    )
                    continue
                item.update(
                    status=status,
                    reason="verified AUTO_GAME_EVENT",
                    evidence=[_evidence(number, line)],
                )
                if item["name"] == _CULTIVATION_TASK:
                    item.update(
                        status="unknown",
                        reason="cultivation report requires independent verification",
                    )

    if mixed_input or config_rejected:
        cultivation = None

    if selected_run is not None:
        start = selected_run[0][0]
        end = len(lines)
        flow_ended = any("一条龙和配置组任务结束" in line for line in lines[start:end])
    elif not builtin_indexes and cultivation is not None:
        flow_ended = any(
            "一条龙和配置组任务结束" in line
            for line in lines[cultivation["line"] - 1 :]
        )
    else:
        flow_ended = False
    if not flow_ended:
        warnings.append("no explicit one-dragon flow-end record in the selected run")

    if execution_outcome != "exited":
        warnings.append(f"execution outcome was {execution_outcome!r}, not 'exited'")

    statuses = [item["status"] for item in task_results]
    if execution_outcome == "exited" and flow_ended and statuses and all(
        status in {"success", "skipped"} for status in statuses
    ):
        outcome = "completed"
    elif any(status == "success" for status in statuses):
        outcome = "partial"
    elif any(status == "failed" for status in statuses):
        outcome = "failed"
    else:
        outcome = "unknown"

    accounting_lines = lines
    line_offset = 0
    if mixed_input:
        accounting_lines = []
        warnings.append("omitted rewards and resin events because the log contains mixed runs")
    elif selected_run is not None:
        accounting_lines = lines[selected_run[0][0] :]
        line_offset = selected_run[0][0]
    if run_id is not None:
        # Preserve physical line numbers while excluding foreign-run machine
        # claims from both completion evidence and resin accounting.
        accounting_lines = [
            "" if (event := _event_from_line(line)) is not None
            and event.get("runId") not in (None, run_id) else line
            for line in accounting_lines
        ]
    resin_events = _parse_resin_events(accounting_lines)
    if line_offset:
        resin_events = [{**event, "line": event["line"] + line_offset} for event in resin_events]
    for event in resin_events:
        if event["type"] == "reported_insufficient":
            warnings.append(f"line {event['line']}: reported resin shortage is unverified OCR evidence")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "outcome": outcome,
        "tasks": task_results,
        "rewards": _parse_rewards(accounting_lines),
        "resinEvents": resin_events,
        "warnings": warnings,
        "flowEnded": flow_ended,
        "cultivation": cultivation,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conservatively analyze a BetterGI log slice")
    parser.add_argument("--log", required=True, help="UTF-8 BetterGI log file")
    parser.add_argument("--tasks-json", required=True, help="JSON array or path to a JSON array")
    parser.add_argument("--output", help="optional JSON output path; otherwise writes stdout")
    parser.add_argument("--execution-outcome", default="exited")
    parser.add_argument("--config-name")
    parser.add_argument("--run-id")
    parser.add_argument("--cultivation-mode", choices=("scan", "execute"), default="execute")
    args = parser.parse_args(argv)

    tasks_source = Path(args.tasks_json)
    tasks_text = tasks_source.read_text(encoding="utf-8-sig") if tasks_source.is_file() else args.tasks_json
    tasks = json.loads(tasks_text)
    if not isinstance(tasks, list) or not all(isinstance(item, str) for item in tasks):
        parser.error("--tasks-json must be a JSON string array or a path to one")
    result = analyze_log(
        Path(args.log).read_text(encoding="utf-8-sig"),
        tasks,
        execution_outcome=args.execution_outcome,
        config_name=args.config_name,
        run_id=args.run_id,
        cultivation_mode=args.cultivation_mode,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
