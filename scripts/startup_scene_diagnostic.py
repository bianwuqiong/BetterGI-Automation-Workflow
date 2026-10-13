"""Validate a scoped startup refusal diagnostic; it never proves live pixels or success."""
import json
import math
import re

try:
    from .named_inventory_capture import rectangle_core
except ImportError:
    from named_inventory_capture import rectangle_core

PREFIX='[AUTOGAME_STARTUP_BLOCK]'
METHOD='startup_readonly_scene_block_v1'
SCENES={
    'startup_requires_local_user_dialogue_choice':'dialogue_choice',
    'startup_requires_local_user_dialogue':'dialogue',
    'startup_requires_local_user_unknown_scene':'unknown',
    'startup_requires_local_user_scene_observation_failed':'observation_failed',
}
EXCEPTION_REASONS={*SCENES,
    'startup_requires_local_user_concurrent_task',
    'startup_requires_local_user_startup_owner_lost',
    'startup_requires_local_user_automatic_trigger_drain_timeout',
    'startup_requires_local_user_automatic_trigger_drain_failed'}
FIELDS={'schemaVersion','method','reason','scene','elapsedMilliseconds','automaticTriggersSuppressed',
    'startupOwnerSource','wakeInputAttempts','nodeExecutionAllowed','nativeObservation'}
OBS_FIELDS={'observedAt','width','height','mainUi','closableUi','domain','dialogueVisible','choiceVisible',
    'templates','method','inputSent','nativePngRetained'}
TEMPLATE_FIELDS={'task','object','region','threshold','matched','matchScore','matchBounds'}
REGIONS=(('DisabledUiButton',(0,0,640,135)),('OptionIcon',(960,90,640,980)))

def parse_startup_exception_diagnostic(line):
    """Called only for the first exception line of an already scoped native refusal ERR."""
    if not isinstance(line,str) or len(line)>4096:return None
    found=re.fullmatch(r'BetterGenshinImpact\.Service\.StartupLocalUserRequiredException: '
        r'(startup_requires_local_user_[a-z_]+): [^\r\n]+',line)
    if found is None or found.group(1) not in EXCEPTION_REASONS:return None
    return {'reason':found.group(1),'requiresLocalUser':True,
        'evidenceScope':'startup-exception-diagnostic-only','livePixelsVerified':False,
        'taskCompletionVerified':False,'resourceAuthorization':False,'automaticReplayAllowed':False}

def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate startup diagnostic key')
        result[key]=value
    return result

def _integer(value,minimum=0,maximum=9007199254740991):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ValueError('startup diagnostic bounded integer required')
    return value

def _box(value):
    parsed=rectangle_core(value)
    box=tuple(parsed[k] for k in ('x','y','width','height'))
    if box[2]<=0 or box[3]<=0 or box[0]<0 or box[1]<0:
        raise ValueError('startup diagnostic positive rectangle required')
    return box

def _inside(a,b):
    return a[0]>=b[0] and a[1]>=b[1] and a[0]+a[2]<=b[0]+b[2] and a[1]+a[3]<=b[1]+b[3]

def parse_startup_scene_diagnostic(message):
    if not isinstance(message,str) or not message.startswith(PREFIX+' ') or len(message.encode('utf-8'))>32768:
        raise ValueError('bounded native startup diagnostic prefix required')
    raw=json.loads(message[len(PREFIX):],object_pairs_hook=_unique,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite startup JSON')))
    if (not isinstance(raw,dict) or set(raw)!=FIELDS or type(raw['schemaVersion']) is not int or raw['schemaVersion']!=1
            or raw['method']!=METHOD or raw['reason'] not in SCENES or raw['scene']!=SCENES[raw['reason']]
            or raw['automaticTriggersSuppressed'] is not True or raw['nodeExecutionAllowed'] is not False
            or type(raw['wakeInputAttempts']) is not int or raw['wakeInputAttempts']!=0
            or raw['startupOwnerSource'] not in ('actual_startup_TaskSemaphore_lease','existing_TaskRunner_owned_TaskSemaphore')):
        raise ValueError('startup refusal diagnostic method or no-input contract differs')
    elapsed=_integer(raw['elapsedMilliseconds'],0,3600000)
    if raw['scene']=='unknown' and elapsed<180000:
        raise ValueError('unknown startup refusal must preserve the original deadline')
    observation=raw['nativeObservation']
    if raw['scene']=='observation_failed' and observation is not None:
        raise ValueError('failed current read cannot borrow an earlier scalar observation')
    if observation is None:
        if raw['scene'] not in ('unknown','observation_failed'):
            raise ValueError('positive dialogue refusal needs its actual scalar observation')
    else:
        if (not isinstance(observation,dict) or set(observation)!=OBS_FIELDS
                or observation['method']!='existing_upstream_dialogue_and_choice_templates_readonly_v1'
                or observation['inputSent'] is not False or observation['nativePngRetained'] is not False
                or any(type(observation[k]) is not bool for k in ('mainUi','closableUi','domain','dialogueVisible','choiceVisible'))):
            raise ValueError('startup scene scalar shape differs')
        _integer(observation['observedAt'],1)
        # This local contract is reviewed only for the configured native resolution.
        if type(observation['width']) is not int or type(observation['height']) is not int or (observation['width'],observation['height'])!=(1920,1080):
            raise ValueError('startup scalar geometry outside reviewed local resolution')
        templates=observation['templates']
        if not isinstance(templates,list) or len(templates)!=2:
            raise ValueError('both unchanged upstream startup templates required')
        for proof,(name,region) in zip(templates,REGIONS):
            if (not isinstance(proof,dict) or set(proof)!=TEMPLATE_FIELDS or proof['task']!='AutoSkip' or proof['object']!=name
                    or _box(proof['region'])!=region or type(proof['threshold']) not in (int,float)
                    or proof['threshold']!=.8 or type(proof['matched']) is not bool):
                raise ValueError('startup template scalar order/ROI/threshold differs')
            if proof['matched']:
                score=proof['matchScore']
                if type(score) not in (int,float) or not math.isfinite(score) or not .8<=score<=1 or not _inside(_box(proof['matchBounds']),region):
                    raise ValueError('startup positive template scalars invalid')
            elif proof['matchScore'] is not None or proof['matchBounds'] is not None:
                raise ValueError('unmatched startup template must preserve null result')
        if (observation['dialogueVisible']!=templates[0]['matched'] or observation['choiceVisible']!=templates[1]['matched']
                or raw['scene']=='dialogue_choice' and not observation['choiceVisible']
                or raw['scene']=='dialogue' and (not observation['dialogueVisible'] or observation['choiceVisible'])):
            raise ValueError('startup scene and actual template scalar claims disagree')
    return {'reason':raw['reason'],'scene':raw['scene'],'requiresLocalUser':True,
        'evidenceScope':'startup-refusal-diagnostic-only','livePixelsVerified':False,
        'taskCompletionVerified':False,'resourceAuthorization':False,'automaticReplayAllowed':False,
        'nativeScalarObservation':raw}
