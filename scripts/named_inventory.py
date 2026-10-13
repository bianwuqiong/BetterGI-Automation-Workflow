"""Independent named material snapshots; explicitly no consumer/Session After verdict."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
try:
    from .backpack_inventory_evidence import _time
    from .named_inventory_catalog import load_runtime_catalog,resolve_material,_file
    from .named_inventory_capture import capture_binding,capture_timeline,original_png,integer,sha
    from .named_inventory_context import validate_game_context
    from .named_inventory_world import verify_world_pixels
    from .named_count_model_assets import read_named_count_model_assets
    from .weekly_inventory import frame_count,HEADER_ALIASES,clean,dimensions,rect,rows
except ImportError:
    from backpack_inventory_evidence import _time
    from named_inventory_catalog import load_runtime_catalog,resolve_material,_file
    from named_inventory_capture import capture_binding,capture_timeline,original_png,integer,sha
    from named_inventory_context import validate_game_context
    from named_inventory_world import verify_world_pixels
    from named_count_model_assets import read_named_count_model_assets
    from weekly_inventory import frame_count,HEADER_ALIASES,clean,dimensions,rect,rows

RAW_DETECTOR='Assets/Model/PaddleOCR/Det/V6/PP-OCRv6_small_det_infer/slim.onnx'
FULL_TITLE_REGION_METHOD='pinned_v6_raw_named_stack_rect_v1'


def prepare_named_request(scope,*,run_id,step_id,phase='diagnostic',trusted_runtime_root):
    if (not isinstance(scope,dict) or set(scope)!={'executionEnabled','policy','materials'} or scope['executionEnabled'] is not False
            or not isinstance(scope['policy'],dict) or set(scope['policy'])!={'originalResinBudget','condensedResinBudget','maxMinutes'}
            or type(scope['policy']['originalResinBudget']) is not int or scope['policy']['originalResinBudget']!=0
            or type(scope['policy']['condensedResinBudget']) is not int or scope['policy']['condensedResinBudget']!=0
            or type(scope['policy']['maxMinutes']) is not int or not 1<=scope['policy']['maxMinutes']<=3):
        raise ValueError('named inventory requires isolated execution=false zero budget scope')
    if (not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',run_id)
            or not isinstance(step_id,str) or not 1<=len(step_id)<=128 or step_id.strip()!=step_id
            or any(ord(c)<32 or 127<=ord(c)<=159 for c in step_id) or phase not in ('before','after','diagnostic')):
        raise ValueError('named inventory runner run/step/phase invalid')
    pairs=scope['materials']
    if not isinstance(pairs,list) or not 1<=len(pairs)<=8:raise ValueError('named inventory requires one to eight admitted pairs')
    catalog=load_runtime_catalog(trusted_runtime_root);resolved=[resolve_material(catalog,m) for m in pairs]
    if len({m['materialId'] for m in resolved})!=len(pairs) or len({m['materialName'] for m in resolved})!=len(pairs):
        raise ValueError('named inventory duplicate scope material')
    return {'runId':run_id,'stepId':step_id,'phase':phase,'materials':deepcopy(pairs)}


def _same_assets(a,b):
    if not isinstance(a,dict) or set(a)!=set(b):return False
    return all(sha(a[k])==sha(b[k]) if k=='sha256' else type(a[k]) is type(b[k]) and a[k]==b[k] for k in b)


def strict_models(value,root):
    if (not isinstance(value,dict) or value.get('loadMethod')!='new_cpu_uncached_original_onnx_and_labels_under_read_pins'
            or value.get('provider')!='Cpu' or value.get('rawModel')!='V6' or value.get('detectorModel')!='V4'):
        raise ValueError('named inventory actual fresh CPU model load source missing')
    actual=read_named_count_model_assets(root);reported=value.get('countModels')
    if not isinstance(reported,dict) or reported.get('pinMethod')!='actual_bundled_open_read_sha256_hold_session':raise ValueError('named inventory count model read pins missing')
    for key in ('rawPaddleConfig','rawPaddleName','fixedDetectorConfig','fixedDetectorName'):
        if type(reported.get(key)) is not type(actual[key]) or reported[key]!=actual[key]:raise ValueError('named inventory actual model versions differ')
    if not isinstance(reported.get('assets'),list) or len(reported['assets'])!=5 or any(not _same_assets(a,b) for a,b in zip(reported['assets'],actual['assets'])):
        raise ValueError('named inventory actual model files differ')
    unused,asset,identity=_file(Path(root).resolve(strict=True),RAW_DETECTOR,1024*1024*1024)
    expected={'modelName':'PpOcrDetV6','relativePath':RAW_DETECTOR,'sha256':asset['sha256'],'length':asset['byteLength']}
    if not _same_assets(value.get('rawDetectorAsset'),expected):raise ValueError('named inventory actual loaded V6 detector source differs')
    return actual['assets']


def _version(actual,reported):
    if not isinstance(reported,dict) or reported.get('parserVersion')!=actual['parserVersion']:return False
    return all(_same_assets(reported.get(k),actual[k]) for k in ('csv','model'))


def named_title_contract(frame,target,start,finish,strict):
    scale=dimensions(frame,start,finish)
    expected=tuple(round(v*scale) for v in (1280,110,540,78))
    if (frame.get('nameRegionMethod')!=FULL_TITLE_REGION_METHOD
            or json.dumps(frame.get('nameModelEvidence'),sort_keys=True,allow_nan=False)!=json.dumps(strict,sort_keys=True,allow_nan=False)
            or rect(frame.get('initialNameRegion'))!=expected
            or not isinstance(frame.get('countReading'),dict) or not isinstance(frame.get('initialStack'),dict)):
        raise ValueError('named inventory pinned full-title method/ROI/model scope missing')
    for stack in (frame['initialStack'],frame.get('stack',{})):
        integer(stack.get('observedAt'))
        if (rect(stack.get('nameRegion'))!=expected
                or stack.get('selectedItemVerified') is not True
                or rows(stack.get('nameRows'),expected,scale)!=[clean(target['materialName'])]):
            raise ValueError('named inventory complete exact initial/final title missing')


def _original(frames,value,at,phase=None):
    matches=[f for f in frames if f['observedAt']==at and f['recognized']==value and (phase is None or f.get('phase')==phase)]
    if len(matches)!=1:raise ValueError('named inventory recognized data not bound to one original acquisition')
    return matches[0]


def _worlds(values,frames,root,start,finish,previous,workflow_root,*,entry=False):
    if not isinstance(values,list) or len(values)<2 or entry and len(values)!=2:raise ValueError('named inventory independent world pair missing')
    for w in values:
        at=integer(w.get('observedAt'))
        if not previous<at<=finish or (w.get('width'),w.get('height'))!=(1920,1080):raise ValueError('named inventory world sequence invalid')
        _original(frames,w,at);previous=at
    a,b=values[-2:]
    if not 0<b['observedAt']-a['observedAt']<=5000 or not entry and finish-b['observedAt']>1500:raise ValueError('named inventory fresh world pair invalid')
    for w in values[-2:]:
        if any(w.get(k) is not v for k,v in (('focused',True),('world',True),('prompt',False),('knownBag',False),('escapeRequested',False))):
            raise ValueError('named inventory unobstructed world flags incomplete')
        raw=_original(frames,w,w['observedAt']);image=original_png(raw['privateCapture'],root,workflow_root)
        try:verify_world_pixels(raw,image,root)
        finally:image.close()
    return previous


def verify_binding_receipt(receipt,game_context,start,read_started):
    if (not isinstance(receipt,dict) or receipt.get('schemaVersion')!=1 or receipt.get('source')!='actual_synchronous_BitBlt_inventory_binding'
            or receipt.get('readOnly') is not True or receipt.get('confirmationSubmitted') is not False
            or type(receipt.get('observedAt')) is not int or not start<=receipt['observedAt']<=read_started
            or read_started-receipt['observedAt']>5000):raise ValueError('named inventory independent native pre-binding receipt missing/stale')
    validate_game_context(game_context,receipt.get('gameBinding'))
    binding=receipt['gameBinding'];capture_binding(binding,binding)
    for key in ('systemInfoGeneration','backendAssemblyMvid'):
        if not isinstance(binding.get(key),str) or not re.fullmatch(r'[0-9a-fA-F]{32}',binding[key]):raise ValueError('named inventory native lifetime identity missing')
    if not isinstance(binding.get('backendGeneration'),str) or not re.fullmatch(r'[1-9][0-9]{0,18}',binding['backendGeneration']):raise ValueError('named inventory actual backend generation missing')
    session=receipt.get('captureSession')
    if not isinstance(session,str) or not re.fullmatch(r'bitblt-inventory:[0-9a-f]{64}',session):raise ValueError('named inventory native scope token missing')
    return binding,session


def _packet_interval(packet,started_at,finished_at):
    if (not isinstance(packet,dict) or packet.get('readOnly') is not True
            or packet.get('targetReached') is not False or type(packet.get('completedUpgrades')) is not int
            or packet['completedUpgrades']!=0 or packet.get('sessionAfterVerified') is not False
            or packet.get('consumptionVerified') is not False or packet.get('liveVerified') is not False
            or packet.get('rawEvidenceVerified') is not False):
        raise ValueError('named inventory diagnostic cannot assert consumption, live or Session After')
    start,finish=_time(started_at),_time(finished_at)
    began,ended=_time(packet.get('readStartedAt')),_time(packet.get('readFinishedAt'))
    if not start<=began<=ended<=finish or ended-began>180000:
        raise ValueError('named inventory packet call interval outside this runner scope')
    return packet['readStartedAt'],packet['readFinishedAt']


def verified_named_observation(raw,request,started_at,finished_at,*,trusted_runtime_root,trusted_game_context,binding_receipt,trusted_workflow_root=None):
    start,finish=_time(started_at),_time(finished_at);root=Path(trusted_runtime_root).resolve(strict=True)
    if (not isinstance(raw,dict) or type(raw.get('schemaVersion')) is not int or raw['schemaVersion']!=2 or raw.get('source')!='named_cultivation_backpack_selected_stack'
            or raw.get('readOnly') is not True or raw.get('confirmationSubmitted') is not False or raw.get('targetReached') is not False
            or type(raw.get('completedUpgrades')) is not int or raw['completedUpgrades']!=0 or raw.get('status')!='verified'
            or raw.get('mainUiRestored') is not True or raw.get('cleanupCompleted') is not True
            or any(raw.get(k)!=request[k] for k in ('runId','stepId','phase'))):raise ValueError('named inventory readonly request/result scope mismatch')
    rs,rf=integer(raw.get('startedAt')),integer(raw.get('finishedAt'))
    if not start<=rs<=rf<=finish or rf-rs>180000:raise ValueError('named inventory native interval outside this runner scope')
    expected_binding,expected_session=verify_binding_receipt(binding_receipt,trusted_game_context,start,rs)
    binding=raw.get('gameBinding');validate_game_context(trusted_game_context,binding)
    if raw.get('captureSession')!=expected_session:raise ValueError('named inventory native owner lifecycle token changed after pre-binding')
    capture_timeline(raw.get('rawFrames'),binding,expected_binding,rs,rf,trusted_runtime_root=root,trusted_workflow_root=trusted_workflow_root)
    # Native-only generation fields are not OS facts: the single trusted direct API
    # return owns this whole scope; every actual capture must match that same binding.
    catalog=load_runtime_catalog(root);targets=[resolve_material(catalog,m) for m in request['materials']]
    if not 1<=len(targets)<=8 or len({m['materialId'] for m in targets})!=len(targets) or len({m['materialName'] for m in targets})!=len(targets):
        raise ValueError('named inventory one to eight unique exact material pairs required')
    if not _version(catalog['version'],raw.get('catalogVersion')) or raw.get('requestedMaterials')!=targets:raise ValueError('named inventory runtime CSV/ONNX exact scope differs')
    assets=strict_models(raw.get('strictModels'),root)
    if raw.get('countModels')!=raw['strictModels']['countModels']:raise ValueError('named inventory shared model scope inconsistent')
    frames=raw['rawFrames'];entry_end=_worlds(raw.get('entryWorldFrames'),frames,root,rs,rf,rs-1,trusted_workflow_root,entry=True)
    ids={m['materialId'] for m in targets};observations=raw.get('observations');inventory=raw.get('inventory');rejected=raw.get('rejectedObservations',{})
    if (not isinstance(observations,dict) or set(observations)!=ids or not isinstance(inventory,dict) or set(inventory)!=ids
            or not isinstance(rejected,dict) or not set(rejected)<=ids or any(not isinstance(v,list) or len(v)>2 for v in rejected.values())):
        raise ValueError('named inventory full admitted material set missing')
    result={};intervals=[]
    for target in targets:
        identifier=target['materialId'];observed=observations[identifier]
        if observed.get('material')!=target:raise ValueError('named inventory selected pair CSV row changed')
        pair=observed.get('pair',{});selection=pair.get('selection',{});a,b=pair.get('first',{}),pair.get('second',{})
        click=selection.get('clickedAt');first=a.get('stack',{}).get('observedAt');second=b.get('stack',{}).get('observedAt')
        if (type(click) is not int or not entry_end<click<first<second<=rf or not 100<=first-click<=5000 or not 100<=second-first<=5000):
            raise ValueError('named inventory selection/fresh pair interval invalid')
        item=selection.get('itemRect',{})
        if (any(type(selection.get(k)) not in (int,float) or not math.isfinite(selection[k]) for k in ('x','y'))
                or not item.get('x',0)<=selection['x']<=item.get('x',0)+item.get('width',0)
                or not item.get('y',0)<=selection['y']<=item.get('y',0)+item.get('height',0)):
            raise ValueError('named inventory actual selected click coordinates invalid')
        original_a=_original(frames,a,first,'named_selected_stack');original_b=_original(frames,b,second,'named_selected_stack')
        if a.get('privateCapture')!=original_a['privateCapture'] or b.get('privateCapture')!=original_b['privateCapture']:
            raise ValueError('named inventory typed frame refers to different original pixels')
        if any((f.get('width'),f.get('height'))!=(original['privateCapture']['width'],original['privateCapture']['height'])
                for f,original in ((a,original_a),(b,original_b))):
            raise ValueError('named inventory recognized frame dimensions differ from original pixels')
        for f in (a,b):
            if f.get('countReading',{}).get('modelEvidence')!=raw['countModels']:raise ValueError('named inventory frame model scope changed')
            named_title_contract(f,target,rs,rf,raw['strictModels'])
        if (a['width'],a['height'])!=(b['width'],b['height']) or a['stack']['nameRegion']!=b['stack']['nameRegion'] or a['stack']['countRegion']!=b['stack']['countRegion']:
            raise ValueError('named inventory independent frame geometry changed')
        va,vb=(frame_count(f,target,selection,rs,rf,assets,named_title=True) for f in (a,b))
        if __package__:from .named_inventory_pixels import verify_selected_pixels
        else:from named_inventory_pixels import verify_selected_pixels
        for f,original in ((a,original_a),(b,original_b)):
            image=original_png(original['privateCapture'],root,trusted_workflow_root)
            try:verify_selected_pixels(f,image)
            finally:image.close()
        aliases=HEADER_ALIASES[target['category']]
        if ([clean(row['text']) for row in a['headerRows'] if clean(row['text']) in aliases]!=[clean(row['text']) for row in b['headerRows'] if clean(row['text']) in aliases]
                or va!=vb or type(inventory[identifier]) is not int or inventory[identifier]!=vb):raise ValueError('named inventory actual named pair counts differ')
        intervals.append((click,second));result[identifier]={'name':target['materialName'],'count':vb,'status':'exact','verified':True,'source':raw['source']}
    intervals.sort()
    if any(b[0]<=a[1] for a,b in zip(intervals,intervals[1:])) or raw.get('observedAt')!=max(v[1] for v in intervals):raise ValueError('named inventory captures reused/overlapped or summary stale')
    _worlds(raw.get('worldFrames'),frames,root,rs,rf,intervals[-1][1],trusted_workflow_root)
    return result


def verify_named_inventory(packet,request,started_at,finished_at,*,trusted_runtime_root,trusted_game_context=None,trusted_workflow_root=None):
    result={'readOnly':True,'rawEvidenceVerified':False,'liveVerified':False,'consumptionVerified':False,'sessionAfterVerified':False,
        'targetReached':False,'completedUpgrades':0,'status':'unknown','inventory':{m['materialId']:{'name':m['materialName'],'count':None,'status':'unknown'} for m in request['materials']}}
    try:
        read_start,read_finish=_packet_interval(packet,started_at,finished_at)
        if packet.get('request')!=request:
            raise ValueError('named inventory diagnostic packet scope mismatch')
        if packet.get('nativeObservation') is None and isinstance(packet.get('reason'),str):
            raise ValueError('native named binding/read failed before evidence: '+packet['reason'][:180])
        raw=packet.get('nativeObservation')
        if isinstance(raw,dict) and raw.get('status')=='unknown' and isinstance(raw.get('primaryReason'),str):
            raise ValueError('native named readonly result remains unknown: '+raw['primaryReason'][:180])
        result['inventory']=verified_named_observation(packet.get('nativeObservation'),request,read_start,read_finish,
            trusted_runtime_root=trusted_runtime_root,trusted_game_context=trusted_game_context,binding_receipt=packet.get('bindingReceipt'),trusted_workflow_root=trusted_workflow_root)
        result.update(status='success',rawEvidenceVerified=True)
    except Exception as error:
        # Optional image decoders and malformed evidence also fail closed.
        result['reason']=str(error)[:300]
    return result


def verify_bound_mora(packet,started_at,finished_at,*,trusted_runtime_root,trusted_game_context=None,trusted_workflow_root=None):
    result={'readOnly':True,'status':'unknown','balance':None,'rawEvidenceVerified':False,'liveVerified':False,
        'consumptionVerified':False,'sessionAfterVerified':False,'completedUpgrades':0,'targetReached':False}
    try:
        if __package__:
            from .resource_coverage import _mora_frame
            from .weekly_inventory import rows,rect
        else:
            from resource_coverage import _mora_frame
            from weekly_inventory import rows,rect
        read_start,read_finish=_packet_interval(packet,started_at,finished_at)
        if packet.get('nativeObservation') is None and isinstance(packet.get('reason'),str):
            raise ValueError('native bound Mora binding/read failed before evidence: '+packet['reason'][:180])
        start,finish=_time(read_start),_time(read_finish);root=Path(trusted_runtime_root).resolve(strict=True);raw=packet.get('nativeObservation')
        if isinstance(raw,dict) and raw.get('status')=='unknown' and isinstance(raw.get('reason'),str):
            raise ValueError('native bound Mora result remains unknown: '+raw['reason'][:180])
        if (not isinstance(raw,dict) or raw.get('schemaVersion')!=1 or raw.get('source')!='bound_precious_items_bottom_mora'
                or raw.get('readOnly') is not True or raw.get('confirmationSubmitted') is not False
                or type(raw.get('completedUpgrades')) is not int or raw['completedUpgrades']!=0
                or raw.get('targetReached') is not False or raw.get('materialId')!='202' or raw.get('materialName')!='摩拉'
                or raw.get('status')!='verified' or raw.get('mainUiRestored') is not True or raw.get('cleanupCompleted') is not True):
            raise ValueError('bound Mora readonly scope/result incomplete')
        rs,rf=integer(raw.get('startedAt')),integer(raw.get('finishedAt'))
        if not start<=rs<=rf<=finish or rf-rs>180000:raise ValueError('bound Mora current native interval invalid')
        expected,session=verify_binding_receipt(packet.get('bindingReceipt'),trusted_game_context,start,rs)
        if raw.get('captureSession')!=session:raise ValueError('bound Mora native capture lifecycle changed')
        capture_timeline(raw.get('rawFrames'),raw.get('gameBinding'),expected,rs,rf,trusted_runtime_root=root,trusted_workflow_root=trusted_workflow_root)
        catalog=load_runtime_catalog(root)
        if not _version(catalog['version'],raw.get('catalogVersion')) or not any(r['itemClassId']=='material:202' and r['fullName']=='摩拉' for r in catalog['rows']) or any(r['fullName']=='摩拉' and r['itemClassId']!='material:202' for r in catalog['rows']):
            raise ValueError('bound Mora actual runtime material202 identity/versions missing')
        strict_models(raw.get('strictModels'),root);frames=raw['rawFrames']
        entry=_worlds(raw.get('entryWorldFrames'),frames,root,rs,rf,rs-1,trusted_workflow_root,entry=True)
        request=raw.get('request',{})
        if request!={'balanceRegion':{'x':392,'y':1000,'width':168,'height':40},'iconRegion':{'x':354,'y':1000,'width':37,'height':37}}:
            raise ValueError('bound Mora only fixed empty-request actual crop is supported')
        readings=raw.get('readings')
        if not isinstance(readings,list) or len(readings)<2:raise ValueError('bound Mora independent original pair missing')
        a,b=readings[-2:]
        if not entry<a['observedAt']<b['observedAt']<=rf or b['observedAt']-a['observedAt']>5000:raise ValueError('bound Mora actual read pair invalid')
        values=[]
        for f in (a,b):
            _original(frames,f,f['observedAt'],'actual_Mora_balance')
            if f.get('balanceRegion')!=request['balanceRegion'] or f.get('iconRegion')!=request['iconRegion']:raise ValueError('bound Mora actual source crop changed')
            rows(f.get('balanceRows'),rect(f['balanceRegion']),1);rows(f.get('headerRows'),(100,0,350,100),1)
            if (not re.fullmatch(r'(0|[1-9][0-9]{0,9})',f.get('rawBalanceText','').strip())
                    or f['rawBalanceText'].strip()!=f['balanceRows'][0]['text'].strip()):raise ValueError('bound Mora complete original ASCII OCR methods disagree')
            values.append(_mora_frame(f,rs,rf))
        if values[0]!=values[1] or type(raw.get('balance')) is not int or raw['balance']!=values[1]:raise ValueError('bound Mora complete model/dual OCR pair differs')
        _worlds(raw.get('worldFrames'),frames,root,rs,rf,b['observedAt'],trusted_workflow_root)
        result.update(status='success',balance=values[1],rawEvidenceVerified=True)
    except Exception as error:result['reason']=str(error)[:300]
    return result
