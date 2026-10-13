"""Original human window accounting; all inputs are synthetic, no game or private state writes."""
from copy import deepcopy
import hashlib
import json
import unittest

from scripts import artifact_farming as artifact
from scripts.artifact_window_funding import review_original_window_stage,_human_source_semantics
from tests import test_artifact_farming as fixtures
from tests.test_workflow import wf


class OriginalWindowFundingTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.ExplicitHumanNewBatchTests();fixture.setUp()
        self.root,self.now,self.probe_id=fixture.root,fixture.now,fixture.probe_id
        self.initial_scope=fixture.old_config['policy']['scopeId'];self.continuation_scope='one-human-continuation'
        self.directory=self.root/'logs/runs/test-run';self.ledger_path=fixture.ledger_path
        config=deepcopy(fixture.old_config);config['policy']['maxCrafts']=5
        config['target'].update(characterName='Synthetic character',artifactSet='Synthetic set',domainName='Synthetic domain',partyName='Synthetic party',strategyName='Synthetic strategy')
        self.group=artifact.build_artifact_group('test-run',config,'2026-10-11',{'autoDomainConfig':{'reviveRetryCount':1}},bettergi_dir=fixture.bgi)
        report=wf.read_json(self.directory/'artifact-farming-report.json')
        report.update(policy=config['policy'],target=config['target'],configSha256=artifact.config_hash(config))
        report['steps'][1]['parameterEvidence'].update(DomainName='Synthetic domain',PartyName='Synthetic party',CombatStrategyPath='C:/synthetic/Synthetic strategy.txt')
        report['steps'][0]['nativeResult'].update(RecipeCostVerified=True,RecipeOriginalResinCost=60)
        wf.atomic_json(self.directory/'artifact-farming-report.json',report)
        wf.atomic_json(self.directory/'artifact-farming-group.json',self.group)
        wf.atomic_json(self.directory/'result.json',{'runId':'test-run','outcome':'unknown','artifactPlugin':{'verified':True},
            'artifactFarming':{'reportVerified':True,'allStepsVerified':False,**report['totals']}})
        text=(self.directory/'bettergi.log').read_text(encoding='utf-8').replace('AutoGame_test','AutoGame_test-run')
        lines=[]
        for line in text.splitlines():
            event=artifact._event_from_line(line)
            if event is not None and event.get('task')=='artifact-domain-claim':continue
            if event is not None and event.get('task')==artifact.TASK_NAME:
                event['status']='unknown';line='[AUTO_GAME_EVENT] '+json.dumps(event)
            lines.append(line)
        (self.directory/'bettergi.log').write_text('\n'.join(lines),encoding='utf-8')
        ledger=wf.read_json(self.ledger_path);ledger['runs'][0].update(configSha256=artifact.config_hash(config),confirmedStepIds=['test-run:step-1'])
        ledger['runs'].append({'runId':'continued-zero','scopeId':self.continuation_scope,'gameDate':'2026-10-11',
            'status':'verified','originalResinSpent':0,'condensedResinSpent':0,'crafts':0})
        wf.atomic_json(self.ledger_path,ledger)
        auth=artifact.build_artifact_authorization(config,'2026-10-11T16:00:00Z','2026-10-11T19:00:00Z')
        auth_path=self.root/'state/artifact-authorizations'/(self.initial_scope+'.json');wf.atomic_json(auth_path,auth)
        unknown=artifact._unknown_rows(self.root,'2026-10-11',ledger)
        sources=[artifact._run_source_fingerprint(self.root,item) for item in unknown]
        permission={'scopeId':self.continuation_scope,'assignedRunId':'continued-zero','authorizationSource':'direct-human-reply','reviewedBy':'root-agent',
            'approvalText':'Synthetic explicit continuation permission','approvedAtUTC':'2026-10-11T16:05:00+00:00','validUntilUTC':auth['validUntilUTC'],
            'sourceRuns':sources,'originalAuthorizationSha256':hashlib.sha256(auth_path.read_bytes()).hexdigest()}
        permission['humanGrantSha256']=artifact._fingerprint({key:permission[key] for key in ('approvedAtUTC','approvalText','validUntilUTC','sourceRuns')})
        wf.atomic_json(self.root/'state/artifact-continuations'/(self.continuation_scope+'.json'),permission)
        self.context={'schemaVersion':2,'kind':'root-reviewed-original-artifact-window','sourceKind':'direct-user-request-in-current-thread',
            'reviewedBy':'root-agent','originalScopeId':self.initial_scope,'continuationScopeId':self.continuation_scope,
            'oldReceiptApprovedAtUTC':auth['approvedAtUTC'],'validUntilUTC':auth['validUntilUTC'],
            'continuationApprovedAtUTC':permission['approvedAtUTC'],'quotes':{'resourceAuthorization':'Synthetic resource permission',
                'targetChange':'Synthetic selected target','developmentWindow':'Synthetic fixed development window',
                'continueNewBatch':'Synthetic explicit continuation permission'},
            'semanticGrants':{'target':config['target'],'originalFundingCaps':{key:auth[key] for key in ('originalResinCap','condensedResinCap','craftCap')},
                'allNaturalOriginal':True,'allCondensed':True,'preferCondensed':True,'forbidFragile':True,'forbidTransient':True,
                'forbidPrimogems':True,'continueUnusedStages':True,'preserveUnknown':True,'replayUnknownAllowed':False}}
        self.context_path=self.root/'synthetic-current-human-attestation.json';wf.atomic_json(self.context_path,self.context)
        self.config=deepcopy(config);self.config['policy'].update(scopeId='new-window-stage',originalResinBudget=60,
            condensedResinBudget=1,maxCrafts=1,maxClaims=1,maxMinutes=5)
        self.probe(60,1)
        self.originals={path:path.read_bytes() for path in self.directory.iterdir()}
        self.old_row=deepcopy(ledger['runs'][0])

    def probe(self,original,condensed):
        directory=self.root/'logs/runs'/self.probe_id
        report=wf.read_json(directory/'cultivation-report.json');observation=report['resinObservation']
        observation.update(originalResin=original,condensedResin=condensed);wf.atomic_json(directory/'cultivation-report.json',report)
        event={'task':'培养材料','runId':self.probe_id,'mode':'scan','readOnly':True,'completedSteps':0}
        (directory/'bettergi.log').write_text('参数指定的一条龙配置：AutoGame_'+self.probe_id
            +'\n[CULTIVATION_RESIN_OBSERVATION] '+json.dumps(observation)+'\n[AUTO_GAME_EVENT] '+json.dumps(event),encoding='utf-8')

    def review(self,apply=False):
        return review_original_window_stage(self.root,self.initial_scope,self.continuation_scope,self.config,self.probe_id,
            source_path=self.context_path,source_sha256=hashlib.sha256(self.context_path.read_bytes()).hexdigest(),
            reviewed_by='root-agent',apply=apply,now=self.now)

    def test_original200_funding_keeps_known60_and_unknown_one_reservation_without_refund_or_new_time(self):
        reviewed=self.review(apply=True);stage=reviewed['windowReview']
        self.assertEqual(stage['originalFundingCaps']['originalResinCap'],200)
        self.assertEqual(stage['confirmedWindowUsage']['originalResinSpent'],60)
        self.assertEqual(stage['unknownResourceReservation']['condensedResinReserved'],1)
        self.assertEqual(stage['unknownResourceReservation']['originalResinReserved'],0)
        self.assertEqual(reviewed['authorization']['approvedAtUTC'],'2026-10-11T16:05:00+00:00')
        bounded,lease=artifact.constrain_artifact_authorization(self.root,self.config,'new-window-run','2026-10-11',assign=True,now=self.now)
        self.assertEqual(bounded['policy']['maxCrafts'],1)
        self.assertEqual(lease['originalWindowFundingScope'],self.initial_scope)
        self.assertEqual(wf.read_json(self.ledger_path)['runs'][0],self.old_row)
        for path,old in self.originals.items():self.assertEqual(path.read_bytes(),old)
        with self.assertRaises(ValueError):artifact.constrain_artifact_authorization(self.root,self.config,'again','2026-10-11',assign=True,now=self.now)

    def test_missing_direct_human_quotes_unchanged_stock_and_stale_probe_do_not_authorize(self):
        self.context['sourceKind']='advisory-session-note';wf.atomic_json(self.context_path,self.context)
        with self.assertRaises(ValueError):self.review()
        self.context['sourceKind']='direct-user-request-in-current-thread';self.context['quotes']['resourceAuthorization']=''
        wf.atomic_json(self.context_path,self.context)
        with self.assertRaises(ValueError):self.review()
        self.context['quotes']['resourceAuthorization']='Synthetic resource permission';wf.atomic_json(self.context_path,self.context)
        self.probe(59,1)
        with self.assertRaisesRegex(ValueError,'fresh actual'):self.review()

    def test_future_unknown_single_stage_and_original_cap_overallocation_block(self):
        self.review(apply=True)
        self.config['policy']['scopeId']='other-window-stage'
        with self.assertRaisesRegex(ValueError,'pending'):self.review()
        self.config['policy']['scopeId']='new-window-stage'
        _,lease=artifact.constrain_artifact_authorization(self.root,self.config,'committed-unknown','2026-10-11',assign=True,now=self.now)
        self.config['policy']['scopeId']='other-window-stage'
        with self.assertRaisesRegex(ValueError,'unresolved'):self.review()

    def test_actual_craft_cost_charges_budget_and_unknown_condensed_reservation_cannot_be_refunded(self):
        ledger=wf.read_json(self.ledger_path)
        ledger['runs'].append({'runId':'later-verified','scopeId':self.continuation_scope,'gameDate':'2026-10-11',
            'status':'verified','originalResinSpent':100,'condensedResinSpent':4,'crafts':1})
        wf.atomic_json(self.ledger_path,ledger)
        with self.assertRaisesRegex(ValueError,'original window'):self.review()
        ledger['runs'][-1]['originalResinSpent']=60;wf.atomic_json(self.ledger_path,ledger)
        with self.assertRaisesRegex(ValueError,'condensedResinCap'):self.review()

    def test_changed_prefix_params_or_native_receipt_deny_even_when_human_source_is_present(self):
        report=wf.read_json(self.directory/'artifact-farming-report.json')
        report['steps'][1]['parameterEvidence']['OriginalResin20UseCount']=1
        wf.atomic_json(self.directory/'artifact-farming-report.json',report)
        with self.assertRaises(ValueError):self.review()

    def test_subsequent_confirmed_condensed_and_craft_are_charged_once_and_cannot_renew_time(self):
        ledger=wf.read_json(self.ledger_path)
        ledger['runs'].append({'runId':'later-paid','scopeId':'older-window-scope','originalWindowFundingScope':self.initial_scope,
            'gameDate':'2026-10-11','status':'verified','originalResinSpent':60,'condensedResinSpent':1,'crafts':1})
        wf.atomic_json(self.ledger_path,ledger)
        review=self.review(apply=True)
        self.assertEqual(review['windowReview']['confirmedWindowUsage'],{'originalResinSpent':120,'condensedResinSpent':1,'crafts':2,'claims':1})
        self.assertEqual(review['windowReview']['confirmedCondensedGenerated'],2)
        auth_path=self.root/'state/artifact-authorizations/new-window-stage.json'
        auth=wf.read_json(auth_path);auth['validUntilUTC']='2026-10-12T01:11:48+00:00';wf.atomic_json(auth_path,auth)
        with self.assertRaises(ValueError):artifact.constrain_artifact_authorization(self.root,self.config,'renewed','2026-10-11',assign=True,now=self.now)

    def test_deployment_or_native_receipt_mismatch_cannot_be_hidden_by_relabeling_unknown(self):
        report=wf.read_json(self.directory/'artifact-farming-report.json')
        report['steps'][0]['nativeResult']['CondensedResinCreated']=2
        wf.atomic_json(self.directory/'artifact-farming-report.json',report)
        # Refreshing a human fingerprint cannot manufacture native/balance consistency.
        ledger=wf.read_json(self.ledger_path)
        unknown=artifact._unknown_rows(self.root,'2026-10-11',ledger)
        permission_path=self.root/'state/artifact-continuations'/(self.continuation_scope+'.json')
        permission=wf.read_json(permission_path);permission['sourceRuns']=[artifact._run_source_fingerprint(self.root,item) for item in unknown]
        permission['humanGrantSha256']=artifact._fingerprint({key:permission[key] for key in ('approvedAtUTC','approvalText','validUntilUTC','sourceRuns')})
        wf.atomic_json(permission_path,permission)
        with self.assertRaisesRegex(ValueError,'native receipt'):self.review()

    def test_typed_semantic_grants_require_exact_target_and_boolean_resource_bounds(self):
        for mutate in (lambda g:g.update(allNaturalOriginal='true'),lambda g:g.update(replayUnknownAllowed=True),
                lambda g:g['target'].update(characterName='Different synthetic character'),
                lambda g:g['originalFundingCaps'].update(originalResinCap=1000)):
            before=deepcopy(self.context);mutate(self.context['semanticGrants']);wf.atomic_json(self.context_path,self.context)
            with self.assertRaises(ValueError):self.review()
            self.context=before

    def test_legacy_private_source_requires_prior_exact_hash_review_without_changing_source_bytes(self):
        context=deepcopy(self.context);context['schemaVersion']=1;context.pop('semanticGrants')
        wf.atomic_json(self.context_path,context);old=self.context_path.read_bytes();sha=hashlib.sha256(old).hexdigest()
        auth=wf.read_json(self.root/'state/artifact-authorizations'/(self.initial_scope+'.json'))
        permission=wf.read_json(self.root/'state/artifact-continuations'/(self.continuation_scope+'.json'))
        with self.assertRaisesRegex(ValueError,'historical'):
            _human_source_semantics(self.root,context,self.context_path,sha,auth,permission,self.config['target'])
        prior={'kind':'explicit-original-window-resource-stage','reviewedBy':'root-agent','originalScopeId':self.initial_scope,
            'continuationScopeId':self.continuation_scope,'originalApprovedAtUTC':auth['approvedAtUTC'],
            'approvedAtUTC':permission['approvedAtUTC'],'validUntilUTC':auth['validUntilUTC'],
            'sourceSha256':sha,'sourcePath':str(self.context_path),'automaticReplayAllowed':False,'oldTaskOutcomesPreserved':True}
        path=self.root/'state/artifact-window-stages/historical-synthetic-review.json';wf.atomic_json(path,prior)
        _human_source_semantics(self.root,context,self.context_path,sha,auth,permission,self.config['target'])
        self.assertEqual(self.context_path.read_bytes(),old)
        prior['sourceSha256']='0'*64;wf.atomic_json(path,prior)
        with self.assertRaisesRegex(ValueError,'historical'):
            _human_source_semantics(self.root,context,self.context_path,sha,auth,permission,self.config['target'])


if __name__=='__main__':unittest.main()
