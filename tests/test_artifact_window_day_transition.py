"""Synthetic cross-day funding admission, no native calls or real state mutation."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import unittest
from scripts import artifact_farming as artifact
from scripts.artifact_window_funding import review_window_game_day_transition,review_original_window_stage
from tests import test_artifact_window_funding as fixtures
from tests.test_workflow import wf


class WindowDayTransitionTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.OriginalWindowFundingTests();fixture.setUp()
        self.root,self.initial_scope,self.continuation_scope,self.probe_id=fixture.root,fixture.initial_scope,fixture.continuation_scope,fixture.probe_id
        self.config=deepcopy(fixture.config);self.config['policy'].update(scopeId='synthetic-new-day-scope',originalResinBudget=20,condensedResinBudget=0,maxCrafts=0)
        self.context_path=fixture.context_path;self.context=deepcopy(fixture.context)
        self.now=datetime(2026,10,11,20,5,10,tzinfo=timezone.utc);self.date='2026-10-12'
        self.ledger_path=fixture.ledger_path
        ledger=wf.read_json(self.ledger_path)
        ledger['runs'] += [
            {'runId':'synthetic-confirmed-held-claim','scopeId':'synthetic-old-held','derivedStageFundingScope':self.continuation_scope,
                'gameDate':'2026-10-11','status':'verified','originalResinSpent':0,'condensedResinSpent':1,'crafts':0},
            {'runId':'synthetic-confirmed-craft-claim','scopeId':'synthetic-old-craft','originalWindowFundingScope':self.initial_scope,
                'gameDate':'2026-10-11','status':'verified','originalResinSpent':60,'condensedResinSpent':1,'crafts':1}]
        wf.atomic_json(self.ledger_path,ledger)
        # Extend this synthetic fixture into a genuinely spanning window, not a real user time.
        auth_path=self.root/'state/artifact-authorizations'/(self.initial_scope+'.json');auth=wf.read_json(auth_path)
        auth['validUntilUTC']='2026-10-12T00:00:00+00:00';wf.atomic_json(auth_path,auth)
        permission_path=self.root/'state/artifact-continuations'/(self.continuation_scope+'.json');permission=wf.read_json(permission_path)
        permission.update(validUntilUTC=auth['validUntilUTC'],originalAuthorizationSha256=hashlib.sha256(auth_path.read_bytes()).hexdigest())
        permission['humanGrantSha256']=artifact._fingerprint({key:permission[key] for key in ('approvedAtUTC','approvalText','validUntilUTC','sourceRuns')})
        wf.atomic_json(permission_path,permission)
        self.context['validUntilUTC']=auth['validUntilUTC'];self.context['semanticGrants']['allowGameDayTransition']=True
        wf.atomic_json(self.context_path,self.context)
        self.probe_dir=self.root/'logs/runs'/self.probe_id
        result=wf.read_json(self.probe_dir/'result.json');result.update(gameDate=self.date,finishedAt='2026-10-11T20:05:01Z',
            keepGameOpen=True,gameProcessSeen=True,adoptedGamePid=1234,adoptedGameExe=str(self.root/'synthetic-game.exe'),
            processMetrics={'GenshinImpact':{'pids':[1234]}},graphicsVerification={'state':'passed','windowSizeMatched':True,
                'runtimeRegistry':{'allMatched':True},'observedWindow':{'width':1920,'height':1080},
                'expectedWindow':{'width':1920,'height':1080,'windowed':True,'monitor':0}})
        wf.atomic_json(self.probe_dir/'result.json',result)
        wf.atomic_json(self.root/'config/settings.json',{'gameExe':str(self.root/'synthetic-game.exe'),
            'gameDisplaySettings':{'width':1920,'height':1080,'windowed':True,'monitor':0}})
        self.current_identity={'pid':1234,'exe':str(self.root/'synthetic-game.exe'),'physicalClient':{'width':1920,'height':1080}}
        self.observation={'originalResin':20,'condensedResin':0,'originalVerified':True,'condensedVerified':True,'mainUiRestored':True,
            'verified':True,'source':'stable_map_ocr','observedAt':'2026-10-11T20:05:00Z'}
        self.probe()
        self.old_ledger=self.ledger_path.read_bytes();self.originals={path:path.read_bytes() for path in (self.root/'logs/runs/test-run').iterdir()}

    def probe(self):
        wf.atomic_json(self.probe_dir/'cultivation-report.json',{'runId':self.probe_id,'mode':'scan','readOnly':True,'steps':[],
            'metadata':{'diagnostic':'resin-only'},'resinObservation':self.observation})
        event={'task':'培养材料','runId':self.probe_id,'mode':'scan','readOnly':True,'completedSteps':0}
        (self.probe_dir/'bettergi.log').write_text('参数指定的一条龙配置：AutoGame_'+self.probe_id
            +'\n[CULTIVATION_RESIN_OBSERVATION] '+json.dumps(self.observation)+'\n[AUTO_GAME_EVENT] '+json.dumps(event),encoding='utf-8')

    def review(self,apply=False,**changes):
        kwargs=dict(new_config=self.config,source_path=self.context_path,source_sha256=hashlib.sha256(self.context_path.read_bytes()).hexdigest(),
            reviewed_by='root-agent',apply=apply,now=self.now);kwargs.update(changes)
        return review_window_game_day_transition(self.root,self.initial_scope,self.continuation_scope,self.probe_id,self.date,**kwargs)

    def test_new_day_single20_keeps_whole_window120_and_unknown_con1_with_no_new_human_time(self):
        result=self.review(apply=True);day=result['gameDayReview']
        self.assertEqual(day['confirmedWindowUsage'],{'originalResinSpent':120,'condensedResinSpent':2,'crafts':2,'claims':2})
        self.assertEqual(day['unknownResourceReservation']['condensedResinReserved'],1)
        self.assertFalse(day['budgetReset']);self.assertFalse(day['newHumanApprovalGenerated'])
        self.assertEqual(result['authorization']['approvedAtUTC'],'2026-10-11T16:05:00+00:00')
        self.assertEqual(result['authorization']['validUntilUTC'],'2026-10-12T00:00:00+00:00')
        self.assertEqual(self.ledger_path.read_bytes(),self.old_ledger)
        self.assertFalse((self.root/'state/artifact-checkpoints'/f'{self.date}.json').exists())
        _,lease=artifact.constrain_artifact_authorization(self.root,self.config,'synthetic-current-day-run',self.date,assign=True,now=self.now,current_game_identity=self.current_identity)
        self.assertEqual(lease['gameDate'],self.date);self.assertEqual(lease['originalWindowFundingScope'],self.initial_scope)
        self.assertEqual(self.ledger_path.read_bytes(),self.old_ledger)
        for path,old in self.originals.items():self.assertEqual(path.read_bytes(),old)
        with self.assertRaises(ValueError):self.review(apply=True)

    def test_regular_stage_cannot_cross_by_only_updating_metadata_and_source_semantics_are_required(self):
        with self.assertRaisesRegex(ValueError,'explicit transition'):
            review_original_window_stage(self.root,self.initial_scope,self.continuation_scope,self.config,self.probe_id,
                source_path=self.context_path,source_sha256=hashlib.sha256(self.context_path.read_bytes()).hexdigest(),reviewed_by='root-agent',now=self.now)
        self.context['semanticGrants'].pop('allowGameDayTransition');wf.atomic_json(self.context_path,self.context)
        with self.assertRaisesRegex(ValueError,'transition semantics'):self.review()
        self.assertEqual(self.ledger_path.read_bytes(),self.old_ledger)

    def test_wrong_game_day_expired_or_stale_and_insufficient_fresh_balance_reject(self):
        with self.assertRaisesRegex(ValueError,'UTC8-04'):
            self.review(now=datetime(2026,10,11,19,59,59,tzinfo=timezone.utc))
        with self.assertRaises(ValueError):self.review(now=datetime(2026,10,12,0,1,tzinfo=timezone.utc))
        with self.assertRaises(ValueError):self.review(now=datetime(2026,10,11,20,8,tzinfo=timezone.utc))
        self.observation['originalResin']=19;self.probe()
        with self.assertRaisesRegex(ValueError,'fresh actual'):self.review()

    def test_unique_pid_exact_exe_full_graphics_and_current_world_resin_proof_are_independent(self):
        path=self.probe_dir/'result.json';original=wf.read_json(path)
        for change in ({'adoptedGameExe':str(self.root/'other.exe')},{'adoptedGamePid':None},
            {'processMetrics':{'GenshinImpact':{'pids':[1234,5678]}}},{'graphicsVerification':{'state':'passed','windowSizeMatched':False}}):
            result=deepcopy(original);result.update(change);wf.atomic_json(path,result)
            with self.assertRaisesRegex(ValueError,'game process/full graphics'):self.review()
        wf.atomic_json(path,original);self.observation['mainUiRestored']=False;self.probe()
        with self.assertRaises(ValueError):self.review()

    def test_target_change_more_confirmed_spend_or_any_new_unknown_does_not_reset_budget(self):
        config=deepcopy(self.config);config['target']['characterName']='Different synthetic character'
        with self.assertRaises(ValueError):self.review(new_config=config)
        ledger=wf.read_json(self.ledger_path)
        ledger['runs'].append({'runId':'synthetic-more-paid','scopeId':'synthetic-extra','originalWindowFundingScope':self.initial_scope,
            'gameDate':'2026-10-11','status':'verified','originalResinSpent':80,'condensedResinSpent':0,'crafts':0})
        wf.atomic_json(self.ledger_path,ledger)
        with self.assertRaisesRegex(ValueError,'originalResinCap'):self.review()
        ledger['runs'][-1].update(status='unknown',originalResinSpent=None,condensedResinSpent=None,crafts=None)
        wf.atomic_json(self.ledger_path,ledger)
        with self.assertRaisesRegex(ValueError,'unresolved'):self.review()

    def test_altered_day_receipt_blocks_gate_even_if_stock_and_old_unknown_are_unchanged(self):
        self.review(apply=True)
        path=self.root/'state/artifact-window-day-reviews'/f'{self.config["policy"]["scopeId"]}.json'
        day=wf.read_json(path);day['budgetReset']=True;wf.atomic_json(path,day)
        with self.assertRaisesRegex(ValueError,'review missing or changed'):
            artifact.constrain_artifact_authorization(self.root,self.config,'changed-review-run',self.date,assign=True,now=self.now)

    def test_new_typed_source_does_not_rewrite_the_previously_reviewed_legacy_source_or_stage(self):
        legacy=deepcopy(self.context);legacy['schemaVersion']=1;legacy.pop('semanticGrants')
        legacy_path=self.root/'synthetic-legacy-source.json';wf.atomic_json(legacy_path,legacy)
        legacy_sha=hashlib.sha256(legacy_path.read_bytes()).hexdigest()
        original_review={'kind':'explicit-original-window-resource-stage','scopeId':'synthetic-legacy-completed-scope',
            'assignedRunId':'synthetic-legacy-completed-run','reviewedBy':'root-agent','originalScopeId':self.initial_scope,
            'continuationScopeId':self.continuation_scope,'originalApprovedAtUTC':self.context['oldReceiptApprovedAtUTC'],
            'approvedAtUTC':self.context['continuationApprovedAtUTC'],'validUntilUTC':self.context['validUntilUTC'],
            'sourcePath':str(legacy_path),'sourceSha256':legacy_sha,'automaticReplayAllowed':False,'oldTaskOutcomesPreserved':True}
        old_path=self.root/'state/artifact-window-stages/synthetic-legacy-completed-scope.json';wf.atomic_json(old_path,original_review)
        originals={path:path.read_bytes() for path in (legacy_path,old_path)}
        with self.assertRaisesRegex(ValueError,'transition semantics'):
            self.review(source_path=legacy_path,source_sha256=legacy_sha)
        self.review(apply=True)
        for path,old in originals.items():self.assertEqual(path.read_bytes(),old)
        self.assertEqual(wf.read_json(old_path)['sourceSha256'],legacy_sha)

    def test_active_today_unknown_cannot_take_another_stage_and_changed_today_stock_invalidates_gate(self):
        self.review(apply=True)
        self.observation['originalResin']=21;self.probe()
        with self.assertRaisesRegex(ValueError,'fresh balance changed'):
            artifact.constrain_artifact_authorization(self.root,self.config,'changed-stock-run',self.date,assign=True,now=self.now,current_game_identity=self.current_identity)
        self.observation['originalResin']=20;self.probe()
        # Replacing the exact bytes back restores the originally reviewed fake evidence, not new authorization.
        _,lease=artifact.constrain_artifact_authorization(self.root,self.config,'today-pending-run',self.date,assign=True,now=self.now,current_game_identity=self.current_identity)
        next_config=deepcopy(self.config);next_config['policy']['scopeId']='synthetic-next-day-scope'
        with self.assertRaisesRegex(ValueError,'unresolved'):
            self.review(new_config=next_config)

    def test_physical1920_expected_and_configured_window_must_all_match(self):
        result_path=self.probe_dir/'result.json';original=wf.read_json(result_path)
        settings_path=self.root/'config/settings.json';settings=wf.read_json(settings_path)
        for mutate in (lambda r:r['graphicsVerification'].update(observedWindow={'width':1536,'height':864}),
                lambda r:r['graphicsVerification'].pop('expectedWindow'),
                lambda r:r['graphicsVerification']['expectedWindow'].update(width=1536,height=864),
                lambda r:r['graphicsVerification']['expectedWindow'].update(monitor=1)):
            result=deepcopy(original);mutate(result);wf.atomic_json(result_path,result)
            with self.assertRaisesRegex(ValueError,'physical game client'):self.review()
        wf.atomic_json(result_path,original)
        for mutate in (lambda s:s.pop('gameDisplaySettings'),lambda s:s['gameDisplaySettings'].update(width=1536,height=864),
                lambda s:s['gameDisplaySettings'].update(windowed=False)):
            changed=deepcopy(settings);mutate(changed);wf.atomic_json(settings_path,changed)
            with self.assertRaisesRegex(ValueError,'physical game client'):self.review()
        self.assertEqual(self.ledger_path.read_bytes(),self.old_ledger)

    def test_current_controller_identity_is_required_and_new_pid_same_exe_cannot_assign_or_write(self):
        self.review(apply=True)
        stage_path=self.root/'state/artifact-window-stages'/f'{self.config["policy"]["scopeId"]}.json'
        day_path=self.root/'state/artifact-window-day-reviews'/f'{self.config["policy"]["scopeId"]}.json'
        authority_path=self.root/'state/artifact-authorizations'/f'{self.config["policy"]["scopeId"]}.json'
        paths=(self.ledger_path,stage_path,day_path,authority_path,self.context_path)
        originals={path:path.read_bytes() for path in paths}
        candidates=[None,{'verified':True},{**self.current_identity,'pid':5678},
            {**self.current_identity,'exe':str(self.root/'wrong-current.exe')},
            {**self.current_identity,'physicalClient':{'width':1536,'height':864}},
            {**self.current_identity,'physicalClient':{'width':1920.0,'height':1080}}]
        for index,identity in enumerate(candidates):
            with self.assertRaisesRegex(ValueError,'current controller game'):
                artifact.constrain_artifact_authorization(self.root,self.config,'bad-current-query-'+str(index),self.date,
                    assign=True,now=self.now,current_game_identity=identity)
            self.assertFalse((self.root/'state/artifact-checkpoints'/f'{self.date}.json').exists())
            for path,old in originals.items():self.assertEqual(path.read_bytes(),old)
        _,lease=artifact.constrain_artifact_authorization(self.root,self.config,'correct-current-query',self.date,
            assign=True,now=self.now,current_game_identity=self.current_identity)
        self.assertEqual(lease['originalWindowFundingScope'],self.initial_scope)
        self.assertEqual(self.ledger_path.read_bytes(),self.old_ledger)

if __name__=='__main__':unittest.main()
