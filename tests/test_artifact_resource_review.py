"""Positive boundary plus independent balances; never infer no-submit from silence."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import io
import os
from pathlib import Path
import shutil
import unittest
from uuid import uuid4
from PIL import Image

from scripts import artifact_farming as artifact
from scripts.artifact_resource_review import review_known_unsubmitted_claim, classified_resource_zero, review_approved_batch_stage
from scripts.artifact_resource_review import _funding_usage, _check_stage_funds
from scripts.artifact_resource_review import _v10_source_phase_proof, DLL10_SHA256, V10_SHIELD_FAILURE, _full_frame_dimensions, _validate_full_frame_layout
from tests import test_artifact_farming as artifact_fixtures
from tests.test_artifact_farming import snapshot
from tests.test_workflow import wf


class ResourceStateReviewTests(unittest.TestCase):
    def setUp(self):
        fixture = artifact_fixtures.ExplicitHumanNewBatchTests()
        fixture.setUp()
        self.root, self.now = fixture.root, fixture.now
        self.run_id = 'new-batch-pre-submit'
        self.probe_id = fixture.probe_id
        self.directory = self.root / 'logs/runs' / self.run_id
        config = fixture.new_config()
        config['policy'].update(maxCrafts=0, originalResinBudget=42, condensedResinBudget=1)
        self.group = artifact.build_artifact_group(self.run_id, config, '2026-10-11',
            {'autoDomainConfig': {'reviveRetryCount': 1}}, bettergi_dir=fixture.bgi)
        self.parent_config = deepcopy(config)
        digest = self.group['Projects'][0]['JsScriptSettingsObject']['configSha256']
        param = {'DomainRoundNum': 1, 'CondensedResinUseCount': 1, 'OriginalResinUseCount': 0,
            'OriginalResin20UseCount': 0, 'OriginalResin40UseCount': 0, 'FragileResinUseCount': 0,
            'TransientResinUseCount': 0, 'SpecifyResinUse': True, 'AutoArtifactSalvage': False,
            'ArtifactRunId': self.run_id, 'ArtifactStepId': self.run_id + ':step-1'}
        self.report = {'runId': self.run_id, 'gameDate': '2026-10-11', 'status': 'unknown', 'configSha256': digest,
            'policy': config['policy'], 'target': config['target'], 'totals': {'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0},
            'finishedAt': '2026-10-11T16:04:59Z', 'reason': 'native positive pre-submit abort',
            'steps': [{'stepId': self.run_id + ':step-1', 'status': 'unknown', 'type': 'claim', 'resin': 'condensed',
                'parameterEvidence': param, 'before': snapshot(42,1,'2026-10-11T16:04:55Z')}]}
        wf.atomic_json(self.directory / 'result.json', {'runId': self.run_id, 'outcome': 'unknown'})
        wf.atomic_json(self.directory / 'artifact-farming-report.json', self.report)
        wf.atomic_json(self.directory / 'artifact-farming-group.json', self.group)
        self.event = {'task': 'artifact-domain-pre-submit-aborted', 'status': 'pre_submit_aborted',
            'runId': self.run_id, 'stepId': self.run_id + ':step-1', 'stateNotSubmitted': True,
            'claimSubmissionRequested': False, 'resourceOutcome': 'unknown'}
        self.log_path = self.directory / 'bettergi.log'
        self.log_path.write_text('[AUTO_GAME_EVENT] ' + json.dumps(self.event), encoding='utf-8')
        self.ledger_path = fixture.ledger_path
        ledger = wf.read_json(self.ledger_path)
        ledger['runs'].append({'runId': self.run_id, 'gameDate': '2026-10-11', 'scopeId': config['policy']['scopeId'],
            'status': 'unknown', 'configSha256': digest, 'originalResinSpent': None, 'condensedResinSpent': None, 'crafts': None})
        wf.atomic_json(self.ledger_path, ledger)
        self.ledger_before = deepcopy(ledger)
        self.originals = {path: path.read_bytes() for path in self.directory.iterdir()}

    def review(self, apply=False):
        return review_known_unsubmitted_claim(self.root, self.run_id, self.probe_id,
            reviewed_by='root-agent', apply=apply, now=self.now)

    def test_positive_boundary_and_fresh_balance_classify_only_resource_not_task(self):
        self.review(apply=True)
        ledger = wf.read_json(self.ledger_path)
        self.assertEqual(ledger['runs'][0], self.ledger_before['runs'][0])
        row = ledger['runs'][1]
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['resourceState'], 'known_not_submitted')
        self.assertIsNone(row['originalResinSpent'])
        self.assertIsNone(row['condensedResinSpent'])
        self.assertTrue(classified_resource_zero(self.root, row))
        for path, content in self.originals.items(): self.assertEqual(path.read_bytes(), content)
        self.assertFalse(artifact._ledger_row_resolved(self.root, ledger['runs'][0]))

    def test_no_event_network_error_or_after_click_requested_never_prove_zero(self):
        self.log_path.write_text('', encoding='utf-8')
        with self.assertRaises(ValueError): self.review(apply=True)
        self.event['claimSubmissionRequested'] = True
        self.log_path.write_text('[AUTO_GAME_EVENT] ' + json.dumps(self.event), encoding='utf-8')
        with self.assertRaises(ValueError): self.review(apply=True)
        self.assertEqual(wf.read_json(self.ledger_path), self.ledger_before)

    def test_returned_claim_receipt_conflicts_with_positive_no_submit_review(self):
        self.log_path.write_text('[AUTO_GAME_EVENT] ' + json.dumps(self.event)
            + '\n[AUTO_GAME_EVENT] {"task":"artifact-domain-claim","rewards":{}}', encoding='utf-8')
        with self.assertRaises(ValueError): self.review(apply=True)

    def test_invocation_owned_original20_abort_requires_exact_zero_phase_counters(self):
        step=self.report['steps'][0];step['resin']='original'
        step['parameterEvidence'].update(CondensedResinUseCount=0,OriginalResin20UseCount=1)
        wf.atomic_json(self.directory/'artifact-farming-report.json',self.report)
        self.event.update(source='invocation_owned_monotonic_resource_phase',owner='AutoDomainTask',
            phase='before_reward_interaction',roundCount=1,activeRound=0,completedClaimCount=0,
            submissionRequests=0,rewardFlowEntered=False,rewardInteractionEntered=False,resin='original')
        self.log_path.write_text('[AUTO_GAME_EVENT] '+json.dumps(self.event),encoding='utf-8')
        self.review()
        for key,bad in (('submissionRequests',1),('rewardFlowEntered',True),('activeRound',1),('roundCount',2),('resin','condensed')):
            old=self.event[key];self.event[key]=bad
            self.log_path.write_text('[AUTO_GAME_EVENT] '+json.dumps(self.event),encoding='utf-8')
            with self.assertRaises(ValueError): self.review()
            self.event[key]=old
        self.event.pop('source');self.event.pop('owner')
        self.log_path.write_text('[AUTO_GAME_EVENT] '+json.dumps(self.event),encoding='utf-8')
        with self.assertRaises(ValueError): self.review()

    def test_known_state_label_without_explicit_audit_is_not_a_resolved_transaction(self):
        row = deepcopy(self.ledger_before['runs'][1])
        row.update(resourceState='known_not_submitted', verifiedResourceConsumption={
            'originalResinSpent': 0, 'condensedResinSpent': 0, 'crafts': 0, 'claims': 0})
        self.assertFalse(classified_resource_zero(self.root, row))

    def test_changing_the_preserved_unknown_archive_invalidates_resource_classification(self):
        self.review(apply=True)
        row=wf.read_json(self.ledger_path)['runs'][1]
        self.assertTrue(classified_resource_zero(self.root,row))
        self.log_path.write_text(self.log_path.read_text(encoding='utf-8')+'\nchanged',encoding='utf-8')
        self.assertFalse(classified_resource_zero(self.root,row))

    def stage_authority(self):
        self.review(apply=True)
        ledger = wf.read_json(self.ledger_path)
        unknown = artifact._unknown_rows(self.root, '2026-10-11', ledger)
        source_runs = [artifact._run_source_fingerprint(self.root, packet) for packet in unknown]
        scope = self.parent_config['policy']['scopeId']
        authorization = artifact.build_artifact_authorization(self.parent_config, '2026-10-11T16:05:00Z', '2026-10-12T00:05:00Z')
        wf.atomic_json(self.root/'state/artifact-authorizations'/(scope+'.json'),authorization)
        wf.atomic_json(self.root/'state/artifact-continuations'/(scope+'.json'),{
            'assignedRunId': self.run_id, 'authorizationSource': 'direct-human-reply',
            'approvalText': '允许新建批次继续，保留原未知记录', 'approvedAtUTC': authorization['approvedAtUTC'],
            'validUntilUTC': authorization['validUntilUTC'], 'sourceRuns': source_runs})
        config = deepcopy(self.parent_config)
        config['policy'].update(scopeId='new-resource-stage', originalResinBudget=0, condensedResinBudget=1,
            maxCrafts=0, maxClaims=1, maxMinutes=5)
        return config

    def test_reviewed_new_stage_inherits_same_approval_and_cannot_charge_second_unit(self):
        config=self.stage_authority()
        reviewed=review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,reviewed_by='root-agent',apply=True,now=self.now)
        self.assertEqual(reviewed['authorization']['approvedAtUTC'],'2026-10-11T16:05:00+00:00')
        self.assertEqual(reviewed['authorization']['validUntilUTC'],'2026-10-12T00:05:00+00:00')
        _,lease=artifact.constrain_artifact_authorization(self.root,config,'new-stage-run','2026-10-11',assign=True,now=self.now)
        self.assertEqual(lease['derivedStageFundingScope'],self.parent_config['policy']['scopeId'])
        self.assertEqual(lease['parentResourceRunId'],self.run_id)
        artifact.finalize_artifact_checkpoint(self.root,lease,{'reportVerified':True,'allStepsVerified':True,
            'originalResinSpent':0,'condensedResinSpent':1,'crafts':0},launch_attempted=True)
        config['policy']['scopeId']='second-resource-stage'
        with self.assertRaisesRegex(ValueError,'no unused unit'):
            review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,reviewed_by='root-agent',apply=True,now=self.now)

    def test_phase_without_positive_resource_review_or_nonzero_original_budget_is_blocked(self):
        config=deepcopy(self.parent_config)
        config['policy'].update(scopeId='new-resource-stage',originalResinBudget=0,condensedResinBudget=1,maxCrafts=0,maxClaims=1,maxMinutes=5)
        with self.assertRaises(ValueError):
            review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,reviewed_by='root-agent',now=self.now)

    def test_original_single20_stages_use_original_cap_twice_without_condensed_or_time_renewal(self):
        config=self.stage_authority()
        config['policy'].update(originalResinBudget=20,condensedResinBudget=0)
        for number in (1,2):
            config['policy']['scopeId']='original-stage-'+str(number)
            reviewed=review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,
                reviewed_by='root-agent',apply=True,now=self.now)
            self.assertEqual(reviewed['stageReview']['fundingScopeId'],self.parent_config['policy']['scopeId'])
            self.assertEqual(reviewed['authorization']['approvedAtUTC'],'2026-10-11T16:05:00+00:00')
            _,lease=artifact.constrain_artifact_authorization(self.root,config,'original-stage-run-'+str(number),
                '2026-10-11',assign=True,now=self.now)
            artifact.finalize_artifact_checkpoint(self.root,lease,{'reportVerified':True,'allStepsVerified':True,
                'originalResinSpent':20,'condensedResinSpent':0,'crafts':0},launch_attempted=True)
        config['policy']['scopeId']='third-original-stage'
        with self.assertRaisesRegex(ValueError,'remaining single20'):
            review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,reviewed_by='root-agent',now=self.now)

    def test_nested_known_zero_stage_keeps_original_funding_and_an_unknown_child_blocks(self):
        config=self.stage_authority()
        review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,reviewed_by='root-agent',apply=True,now=self.now)
        _,lease=artifact.constrain_artifact_authorization(self.root,config,'nested-parent-run','2026-10-11',assign=True,now=self.now)
        config2=deepcopy(config);config2['policy']['scopeId']='nested-child-scope'
        with self.assertRaises(ValueError):
            review_approved_batch_stage(self.root,'nested-parent-run',config2,self.probe_id,reviewed_by='root-agent',now=self.now)
        # Synthetic already-reviewed source: no real run or native input.
        archive=self.root/'logs/runs/nested-parent-run/artifact-farming-report.json'
        parent_report=deepcopy(self.report)
        parent_report.update(runId='nested-parent-run',policy=config['policy'],configSha256=artifact.config_hash(config))
        wf.atomic_json(archive,parent_report)
        old_audit=wf.read_json(self.directory/'resource-pre-submit-review.json')
        old_audit.update(runId='nested-parent-run',stepId='nested-parent-run:step-1')
        for name in ('result.json','artifact-farming-group.json','bettergi.log'):
            shutil.copyfile(self.directory/name,archive.parent/name)
        old_audit['sourceSha256']={str(path.relative_to(self.root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in archive.parent.iterdir() if path.name in ('result.json','artifact-farming-report.json','artifact-farming-group.json','bettergi.log')}
        audit_path=archive.parent/'resource-pre-submit-review.json';wf.atomic_json(audit_path,old_audit)
        ledger=wf.read_json(self.ledger_path);row=ledger['runs'][-1]
        row.update(resourceState='known_not_submitted',verifiedResourceConsumption={
            'originalResinSpent':0,'condensedResinSpent':0,'crafts':0,'claims':0},
            resourceReviewPath=str(audit_path.relative_to(self.root)),
            resourceReviewSha256=__import__('hashlib').sha256(audit_path.read_bytes()).hexdigest())
        wf.atomic_json(self.ledger_path,ledger)
        reviewed=review_approved_batch_stage(self.root,'nested-parent-run',config2,self.probe_id,
            reviewed_by='root-agent',apply=True,now=self.now)
        self.assertEqual(reviewed['stageReview']['fundingScopeId'],self.parent_config['policy']['scopeId'])
        self.assertEqual(reviewed['stageReview']['fundingChain'][-1]['runId'],self.run_id)
        self.assertEqual(reviewed['authorization']['validUntilUTC'],'2026-10-12T00:05:00+00:00')

    def test_original_spending_includes_confirmed_crafting_and_generated_condensed_is_not_new_authority(self):
        packets=[(None,{'runs':[{'runId':'funding-parent','scopeId':'funding','status':'verified',
            'originalResinSpent':60,'condensedResinSpent':0,'crafts':1}]})]
        auth={'originalResinCap':100,'condensedResinCap':2,'craftCap':1}
        usage=_funding_usage(self.root,'funding',packets,auth,{'freshResinObservation':{'condensedResin':1}})
        self.assertEqual(usage['originalResinSpent'],60)
        self.assertEqual(usage['condensedGenerated'],1)
        _check_stage_funds({'originalResinBudget':20,'condensedResinBudget':0},usage,auth)
        with self.assertRaises(ValueError):_check_stage_funds({'originalResinBudget':60,'condensedResinBudget':0},usage,auth)
        usage['condensedResinSpent']=2
        with self.assertRaises(ValueError):_check_stage_funds({'originalResinBudget':0,'condensedResinBudget':1},usage,auth)
        config=self.stage_authority();config['policy']['originalResinBudget']=20
        with self.assertRaises(ValueError):
            review_approved_batch_stage(self.root,self.run_id,config,self.probe_id,reviewed_by='root-agent',now=self.now)


class FullFrameDecoderTests(unittest.TestCase):
    """Always runs in CI: decoding needs no private binary/screenshot fixture."""
    def encoded(self,format,size):
        stream=io.BytesIO();Image.new('RGB',size).save(stream,format=format);return stream.getvalue()

    def test_png_and_jpeg_full_raw_window_shape_and_integrity(self):
        metadata={'layout':'raw-sky-window-frame','clientRegion':{'x':1,'y':30,'width':1536,'height':864}}
        for format in ('PNG','JPEG'):
            content=self.encoded(format,(1538,895))
            dimensions=_full_frame_dimensions(content,format)
            self.assertEqual(dimensions,(1538,895))
            _validate_full_frame_layout(*dimensions,metadata)

    def test_jpeg_truncation_bad_signature_and_declared_format_rejected(self):
        content=self.encoded('JPEG',(1538,895))
        for bad in (content[:-2],content[:30]+b'\xff\xd9',b'bad'+content[3:]):
            with self.assertRaises(ValueError):_full_frame_dimensions(bad,'JPEG')
        with self.assertRaises(ValueError):_full_frame_dimensions(content,'PNG')
        with self.assertRaises(ValueError):_full_frame_dimensions(self.encoded('PNG',(1920,1080))[:-10],'PNG')

    def test_decoded_money_crop_and_wrong_full_window_size_rejected(self):
        metadata={'layout':'raw-sky-window-frame','clientRegion':{'x':1,'y':30,'width':1536,'height':864}}
        for size in ((200,100),(1540,895),(1538,864)):
            with self.assertRaises(ValueError):_validate_full_frame_layout(*_full_frame_dimensions(self.encoded('JPEG',size)),metadata)
        with self.assertRaises(ValueError):_validate_full_frame_layout(200,100,{})


class PinnedNative10PhaseTests(unittest.TestCase):
    """Copied immutable source baseline and synthetic timestamps; no native UI/state writes."""
    @classmethod
    def setUpClass(cls):
        cls.repo=Path(__file__).resolve().parents[1]
        baseline=cls.repo/'state/audit-native10-before-shield-fix'
        if not baseline.exists(): raise unittest.SkipTest('private pinned native10 audit not present')
        cls.root=cls.repo/'tests/.artifacts'/('native10-phase-proof-'+uuid4().hex[:10])
        shutil.copytree(baseline,cls.root/'state/audit-native10-before-shield-fix')

    def setUp(self):
        self.run_id='20261011T160000-'+uuid4().hex[:8]
        self.directory=self.root/'synthetic-context'/self.run_id
        self.directory.mkdir(parents=True)
        self.image=self.directory/'synthetic-full-frame.png'
        # Synthetic fixture is never used as actual visual proof: no native API is called.
        Image.new('RGB',(1920,1080)).save(self.image,format='PNG')
        stamp=datetime(2026,10,11,16,0,40,tzinfo=timezone.utc).timestamp()
        os.utime(self.image,(stamp,stamp))
        self.report={'reason':V10_SHIELD_FAILURE,'startedAt':'2026-10-11T16:00:00Z','finishedAt':'2026-10-11T16:00:20Z',
            'target':{'domainName':'逆悬的冰河','partyName':'待命队伍','strategyName':'木偶星超导'}}
        wf.atomic_json(self.root/'logs/runs'/self.run_id/'result.json',{'runId':self.run_id,'finishedAt':'2026-10-11T16:00:21Z'})
        self.param={'RequireZhongliShieldCast':True,'DomainRoundNum':1,'CombatOnly':False,
            'CombatStrategyPath':r'C:\fake\木偶星超导.txt','DomainName':'逆悬的冰河','PartyName':'待命队伍'}
        self.text='2. 执行战斗策略\n'+V10_SHIELD_FAILURE
        self.machine_run='20261011T160100-'+uuid4().hex[:8]
        wf.atomic_json(self.root/'logs/runs'/self.machine_run/'result.json',{'runId':self.machine_run,
            'triggeredAt':'2026-10-11T16:01:00Z','partyPreparation':{'reportVerified':True,'preparationCompleted':True}})
        self.context={'schemaVersion':1,'kind':'root-observed-native10-battle-failure-context','runId':self.run_id,
            'stepId':self.run_id+':step-1','reviewedBy':'root-agent','nativeDllSha256':DLL10_SHA256,
            'runtimeIdentityConfirmed':True,'battleClockActiveObserved':True,'remainingEnemiesObserved':2,'totalEnemiesObserved':4,
            'claimUiObserved':False,'manualRewardClaimObserved':False,
            'fullFrame':{'path':str(self.image),'sha256':hashlib.sha256(self.image.read_bytes()).hexdigest(),'capturedAtUTC':None,
                'captureTimeEvidence':{'kind':'trusted-ordered-tool-history-with-file-save-upper-bound',
                    'capturedAfterUTC':'2026-10-11T16:00:21Z','savedAtUTC':'2026-10-11T16:00:40Z','capturedAtUTC':None,
                    'toolHistoryNote':'Synthetic fixture: get state after run finish, save full frame before any exit input.'}},
            'exitObservation':{'worldExitObserved':True,'observedBy':'root-agent','sourceKind':'trusted-tool-history-written-observation',
                'imageEvidenceMissing':True,'toolHistoryNote':'Synthetic fixture: exit after frame save, world before freeprep.',
                'observedAtUTC':None,'exitedBeforeUTC':'2026-10-11T16:01:00Z','worldBeforeMachineRunId':self.machine_run}}
        self.path=self.directory/'synthetic-context.json'

    def proof(self):
        wf.atomic_json(self.path,self.context)
        return _v10_source_phase_proof(self.root,self.run_id,self.report,self.param,self.text,self.path)[0]

    def test_pinned_awaited_phase_and_ordered_bounds_preserve_unknown_exact_times_and_missing_exit_image(self):
        proof=self.proof()
        self.assertFalse(proof['captureAtUTCExactKnown'])
        self.assertFalse(proof['exitAtUTCExactKnown'])
        self.assertFalse(proof['nativePositiveEventFabricated'])
        self.assertTrue(proof['exitImageMissingPreserved'])

    def test_changed_binary_identity_context_or_target_cannot_unlock(self):
        for section,key,bad in ((self.context,'nativeDllSha256','0'*64),(self.context,'runtimeIdentityConfirmed',False),
                (self.param,'DomainRoundNum',2),(self.param,'DomainName','另一秘境')):
            old=section[key];section[key]=bad
            with self.assertRaises(ValueError): self.proof()
            section[key]=old
        self.image.write_bytes(self.image.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'missing/changed'): self.proof()

    def test_missing_context_network_failure_or_reward_phase_never_qualify(self):
        self.report['reason']='network cancellation'
        with self.assertRaises(ValueError): self.proof()
        self.report['reason']=V10_SHIELD_FAILURE
        self.text+='\n3. 寻找石化古树'
        with self.assertRaisesRegex(ValueError,'phase trace'): self.proof()
        self.text='2. 执行战斗策略\n'+V10_SHIELD_FAILURE
        self.context['exitObservation']['imageEvidenceMissing']=False
        with self.assertRaises(ValueError): self.proof()

    def test_wide_unordered_or_unbound_times_fail_closed_without_null_to_epoch(self):
        interval=self.context['fullFrame']['captureTimeEvidence']
        for key,bad in (('capturedAfterUTC','2026-10-11T15:59:59Z'),('savedAtUTC','2026-10-11T16:03:00Z'),
                ('savedAtUTC','2026-10-11T16:00:19Z'),('savedAtUTC',None)):
            old=interval[key];interval[key]=bad
            with self.assertRaises(ValueError): self.proof()
            interval[key]=old
        self.context['exitObservation']['exitedBeforeUTC']='2026-10-11T16:00:30Z'
        with self.assertRaises(ValueError): self.proof()

    def test_raw_sky_full_window_preserves_titlebar_but_rejects_other_size_or_crop(self):
        Image.new('RGB',(1538,895)).save(self.image,format='PNG')
        self.context['fullFrame'].update(layout='raw-sky-window-frame',
            clientRegion={'x':1,'y':30,'width':1536,'height':864},sha256=hashlib.sha256(self.image.read_bytes()).hexdigest())
        stamp=datetime(2026,10,11,16,0,40,tzinfo=timezone.utc).timestamp();os.utime(self.image,(stamp,stamp))
        self.proof()
        self.context['fullFrame']['clientRegion']['width']=1500
        with self.assertRaisesRegex(ValueError,'boundaries'): self.proof()
        self.context['fullFrame']['clientRegion']['width']=1536
        Image.new('RGB',(1540,895)).save(self.image,format='PNG')
        self.context['fullFrame']['sha256']=hashlib.sha256(self.image.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'boundaries'): self.proof()

    def test_raw_jpeg_bytes_with_png_filename_are_valid_but_wrong_signature_and_truncation_block(self):
        Image.new('RGB',(1538,895)).save(self.image,format='JPEG')
        self.context['fullFrame'].update(format='JPEG',layout='raw-sky-window-frame',
            clientRegion={'x':1,'y':30,'width':1536,'height':864},sha256=hashlib.sha256(self.image.read_bytes()).hexdigest())
        stamp=datetime(2026,10,11,16,0,40,tzinfo=timezone.utc).timestamp();os.utime(self.image,(stamp,stamp))
        self.proof()
        self.context['fullFrame']['format']='PNG'
        with self.assertRaisesRegex(ValueError,'format mismatch'): self.proof()
        self.context['fullFrame']['format']='JPEG'
        data=self.image.read_bytes()
        for bad in (data[:-2],data[:30]+b'\xff\xd9',b'bad'+data[3:]):
            self.image.write_bytes(bad);self.context['fullFrame']['sha256']=hashlib.sha256(bad).hexdigest()
            with self.assertRaises(ValueError): self.proof()


if __name__ == '__main__': unittest.main()
