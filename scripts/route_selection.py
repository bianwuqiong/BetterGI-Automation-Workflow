"""Pure read-only handguard route preview. Never runs or authorizes a route.

Requirements are the materials still required by future upgrades BEFORE assigning
current stock. They are not shortages that have already subtracted that stock.
Only exact inventory and material output evidence participate. All future output
and 3:1 promotions remain hypothetical, including forecasts from historical gains.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import math
import re

MATERIAL_IDS = ('112044', '112045', '112046')
WEIGHTS = (1, 3, 9)
OVERLAP_DISTANCE = 80.0
_ATTEMPTED = {'started', 'completed', 'partial', 'failed', 'unknown', 'cancelled', 'timeout'}
_UNRESOLVED = _ATTEMPTED - {'completed'}


def game_date_at(now: datetime) -> str:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('preview clock must be timezone aware')
    return (now.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)).date().isoformat()


def _date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid game date')
    datetime.fromisoformat(value)
    return value


def _counts(rows: object, *, exact: bool) -> tuple[int, int, int]:
    if not isinstance(rows, dict) or set(rows) != set(MATERIAL_IDS):
        raise ValueError('all three handguard tiers are required')
    counts = []
    for identifier in MATERIAL_IDS:
        row = rows[identifier]
        if exact:
            if not isinstance(row, dict) or row.get('status') != 'exact':
                raise ValueError('inventory is unknown or lower bound')
            row = row.get('count')
        if type(row) is not int or not 0 <= row <= 999999999:
            raise ValueError('material count must be a bounded exact integer')
        counts.append(row)
    return tuple(counts)


def _rows(counts: tuple[int, int, int]) -> dict[str, int]:
    return dict(zip(MATERIAL_IDS, counts))


def _allocation(stock: tuple[int, int, int], requirements: tuple[int, int, int]) -> dict:
    # Reserve each actual tier's direct demand before using any surplus upwards.
    direct = [min(count, needed) for count, needed in zip(stock, requirements)]
    missing = [needed - reserved for needed, reserved in zip(requirements, direct)]
    surplus = [count - reserved for count, reserved in zip(stock, direct)]
    actual_shortages = missing[:]
    # Partial lower-tier inputs count as useful progress toward a missing higher
    # tier, but are never represented as a completed or fractional craft output.
    lower_for_mid = min(surplus[0], missing[1] * 3)
    lower_for_high = min(surplus[0] - lower_for_mid + surplus[1] * 3, missing[2] * 9)
    deficit = sum(n * weight for n, weight in zip(missing, WEIGHTS)) - lower_for_mid - lower_for_high
    promotions = []
    mid_for_direct = min(missing[1], surplus[0] // 3)
    if mid_for_direct:
        promotions.append({'from': MATERIAL_IDS[0], 'to': MATERIAL_IDS[1], 'count': mid_for_direct})
        surplus[0] -= mid_for_direct * 3
        missing[1] -= mid_for_direct
    # An incomplete direct mid demand must reserve any remaining low-tier inputs.
    if missing[1]:
        surplus[0] = 0
    high_from_surplus = min(missing[2], (surplus[1] + surplus[0] // 3) // 3)
    mid_for_high = max(0, high_from_surplus * 3 - surplus[1])
    if mid_for_high:
        promotions.append({'from': MATERIAL_IDS[0], 'to': MATERIAL_IDS[1], 'count': mid_for_high})
    if high_from_surplus:
        promotions.append({'from': MATERIAL_IDS[1], 'to': MATERIAL_IDS[2], 'count': high_from_surplus})
        missing[2] -= high_from_surplus
    return {'hypothetical': True, 'actualShortages': _rows(tuple(actual_shortages)),
            'shortagesAfterLegalPromotions': _rows(tuple(missing)),
            'suggestedPromotions': promotions, 'remainingMaterialEquivalent': deficit,
            'equivalentUnit': 'old-handguard', 'actualInventoryChanged': False}


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 120 or any(ord(c) < 32 for c in value):
        raise ValueError('candidate identity missing or invalid')
    return value


def _points(value: object) -> list[tuple[float, float]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 500:
        raise ValueError('explicit bounded fight-point coverage required')
    result = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError('fight point must have map coordinates')
        pair = tuple(row.get(key) for key in ('x', 'y'))
        if any(type(n) not in (int, float) or not math.isfinite(n) or abs(n) > 100000 for n in pair):
            raise ValueError('fight point must have finite map coordinates')
        result.append(pair)
    if len(result) != len(set(result)):
        raise ValueError('duplicate fight-point coverage')
    return result


class _Coverage:
    """Conservative physical coverage index; author/hash changes cannot reset it."""
    def __init__(self):
        self.cells = {}

    def add(self, points, scope):
        for x, y in points:
            self.cells.setdefault((math.floor(x / OVERLAP_DISTANCE), math.floor(y / OVERLAP_DISTANCE)), []).append((x, y, scope))

    def overlap(self, points):
        for x, y in points:
            bx, by = math.floor(x / OVERLAP_DISTANCE), math.floor(y / OVERLAP_DISTANCE)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for px, py, scope in self.cells.get((bx + dx, by + dy), ()):
                        if (px - x) ** 2 + (py - y) ** 2 <= OVERLAP_DISTANCE ** 2:
                            return scope
        return None


def _yield(candidate: dict, now: datetime) -> tuple[tuple[int, int, int], str]:
    evidence = candidate.get('yieldEvidence')
    if not isinstance(evidence, dict) or evidence.get('verified') is not True:
        raise ValueError('unverified material output')
    if any(evidence.get(key) != candidate[key] for key in ('candidateId', 'sha256', 'catalogCommit')):
        raise ValueError('output evidence belongs to another pinned route')
    recorded = evidence.get('recordedAtUTC')
    if not isinstance(recorded, str):
        raise ValueError('output evidence time missing')
    try:
        at = datetime.fromisoformat(recorded.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('output evidence time invalid') from error
    if at.tzinfo is None or at.utcoffset() is None or at > now:
        raise ValueError('output evidence time invalid or future')
    source = evidence.get('source')
    if source == 'actual_net_inventory':
        if evidence.get('outcome') != 'completed':
            raise ValueError('unknown or partial route outcome is not a verified total yield')
        before, after = _counts(evidence.get('before'), exact=True), _counts(evidence.get('after'), exact=True)
        counts = tuple(b - a for a, b in zip(before, after))
        if any(n < 0 for n in counts):
            raise ValueError('negative inventory change cannot forecast route output')
    elif source == 'explicit_material_count_estimate':
        if evidence.get('basisType') != 'material_count' or not isinstance(evidence.get('basis'), str) or not evidence['basis'].strip():
            raise ValueError('enemy/file/fight annotations cannot substitute for material counts')
        counts = _counts(evidence.get('materialCounts'), exact=False)
    else:
        raise ValueError('source is not material-output evidence')
    return counts, source


def preview_route_selection(inventory: dict, requirements: dict, candidates: list, *,
                            now: datetime, day_records: list | None = None) -> dict:
    """Rank eligible nonoverlapping segments by useful total, then duration/reliability.

    ``day_records`` contains externally verified route-day records with candidateId,
    gameDate, status and fightPoints. Current-day attempted scopes and all unresolved
    scopes are excluded, even after author/hash/day changes. No replay is issued.
    Candidate eligibilityVerified/availableGameDate must come from a separate local
    review of uncleared/spawned points; the 04:00 calendar alone proves no respawn.
    """
    day = game_date_at(now)
    report = {'previewOnly': True, 'executionAuthorized': False, 'inventoryChanged': False,
              'ledgerChanged': False, 'gameDate': day, 'gameDayTimezone': 'UTC+8', 'resetHour': 4,
              'futureYieldIsHypothetical': True, 'rankable': False, 'ranked': [], 'excluded': []}
    try:
        stock = _counts(inventory, exact=True)
        needed = _counts(requirements, exact=False)
    except ValueError as error:
        report['reason'] = str(error)
        return report
    if not isinstance(candidates, list) or len(candidates) > 100:
        raise ValueError('candidate list exceeds preview bound')
    records = [] if day_records is None else day_records
    if not isinstance(records, list) or len(records) > 200:
        raise ValueError('day records exceed preview bound')
    reserved, attempted = _Coverage(), set()
    total_points = 0
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('malformed route-day record')
        record_day = _date(row.get('gameDate'))
        status = row.get('status')
        if status not in _ATTEMPTED:
            raise ValueError('unknown route-day status cannot be ignored')
        scope = _identifier(row.get('candidateId'))
        points = _points(row.get('fightPoints'))
        total_points += len(points)
        if total_points > 5000:
            raise ValueError('day coverage exceeds preview bound')
        if record_day > day:
            raise ValueError('future day record cannot prove current eligibility')
        if record_day == day or status in _UNRESOLVED:
            attempted.add(scope)
            reserved.add(points, scope)
    baseline = _allocation(stock, needed)
    report['currentAllocation'] = baseline
    report['requirementsMeaning'] = 'future upgrade requirements before assigning current inventory'
    ranked = []
    identities = Counter(row.get('candidateId') for row in candidates
                         if isinstance(row, dict) and isinstance(row.get('candidateId'), str))
    total_points = 0
    for row in candidates:
        scope = row.get('candidateId') if isinstance(row, dict) else None
        try:
            if not isinstance(row, dict):
                raise ValueError('candidate is not an object')
            scope = _identifier(scope)
            if identities[scope] != 1:
                raise ValueError('duplicate candidate identity')
            if not re.fullmatch('[0-9a-f]{64}', str(row.get('sha256', ''))) or not re.fullmatch('[0-9a-f]{40}', str(row.get('catalogCommit', ''))):
                raise ValueError('candidate is not hash/commit pinned')
            if row.get('status') != 'unattempted' or scope in attempted:
                raise ValueError('attempted or unknown route is not replayable')
            if row.get('eligibilityVerified') is not True or _date(row.get('availableGameDate')) != day:
                raise ValueError('uncleared current-day coverage has not been verified')
            points = _points(row.get('fightPoints'))
            total_points += len(points)
            if total_points > 5000:
                raise ValueError('candidate coverage exceeds preview bound')
            conflict = reserved.overlap(points)
            if conflict is not None:
                raise ValueError('coverage overlaps a cleared/attempted/unresolved scope: ' + conflict)
            gains, source = _yield(row, now)
            projected = tuple(n + gain for n, gain in zip(stock, gains))
            allocation = _allocation(projected, needed)
            useful = baseline['remainingMaterialEquivalent'] - allocation['remainingMaterialEquivalent']
            if useful <= 0:
                raise ValueError('no shortage-limited useful material progress')
            duration = row.get('estimatedDurationSeconds')
            if duration is not None and (type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 86400):
                raise ValueError('duration estimate must be positive and bounded')
            reliability = row.get('reliability')
            if reliability is not None:
                if (not isinstance(reliability, dict) or type(reliability.get('successfulRuns')) is not int
                        or type(reliability.get('attemptedRuns')) is not int
                        or not 0 <= reliability['successfulRuns'] <= reliability['attemptedRuns'] <= 10000
                        or reliability['attemptedRuns'] == 0):
                    raise ValueError('reliability needs observed bounded run counts')
                reliability = reliability['successfulRuns'] / reliability['attemptedRuns']
            ranked.append({'candidateId': scope, 'sha256': row['sha256'], 'catalogCommit': row['catalogCommit'],
                           'usefulMaterialEquivalent': useful, 'yieldMaterialCounts': _rows(gains),
                           'yieldEvidenceSource': source, 'yieldUncertainty': 'historical result is a future forecast' if source == 'actual_net_inventory' else 'explicit material estimate; not measured output',
                           'estimatedDurationSeconds': duration, 'reliability': reliability,
                           'hypotheticalAllocation': allocation, '_points': points})
        except ValueError as error:
            report['excluded'].append({'candidateId': scope, 'reason': str(error), 'rankable': False})
    ranked.sort(key=lambda row: (-row['usefulMaterialEquivalent'], row['estimatedDurationSeconds'] if row['estimatedDurationSeconds'] is not None else math.inf,
                                 -(row['reliability'] if row['reliability'] is not None else -1), row['candidateId']))
    # These are alternative rankings, not an additive yield itinerary. A second
    # selected segment still needs fresh stock and shortage-limited re-ranking.
    selected = _Coverage()
    for row in ranked:
        conflict = selected.overlap(row['_points'])
        if conflict is not None:
            report['excluded'].append({'candidateId': row['candidateId'], 'reason': 'coverage overlaps a higher-ranked alternative: ' + conflict, 'rankable': False})
        else:
            selected.add(row['_points'], row['candidateId'])
            report['ranked'].append({key: value for key, value in row.items() if key != '_points'})
    report['rankable'] = bool(report['ranked'])
    report['rankingMeaning'] = 'alternative segments ranked by useful total; not an authorized/additive itinerary'
    return report
