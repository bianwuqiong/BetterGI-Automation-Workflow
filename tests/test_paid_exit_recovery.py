import copy
import json
from datetime import datetime, timedelta
import unittest
from tests import test_paid_inventory_reconciliation as paid


class PaidExitRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.helper=paid.PaidReconciliationTests(); self.helper.setUp()
        self.h=self.helper;self.a=self.h.a;self.root=self.h.root
        path, reader=self.a.transition()
        reader['effectiveAtUTC']='2026-10-10T02:15:00Z';self.a.write(path,reader)
        self.reader=reader;self.reader_path=path
        audit=copy.deepcopy(self.h.audit);audit['probeRuntimeIdentity']=reader['currentRuntimeIdentity']
        for i,ref in enumerate(audit['ownedBoundaries']['probeRuntimes']):
            p=self.root/ref['path'];row=json.loads(p.read_text(encoding='utf-8'));row['runtimeIdentity']=reader['currentRuntimeIdentity']
            self.a.write(p,row);audit['ownedBoundaries']['probeRuntimes'][i]=self.a.reference(p)
        self.a.write(self.h.path,audit);self.old_audit=audit
        _,auth=self.a.guard('exit-run',assign=True)
        old=self.h.base('exit-run','execute','2026-10-10T02:24:00Z','2026-10-10T02:26:00Z')
        earlier=json.loads(self.h.raw_paths['paid-run'].read_text(encoding='utf-8'))
        step=copy.deepcopy(earlier['steps'][0])
        step.update(stepId='exit-run:step-1',startedAt='2026-10-10T02:24:05Z',finishedAt=old['finishedAt'],
            before=self.h.stock([22,10,2,0]),after=None,resinAfter=None,actualResinDelta=None,
            resinBefore=self.h.resin(119,'2026-10-10T02:24:05Z'),
            reason='单次原粹20提交后安全退出未获双帧世界证明；结果未知，禁止再次领奖或普通退出兜底')
        old.update(status='unknown',steps=[step],inventory=step['before']);old['policy']=earlier['policy']
        old_sources=self.h.persist('exit-run',old,auth)
        log=self.root/'logs/runs/exit-run/bettergi.log'
        log.write_text('[10:24:05.000] [CULTIVATION_RESIN_OBSERVATION] '+json.dumps(step['resinBefore'])+'\n'
            '[10:24:58.000] 单次原粹20提交请求已发送：Original20第一行和独立使用按钮双帧；singleClick=True\n'
            '[10:25:00.000] 受保护单次领奖：经典结果页奖励仅作观察，paid状态仍待外层库存/余额，不累加native成功轮数',encoding='utf-8')
        old_sources['log']=self.a.reference(log)
        self.exit_transition=self.make_exit_epoch(reader)
        new=self.h.base('fixed-probe','scan','2026-10-10T02:35:00Z','2026-10-10T02:35:10Z')
        new.update(inventory=self.h.stack_stock([24,11,2,0],new['startedAt']),metadata={'diagnostic':'inventory-and-resin'},
            resinObservation=self.h.resin(100,'2026-10-10T02:35:05Z'))
        sources=self.h.persist('fixed-probe',new)
        log=self.root/'logs/runs/fixed-probe/bettergi.log';log.write_text('[CULTIVATION_RESIN_OBSERVATION] '+json.dumps(new['resinObservation']),encoding='utf-8')
        sources['log']=self.a.reference(log)
        snapshot=self.root/'state/cultivation-authorization-snapshots/exit-review-parent.json';snapshot.write_bytes(self.a.path.read_bytes())
        closed=self.root/'tests/.artifacts/exit-closed.json';self.a.write(closed,{'runId':'exit-run','finishedAt':'2026-10-10T02:26:05Z','gameBGIProcesses':0,'settingsMatch':True,'graphicsRegistryMatchesSnapshot':True})
        pre=self.root/'tests/.artifacts/exit-prelaunch.json';self.a.write(pre,{'runId':'fixed-probe','observedAtUTC':'2026-10-10T02:34:59Z','gameBGIProcesses':0})
        owned=self.root/'tests/.artifacts/fixed-runtime.json';self.a.write(owned,{'runId':'fixed-probe','observedAtUTC':'2026-10-10T02:35:01Z','bettergiPid':123,'gamePid':456,'runtimeIdentity':self.exit_transition['currentRuntimeIdentity']})
        self.audit={**copy.deepcopy(self.old_audit),'kind':'paid-exit-recovery-review','runId':'exit-run','stepId':'exit-run:step-1',
            'reviewedAtUTC':'2026-10-10T02:36:00Z','authorizationSnapshot':self.a.reference(snapshot),'oldSources':old_sources,
            'inventoryRunId':'fixed-probe','resinRunId':'fixed-probe','inventorySources':sources,'resinSources':sources,
            'probeRuntimeIdentity':self.exit_transition['currentRuntimeIdentity'],
            'ownedBoundaries':{'oldClosed':self.a.reference(closed),'newPrelaunch':self.a.reference(pre),'probeRuntimes':[self.a.reference(owned)]}}
        self.add_classifier_sources()
        self.path=self.root/'state/cultivation-paid-exit-recoveries/exit-run.json';self.a.write(self.path,self.audit)

    def make_exit_epoch(self, reader):
        snapshot=self.root/'state/cultivation-authorization-snapshots/exit-runtime-parent.json';snapshot.write_bytes(self.a.path.read_bytes())
        source=self.root/reader['currentRuntimeIdentity']['domainSource']['path'];backup=self.root/'backups/exit/source.cs';backup.parent.mkdir(parents=True)
        backup.write_bytes(source.read_bytes());dll=self.a.bgi/'BetterGI.dll';old_dll=backup.parent/'BetterGI.dll';old_dll.write_bytes(dll.read_bytes())
        source.write_bytes(source.read_bytes().replace(b'return false;',b'return true;'));dll.write_bytes(b'new dark classifier engine')
        current={'domainSource':self.a.reference(source),'engineDll':self.a.reference(dll)}
        change={'schemaVersion':1,'kind':'dark-loading-classifier-fix','scopeId':'new-day','gameDate':'2026-10-10',
            'effectiveAtUTC':'2026-10-10T02:30:00Z','reviewedBy':'root-agent','reason':'Only reviewed loading classifier body changed.',
            'previousTransition':self.a.reference(self.reader_path),'parentReceipt':self.a.reference(snapshot),
            'priorRuntimeIdentity':reader['currentRuntimeIdentity'],'currentRuntimeIdentity':current,
            'oldDomainSourceBackup':self.a.reference(backup),'oldDllBackup':self.a.reference(old_dll),
            'reviewedSourceChanges':[{'path':current['domainSource']['path'],'before':self.a.reference(backup),'after':current['domainSource']}]}
        self.epoch_path=self.root/'state/cultivation-daily-exit-transitions/new-day.json';self.a.write(self.epoch_path,change)
        return change

    def add_classifier_sources(self):
        directory=self.root/'tests/.artifacts/exit-stages';directory.mkdir(parents=True)
        frames=[]
        for offset,loading in ((62,True),(64,True),(66,False),(68,False)):
            p=directory/f'stage-{offset}.png';p.write_bytes(f'fake retained stage{offset}'.encode())
            frames.append({'privatePath':str(p),'sha256':self.a.reference(p)['sha256'],'videoOffsetSeconds':offset,
                           'nativeCaptureTimestamp':None,'afterBackgroundClassifierExpected':loading})
        replay={'schemaVersion':1,'runId':'exit-run','sourceOnlyClassifier':'HasProtectedLoadingBackground',
            'noRuntimeCompletionInference':True,'frames':frames,'validation':{'productionClassifierUnitAssertionsPassed':True}}
        replay_path=directory/'classifier.json';self.a.write(replay_path,replay)
        manifest={'candidateDll':{'sha256':self.exit_transition['currentRuntimeIdentity']['engineDll']['sha256']},
            'sourceChanges':[{'afterSha256':self.exit_transition['currentRuntimeIdentity']['domainSource']['sha256']}],
            'privateFrameClassificationArtifact':self.a.reference(replay_path),'validation':{'selectedRegressionFailed':0}}
        manifest_path=directory/'source-manifest.json';self.a.write(manifest_path,manifest)
        paid_frame=directory/'paid-99.png';paid_frame.write_bytes(b'fake classic balance99')
        self.audit.update(exitClassifierReplay=self.a.reference(replay_path),classifierSourceManifest=self.a.reference(manifest_path),
            immediatePaidObservation={'source':'reviewed-classic-reward-frame','reviewedBy':'root-agent','originalResin':99,'condensedResin':0,
                'videoSha256':self.audit['oldSources']['video']['sha256'],'frame':self.a.reference(paid_frame),'videoOffsetSeconds':60,'observedAtUTC':'2026-10-10T02:25:00Z'},
            outsideWorldFrames=[{'frame':{'path':self.a.reference(self.root/'tests/.artifacts/exit-stages'/f'stage-{o}.png')['path'],
                'sha256':frames[i]['sha256']},'videoOffsetSeconds':o,'outsideWorldObserved':True,'reviewedBy':'root-agent'} for i,o in ((2,66),(3,68))],
            videoReviews=[{'runId':'exit-run','frames':[self.a.reference(paid_frame),self.a.reference(directory/'stage-66.png')]},
                {'runId':'fixed-probe','frames':self.old_audit['videoReviews'][1]['frames']}])

    def test_three_eras_old_review_still_valid_and_exit_unknown_keeps_sixty_charge(self):
        before=self.h.raw_paths['exit-run'].read_bytes();old_review=self.h.path.read_bytes();reader=self.reader_path.read_bytes()
        cfg,summary=self.a.guard()
        self.assertEqual(summary['priorReservedOriginal'],60);self.assertEqual(cfg['policy']['originalResinBudget'],140)
        self.assertEqual(summary['unknownRuns'],[]);self.assertEqual(summary['runtimeIdentity'],self.exit_transition['currentRuntimeIdentity'])
        self.assertEqual(set(summary['reconciledPaidUnknownRuns']),{'paid-run','exit-run'})
        self.assertEqual(self.h.raw_paths['exit-run'].read_bytes(),before);self.assertEqual(self.h.path.read_bytes(),old_review)
        self.assertEqual(self.reader_path.read_bytes(),reader)

    def test_classifier_epoch_rejects_changed_outside_code_or_old_backup(self):
        source=self.root/self.exit_transition['currentRuntimeIdentity']['domainSource']['path']; original=source.read_bytes()
        source.write_bytes(original+b' changed resource limit')
        change=copy.deepcopy(self.exit_transition);change['currentRuntimeIdentity']['domainSource']=self.a.reference(source)
        change['reviewedSourceChanges'][0]['after']=self.a.reference(source);self.a.write(self.epoch_path,change)
        with self.assertRaisesRegex(ValueError,'outside loading classification'):self.a.guard()

    def test_exit_review_cannot_fake_api_after_or_reuse_old_probe(self):
        for changes in ({'probeRuntimeIdentity':self.reader['currentRuntimeIdentity']}, {'releasedOriginalReservation':20},
                        {'immediatePaidObservation':{**self.audit['immediatePaidObservation'],'originalResin':119}}):
            self.a.write(self.path,{**self.audit,**changes})
            with self.assertRaises(ValueError):self.a.guard()

    def test_exit_review_missing_stages_or_wrong_video_clock_stays_blocked(self):
        for changes in ({'outsideWorldFrames':[]}, {'immediatePaidObservation':{**self.audit['immediatePaidObservation'],'observedAtUTC':'2026-10-10T02:24:05Z'}}):
            self.a.write(self.path,{**self.audit,**changes})
            with self.assertRaises(ValueError):self.a.guard()
