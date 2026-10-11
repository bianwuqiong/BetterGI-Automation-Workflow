"""Cross-day workflow platform reads use fake hosts; no native WinAPI or game launch."""
import argparse
import contextlib
import io
import json
from unittest.mock import patch
import unittest
from tests import test_workflow as tw
from tests import test_artifact_farming as artifact_tests
from scripts import artifact_farming as artifact

wf = tw.wf


class DayReviewHost(tw.FakeHost):
    def __init__(self, root, *, changed=False, missing=False, wrong_path=False):
        super().__init__(root);self.changed=changed;self.missing=missing;self.wrong_path=wrong_path;self.reads=0
    def processes(self, names):
        if 'GenshinImpact' not in names:return []
        self.reads+=1
        return [] if self.missing else [222 if self.changed and self.reads>=3 else 111]
    def process_path(self, pid):return self.root/('other-game.exe' if self.wrong_path else 'game.exe')


class WorkflowDayReviewIdentityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=artifact_tests.ArtifactWorkflowTests();self.fixture.setUp()
        self.root=self.fixture.root
        self.config=wf.read_json(self.root/'config/artifact-farming.json')
        self.config['executionEnabled']=True
        self.config['policy']['domainValidated']=True
        wf.atomic_json(self.root/'config/artifact-farming.json',self.config)
        self.settings=dict(self.fixture.cfg,checkpointOnly=False,restoreManualGraphicsAfterRun=False,
            verifyAutomationGraphicsAfterStart=False,gameGraphicsProfile='config/fake-profile.json',
            gameDisplaySettings={'width':1920,'height':1080,'windowed':True})
        wf.atomic_json(self.root/'config/settings.json',self.settings)
        wf.atomic_json(self.root/'config/fake-profile.json',{})
        self.stage=self.root/'state/artifact-window-stages'/(self.config['policy']['scopeId']+'.json')
        self.ledger=self.root/'state/artifact-checkpoints/2026-09-12.json'
        wf.atomic_json(self.ledger,{'preserved':'old-unknown'})
        self.old_ledger=self.ledger.read_bytes()
    def day_stage(self):wf.atomic_json(self.stage,{'gameDayTransition':{'path':'review.json','sha256':'fixed-review'}})
    def query(self, host):
        return wf.fresh_artifact_day_review_identity(self.root,self.config,host,self.settings,
            profile_path=self.settings['gameGraphicsProfile'],quality_level=None,display_settings=self.settings['gameDisplaySettings'])
    def run_flow(self, host, *, physical=None, graphics=None):
        args=argparse.Namespace(root=str(self.root),dry_run=False,task=artifact.TASK_NAME,profile='artifact-farming',
            timeout_minutes=1,no_delay=True,allow_repeat=False,keep_game=True,allow_existing_game=True,graphics_check=False)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),patch.object(wf,'datetime',tw.FixedClock), \
                patch.object(wf,'observed_game_client_size',return_value=physical or {'width':1920,'height':1080}) as client, \
                patch.object(wf,'verify_genshin_automation_graphics',return_value=graphics or {'allMatched':True,'rawRegistry':'fresh'}) as registry, \
                patch('artifact_farming.constrain_artifact_authorization',side_effect=ValueError('gate_reached_after_fresh_platform_reads')) as gate:
            code=wf.execute(args,host)
        result=wf.read_json(json.loads(stream.getvalue())['resultPath'])
        return code,result,gate,client,registry
    def test_ordinary_no_stage_or_non_day_stage_never_queries_platform(self):
        host=DayReviewHost(self.root)
        with patch.object(wf,'observed_game_client_size') as size,patch.object(wf,'verify_genshin_automation_graphics') as registry:
            self.assertEqual(self.query(host),(None,None))
            wf.atomic_json(self.stage,{'ordinary':'stage'})
            self.assertEqual(self.query(host),(None,None));size.assert_not_called();registry.assert_not_called()
        self.assertEqual(host.reads,0)
    def test_fresh_unique_configured_pid_physical_client_and_registry_are_passed_before_assign(self):
        self.day_stage();host=DayReviewHost(self.root)
        code,result,gate,size,registry=self.run_flow(host)
        self.assertNotEqual(code,0,result);self.assertFalse(host.launched)
        self.assertIn('gate_reached_after_fresh', ' '.join(result['errors']))
        size.assert_called_once_with(111);registry.assert_called_once_with(profile_path=(self.root/'config/fake-profile.json').resolve(),quality_level=None,
            display_settings={**self.settings['gameDisplaySettings'],'monitor':0})
        self.assertEqual(gate.call_args.kwargs['current_game_identity'],{'pid':111,'exe':str((self.root/'game.exe').resolve()),'physicalClient':{'width':1920,'height':1080}})
        self.assertTrue(gate.call_args.kwargs['assign']);self.assertEqual(self.ledger.read_bytes(),self.old_ledger)
    def test_missing_or_new_pid_and_wrong_exe_reject_before_any_assign_or_launch(self):
        self.day_stage()
        for options in ({'missing':True},{'changed':True},{'wrong_path':True}):
            with self.subTest(options=options):
                host=DayReviewHost(self.root,**options);code,result,gate,_,_=self.run_flow(host)
                self.assertNotEqual(code,0,result);gate.assert_not_called();self.assertFalse(host.launched)
                self.assertEqual(self.ledger.read_bytes(),self.old_ledger)
    def test_logical_size_and_changed_registry_reject_before_any_assign_or_launch(self):
        self.day_stage()
        for options in ({'physical':{'width':1536,'height':864}},{'graphics':{'allMatched':False}}):
            with self.subTest(options=options):
                host=DayReviewHost(self.root);code,result,gate,_,_=self.run_flow(host,**options)
                self.assertNotEqual(code,0,result);gate.assert_not_called();self.assertFalse(host.launched)
                self.assertEqual(self.ledger.read_bytes(),self.old_ledger)


if __name__=='__main__':unittest.main()
