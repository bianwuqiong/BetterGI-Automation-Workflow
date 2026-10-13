"""Pure post-run artifact-family yield; never changes run status or implies gear completion."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

try:
    from .cultivation import _integer, _json_file, _object, _run_id, _safe_path, _text
except ImportError:
    from cultivation import _integer, _json_file, _object, _run_id, _safe_path, _text


def model_family(model_table, artifact_set, class_prefix):
    artifact_set = _text(artifact_set, 'artifactSet')
    if not isinstance(class_prefix, str) or not re.fullmatch(r'relic:[1-9][0-9]*_', class_prefix):
        raise ValueError('target family requires an explicit exact relic family prefix')
    path = _safe_path(model_table)
    names, artifacts = {}, set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        table = csv.DictReader(stream)
        if not {'item_class_id', 'item_name', 'quality_level'} <= set(table.fieldnames or []):
            raise ValueError('native ItemV2 table lacks family/name/quality columns')
        for row in table:
            identifier, name = row['item_class_id'], row['item_name'].strip()
            if identifier.startswith('relic:') and name:
                artifacts.add(name)
            if not identifier.startswith(class_prefix):
                continue
            if not re.fullmatch(re.escape(class_prefix) + r'[1-5]', identifier) or not name:
                raise ValueError('target family has an unexpected slot or missing name')
            quality = int(row['quality_level'])
            if quality not in (1, 2, 3, 4, 5):
                raise ValueError('target family quality metadata is invalid')
            if identifier in names and names[identifier]['name'] != name:
                raise ValueError('target family has ambiguous item names')
            names.setdefault(identifier, {'name': name, 'modelQualities': set()})['modelQualities'].add(quality)
    if len(names) != 5 or len({row['name'] for row in names.values()}) != 5:
        raise ValueError('target family must contain five distinct pieces')
    family = {'artifactSet': artifact_set, 'classPrefix': class_prefix,
        'source': 'local-native-ItemV2-item.csv', 'modelTableSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'mappingMeaning': 'caller-supplied exact set-to-family mapping; CSV names and model quality variants only',
        'pieces': {identifier: {'name': row['name'], 'modelQualities': sorted(row['modelQualities'])}
                   for identifier, row in sorted(names.items())}}
    return family, artifacts


def build_target_yield(run_result, artifact_report, model_table, *, artifact_set, class_prefix):
    """Count only independently verified successful claims; zero target yield is a valid result."""
    run_result, report = _object(run_result, 'run result'), _object(artifact_report, 'artifact report')
    run_id = _run_id(run_result.get('runId'))
    summary = _object(run_result.get('artifactFarming'), 'independently verified artifact summary')
    if (summary.get('reportVerified') is not True or report.get('runId') != run_id
            or report.get('mode') != 'artifact-farming' or report.get('gameDate') != run_result.get('gameDate')
            or report.get('targetReached') is not False or report.get('target', {}).get('artifactSet') != artifact_set):
        raise ValueError('post-run yield requires a verified same-run target report')
    family, artifact_names = model_family(model_table, artifact_set, class_prefix)
    rewards, step_ids = {}, []
    for step in report.get('steps', []):
        if step.get('type') != 'claim' or step.get('status') != 'success':
            continue
        step_id = step.get('stepId')
        if not isinstance(step_id, str) or not step_id.startswith(run_id + ':step-') or step_id in step_ids:
            raise ValueError('artifact claim yield has ambiguous step identity')
        step_ids.append(step_id)
        for name, count in _object(step.get('rewards'), 'verified claim rewards').items():
            name = _text(name, 'reward name')
            rewards[name] = rewards.get(name, 0) + _integer(count, 1, 999999999, 'reward count')
    if summary.get('claims') != len(step_ids) or summary.get('rewards') != rewards:
        raise ValueError('saved claim rewards differ from the independent verified summary')
    target_names = {row['name'] for row in family['pieces'].values()}
    target = {name: rewards.get(name, 0) for name in sorted(target_names)}
    other = {name: count for name, count in rewards.items() if name in artifact_names and name not in target_names}
    total_target = sum(target.values())
    return {'schemaVersion': 1, 'kind': 'post-run-artifact-target-yield', 'runId': run_id,
        'gameDate': report['gameDate'], 'scopeId': report.get('policy', {}).get('scopeId'), 'target': report['target'],
        'familyMapping': family, 'verifiedClaimStepIds': step_ids, 'yieldMeaning': 'recognized reward names and quantities only',
        'targetSetPieces': target, 'targetSetPieceDrops': total_target, 'otherArtifactDrops': sum(other.values()),
        'otherArtifactRewards': other, 'targetSetYieldStatus': 'observed-target-pieces' if total_target else 'no-target-piece-observed',
        'qualityObserved': False, 'fiveStarDrops': None, 'mainStatsObserved': False, 'mainStatsMatched': None,
        'inventoryReconciled': False, 'targetReached': False, 'originalOutcome': run_result.get('outcome'),
        'changesRunOutcome': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--artifact-report', type=Path, required=True)
    parser.add_argument('--model-table', type=Path, required=True)
    parser.add_argument('--artifact-set', required=True)
    parser.add_argument('--class-prefix', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = build_target_yield(_json_file(_safe_path(args.result)), _json_file(_safe_path(args.artifact_report)),
        args.model_table, artifact_set=args.artifact_set, class_prefix=args.class_prefix)
    if args.output:
        try:
            from .workflow import atomic_json
        except ImportError:
            from workflow import atomic_json
        atomic_json(_safe_path(args.output), result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
