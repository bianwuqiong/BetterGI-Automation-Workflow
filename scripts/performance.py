"""Read-only timing analysis for one PID-filtered BetterGI log slice.

``analyze_performance`` measures observed elapsed time only.  ``complete``
means that a timing boundary was seen (for example, the next phase began); it
does not mean the game task succeeded. ``endedBy`` records that boundary, such
as ``success``, ``failure``, ``superseded``, or ``task_end``. It accepts raw BetterGI records where
the timestamp header and message occupy separate lines, rejects ambiguous
multi-run marker input, and never starts a process or writes a file.

``now_elapsed_sec`` is an optional elapsed value relative to the first log
timestamp.  It is used only to estimate an incomplete final stage; wall-clock
time is never consulted.  Output durations are seconds rounded to milliseconds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\.(\d{1,3})\]")
_MARKER_RE = re.compile(r"一条龙任务执行\s*:\s*(\d+)\s*/\s*(\d+)")
_PHASES = (
    ("domain_enter", re.compile(r'自动秘境：?["“]?1\.\s*走到钥匙处启动')),
    ("domain_fight", re.compile(r'自动秘境：?["“]?2\.\s*执行战斗策略')),
    ("tree_search", re.compile(r'自动秘境：?["“]?3\.\s*寻找石化古树')),
    ("tree_approach", re.compile(r'自动秘境：?["“]?4\.\s*走到石化古树处')),
    ("domain_reward", re.compile(r'自动秘境：?["“]?5\.\s*领取奖励')),
)
_PHASE_LABELS = {
    "domain_enter": "进入/开启钥匙",
    "domain_fight": "执行战斗策略",
    "tree_search": "寻找石化古树",
    "tree_approach": "走到石化古树",
    "domain_reward": "领取奖励",
    "teleport": "传送",
    "task": "任务",
}
_TELEPORT_FAILURE_RE = re.compile(r"传送.*(?:失败|未出现交互面板|不可点击区域|超过\s*60\s*秒)|单次传送超过")


@dataclass(frozen=True)
class _Record:
    line: int
    text: str
    second: float | None


def _round(value: float | None) -> float | None:
    return round(max(0.0, value), 3) if value is not None else None


def _records(text: str) -> tuple[list[_Record], float | None, float | None]:
    records: list[_Record] = []
    current: float | None = None
    first: float | None = None
    last: float | None = None
    previous_clock: float | None = None
    day_offset = 0.0
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _TIMESTAMP_RE.match(line)
        if match:
            hour, minute, second = (int(part) for part in match.groups()[:3])
            millis_text = match.group(4)
            # BetterGI permits one to three fractional digits: .1 is 100 ms,
            # not one millisecond.
            fraction = int(millis_text) / 10 ** len(millis_text)
            clock = hour * 3600 + minute * 60 + second + fraction
            # A large backwards jump is a midnight rollover, not a negative
            # duration. Small disorder is left untouched and later clamped.
            if previous_clock is not None and clock < previous_clock - 12 * 3600:
                day_offset += 24 * 3600
            previous_clock = clock
            current = day_offset + clock
            first = current if first is None else first
            last = current
        records.append(_Record(line_number, line, current))
    return records, first, last


def _marker_runs(records: list[_Record], task_count: int) -> tuple[list[list[tuple[int, int]]], set[int]]:
    markers: list[tuple[int, int, int]] = []
    denominators: set[int] = set()
    for index, record in enumerate(records):
        match = _MARKER_RE.search(record.text)
        if match:
            ordinal, denominator = int(match.group(1)), int(match.group(2))
            denominators.add(denominator)
            if denominator == task_count:
                markers.append((index, ordinal, denominator))
    runs: list[list[tuple[int, int]]] = []
    pos = 0
    while pos < len(markers):
        if markers[pos][1] != 1:
            pos += 1
            continue
        run = [(markers[pos][0], 1)]
        next_ordinal = 2
        pos += 1
        while pos < len(markers):
            index, ordinal, _ = markers[pos]
            if ordinal == 1:
                break
            if ordinal == next_ordinal:
                run.append((index, ordinal))
                next_ordinal += 1
            elif ordinal > next_ordinal:
                break
            pos += 1
        runs.append(run)
    return runs, denominators


def _end_for_task(records: list[_Record], start: int, stop: int) -> tuple[float | None, bool, str | None]:
    terminal_failure = any(
        "任务被取消" in record.text or "任务取消" in record.text or "执行异常" in record.text
        for record in records[start:stop]
    )
    for record in records[start:stop]:
        if "任务结束" in record.text or "一条龙和配置组任务结束" in record.text:
            return record.second, True, "failure" if terminal_failure else "task_end"
    if stop < len(records):
        return records[stop].second, True, "failure" if terminal_failure else "task_end"
    return None, False, None


def _elapsed(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return _round(end - start)


def _phase_name(text: str) -> str | None:
    for name, pattern in _PHASES:
        if pattern.search(text):
            return name
    return None


def _fallback_end(
    task_end: float | None,
    last_second: float | None,
    run_start: float | None,
    now_elapsed_sec: float | None,
) -> float | None:
    if task_end is not None:
        return task_end
    if now_elapsed_sec is not None and run_start is not None:
        now_end = run_start + max(0.0, now_elapsed_sec)
        return max(now_end, last_second) if last_second is not None else now_end
    return last_second


def _domain_rounds(
    records: list[_Record],
    start: int,
    stop: int,
    task_end: float | None,
    last_second: float | None,
    run_start: float | None,
    now_elapsed_sec: float | None,
    task_name: str,
    task_ended_by: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    phase_events: list[tuple[int, str, float | None]] = []
    for index in range(start, stop):
        name = _phase_name(records[index].text)
        if name:
            phase_events.append((index, name, records[index].second))
    starts = [position for position, (_, name, _) in enumerate(phase_events) if name == "domain_enter"]
    rounds: list[dict[str, Any]] = []
    current_stage: dict[str, Any] | None = None
    for round_index, event_start in enumerate(starts, start=1):
        event_stop = starts[round_index] if round_index < len(starts) else len(phase_events)
        group = phase_events[event_start:event_stop]
        group_start_record = group[0][0]
        next_round_record = phase_events[event_stop][0] if event_stop < len(phase_events) else stop
        reward_records = [
            record for record in records[group_start_record:next_round_record]
            if "本轮奖励识别结果" in record.text
        ]
        phases: dict[str, dict[str, Any]] = {}
        for phase_index, (_, name, began) in enumerate(group):
            next_phase = group[phase_index + 1] if phase_index + 1 < len(group) else None
            # The useful tree-search metric is phase 3 through phase 5: it
            # captures both search and the final approach, matching the
            # historical 159/208/270-second regression baseline. Phase 4 is
            # retained separately for narrower navigation diagnosis.
            if name == "tree_search":
                next_phase = next((event for event in group[phase_index + 1 :] if event[1] == "domain_reward"), None)
            reward_end = reward_records[0].second if name == "domain_reward" and reward_records else None
            if next_phase:
                ended, complete, ended_by = next_phase[2], True, "phase_transition"
            elif reward_end is not None:
                ended, complete, ended_by = reward_end, True, "success"
            elif task_end is not None:
                ended, complete, ended_by = task_end, True, task_ended_by or "task_end"
            else:
                ended = _fallback_end(task_end, last_second, run_start, now_elapsed_sec)
                complete = False
                ended_by = "last_log"
            phases[name] = {"elapsedSec": _elapsed(began, ended), "complete": complete, "endedBy": ended_by}
            if not complete and task_end is None:
                current_stage = {
                    "name": name,
                    "label": _PHASE_LABELS[name],
                    "task": task_name,
                    "elapsedSec": _elapsed(began, ended),
                }
        rounds.append({"index": round_index, "phases": phases, "rewardObserved": bool(reward_records)})
    return rounds, current_stage


def _teleports(records: list[_Record], start: int, stop: int, fallback: float | None) -> list[dict[str, Any]]:
    pending: tuple[int, float | None] | None = None
    values: list[dict[str, Any]] = []

    def finish(began: float | None, ended: float | None, ended_by: str, complete: bool = True) -> None:
        values.append({
            "index": len(values) + 1,
            "elapsedSec": _elapsed(began, ended),
            "complete": complete,
            "endedBy": ended_by,
        })

    for index in range(start, stop):
        text = records[index].text
        if "开始传送" in text:
            if pending is not None:
                # A new attempt supersedes the prior attempt. FIFO would pair
                # a later success with the old attempt and leave a false stall.
                finish(pending[1], records[index].second, "superseded")
            pending = (index, records[index].second)
        elif pending is not None and _TELEPORT_FAILURE_RE.search(text):
            finish(pending[1], records[index].second, "failure")
            pending = None
        elif pending is not None and ("传送完成" in text or "传送成功" in text):
            finish(pending[1], records[index].second, "success")
            pending = None
        elif pending is not None and ("任务结束" in text or "一条龙和配置组任务结束" in text):
            finish(pending[1], records[index].second, "task_end")
            pending = None
    if pending is not None:
        finish(pending[1], fallback, "last_log", complete=False)
    return values


def _counters(records: list[_Record]) -> dict[str, int]:
    return {
        "deaths": sum("存在角色死亡" in item.text or "角色死亡" in item.text for item in records),
        "retries": sum("重试" in item.text for item in records),
        "teleportFailures": sum(bool(_TELEPORT_FAILURE_RE.search(item.text)) for item in records),
    }


def _bottlenecks(tasks: list[dict[str, Any]], rounds: list[dict[str, Any]], teleports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for task in tasks:
        duration = task["elapsedSec"]
        if duration is not None and duration >= 120:
            items.append({"kind": "task", "name": task["name"], "elapsedSec": duration})
    for round_value in rounds:
        for name, phase in round_value["phases"].items():
            duration = phase["elapsedSec"]
            if duration is not None and duration >= 60:
                items.append({"kind": "phase", "name": name, "round": round_value["index"], "elapsedSec": duration})
    for teleport in teleports:
        duration = teleport["elapsedSec"]
        if duration is not None and duration >= 30:
            items.append({"kind": "teleport", "name": "teleport", "index": teleport["index"], "elapsedSec": duration})
    return sorted(items, key=lambda item: item["elapsedSec"], reverse=True)[:8]


def analyze_performance(
    text: str,
    expected_tasks: list[str],
    *,
    now_elapsed_sec: float | None = None,
) -> dict[str, Any]:
    """Return timing observations for exactly one unambiguous task-marker run."""
    records, run_start, last_second = _records(text)
    warnings: list[str] = []
    tasks = [{"name": name, "elapsedSec": None, "complete": False, "endedBy": None} for name in expected_tasks]
    if now_elapsed_sec is not None and now_elapsed_sec < 0:
        warnings.append("now_elapsed_sec was negative and was clamped to zero")
    if now_elapsed_sec is not None and run_start is not None and last_second is not None:
        if run_start + max(0.0, now_elapsed_sec) < last_second:
            warnings.append("now_elapsed_sec predates the last log timestamp; the last log time was retained")
    if not records:
        warnings.append("empty log slice")
    if run_start is None:
        warnings.append("no BetterGI timestamp headers; elapsed time is unavailable")

    runs, denominators = _marker_runs(records, len(expected_tasks))
    mixed = len(runs) > 1 or len(denominators) > 1
    selected: list[tuple[int, int]] | None = None
    if mixed:
        warnings.append("multiple or differently sized one-dragon runs; timing was not attributed")
    elif len(runs) == 1:
        selected = runs[0]
    elif expected_tasks:
        warnings.append("no one-dragon markers matching expected_tasks; timing was not attributed")

    rounds: list[dict[str, Any]] = []
    teleports: list[dict[str, Any]] = []
    current_stage: dict[str, Any] | None = None
    if selected is not None:
        bounds = {ordinal: (start, selected[position + 1][0] if position + 1 < len(selected) else len(records))
                  for position, (start, ordinal) in enumerate(selected)}
        all_start, all_stop = selected[0][0], len(records)
        fallback = _fallback_end(None, last_second, run_start, now_elapsed_sec)
        teleports = _teleports(records, all_start, all_stop, fallback)
        for ordinal, (start, stop) in bounds.items():
            index = ordinal - 1
            if index >= len(tasks):
                continue
            began = records[start].second
            ended, complete, ended_by = _end_for_task(records, start, stop)
            if not complete:
                ended = _fallback_end(None, last_second, run_start, now_elapsed_sec)
                ended_by = "last_log"
            tasks[index].update(elapsedSec=_elapsed(began, ended), complete=complete, endedBy=ended_by)
            if expected_tasks[index] == "自动秘境":
                rounds, stage = _domain_rounds(records, start, stop, ended if complete else None,
                                               last_second, run_start, now_elapsed_sec, expected_tasks[index], ended_by)
                if stage:
                    current_stage = stage
        if current_stage is None:
            incomplete = next((task for task in reversed(tasks) if not task["complete"] and task["elapsedSec"] is not None), None)
            if incomplete:
                current_stage = {
                    "name": "task",
                    "label": _PHASE_LABELS["task"],
                    "task": incomplete["name"],
                    "elapsedSec": incomplete["elapsedSec"],
                }
        # A pending teleport is more specific than the enclosing task or a
        # domain phase, so watchdog callers can act on it first.
        pending_teleport = next((item for item in reversed(teleports) if not item["complete"]), None)
        if pending_teleport:
            task = current_stage["task"] if current_stage else expected_tasks[-1]
            current_stage = {
                "name": "teleport",
                "label": _PHASE_LABELS["teleport"],
                "task": task,
                "elapsedSec": pending_teleport["elapsedSec"],
            }

    counters = _counters(records if selected is not None else [])
    return {
        "schemaVersion": 1,
        "tasks": tasks,
        "rounds": rounds,
        "teleports": teleports,
        "currentStage": current_stage,
        "counters": counters,
        "bottlenecks": _bottlenecks(tasks, rounds, teleports),
        "warnings": warnings,
    }
