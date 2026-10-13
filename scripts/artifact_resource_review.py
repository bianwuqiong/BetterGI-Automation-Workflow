"""Explicit positive pre-submit review. Task unknown and resource certainty stay separate."""
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import io

try:
    from . import artifact_farming as artifact
    from .cultivation import _json_file, _safe_path, _timestamp
    from .analyze_run import _event_from_line
except ImportError:
    import artifact_farming as artifact
    from cultivation import _json_file, _safe_path, _timestamp
    from analyze_run import _event_from_line

LEGACY_LITERAL = '受保护单次树脂第一行/独立使用按钮未获新鲜双帧证明，未提交且禁止通用确认或其他资源'
DLL7_SHA256 = '53c3af3401f6349eca9e61a7e6276b71f7f103bf64962254851cb68a9534d882'
DLL10_SHA256 = 'ac67f446b6b54fcfa6e0ded29b6fe3949fad532e69b5e570e0c760465f425155'
V10_SHIELD_FAILURE = '钟离连续两帧出战未获核验，停止战斗'
V10_CONTROL_SOURCES = {
    'BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.cs': '9d8e88ca0a25f91c0f467230a40f77f36381447632c753c7d0c72660e62c2c82',
    'BetterGenshinImpact/GameTask/AutoDomain/DomainCombatSafety.cs': '48ef56d0e4fe2c102963bba9cdfafc7e00c49b4b733416874ae3aeb217378daa',
    'BetterGenshinImpact/GameTask/AutoFight/ZhongliHoldShieldGuard.cs': 'dfcb7ca17b12852bebb31e43ac64598b7e7063418e971f8d85eaaa352d060333',
    'BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.SingleOriginal20.cs': '89a7d9fbcc199767f0a0171c760b80c4337b0f58cf4dcdb237bce5beb4bd7984',
}


def _full_frame_dimensions(content, declared_format=None):
    detected='PNG' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'JPEG' if content.startswith(b'\xff\xd8\xff') else None
    if detected is None or (declared_format is not None and declared_format!=detected):
        raise ValueError('actual full-HUD image signature/declared format mismatch')
    if detected=='JPEG' and not content.endswith(b'\xff\xd9'):
        raise ValueError('actual JPEG full frame is truncated')
    try:
        from PIL import Image
        with Image.open(io.BytesIO(content)) as image:
            if image.format!=detected: raise ValueError('image format differs from its signature')
            dimensions=image.size
            if dimensions[0]>4096 or dimensions[1]>2160: raise ValueError('context frame dimensions outside supported full window')
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()  # JPEG verify alone does not decode the entropy stream.
    except Exception as exc:
        raise ValueError('actual full-HUD image is invalid/truncated or verifier unavailable') from exc
    return dimensions


def _validate_full_frame_layout(width,height,metadata):
    if metadata.get('layout') == 'raw-sky-window-frame':
        region=metadata.get('clientRegion')
        expected={'x':1,'y':30,'width':1536,'height':864}
        if ((width,height)!=(1538,895) or not isinstance(region,dict)
                or any(type(region.get(key)) is not int or region[key]!=value for key,value in expected.items())
                or region['x']+region['width']!=width-1 or region['y']+region['height']!=height-1):
            raise ValueError('raw Sky context does not match the observed full window/client boundaries')
    elif width<800 or abs(width*9-height*16)>16:
        raise ValueError('context attachment is not a full game frame')


def _v10_source_phase_proof(root, run_id, report, param, text, context_path):
    """Pinned binary/source control-flow plus a real root-reviewed context attachment."""
    base = _safe_path(root/'state/audit-native10-before-shield-fix')
    manifest_path, binary_path = base/'manifest.json', base/'BetterGI.dll'
    manifest = _json_file(manifest_path)
    if manifest.get('dllSha256') != DLL10_SHA256 or hashlib.sha256(binary_path.read_bytes()).hexdigest() != DLL10_SHA256:
        raise ValueError('native10 compiled audit identity is not the explicitly reviewed baseline')
    files = manifest.get('files')
    if not isinstance(files, dict) or not V10_CONTROL_SOURCES.items() <= files.items():
        raise ValueError('native10 control-flow source fingerprints differ from audited baseline')
    paths = [manifest_path, binary_path]
    for relative, digest in files.items():
        path = _safe_path(base/relative)
        if not path.is_relative_to(base) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('native10 audit source file changed')
        paths.append(path)
    source = (base/'BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.cs').read_text(encoding='utf-8-sig')
    guard = (base/'BetterGenshinImpact/GameTask/AutoFight/ZhongliHoldShieldGuard.cs').read_text(encoding='utf-8-sig')
    safety = (base/'BetterGenshinImpact/GameTask/AutoDomain/DomainCombatSafety.cs').read_text(encoding='utf-8-sig')
    do_domain = source[source.index('private async Task DoDomain()'):source.index('private void Init()')]
    fight = source[source.index('private async Task StartFight('):source.index('private async Task StartJsonFight()')]
    if (report.get('reason') != V10_SHIELD_FAILURE or param.get('RequireZhongliShieldCast') is not True
            or param.get('DomainRoundNum') != 1 or param.get('CombatOnly') is not False
            or not param.get('CombatStrategyPath', '').endswith('.txt')
            or 'protectedCombat ? 1 : _config.ReviveRetryCount' not in source
            or 'if (protectedCombat) throw;' not in source
            or 'combatOnly ? 1 : configuredRounds' not in safety
            or not do_domain.index('await StartFight(combatScenes, combatCommands);') < do_domain.index('await FindPetrifiedTree();') < do_domain.index('await GettingTreasure()')
            or 'await WalkToPressF();' not in do_domain[do_domain.index('await FindPetrifiedTree();'):]
            or 'await Task.WhenAll(combatTask, domainEndTask);' not in fight
            or 'Logger.LogWarning(e.Message);\n                throw;' not in fight
            or guard.count(V10_SHIELD_FAILURE) != 1 or 'if (!zhongli.TrySwitchVerified(activeContext)) throw new InvalidOperationException("'+V10_SHIELD_FAILURE+'");' not in guard):
        raise ValueError('v10 exception/parameters/single-round awaited phase order do not prove pre-reward failure')
    target = report.get('target', {})
    if (param.get('DomainName') != target.get('domainName') or param.get('PartyName') != target.get('partyName')
            or param.get('CombatStrategyPath', '').replace('\\', '/').rsplit('/', 1)[-1] != target.get('strategyName', '')+'.txt'):
        raise ValueError('v10 native battle parameters are not bound to this scoped target/party/strategy')
    if ('2. 执行战斗策略' not in text or V10_SHIELD_FAILURE not in text
            or any(marker in text for marker in ('3. 寻找石化古树', '4. 走到石化古树处', '5. 领取奖励', '领取奖励成功', '已使用浓缩树脂'))):
        raise ValueError('native phase trace conflicts with the v10 pre-reward source path')
    context_path = _safe_path(context_path)
    context = _json_file(context_path)
    fixed = {'schemaVersion':1,'kind':'root-observed-native10-battle-failure-context','runId':run_id,
        'stepId':run_id+':step-1','reviewedBy':'root-agent','nativeDllSha256':DLL10_SHA256,
        'runtimeIdentityConfirmed':True,'battleClockActiveObserved':True,'remainingEnemiesObserved':2,
        'totalEnemiesObserved':4,'claimUiObserved':False,'manualRewardClaimObserved':False}
    if any(type(context.get(key)) is not type(value) or context[key] != value for key,value in fixed.items()):
        raise ValueError('explicit real native10 run context attestation missing')
    image = _safe_path(context['fullFrame']['path'])
    image_bytes = image.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != context['fullFrame']['sha256']:
        raise ValueError('actual full-HUD image context is missing/changed')
    width,height = _full_frame_dimensions(image_bytes,context['fullFrame'].get('format'))
    _validate_full_frame_layout(width,height,context['fullFrame'])
    finished = _timestamp(report['finishedAt'],'run finish')
    exact_capture = context['fullFrame'].get('capturedAtUTC')
    interval = context['fullFrame'].get('captureTimeEvidence')
    if exact_capture is not None:
        captured_lower = captured_upper = _timestamp(exact_capture,'real frame capture')
        if not _timestamp(report['startedAt'],'run start') <= captured_lower or (captured_upper-finished).total_seconds() > 120:
            raise ValueError('real frame context is not within the scoped run or its immediate failed-battle aftermath')
    elif isinstance(interval,dict):
        if (interval.get('kind')!='trusted-ordered-tool-history-with-file-save-upper-bound'
                or interval.get('capturedAtUTC') is not None or not isinstance(interval.get('toolHistoryNote'),str)
                or not interval['toolHistoryNote'].strip()):
            raise ValueError('truthful ordered capture/save evidence required when capture timestamp is unavailable')
        captured_lower = _timestamp(interval.get('capturedAfterUTC'),'capture lower bound')
        captured_upper = _timestamp(interval.get('savedAtUTC'),'actual file-save upper bound')
        result_path=_safe_path(root/'logs/runs'/run_id/'result.json')
        result=_json_file(result_path)
        runner_finished=_timestamp(result.get('finishedAt'),'actual runner finish')
        if (result.get('runId')!=run_id or runner_finished<finished or captured_lower != runner_finished or not captured_lower <= captured_upper
                or (captured_upper-captured_lower).total_seconds()>120
                or abs(captured_upper.timestamp()-image.stat().st_mtime)>1):
            raise ValueError('capture/save bounds are too wide, unordered, or differ from actual file mtime')
        paths.append(result_path)
    else:
        raise ValueError('capture timestamp is unavailable and no ordered real tool-history bounds are supplied')
    exit_observation = context.get('exitObservation',{})
    if (exit_observation.get('worldExitObserved') is not True or exit_observation.get('observedBy') != 'root-agent'
            or exit_observation.get('sourceKind') != 'trusted-tool-history-written-observation'
            or exit_observation.get('imageEvidenceMissing') is not True
            or not isinstance(exit_observation.get('toolHistoryNote'),str) or not exit_observation['toolHistoryNote'].strip()):
        raise ValueError('truthful failed-exit tool-history observation required; do not invent an image')
    exact_exit=exit_observation.get('observedAtUTC')
    if exact_exit is not None:
        exit_at = _timestamp(exact_exit,'actual exit observation')
    else:
        exit_at = _timestamp(exit_observation.get('exitedBeforeUTC'),'truthful exit upper bound')
        machine_run=exit_observation.get('worldBeforeMachineRunId')
        artifact._run_id(machine_run)
        machine=_json_file(_safe_path(root/'logs/runs'/machine_run/'result.json'))
        if (machine.get('runId')!=machine_run or machine.get('partyPreparation',{}).get('reportVerified') is not True
                or machine.get('partyPreparation',{}).get('preparationCompleted') is not True
                or _timestamp(machine.get('triggeredAt'),'world-before preparation trigger') != exit_at):
            raise ValueError('exit upper bound is not tied to the later real verified world-preparation run')
        paths.append(_safe_path(root/'logs/runs'/machine_run/'result.json'))
    if exit_at < captured_upper or exit_at < finished or (exit_at-captured_upper).total_seconds()>300:
        raise ValueError('exit observation bounds are unordered or too wide for immediate failed-battle context')
    paths += [context_path,image]
    return {'kind':'explicit-pinned-native10-before-reward-flow-source-and-context',
        'dllSha256':DLL10_SHA256,'phase':'single-round protected battle; awaited failure before tree/reward flow',
        'nativePositiveEventFabricated':False,'exitImageMissingPreserved':True,
        'captureAtUTCExactKnown':exact_capture is not None,'exitAtUTCExactKnown':exact_exit is not None,
        'exitObservedBeforeUTC':exit_at.isoformat()},paths


def classified_resource_zero(root, row):
    if row.get('resourceState') != 'known_not_submitted' or row.get('status') != 'unknown':
        return False
    if row.get('verifiedResourceConsumption') != {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0}:
        return False
    relative = row.get('resourceReviewPath')
    if not isinstance(relative, str) or Path(relative).is_absolute(): return False
    path = _safe_path(Path(root) / relative)
    if path != _safe_path(Path(root) / 'logs/runs' / row['runId'] / 'resource-pre-submit-review.json'): return False
    audit = _json_file(path)
    sources=audit.get('sourceSha256')
    if not isinstance(sources,dict) or not sources: return False
    required={str(Path('logs/runs')/row['runId']/name) for name in
        ('result.json','artifact-farming-report.json','artifact-farming-group.json','bettergi.log')}
    if not required <= sources.keys(): return False
    try:
        for relative,digest in sources.items():
            source=_safe_path(Path(relative) if Path(relative).is_absolute() else Path(root)/relative)
            if hashlib.sha256(source.read_bytes()).hexdigest()!=digest: return False
    except (OSError,ValueError):
        return False
    return (hashlib.sha256(path.read_bytes()).hexdigest() == row.get('resourceReviewSha256')
        and audit.get('runId') == row['runId'] and audit.get('gameDate') == row['gameDate']
        and audit.get('reviewedBy') == 'root-agent' and audit.get('taskOutcomePreserved') == 'unknown'
        and audit.get('resourceState') == 'known_not_submitted' and audit.get('positiveSubmissionBoundaryVerified') is True
        and audit.get('noRefundOfConfirmedConsumption') is True and audit.get('automaticReplayAllowed') is False)


def review_known_unsubmitted_claim(root, run_id, fresh_probe_run_id, *, reviewed_by,
        allow_source_audited_v7=False, source_audited_native10_context=None, apply=False, now=None):
    """Only a scoped positive latch-false boundary plus independent fresh balances.

    A missing reward event, network cancellation, or unchanged balance alone
    cannot establish this classification. This never edits the old task/report.
    """
    try:
        from .workflow import RunLock, atomic_json
    except ImportError:
        from workflow import RunLock, atomic_json
    if reviewed_by != 'root-agent': raise ValueError('explicit root-agent resource review required')
    artifact._run_id(run_id)
    root = _safe_path(root)
    now = now or datetime.now(timezone.utc)
    date = artifact.game_date(now)
    with RunLock(root / 'state/workflow.lock'):
        directory = _safe_path(root / 'logs/runs' / run_id)
        paths = [directory / name for name in ('result.json', 'artifact-farming-report.json', 'artifact-farming-group.json', 'bettergi.log')]
        result, report, group = (_json_file(path) for path in paths[:3])
        source_date = report.get('gameDate')
        ledger_path = _safe_path(root / 'state/artifact-checkpoints' / (source_date + '.json'))
        ledger = _json_file(ledger_path)
        matches = [row for row in ledger['runs'] if row.get('runId') == run_id]
        if len(matches) != 1: raise ValueError('resource review source ledger is ambiguous')
        row = matches[0]
        settings = group['Projects'][0]['JsScriptSettingsObject']
        if (row.get('status') != 'unknown' or row.get('resourceState') is not None or result.get('outcome') != 'unknown'
                or result.get('runId') != run_id or report.get('runId') != run_id or report.get('status') != 'unknown'
                or report.get('configSha256') != row.get('configSha256') or settings.get('configSha256') != row.get('configSha256')
                or report.get('totals') != {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0}
                or report.get('policy', {}).get('maxCrafts') != 0
                or any(row.get(key) is not None for key in ('originalResinSpent', 'condensedResinSpent', 'crafts'))):
            raise ValueError('only preserved unknown single unsubmitted claim with zero prior resource steps is supported')
        steps = report.get('steps')
        if not isinstance(steps, list) or len(steps) != 1: raise ValueError('resource review cannot hide other steps')
        step = steps[0]
        if step.get('status') != 'unknown' or step.get('type') != 'claim' or step.get('resin') not in ('condensed','original') or step.get('stepId') != run_id + ':step-1':
            raise ValueError('resource review is limited to the exact single condensed/original20 claim')
        param = step.get('parameterEvidence', {})
        fixed = {'DomainRoundNum': 1, 'CondensedResinUseCount': int(step['resin']=='condensed'), 'OriginalResinUseCount': 0,
            'OriginalResin20UseCount': int(step['resin']=='original'), 'OriginalResin40UseCount': 0, 'FragileResinUseCount': 0,
            'TransientResinUseCount': 0, 'SpecifyResinUse': True, 'AutoArtifactSalvage': False,
            'ArtifactRunId': run_id, 'ArtifactStepId': step['stepId']}
        if any(type(param.get(key)) is not type(value) or param[key] != value for key, value in fixed.items()):
            raise ValueError('resource review native single-claim parameters mismatch')
        text = paths[3].read_text(encoding='utf-8-sig')
        events = [_event_from_line(line) for line in text.splitlines() if '[AUTO_GAME_EVENT]' in line]
        if any(event is None or event.get('task') == 'artifact-domain-claim' for event in events):
            raise ValueError('ambiguous or returned claim receipt contradicts pre-submit review')
        positive = [event for event in events if event.get('task') == 'artifact-domain-pre-submit-aborted'
            and event.get('status') == 'pre_submit_aborted' and event.get('runId') == run_id
            and event.get('stepId') == step['stepId'] and event.get('stateNotSubmitted') is True
            and event.get('claimSubmissionRequested') is False and event.get('resourceOutcome') == 'unknown']
        proof = None
        legacy_paths = []
        if len(positive) == 1:
            event=positive[0]
            if event.get('source') == 'invocation_owned_monotonic_resource_phase' or event.get('owner')=='AutoDomainTask':
                scoped={'owner':'AutoDomainTask','roundCount':1,'activeRound':0,'completedClaimCount':0,
                    'claimSubmissionRequested':False,'submissionRequests':0,'resin':step['resin']}
                phase=event.get('phase')
                if (any(type(event.get(key)) is not type(value) or event[key]!=value for key,value in scoped.items())
                        or phase not in ('before_reward_interaction','pre_submit_validation')
                        or (phase=='before_reward_interaction' and
                            (event.get('source')!='invocation_owned_monotonic_resource_phase'
                             or event.get('rewardFlowEntered') is not False or event.get('rewardInteractionEntered') is not False))):
                    raise ValueError('invocation-owned positive event conflicts with round/phase/submission ownership')
            elif step['resin'] != 'condensed':
                raise ValueError('original20 review requires the invocation-owned positive resource phase event')
            proof = {'kind': 'positive-native-latch-false-event', 'event': positive[0]}
        elif allow_source_audited_v7 and step['resin']=='condensed' and not positive and report.get('reason') == LEGACY_LITERAL:
            binary = _safe_path(root / 'state/condensed-claim-row-engine-backup-20261012/BetterGI.dll')
            source = _safe_path(root / 'state/condensed-row-overlay-base/BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.SingleOriginal20.cs')
            latch = _safe_path(root / 'better-genshin-impact/BetterGenshinImpact/GameTask/AutoDomain/SingleOriginal20ClaimSafety.cs')
            source_text, latch_text = source.read_text(encoding='utf-8-sig'), latch.read_text(encoding='utf-8-sig')
            compact = re.sub(r'\s+', '', source_text)
            if (hashlib.sha256(binary.read_bytes()).hexdigest() != DLL7_SHA256
                    or 'if(!submission.Requested)thrownewNormalEndException("' + LEGACY_LITERAL + '");' not in compact
                    or latch_text.index('Requested = true;') >= latch_text.index('click(second!.Button);')):
                raise ValueError('legacy exact literal is not bound to the audited v7 pre-click boundary')
            legacy_paths = [binary, source, latch]
            proof = {'kind': 'explicit-source-audited-v7-pre-click-boundary', 'literal': LEGACY_LITERAL, 'dllSha256': DLL7_SHA256}
        elif source_audited_native10_context is not None and step['resin']=='condensed' and not positive:
            proof,legacy_paths = _v10_source_phase_proof(root,run_id,report,param,text,source_audited_native10_context)
        if proof is None: raise ValueError('positive pre-submit proof missing; absence of events is insufficient')
        observation, balances, probe_paths = artifact._probe_resin_for_review(root, fresh_probe_run_id, date, now,
            report['policy']['condensedCapacity'])
        before = step['before']
        old_balance = artifact._resin(before, _timestamp(before['observedAt'], 'old before'), source_date,
            report['policy']['condensedCapacity'])
        observed = _timestamp(observation['observedAt'], 'fresh after')
        finished = _timestamp(report['finishedAt'], 'unknown source finish')
        if observed < finished: raise ValueError('independent balance precedes the failed source task')
        if proof.get('exitObservedBeforeUTC') is not None and observed < _timestamp(proof['exitObservedBeforeUTC'],'reviewed exit bound'):
            raise ValueError('independent world balance precedes the root-reviewed failed exit')
        max_growth = math.ceil((observed - _timestamp(before['observedAt'], 'before')).total_seconds()/480) + 1
        if balances[1] != old_balance[1] or not old_balance[0] <= balances[0] <= min(200, old_balance[0]+max_growth):
            raise ValueError('fresh independent balances do not corroborate the positive no-submit boundary')
        audit = {'schemaVersion': 1, 'kind': 'explicit-positive-pre-submit-resource-review', 'runId': run_id,
            'gameDate': source_date, 'stepId': step['stepId'], 'reviewedBy': reviewed_by, 'reviewedAtUTC': now.isoformat(),
            'taskOutcomePreserved': 'unknown', 'stepOutcomePreserved': 'unknown', 'resourceState': 'known_not_submitted',
            'positiveSubmissionBoundaryVerified': True, 'proof': proof, 'before': before, 'freshResinObservation': observation,
            'freshProbeRunId': fresh_probe_run_id, 'noRefundOfConfirmedConsumption': True, 'automaticReplayAllowed': False,
            'sourceSha256': {str(path.relative_to(root)) if path.is_relative_to(root) else str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths + probe_paths + legacy_paths}}
        if apply:
            audit_path = directory / 'resource-pre-submit-review.json'
            if audit_path.exists(): raise ValueError('existing resource review must not be overwritten')
            atomic_json(audit_path, audit)
            row.update(resourceState='known_not_submitted', verifiedResourceConsumption={
                'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0},
                resourceReviewPath=str(audit_path.relative_to(root)), resourceReviewSha256=hashlib.sha256(audit_path.read_bytes()).hexdigest())
            atomic_json(ledger_path, ledger)
        return audit


def review_approved_batch_stage(root, parent_run_id, new_config, fresh_probe_run_id, *, reviewed_by, apply=False, now=None):
    """One new single-condensed or single20 stage charged to the approved batch.

    Preserves every old task/step outcome and human approval time. Cannot cover
    any committed-unknown transaction or allocate a second condensed unit.
    """
    try:
        from .workflow import RunLock, atomic_json
    except ImportError:
        from workflow import RunLock, atomic_json
    if reviewed_by != 'root-agent': raise ValueError('explicit root-agent stage review required')
    root, config = _safe_path(root), artifact.normalize_config(new_config)
    now = now or datetime.now(timezone.utc)
    date = artifact.game_date(now)
    policy = config['policy']
    if (not config['executionEnabled'] or policy['validationOnly']
            or (policy['originalResinBudget'],policy['condensedResinBudget']) not in ((0,1),(20,0))
            or policy['maxCrafts'] != 0 or policy['maxClaims'] != 1 or policy['maxMinutes'] > 5):
        raise ValueError('approved-batch stage is strictly original0/condensed1 OR original20/condensed0/no-craft/one-claim/max5min')
    with RunLock(root / 'state/workflow.lock'):
        packets = [(path, _json_file(_safe_path(path))) for path in (root / 'state/artifact-checkpoints').glob('*.json')]
        parents = [row for _, packet in packets for row in packet['runs'] if row.get('runId') == parent_run_id]
        if len(parents) != 1 or not classified_resource_zero(root, parents[0]):
            raise ValueError('parent resource state is not explicitly known-not-submitted')
        parent = parents[0]
        report_path = _safe_path(root / 'logs/runs' / parent_run_id / 'artifact-farming-report.json')
        report = _json_file(report_path)
        if report['target'] != config['target'] or parent['scopeId'] == policy['scopeId']:
            raise ValueError('new stage target/scope does not match the parent approved batch')
        funding_scope,permission_path,permission,authorization_path,authorization,chain = _funding_authority(root,parent,packets)
        authorization = _json_file(authorization_path)
        if (permission.get('approvedAtUTC') != authorization.get('approvedAtUTC')
                or not _timestamp(permission['approvedAtUTC'], 'actual parent approval') <= now < _timestamp(permission['validUntilUTC'], 'parent end')):
            raise ValueError('stage lacks the original explicitly approved batch/window')
        current = next((packet for path, packet in packets if path.name == date+'.json'), {'schemaVersion':1,'gameDate':date,'runs':[]})
        unknown = artifact._unknown_rows(root, date, current)
        if [artifact._run_source_fingerprint(root, item) for item in unknown] != permission.get('sourceRuns'):
            raise ValueError('new unreviewed resource unknown remains globally blocked')
        usage = _funding_usage(root,funding_scope,packets,authorization,permission)
        _check_stage_funds(policy,usage,authorization)
        observation, balances, probe_paths = artifact._probe_resin_for_review(root, fresh_probe_run_id, date, now, policy['condensedCapacity'])
        if balances[1] < policy['condensedResinBudget'] or balances[0]-policy['reserveOriginalResin'] < policy['originalResinBudget']:
            raise ValueError('new stage lacks independently verified actual resource balance/reserve')
        scope = policy['scopeId']
        if any(row.get('scopeId') == scope for _, packet in packets for row in packet['runs']): raise ValueError('new stage scope already used')
        stage = {'schemaVersion':1,'kind':'explicit-approved-batch-resource-stage','scopeId':scope,'gameDate':date,
            'configSha256':artifact.config_hash(config),'fundingScopeId':funding_scope,'parentRunId':parent_run_id,
            'fundingChain':chain,'fundingUsageAtReview':usage,
            'parentRowSha256':artifact._fingerprint(parent),'originalPermissionSha256':hashlib.sha256(permission_path.read_bytes()).hexdigest(),
            'parentAuthorizationSha256':hashlib.sha256(authorization_path.read_bytes()).hexdigest(),
            'parentReportSha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
            'humanApprovalInherited':True,'approvedAtUTC':permission['approvedAtUTC'],'validUntilUTC':permission['validUntilUTC'],
            'reviewedBy':reviewed_by,'reviewedAtUTC':now.isoformat(),'assignedRunId':None,'oneResourceStageOnly':True,
            'originalBudget':policy['originalResinBudget'],'condensedBudget':policy['condensedResinBudget'],'replayParentStep':False,'oldTaskOutcomesPreserved':True,
            'preservedUnknownSources':permission['sourceRuns'],'freshProbeRunId':fresh_probe_run_id,'freshResinObservation':observation,
            'freshProbeSha256':{str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in probe_paths}}
        derived = artifact.build_artifact_authorization(config, stage['approvedAtUTC'], stage['validUntilUTC'])
        if apply:
            stage_path = _safe_path(root / 'state/artifact-stage-continuations' / (scope+'.json'))
            auth_path = _safe_path(root / 'state/artifact-authorizations' / (scope+'.json'))
            if stage_path.exists() or auth_path.exists(): raise ValueError('existing stage authority must not be overwritten')
            # Reserve one resource stage. A second review cannot reuse this funding scope while pending.
            for other_path in stage_path.parent.glob('*.json'):
                other = _json_file(_safe_path(other_path))
                if other.get('fundingScopeId') == funding_scope and other.get('assignedRunId') is None:
                    raise ValueError('parent already has a pending explicitly reviewed resource stage')
            for other_path in (root/'state/artifact-window-stages').glob('*.json'):
                other=_json_file(_safe_path(other_path))
                if other.get('continuationScopeId')==funding_scope and other.get('assignedRunId') is None:
                    raise ValueError('same original funding already has a pending window resource stage')
            atomic_json(stage_path,stage);atomic_json(auth_path,derived)
        return {'config':config,'authorization':derived,'stageReview':stage}


def stage_for_gate(root, config, run_id, date, now, unknown):
    path = _safe_path(Path(root)/'state/artifact-stage-continuations'/(config['policy']['scopeId']+'.json'))
    stage = _json_file(path)
    p = config['policy']
    if (stage.get('kind')!='explicit-approved-batch-resource-stage' or stage.get('scopeId')!=p['scopeId']
            or stage.get('gameDate')!=date or stage.get('configSha256')!=artifact.config_hash(config)
            or stage.get('assignedRunId') is not None or stage.get('reviewedBy')!='root-agent'
            or stage.get('humanApprovalInherited') is not True or stage.get('replayParentStep') is not False
            or stage.get('oldTaskOutcomesPreserved') is not True or (p['originalResinBudget'],p['condensedResinBudget']) not in ((0,1),(20,0))
            or stage.get('originalBudget')!=p['originalResinBudget'] or stage.get('condensedBudget')!=p['condensedResinBudget']
            or p['maxCrafts']!=0 or p['maxClaims']!=1 or p['maxMinutes']>5
            or not _timestamp(stage['approvedAtUTC'],'inherited approval')<=now<_timestamp(stage['validUntilUTC'],'inherited deadline')
            or run_id==stage['parentRunId'] or [artifact._run_source_fingerprint(root,item) for item in unknown]!=stage['preservedUnknownSources']):
        raise ValueError('approved-batch stage is changed/consumed or contains a new unresolved resource unknown')
    parent_rows=[row for ledger_path in (Path(root)/'state/artifact-checkpoints').glob('*.json')
        for row in _json_file(_safe_path(ledger_path))['runs'] if row.get('runId')==stage['parentRunId']]
    if len(parent_rows)!=1 or not classified_resource_zero(root,parent_rows[0]) or artifact._fingerprint(parent_rows[0])!=stage['parentRowSha256']:
        raise ValueError('parent known-not-submitted resource proof changed')
    permission_path=_safe_path(Path(root)/'state/artifact-continuations'/(stage['fundingScopeId']+'.json'))
    auth_path=_safe_path(Path(root)/'state/artifact-authorizations'/(stage['fundingScopeId']+'.json'))
    report_path=_safe_path(Path(root)/'logs/runs'/stage['parentRunId']/'artifact-farming-report.json')
    if any(hashlib.sha256(item.read_bytes()).hexdigest()!=stage[key] for item,key in (
        (permission_path,'originalPermissionSha256'),(auth_path,'parentAuthorizationSha256'),(report_path,'parentReportSha256'))):
        raise ValueError('original inherited approval/parent report changed')
    packets=[(ledger_path,_json_file(_safe_path(ledger_path))) for ledger_path in (Path(root)/'state/artifact-checkpoints').glob('*.json')]
    funding_scope,_,permission,_,parent_authorization,chain=_funding_authority(_safe_path(root),parent_rows[0],packets)
    if funding_scope!=stage['fundingScopeId'] or stage.get('fundingChain',chain)!=chain:
        raise ValueError('nested stage original funding chain changed')
    _check_stage_funds(p,_funding_usage(_safe_path(root),funding_scope,packets,parent_authorization,permission),parent_authorization)
    child_authorization=_json_file(_safe_path(Path(root)/'state/artifact-authorizations'/(p['scopeId']+'.json')))
    if child_authorization.get('approvedAtUTC')!=stage['approvedAtUTC'] or child_authorization.get('validUntilUTC')!=stage['validUntilUTC']:
        raise ValueError('stage cannot renew or change inherited human approval')
    observation,balances,paths=artifact._probe_resin_for_review(root,stage['freshProbeRunId'],date,now,p['condensedCapacity'])
    if observation!=stage['freshResinObservation'] or balances[1]<p['condensedResinBudget'] or balances[0]-p['reserveOriginalResin']<p['originalResinBudget'] or any(hashlib.sha256(item.read_bytes()).hexdigest()!=stage['freshProbeSha256'].get(str(item.relative_to(_safe_path(root)))) for item in paths):
        raise ValueError('fresh resource stage balance/source changed')
    return path,stage


def _funding_authority(root,parent,packets):
    rows={row['runId']:row for _,packet in packets for row in packet['runs']}
    chain=[];current=parent;seen=set()
    funding_scope=parent.get('derivedStageFundingScope',parent['scopeId'])
    while current.get('derivedStageFundingScope') is not None:
        if current['runId'] in seen or len(chain)>12 or current['derivedStageFundingScope']!=funding_scope:
            raise ValueError('funding parent chain is cyclic or changes original approval scope')
        seen.add(current['runId'])
        if not artifact._ledger_row_resolved(root,current): raise ValueError('funding chain contains resource-unknown stage')
        stage_path=_safe_path(root/'state/artifact-stage-continuations'/(current['scopeId']+'.json'))
        stage=_json_file(stage_path)
        if stage.get('assignedRunId')!=current['runId'] or stage.get('fundingScopeId')!=funding_scope or stage.get('parentRunId')!=current.get('parentResourceRunId'):
            raise ValueError('funding chain stage assignment/parent binding missing')
        chain.append({'runId':current['runId'],'scopeId':current['scopeId'],'stageReceiptSha256':hashlib.sha256(stage_path.read_bytes()).hexdigest()})
        current=rows.get(current['parentResourceRunId'])
        if current is None: raise ValueError('funding parent run missing')
    if current['scopeId']!=funding_scope or not artifact._ledger_row_resolved(root,current):
        raise ValueError('original approved funding run is unresolved or does not match chain')
    permission_path=_safe_path(root/'state/artifact-continuations'/(funding_scope+'.json'))
    auth_path=_safe_path(root/'state/artifact-authorizations'/(funding_scope+'.json'))
    permission,authorization=_json_file(permission_path),_json_file(auth_path)
    if (permission.get('assignedRunId')!=current['runId'] or permission.get('authorizationSource')!='direct-human-reply'
            or permission.get('approvalText')!='允许新建批次继续，保留原未知记录'
            or permission.get('approvedAtUTC')!=authorization.get('approvedAtUTC')
            or permission.get('validUntilUTC')!=authorization.get('validUntilUTC')):
        raise ValueError('original explicit human funding permission missing or approval/window changed')
    chain.append({'runId':current['runId'],'scopeId':funding_scope,'originalFunding':True})
    return funding_scope,permission_path,permission,auth_path,authorization,chain


def _funding_usage(root,funding_scope,packets,authorization,permission):
    usage={'originalResinSpent':0,'condensedResinSpent':0,'crafts':0}
    for _,packet in packets:
        for row in packet['runs']:
            if row.get('scopeId')!=funding_scope and row.get('derivedStageFundingScope')!=funding_scope: continue
            if not artifact._ledger_row_resolved(root,row): raise ValueError('funded stage resource outcome remains unknown; full amount remains reserved')
            if row.get('resourceState')=='known_not_submitted': continue
            for key in usage: usage[key]+=artifact._integer(row.get(key),0,10000,'actual funded '+key)
    if usage['originalResinSpent']>authorization['originalResinCap'] or usage['condensedResinSpent']>authorization['condensedResinCap'] or usage['crafts']>authorization['craftCap']:
        raise ValueError('actual funded consumption already exceeds original approved caps')
    # Generated condensed is a confirmed transfer, never additional authorization.
    admitted=permission.get('freshResinObservation',{}).get('condensedResin')
    if admitted is None: admitted=authorization['condensedResinCap'] # retained legacy receipts used exact held cap
    usage['admittedCondensed']=artifact._integer(admitted,0,100,'original admitted condensed')
    usage['condensedGenerated']=usage['crafts']
    return usage


def _check_stage_funds(policy,usage,authorization):
    if usage['originalResinSpent']+policy['originalResinBudget']>authorization['originalResinCap']:
        raise ValueError('approved original funding has no remaining single20 budget')
    if usage['condensedResinSpent']+policy['condensedResinBudget']>authorization['condensedResinCap']:
        raise ValueError('approved parent condensed budget has no unused unit')
    if usage['condensedResinSpent']+policy['condensedResinBudget']>usage['admittedCondensed']+usage['condensedGenerated']:
        raise ValueError('funding admitted/generated condensed accounting has no available unit')
