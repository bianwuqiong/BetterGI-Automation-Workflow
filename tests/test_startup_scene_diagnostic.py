"""Synthetic startup refusal packets; no game, OCR, authentication or resource actions."""
from copy import deepcopy
import json
import unittest
from scripts.startup_scene_diagnostic import PREFIX,parse_startup_scene_diagnostic,parse_startup_exception_diagnostic,EXCEPTION_REASONS
from scripts.workflow import startup_failure_evidence

def fixture():
    box=lambda x,y,w,h:dict(x=x,y=y,width=w,height=h)
    return dict(schemaVersion=1,method='startup_readonly_scene_block_v1',
        reason='startup_requires_local_user_dialogue_choice',scene='dialogue_choice',elapsedMilliseconds=500,
        automaticTriggersSuppressed=True,startupOwnerSource='actual_startup_TaskSemaphore_lease',
        wakeInputAttempts=0,nodeExecutionAllowed=False,
        nativeObservation=dict(observedAt=1791856800500,width=1920,height=1080,mainUi=False,closableUi=True,domain=False,
            dialogueVisible=True,choiceVisible=True,method='existing_upstream_dialogue_and_choice_templates_readonly_v1',
            inputSent=False,nativePngRetained=False,templates=[
                dict(task='AutoSkip',object='DisabledUiButton',region=box(0,0,640,135),threshold=.8,matched=True,
                    matchScore=.95,matchBounds=box(25,20,48,30)),
                dict(task='AutoSkip',object='OptionIcon',region=box(960,90,640,980),threshold=.8,matched=True,
                    matchScore=.96,matchBounds=box(1250,790,45,28))]))

def message(value):return PREFIX+' '+json.dumps(value,ensure_ascii=False)
def record(level,source,text,pid=555,time='10:00:00.000'):
    return f'[{time}] [{level}] [Primary:S1:P{pid}:T1791856800000] BetterGenshinImpact.{source}\n{text}\n\n'
def log(value,pid=555,config='AutoGame_synthetic'):
    return (record('INF','ViewModel.Pages.OneDragonFlowViewModel','启用一条龙配置：'+config,pid)
        +record('WRN','Service.ScriptService',message(value),pid,time='10:00:00.500')
        +record('ERR','ViewModel.Pages.OneDragonFlowViewModel','一条龙启动核验失败，未执行任务节点',pid,time='10:00:00.600'))

class StartupSceneDiagnosticTests(unittest.TestCase):
    def test_actual_typed_guard_reason_only_annotates_scoped_error_never_claims_completion(self):
        for reason in EXCEPTION_REASONS:
            line='BetterGenshinImpact.Service.StartupLocalUserRequiredException: '+reason+': synthetic local instruction'
            parsed=parse_startup_exception_diagnostic(line)
            self.assertEqual(parsed['reason'],reason);self.assertFalse(parsed['automaticReplayAllowed'])
            text=record('INF','ViewModel.Pages.OneDragonFlowViewModel','启用一条龙配置：AutoGame_synthetic')
            text+=record('ERR','Service.ScriptService','一条龙启动核验失败，未执行任务节点\n'+line)
            failure=startup_failure_evidence(text,'AutoGame_synthetic',555)
            self.assertEqual(failure['guardDiagnostic']['reason'],reason)
            self.assertEqual(failure['evidenceScope'],'startup-block-only')
            self.assertIsNone(startup_failure_evidence(line,'AutoGame_synthetic',555))
        for line in ('OCR文字：BetterGenshinImpact.Service.StartupLocalUserRequiredException: startup_requires_local_user_dialogue: sample',
                'Other.Service.StartupLocalUserRequiredException: startup_requires_local_user_dialogue: sample',
                'BetterGenshinImpact.Service.StartupLocalUserRequiredException: startup_requires_local_user_success: sample'):
            self.assertIsNone(parse_startup_exception_diagnostic(line))

    def test_positive_scene_claim_is_only_refusal_diagnostic_and_preserves_original_scalars(self):
        raw=fixture();before=deepcopy(raw);parsed=parse_startup_scene_diagnostic(message(raw))
        self.assertTrue(parsed['requiresLocalUser']);self.assertFalse(parsed['livePixelsVerified'])
        self.assertFalse(parsed['taskCompletionVerified']);self.assertFalse(parsed['resourceAuthorization'])
        self.assertFalse(parsed['automaticReplayAllowed']);self.assertEqual(raw,before)
        evidence=startup_failure_evidence(log(raw),'AutoGame_synthetic',555)
        self.assertEqual(evidence['evidenceScope'],'startup-block-only')
        self.assertEqual(evidence['sceneDiagnostic']['reason'],raw['reason'])
        self.assertLess(evidence['sceneDiagnostic']['line'],evidence['line'])

    def test_missing_duplicate_partial_scalar_and_input_claims_cannot_authenticate_diagnostic(self):
        raw=fixture()
        for key in raw:
            bad=deepcopy(raw);bad.pop(key)
            with self.subTest(key=key),self.assertRaises((ValueError,KeyError)):parse_startup_scene_diagnostic(message(bad))
        for key,value in (('schemaVersion',True),('elapsedMilliseconds',1.5),('wakeInputAttempts',True),
                ('wakeInputAttempts',1),('nodeExecutionAllowed',True),('automaticTriggersSuppressed',False),
                ('startupOwnerSource','caller-approved'),('method','legacy'),('reason','verified_success'),('scene','main_ui')):
            bad=deepcopy(raw);bad[key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):parse_startup_scene_diagnostic(message(bad))
        for value in (PREFIX+' '+json.dumps(raw).replace('"schemaVersion": 1','"schemaVersion": 1, "schemaVersion": 1'),
                message(raw).replace('0.95','NaN'),PREFIX+' '+'x'*32769):
            with self.assertRaises(ValueError):parse_startup_scene_diagnostic(value)

    def test_actual_template_order_geometry_score_and_null_semantics_are_required(self):
        for change in (lambda r:r['nativeObservation']['templates'].reverse(),
                lambda r:r['nativeObservation']['templates'][0].update(threshold=.7),
                lambda r:r['nativeObservation']['templates'][1].update(matchScore=True),
                lambda r:r['nativeObservation']['templates'][0]['region'].update(width=0),
                lambda r:r['nativeObservation']['templates'][1]['matchBounds'].update(x=950),
                lambda r:r['nativeObservation']['templates'][0]['matchBounds'].update(width=True),
                lambda r:r['nativeObservation'].update(choiceVisible=False),
                lambda r:r['nativeObservation'].update(observedAt=False),
                lambda r:r['nativeObservation'].update(nativePngRetained=True),
                lambda r:r['nativeObservation'].update(width=1536)):
            bad=fixture();change(bad)
            with self.assertRaises(ValueError):parse_startup_scene_diagnostic(message(bad))
        raw=fixture();raw.update(scene='dialogue',reason='startup_requires_local_user_dialogue')
        raw['nativeObservation'].update(choiceVisible=False)
        raw['nativeObservation']['templates'][1].update(matched=False,matchScore=None,matchBounds=None)
        self.assertEqual(parse_startup_scene_diagnostic(message(raw))['scene'],'dialogue')
        raw['nativeObservation']['templates'][1]['matchBounds']={'x':960,'y':90,'width':1,'height':1}
        with self.assertRaises(ValueError):parse_startup_scene_diagnostic(message(raw))

    def test_missing_failed_observation_never_borrows_a_positive_dialogue(self):
        raw=fixture();raw['nativeObservation']=None
        with self.assertRaises(ValueError):parse_startup_scene_diagnostic(message(raw))
        raw.update(scene='observation_failed',reason='startup_requires_local_user_scene_observation_failed')
        self.assertEqual(parse_startup_scene_diagnostic(message(raw))['scene'],'observation_failed')
        raw['nativeObservation']=fixture()['nativeObservation']
        with self.assertRaises(ValueError):parse_startup_scene_diagnostic(message(raw))
        raw.update(scene='unknown',reason='startup_requires_local_user_unknown_scene',nativeObservation=None)
        with self.assertRaises(ValueError):parse_startup_scene_diagnostic(message(raw))
        raw['elapsedMilliseconds']=180000
        self.assertEqual(parse_startup_scene_diagnostic(message(raw))['scene'],'unknown')

    def test_refusal_is_bound_to_owned_native_records_current_config_and_later_failure(self):
        base=log(fixture())
        for text in (message(fixture()),base.split('[10:00:00.600]')[0],
                base.replace('[WRN]','[INF]'),base.replace('Service.ScriptService','Service.OcrScanService'),
                base.replace(message(fixture()),'OCR文字：'+message(fixture())),
                base.replace('[10:00:00.500] [WRN] [Primary:S1:P555','[10:00:00.500] [WRN] [Primary:S1:P999')):
            failure=startup_failure_evidence(text,'AutoGame_synthetic',555)
            self.assertTrue(failure is None or 'sceneDiagnostic' not in failure)
        malformed=base.replace(message(fixture()),PREFIX+' {bad}')
        failure=startup_failure_evidence(malformed,'AutoGame_synthetic',555)
        self.assertIsNotNone(failure);self.assertNotIn('sceneDiagnostic',failure)
        twice=base.replace('[10:00:00.600]',record('WRN','Service.ScriptService',message(fixture()),time='10:00:00.550')+'[10:00:00.600]')
        self.assertNotIn('sceneDiagnostic',startup_failure_evidence(twice,'AutoGame_synthetic',555))
        self.assertIsNone(startup_failure_evidence(log(fixture(),config='Other'),'AutoGame_synthetic',555))

if __name__=='__main__':unittest.main()
