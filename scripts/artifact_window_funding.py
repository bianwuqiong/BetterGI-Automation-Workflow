"""Explicit unused original-window funding; no UI, replay, refund, or implicit authorization."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

try:
    from . import artifact_farming as artifact
    from .artifact_resource_review import classified_resource_zero
    from .cultivation import _json_file, _safe_path, _timestamp
    from .workflow import RunLock, atomic_json
except ImportError:
    import artifact_farming as artifact
    from artifact_resource_review import classified_resource_zero
    from cultivation import _json_file, _safe_path, _timestamp
    from workflow import RunLock, atomic_json

KIND='explicit-original-window-resource-stage'


def _digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def _human_source_semantics(root,source,source_path,source_sha256,auth,permission,target):
    """Private quotation bytes stay private; public logic checks typed grants and receipt bindings."""
    quotes=source.get('quotes')
    if (not isinstance(quotes,dict) or any(not isinstance(quotes.get(key),str) or not quotes[key].strip()
            or len(quotes[key])>5000 for key in ('resourceAuthorization','targetChange','developmentWindow','continueNewBatch'))):
        raise ValueError('explicit private human-source excerpts are missing')
    if source.get('schemaVersion')==2:
        grants=source.get('semanticGrants',{})
        flags={'allNaturalOriginal':True,'allCondensed':True,'preferCondensed':True,'forbidFragile':True,
            'forbidTransient':True,'forbidPrimogems':True,'continueUnusedStages':True,'preserveUnknown':True,
            'replayUnknownAllowed':False}
        caps={key:auth[key] for key in ('originalResinCap','condensedResinCap','craftCap')}
        if (not isinstance(grants,dict) or any(type(grants.get(key)) is not bool or grants[key]!=value for key,value in flags.items())
                or grants.get('target')!=target or grants.get('originalFundingCaps')!=caps):
            raise ValueError('explicit typed human grants do not match the original target/caps/forbidden resources')
        return
    if source.get('schemaVersion')!=1: raise ValueError('unsupported human-source schema')
    # Read compatibility only for a real historical root review of these exact private bytes.
    for path in (root/'state/artifact-window-stages').glob('*.json'):
        prior=_json_file(_safe_path(path))
        if (prior.get('kind')==KIND and prior.get('reviewedBy')=='root-agent'
                and prior.get('originalScopeId')==auth['scopeId'] and prior.get('continuationScopeId')==permission['scopeId']
                and prior.get('originalApprovedAtUTC')==auth['approvedAtUTC'] and prior.get('approvedAtUTC')==permission['approvedAtUTC']
                and prior.get('validUntilUTC')==auth['validUntilUTC'] and prior.get('sourceSha256')==source_sha256
                and prior.get('automaticReplayAllowed') is False and prior.get('oldTaskOutcomesPreserved') is True
                and isinstance(prior.get('sourcePath'),str) and _safe_path(prior['sourcePath'])==source_path):
            return
    raise ValueError('legacy private source has no historical root review; new typed source is required')


def _scope_policy(config):
    p=config['policy']
    if (not config['executionEnabled'] or p['validationOnly'] or p['maxClaims']!=1 or p['maxMinutes']>5
            or (p['originalResinBudget'],p['condensedResinBudget'],p['maxCrafts']) not in ((60,1,1),(0,1,0),(20,0,0))
            or not p['preferCondensed'] or p['craftOriginalResinCost']!=60
            or not p['domainValidated'] or not p['craftingValidated']):
        raise ValueError('original-window stage is only one craft60+claim, single condensed, or single20/max5min')


def _prefix_reservation(root,row,authorization,target):
    """Recheck the exact confirmed single craft and reserve the unknown condensed claim."""
    run=row['runId'];directory=root/'logs/runs'/run
    report,group,result=(_json_file(directory/name) for name in
        ('artifact-farming-report.json','artifact-farming-group.json','result.json'))
    settings=group['Projects'][0]['JsScriptSettingsObject']
    config=artifact.normalize_config(json.loads(settings['configJson']))
    if authorization!=artifact.build_artifact_authorization(config,authorization.get('authorizedAtUTC'),authorization.get('validUntilUTC')):
        raise ValueError('initial authority no longer matches its exact scoped config/window/budgets')
    known={'originalResinSpent':60,'condensedResinSpent':0,'crafts':1,'claims':0}
    proof=result.get('artifactFarming',{})
    if (row.get('status')!='unknown' or row.get('resourceState') is not None
            or any(row.get(key) is not None for key in ('originalResinSpent','condensedResinSpent','crafts'))
            or row.get('confirmedSubtotals')!=known or row.get('unknownStepIds')!=[run+':step-2']
            or row.get('confirmedSubtotalOnly') is not True or row.get('unknownStepOutcomeUnresolved') is not True
            or row.get('confirmedStepIds')!=[run+':step-1']
            or config['target']!=target or settings.get('runId')!=run or report.get('runId')!=run
            or report.get('target')!=target or report.get('policy')!=config['policy']
            or config['policy']['scopeId']!=authorization['scopeId']
            or settings.get('configSha256')!=authorization['configSha256']
            or report.get('configSha256')!=authorization['configSha256'] or artifact.config_hash(config)!=authorization['configSha256']
            or result.get('runId')!=run or result.get('outcome')!='unknown'
            or result.get('artifactPlugin',{}).get('verified') is not True
            or proof.get('reportVerified') is not True or proof.get('allStepsVerified') is not False
            or any(proof.get(key)!=value for key,value in known.items()) or report.get('totals')!=known):
        raise ValueError('initial unknown is not independently verified craft60 plus exactly one unknown condensed claim')
    steps=report.get('steps',[])
    if len(steps)!=2: raise ValueError('initial prefix has additional resource steps')
    craft,claim=steps
    if (craft.get('stepId')!=run+':step-1' or craft.get('type')!='craft' or craft.get('status')!='success'
            or claim.get('stepId')!=run+':step-2' or claim.get('status')!='unknown' or claim.get('type')!='claim'
            or claim.get('resin')!='condensed' or claim.get('before')!=craft.get('after')
            or craft.get('requestedCount',1)!=1 or craft.get('actualCreated',1)!=1):
        raise ValueError('initial prefix/unknown nonce or single craft count mismatch')
    start,finish=(_timestamp(craft[key],key) for key in ('startedAt','finishedAt'))
    before=artifact._resin(craft['before'],start,report['gameDate'],config['policy']['condensedCapacity'])
    after=artifact._resin(craft['after'],finish,report['gameDate'],config['policy']['condensedCapacity'])
    native=craft.get('nativeResult',{})
    exact={'Status':'success','OriginalResinBefore':before[0],'OriginalResinAfter':after[0],
        'CondensedResinBefore':before[1],'CondensedResinAfter':after[1],'CondensedResinCreated':1,
        'OriginalResinSpent':60,'MainUiRestored':True,'RecipeCostVerified':True,'RecipeOriginalResinCost':60}
    if ([after[i]-before[i] for i in range(2)]!=[-60,1]
            or any(type(native.get(key)) is not type(value) or native[key]!=value for key,value in exact.items())):
        raise ValueError('initial craft native receipt and fresh before/after do not confirm actual60/one generated')
    params=claim.get('parameterEvidence',{})
    fixed={'ArtifactRunId':run,'ArtifactStepId':run+':step-2','DomainRoundNum':1,
        'DomainName':target['domainName'],'PartyName':target['partyName'],'RequireZhongliShieldCast':True,
        'SpecifyResinUse':True,'CombatOnly':False,'CondensedResinUseCount':1,'OriginalResinUseCount':0,
        'OriginalResin20UseCount':0,'OriginalResin40UseCount':0,'FragileResinUseCount':0,'TransientResinUseCount':0,
        'AutoArtifactSalvage':False,'RewardRecognitionEnabled':True,'ResinPriorityList':['浓缩树脂']}
    if any(type(params.get(key)) is not type(value) or params[key]!=value for key,value in fixed.items()):
        raise ValueError('initial unknown resource upper bound is not strictly original0/condensed1')
    if params.get('CombatStrategyPath','').replace('\\','/').rsplit('/',1)[-1]!=target['strategyName']+'.txt':
        raise ValueError('initial unknown strategy differs from the approved target')
    text=(directory/'bettergi.log').read_text(encoding='utf-8-sig')
    refs=[artifact._config_reference(line) for line in text.splitlines() if artifact._config_reference(line)]
    events=[event for line in text.splitlines() if (event:=artifact._event_from_line(line)) is not None]
    groups=[match for line in text.splitlines() if (match:=artifact._GROUP_MARKER_RE.search(line))]
    receipt={'originalResinBefore':before[0],'originalResinAfter':after[0],'condensedResinBefore':before[1],
        'condensedResinAfter':after[1],'condensedResinCreated':1,'originalResinSpent':60}
    native_events=[event for event in events if event.get('task')=='artifact-condensed-craft'
        and event.get('status')=='success' and event.get('evidenceVerified') is True
        and all(event.get(key)==value for key,value in receipt.items())]
    plugin=[event for event in events if event.get('task')==artifact.TASK_NAME]
    if (set(refs)!={'AutoGame_'+run} or len(groups)!=1 or groups[0].groups()!=('1','1') or len(native_events)!=1
            or len(plugin)!=1 or plugin[0].get('runId')!=run or plugin[0].get('status')!='unknown'
            or plugin[0].get('mode')!=artifact.MODE or plugin[0].get('evidenceVerified') is not True
            or plugin[0].get('reportRelativePath')!=f'record/{run}.json'
            or len([event for event in events if event.get('task')=='artifact-condensed-craft'])!=1
            or any(event.get('task')=='artifact-domain-claim' for event in events)):
        raise ValueError('initial confirmed craft/unknown claim does not have unique scoped native log receipts')
    return known,{'originalResinReserved':0,'condensedResinReserved':1,'craftsReserved':0}


def _authority(root,initial_scope,continuation_scope,source_path,source_sha256,target,now,*,allow_game_day_transition=False):
    source_path=_safe_path(source_path)
    if _digest(source_path)!=source_sha256: raise ValueError('explicit human-source attachment changed')
    source=_json_file(source_path)
    auth_path=root/'state/artifact-authorizations'/(initial_scope+'.json')
    permission_path=root/'state/artifact-continuations'/(continuation_scope+'.json')
    auth,permission=_json_file(auth_path),_json_file(permission_path)
    if permission.get('originalAuthorizationSha256')!=_digest(auth_path):
        raise ValueError('continuation does not preserve the original authorization fingerprint')
    fixed={'kind':'root-reviewed-original-artifact-window',
        'sourceKind':'direct-user-request-in-current-thread','reviewedBy':'root-agent',
        'originalScopeId':initial_scope,'continuationScopeId':continuation_scope,
        'oldReceiptApprovedAtUTC':auth.get('approvedAtUTC'),'validUntilUTC':auth.get('validUntilUTC'),
        'continuationApprovedAtUTC':permission.get('approvedAtUTC')}
    if any(type(source.get(key)) is not type(value) or source[key]!=value for key,value in fixed.items()):
        raise ValueError('explicit original human window/source attestation not bound to the real receipts')
    if (permission.get('authorizationSource')!='direct-human-reply' or permission.get('reviewedBy')!='root-agent'
            or not isinstance(permission.get('approvalText'),str) or not permission['approvalText'].strip()
            or permission.get('validUntilUTC')!=auth.get('validUntilUTC')
            or auth.get('authorizationSource')!='explicit-user-instruction' or auth.get('schemaVersion')!=2
            or auth.get('scopeId')!=initial_scope or auth.get('forbidFragileTransientPrimogems') is not True
            or (auth.get('originalResinCap'),auth.get('condensedResinCap'),auth.get('craftCap'))!=(200,5,5)
            or not _timestamp(auth['approvedAtUTC'],'original approval')<=_timestamp(permission['approvedAtUTC'],'continuation')<=now<_timestamp(auth['validUntilUTC'],'original deadline')):
        raise ValueError('human request/target/original200/5/window or explicit continuation missing')
    _human_source_semantics(root,source,source_path,source_sha256,auth,permission,target)
    if not allow_game_day_transition and artifact.game_date(now)!=auth['gameDate']:
        raise ValueError('a new game day needs an explicit transition review; metadata cannot renew the original stage')
    if allow_game_day_transition and (source.get('schemaVersion')!=2
            or source.get('semanticGrants',{}).get('allowGameDayTransition') is not True):
        raise ValueError('new typed human-source game-day transition semantics required; legacy source cannot be extended')
    packets=[(path,_json_file(_safe_path(path))) for path in (root/'state/artifact-checkpoints').glob('*.json')]
    rows=[row for _,packet in packets for row in packet['runs']]
    source_runs=permission.get('sourceRuns',[])
    if len(source_runs)!=1 or source_runs[0].get('scopeId')!=initial_scope: raise ValueError('continuation does not bind one original unknown')
    grant=artifact._fingerprint({'approvedAtUTC':permission['approvedAtUTC'],'approvalText':permission['approvalText'],
        'validUntilUTC':permission['validUntilUTC'],'sourceRuns':source_runs})
    if permission.get('humanGrantSha256')!=grant: raise ValueError('direct-human continuation source grant changed')
    initial=[row for row in rows if row['runId']==source_runs[0]['runId']]
    assigned=[row for row in rows if row['runId']==permission.get('assignedRunId') and row.get('scopeId')==continuation_scope]
    if len(assigned)!=1: raise ValueError('continuation is not assigned to its exact original new batch')
    current=next((packet for path,packet in packets if path.name==artifact.game_date(now)+'.json'),{'schemaVersion':1,'gameDate':artifact.game_date(now),'runs':[]})
    unknown=artifact._unknown_rows(root,artifact.game_date(now),current)
    if len(unknown)!=1 or unknown[0]['runId']!=source_runs[0]['runId']:
        raise ValueError('another unresolved transaction remains blocked; no new unknown uses this permission')
    if len(initial)!=1 or [artifact._run_source_fingerprint(root,item) for item in unknown]!=source_runs:
        raise ValueError('original unknown fingerprint changed or another unresolved transaction remains blocked')
    known,reserved=_prefix_reservation(root,initial[0],auth,target)
    # Do not replenish caps implicitly at a day boundary; this explicit window review is conservative.
    usage={key:value for key,value in known.items()}
    included=[]
    for row in rows:
        if row['runId']==initial[0]['runId']: continue
        member=(row.get('scopeId') in (initial_scope,continuation_scope)
            or row.get('derivedStageFundingScope')==continuation_scope or row.get('originalWindowFundingScope')==initial_scope)
        if not member: continue
        if not allow_game_day_transition and row.get('gameDate')!=current['gameDate'] and row.get('originalWindowFundingScope')!=initial_scope:
            raise ValueError('cross-day continuation funding requires a new explicit day review')
        if not artifact._ledger_row_resolved(root,row): raise ValueError('later funded transaction remains unknown')
        included.append({'runId':row['runId'],'rowSha256':artifact._fingerprint(row)})
        if classified_resource_zero(root,row): continue
        original=artifact._integer(row.get('originalResinSpent'),0,10000,'actual window original')
        crafts=artifact._integer(row.get('crafts'),0,10000,'actual window crafts')
        if original<crafts*60 or (original-crafts*60)%20:
            raise ValueError('actual funded original spending is not confirmed craft60/single20 accounting')
        usage['claims']+=artifact._integer(row.get('condensedResinSpent'),0,10000,'actual window condensed')+(original-crafts*60)//20
        for key in ('originalResinSpent','condensedResinSpent','crafts'):
            usage[key]+=artifact._integer(row.get(key),0,10000,'actual window '+key)
    paths=[source_path,auth_path,permission_path]
    for relative,digest in source_runs[0]['sourceSha256'].items():
        path=_safe_path(root/relative)
        if _digest(path)!=digest: raise ValueError('original archived resource evidence changed')
        paths.append(path)
    return auth,permission,usage,reserved,included,paths,unknown


def _caps(policy,usage,reserved,auth):
    for budget,total,reserve,cap in (('originalResinBudget','originalResinSpent','originalResinReserved','originalResinCap'),
        ('condensedResinBudget','condensedResinSpent','condensedResinReserved','condensedResinCap'),
        ('maxCrafts','crafts','craftsReserved','craftCap')):
        if usage[total]+reserved[reserve]+policy[budget]>auth[cap]:
            raise ValueError('confirmed usage plus conservative unknown reservation exceeds original window '+cap)


def _game_identity(root,probe_id,date):
    """The read-only probe's actual shared-host unique/exact process and graphics proof."""
    result_path=_safe_path(root/'logs/runs'/probe_id/'result.json');result=_json_file(result_path)
    settings_path=_safe_path(root/'config/settings.json');settings=_json_file(settings_path)
    configured=Path(settings.get('gameExe',''))
    if not str(configured) or str(configured)=='.': raise ValueError('configured game executable identity missing')
    expected=_safe_path(configured if configured.is_absolute() else root/configured)
    observed=result.get('adoptedGameExe');pid=result.get('adoptedGamePid')
    graphics=result.get('graphicsVerification',{})
    if (result.get('gameDate')!=date or result.get('keepGameOpen') is not True or result.get('gameProcessSeen') is not True
            or type(pid) is not int or pid<=0 or not isinstance(observed,str) or _safe_path(observed)!=expected
            or result.get('processMetrics',{}).get('GenshinImpact',{}).get('pids')!=[pid]
            or graphics.get('state')!='passed' or graphics.get('windowSizeMatched') is not True
            or graphics.get('runtimeRegistry',{}).get('allMatched') is not True):
        raise ValueError('current-game-day unique exact game process/full graphics proof missing')
    window=graphics.get('observedWindow',{});width=window.get('width');height=window.get('height')
    configured_window=settings.get('gameDisplaySettings');expected_window=graphics.get('expectedWindow')
    if (type(width) is not int or type(height) is not int or (width,height)!=(1920,1080)
            or not isinstance(configured_window,dict) or not isinstance(expected_window,dict)
            or type(configured_window.get('width')) is not int or type(configured_window.get('height')) is not int
            or (configured_window.get('width'),configured_window.get('height'))!=(1920,1080)
            or configured_window.get('windowed') is not True or configured_window!=expected_window):
        raise ValueError('current-game-day physical game client proof invalid')
    return {'pid':pid,'exe':str(expected),'physicalClient':{'width':width,'height':height}},[result_path,settings_path]


def review_original_window_stage(root,initial_scope,continuation_scope,new_config,fresh_probe_run_id,*,
        source_path,source_sha256,reviewed_by,apply=False,now=None,_game_day_transition=None):
    if reviewed_by!='root-agent': raise ValueError('explicit root review required')
    root=_safe_path(root);config=artifact.normalize_config(new_config);_scope_policy(config)
    now=now or datetime.now(timezone.utc);date=artifact.game_date(now);p=config['policy']
    if _game_day_transition is not None and _game_day_transition!=date:
        raise ValueError('explicit game-day transition differs from actual UTC8-04 time')
    with RunLock(root/'state/workflow.lock'):
        auth,permission,usage,reserved,included,paths,unknown=_authority(root,initial_scope,continuation_scope,
            source_path,source_sha256,config['target'],now,allow_game_day_transition=_game_day_transition is not None)
        _caps(p,usage,reserved,auth)
        observation,balances,probe_paths=artifact._probe_resin_for_review(root,fresh_probe_run_id,date,now,p['condensedCapacity'])
        if balances[0]-p['reserveOriginalResin']<p['originalResinBudget'] or balances[1]+p['maxCrafts']<p['condensedResinBudget']:
            raise ValueError('fresh actual resources cannot fund the bounded new stage')
        if p['maxCrafts'] and balances[1]+1>p['condensedCapacity']: raise ValueError('fresh condensed balance lacks safe crafting capacity')
        scope=p['scopeId'];stage_path=root/'state/artifact-window-stages'/(scope+'.json')
        day_path=None;day_review=None
        if _game_day_transition is not None:
            if date<=auth['gameDate']:
                raise ValueError('game-day transition requires a later game day inside the original real window')
            identity,identity_paths=_game_identity(root,fresh_probe_run_id,date);paths+=identity_paths
            day_path=_safe_path(root/'state/artifact-window-day-reviews'/(scope+'.json'))
            day_review={'schemaVersion':1,'kind':'explicit-original-window-game-day-transition','scopeId':scope,'gameDate':date,
                'originalGameDate':auth['gameDate'],'originalScopeId':initial_scope,'continuationScopeId':continuation_scope,
                'configSha256':artifact.config_hash(config),'target':config['target'],'reviewedBy':reviewed_by,'reviewedAtUTC':now.isoformat(),
                'sourcePath':str(_safe_path(source_path)),'sourceSha256':source_sha256,
                'originalApprovedAtUTC':auth['approvedAtUTC'],'approvedAtUTC':permission['approvedAtUTC'],'validUntilUTC':auth['validUntilUTC'],
                'confirmedWindowUsage':usage,'unknownResourceReservation':reserved,'includedFundedRows':included,
                'originalFundingCaps':{key:auth[key] for key in ('originalResinCap','condensedResinCap','craftCap')},
                'budgetReset':False,'newHumanApprovalGenerated':False,'oldUnknownOutcomesPreserved':True,'automaticReplayAllowed':False,
                'freshProbeRunId':fresh_probe_run_id,'freshResinObservation':observation,'gameIdentity':identity,
                'evidenceSha256':{str(path.relative_to(root)) if path.is_relative_to(root) else str(path):_digest(path) for path in paths+probe_paths}}
        for folder in ('artifact-window-stages','artifact-stage-continuations','artifact-continuations'):
            for path in (root/'state'/folder).glob('*.json'):
                old=_json_file(_safe_path(path))
                if old.get('scopeId')==scope or (old.get('assignedRunId') is None and
                    (old.get('originalScopeId')==initial_scope or old.get('fundingScopeId')==continuation_scope or old.get('scopeId')==continuation_scope)):
                    raise ValueError('same original funding already has a pending stage/scope')
        if any(row.get('scopeId')==scope for path in (root/'state/artifact-checkpoints').glob('*.json') for row in _json_file(path)['runs']):
            raise ValueError('new original-window scope already used')
        authorization=artifact.build_artifact_authorization(config,permission['approvedAtUTC'],auth['validUntilUTC'])
        stage={'schemaVersion':1,'kind':KIND,'scopeId':scope,'gameDate':date,'configSha256':artifact.config_hash(config),
            'originalScopeId':initial_scope,'continuationScopeId':continuation_scope,'assignedRunId':None,
            'approvedAtUTC':permission['approvedAtUTC'],'originalApprovedAtUTC':auth['approvedAtUTC'],'validUntilUTC':auth['validUntilUTC'],
            'sourcePath':str(_safe_path(source_path)),'sourceSha256':source_sha256,'reviewedBy':reviewed_by,'reviewedAtUTC':now.isoformat(),
            'confirmedWindowUsage':usage,'unknownResourceReservation':reserved,'includedFundedRows':included,
            'confirmedCondensedGenerated':usage['crafts'],
            'preservedUnknownSources':[artifact._run_source_fingerprint(root,item) for item in unknown],
            'automaticReplayAllowed':False,'oldTaskOutcomesPreserved':True,'refundOldConfirmedConsumption':False,
            'originalFundingCaps':{key:auth[key] for key in ('originalResinCap','condensedResinCap','craftCap')},
            'budgetAccounting':'conservative-whole-window-no-implicit-day-reset',
            'freshProbeRunId':fresh_probe_run_id,'freshResinObservation':observation,
            'evidenceSha256':{str(path.relative_to(root)) if path.is_relative_to(root) else str(path):_digest(path) for path in paths+probe_paths}}
        auth_path=root/'state/artifact-authorizations'/(scope+'.json')
        if auth_path.exists() or stage_path.exists() or day_path is not None and day_path.exists(): raise ValueError('original-window review cannot overwrite receipts')
        if day_review is not None:
            serialized=json.dumps(day_review,ensure_ascii=False,indent=2)+'\n'
            stage['gameDayTransition']={'path':str(day_path.relative_to(root)),'sha256':hashlib.sha256(serialized.encode('utf-8')).hexdigest()}
        if apply:
            if day_review is not None:
                atomic_json(day_path,day_review)
                stage['gameDayTransition']['sha256']=_digest(day_path)
            atomic_json(stage_path,stage);atomic_json(auth_path,authorization)
        return {'config':config,'authorization':authorization,'windowReview':stage,**({'gameDayReview':day_review} if day_review is not None else {})}


def review_window_game_day_transition(root,initial_scope,continuation_scope,fresh_today_probe_run_id,current_game_date,*,
        new_config,source_path,source_sha256,reviewed_by,apply=False,now=None):
    """Explicit concrete new-scope day admission, preserving whole-window costs/reservations and human times."""
    return review_original_window_stage(root,initial_scope,continuation_scope,new_config,fresh_today_probe_run_id,
        source_path=source_path,source_sha256=source_sha256,reviewed_by=reviewed_by,apply=apply,now=now,
        _game_day_transition=current_game_date)


def _day_for_gate(root,stage,config,date,current_game_identity=None):
    reference=stage.get('gameDayTransition')
    if reference is None:return None
    if not isinstance(reference,dict) or not isinstance(reference.get('path'),str):raise ValueError('explicit game-day review pointer invalid')
    path=_safe_path(root/reference['path']);expected=_safe_path(root/'state/artifact-window-day-reviews'/(stage['scopeId']+'.json'))
    if path!=expected or _digest(path)!=reference.get('sha256'):raise ValueError('explicit game-day review missing or changed')
    day=_json_file(path)
    equal={'schemaVersion':1,'kind':'explicit-original-window-game-day-transition','scopeId':stage['scopeId'],'gameDate':date,
        'originalScopeId':stage['originalScopeId'],'continuationScopeId':stage['continuationScopeId'],
        'configSha256':artifact.config_hash(config),'target':config['target'],'reviewedBy':'root-agent',
        'sourcePath':stage['sourcePath'],'sourceSha256':stage['sourceSha256'],'originalApprovedAtUTC':stage['originalApprovedAtUTC'],
        'approvedAtUTC':stage['approvedAtUTC'],'validUntilUTC':stage['validUntilUTC'],
        'confirmedWindowUsage':stage['confirmedWindowUsage'],'unknownResourceReservation':stage['unknownResourceReservation'],
        'includedFundedRows':stage['includedFundedRows'],'originalFundingCaps':stage['originalFundingCaps'],
        'budgetReset':False,'newHumanApprovalGenerated':False,'oldUnknownOutcomesPreserved':True,'automaticReplayAllowed':False,
        'freshProbeRunId':stage['freshProbeRunId'],'freshResinObservation':stage['freshResinObservation']}
    if any(type(day.get(key)) is not type(value) or day[key]!=value for key,value in equal.items()):
        raise ValueError('explicit game-day review scope/authority/whole-window totals changed')
    identity,paths=_game_identity(root,stage['freshProbeRunId'],date)
    if identity!=day.get('gameIdentity') or any(_digest(item)!=day.get('evidenceSha256',{}).get(str(item.relative_to(root))) for item in paths):
        raise ValueError('explicit game-day unique process/graphics identity changed')
    if not isinstance(current_game_identity,dict):
        raise ValueError('current controller game process query is required before day-stage assignment')
    current_pid=current_game_identity.get('pid');current_exe=current_game_identity.get('exe');current_client=current_game_identity.get('physicalClient')
    if (type(current_pid) is not int or current_pid!=identity['pid'] or not isinstance(current_exe,(str,Path))
            or not Path(current_exe).is_absolute() or _safe_path(current_exe)!=_safe_path(identity['exe'])
            or not isinstance(current_client,dict) or type(current_client.get('width')) is not int or type(current_client.get('height')) is not int
            or current_client.get('width')!=1920 or current_client.get('height')!=1080
            or {'width':current_client['width'],'height':current_client['height']}!=identity['physicalClient']):
        raise ValueError('current controller game PID/exe/physical client differs from reviewed day identity')
    return path


def window_for_gate(root,config,run_id,date,now,unknown,*,current_game_identity=None):
    root=_safe_path(root);_scope_policy(config)
    path=root/'state/artifact-window-stages'/(config['policy']['scopeId']+'.json');stage=_json_file(path)
    if (stage.get('kind')!=KIND or stage.get('scopeId')!=config['policy']['scopeId'] or stage.get('gameDate')!=date
            or stage.get('configSha256')!=artifact.config_hash(config) or stage.get('assignedRunId') is not None
            or stage.get('reviewedBy')!='root-agent' or stage.get('automaticReplayAllowed') is not False
            or stage.get('oldTaskOutcomesPreserved') is not True or stage.get('refundOldConfirmedConsumption') is not False):
        raise ValueError('original-window stage changed or already assigned')
    day_path=_day_for_gate(root,stage,config,date,current_game_identity)
    auth,permission,usage,reserved,included,paths,current_unknown=_authority(root,stage['originalScopeId'],stage['continuationScopeId'],
        stage['sourcePath'],stage['sourceSha256'],config['target'],now,allow_game_day_transition=day_path is not None)
    if ([artifact._run_source_fingerprint(root,item) for item in current_unknown]!=stage['preservedUnknownSources']
            or usage!=stage['confirmedWindowUsage'] or reserved!=stage['unknownResourceReservation'] or included!=stage['includedFundedRows']
            or stage['approvedAtUTC']!=permission['approvedAtUTC'] or stage['originalApprovedAtUTC']!=auth['approvedAtUTC']
            or stage['validUntilUTC']!=auth['validUntilUTC']): raise ValueError('original window authority/usage/reservation changed')
    _caps(config['policy'],usage,reserved,auth)
    observation,balances,probe_paths=artifact._probe_resin_for_review(root,stage['freshProbeRunId'],date,now,config['policy']['condensedCapacity'])
    if observation!=stage['freshResinObservation'] or any(_digest(item)!=stage['evidenceSha256'].get(str(item.relative_to(root)) if item.is_relative_to(root) else str(item)) for item in paths+probe_paths):
        raise ValueError('original-window explicit review source/fresh balance changed')
    child=_json_file(root/'state/artifact-authorizations'/(config['policy']['scopeId']+'.json'))
    if child!=artifact.build_artifact_authorization(config,permission['approvedAtUTC'],auth['validUntilUTC']):
        raise ValueError('original-window child approval/target/budget changed')
    if balances[0]-config['policy']['reserveOriginalResin']<config['policy']['originalResinBudget'] or balances[1]+config['policy']['maxCrafts']<config['policy']['condensedResinBudget']:
        raise ValueError('original-window current fresh funds insufficient')
    return path,stage
