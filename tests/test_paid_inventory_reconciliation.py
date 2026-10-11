"""Retained fake paid attempts/probes verify continuation eligibility, never a refund."""
import copy
import json
from datetime import datetime, timedelta
import unittest

from tests import test_cultivation as reports
from tests import test_cultivation_daily_authorization as ledger
from tests import test_backpack_inventory_evidence as backpack
from scripts.cultivation import verify_cultivation_report
from scripts.cultivation_validation import _prelaunch_before_trigger


class PaidReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.authorizer = ledger.DailyAuthorizationTests(); self.authorizer.setUp()
        self.a = self.authorizer
        self.a.prior()
        self.root, self.bgi = self.a.root, self.a.bgi
        self.materials = json.loads((reports.ROOT / 'bgi-scripts/AutoGameCultivation/upstream/data/materials.json').read_text(encoding='utf-8'))
        self.chain = ['114009', '114010', '114011', '114012']
        self.profile = reports.CultivationTests().report()['profile']
        self.raw_paths = {}
        _, auth = self.a.guard('paid-run', assign=True)
        raw = self.base('paid-run', 'execute', '2026-10-10T02:06:00Z', '2026-10-10T02:10:05Z')
        raw['policy'] = {**self.a.config['policy'], 'domainSingleAttemptVerified': True, 'maxSteps': 2,
                         'dailyDomainReady': True, 'originalResinBudget': 180}
        before = self.stock([20, 7, 2, 0]); after = self.stock([22, None, 2, 0])
        step = {'stepId': 'paid-run:step-1', 'type': 'domain', 'status': 'unknown', 'maxClaims': 1,
            'validationAttempt': False, 'resin': 'original', 'domainName': self.materials['114009']['domainName'],
            'sundaySelectedValue': '3', 'before': before, 'after': after, 'delta': {},
            'startedAt': '2026-10-10T02:06:00Z', 'finishedAt': '2026-10-10T02:10:05Z',
            'parameterEvidence': {'DomainRoundNum': 1, 'SpecifyResinUse': True, 'AutoArtifactSalvage': False,
                'RewardRecognitionEnabled': True, 'DomainName': self.materials['114009']['domainName'],
                'PartyName': raw['policy']['domainPartyName'], 'SundaySelectedValue': '3',
                'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 1, 'OriginalResin40UseCount': 0,
                'CondensedResinUseCount': 0, 'TransientResinUseCount': 0, 'FragileResinUseCount': 0,
                'RequireZhongliShieldCast': True, 'CombatOnly': False, 'ResinPriorityList': ['原粹树脂']},
            'resinBefore': self.resin(130, '2026-10-10T02:06:00Z'),
            'resinAfter': self.resin(111, '2026-10-10T02:10:04Z'), 'actualResinDelta': {'original': 19, 'condensed': 0}}
        raw.update(status='unknown', inventory=after, steps=[step])
        self.old_sources = self.persist('paid-run', raw, auth)
        (self.root / 'logs/runs/paid-run/bettergi.log').write_text('[10:08:00.000] '+ledger.MARKER, encoding='utf-8')
        self.old_sources['log'] = self.a.reference(self.root / 'logs/runs/paid-run/bettergi.log')
        scan = self.base('inventory-probe', 'scan', '2026-10-10T02:20:00Z', '2026-10-10T02:20:10Z')
        scan['inventory'] = self.stack_stock([22, 9, 2, 0], scan['startedAt'])
        self.scan_sources = self.persist('inventory-probe', scan)
        resin = self.base('resin-probe', 'scan', '2026-10-10T02:21:00Z', '2026-10-10T02:21:10Z')
        resin.update(profile=None, plan=None, inventory={}, requiredScanIds=[], status='unknown',
                     resinObservation=self.resin(112, '2026-10-10T02:21:05Z'))
        self.resin_sources = self.persist('resin-probe', resin)
        resin_log = self.root / 'logs/runs/resin-probe/bettergi.log'
        resin_log.write_text('[10:21:05.000] [CULTIVATION_RESIN_OBSERVATION] '+json.dumps(resin['resinObservation']), encoding='utf-8')
        self.resin_sources['log'] = self.a.reference(resin_log)
        snapshot = self.root / 'state/cultivation-authorization-snapshots/paid-parent.json'
        snapshot.write_bytes(self.a.path.read_bytes())
        closed = self.root / 'tests/.artifacts/closed.json'
        self.a.write(closed, {'runId': 'paid-run', 'finishedAt': '2026-10-10T02:12:01Z',
            'gameBGIProcesses': 0, 'settingsMatch': True, 'graphicsRegistryMatchesSnapshot': True})
        fresh = self.root / 'tests/.artifacts/prelaunch.json'
        self.a.write(fresh, {'runId': 'inventory-probe', 'observedAtUTC': '2026-10-10T02:19:59Z', 'gameBGIProcesses': 0})
        runtimes = []
        for rid, at in [('inventory-probe', '2026-10-10T02:20:01Z'), ('resin-probe', '2026-10-10T02:21:01Z')]:
            p = self.root / f'tests/.artifacts/{rid}-runtime.json'
            self.a.write(p, {'runId': rid, 'observedAtUTC': at, 'bettergiPid': 123, 'gamePid': 456,
                            'runtimeIdentity': self.a.receipt['runtimeIdentity']})
            runtimes.append(self.a.reference(p))
        frame = self.root / 'tests/.artifacts/fake-stage.png'; frame.write_bytes(b'fake retained frame')
        frame2 = self.root / 'tests/.artifacts/fake-stage-2.png'; frame2.write_bytes(b'second retained frame')
        self.audit = {'schemaVersion': 1, 'kind': 'paid-domain-inventory-reconciliation', 'scopeId': 'new-day',
            'runId': 'paid-run', 'stepId': 'paid-run:step-1', 'gameDate': '2026-10-10',
            'chargedOriginalReservation': 20, 'releasedOriginalReservation': 0, 'historicalOutcomeRetained': 'unknown',
            'reviewedBy': 'root-agent', 'reviewedAtUTC': '2026-10-10T02:22:00Z',
            'coverageLimit': 'bounded-recordings-and-closed-game-boundaries',
            'reason': 'Independent retained stage frames, original resin/exit and later named stacks support new claims only.',
            'authorizationSnapshot': self.a.reference(snapshot), 'oldSources': self.old_sources,
            'inventoryRunId': 'inventory-probe', 'inventorySources': self.scan_sources,
            'resinRunId': 'resin-probe', 'resinSources': self.resin_sources,
            'probeRuntimeIdentity': self.a.receipt['runtimeIdentity'],
            'ownedBoundaries': {'oldClosed': self.a.reference(closed), 'newPrelaunch': self.a.reference(fresh), 'probeRuntimes': runtimes},
            'videoReviews': [{'runId': rid, 'frames': [self.a.reference(frame), self.a.reference(frame2)]}
                             for rid in ('paid-run', 'inventory-probe', 'resin-probe')]}
        self.path = self.root / 'state/cultivation-paid-reconciliations/paid-run.json'
        self.a.write(self.path, self.audit)

    def resin(self, count, at):
        return {'originalResin': count, 'condensedResin': 0, 'observedAt': at, 'originalVerified': True,
                'condensedVerified': True, 'verified': True, 'mainUiRestored': True}

    def stock(self, values):
        return {k: {'name': self.materials[k]['name'], 'count': n, 'status': 'unknown' if n is None else 'exact'}
                for k, n in zip(self.chain, values)}

    def stack_stock(self, values, start):
        base = int(datetime.fromisoformat(start.replace('Z', '+00:00')).timestamp()*1000)
        rows = {}
        for k, n in zip(self.chain, values):
            row = backpack.evidence(n); row['name'] = self.materials[k]['name']; row['evidence']['materialId'] = k
            row['evidence']['selection']['clickedAt'] = base+1000
            for name, offset in [('first', 1400), ('second', 1600)]:
                row['evidence'][name]['observedAt'] = base+offset
                row['evidence'][name]['nameRows'][0]['text'] = row['name']
            rows[k] = row
        return rows

    def base(self, rid, mode, start, finish):
        raw = reports.CultivationTests().report(mode)
        raw.update(runId=rid, startedAt=start, finishedAt=finish, requiredScanIds=self.chain.copy(),
                   inventory=self.stock([22, 9, 2, 0]), profile=copy.deepcopy(self.profile))
        raw['plan']['requirements'] = {k: 30 for k in self.chain}
        raw['policy'] = {**self.a.config['policy'], 'maxSteps': 1, 'originalResinBudget': 20, 'domainSingleAttemptVerified': True}
        return raw

    def persist(self, rid, raw, authorization=None):
        directory = self.root / 'logs/runs' / rid; directory.mkdir(parents=True, exist_ok=True)
        path = self.bgi / f'User/JsScript/AutoGameCultivation/record/{rid}.json'
        self.a.write(path, raw); self.raw_paths[rid] = path
        event = {'runId': rid, 'mode': raw['mode'], 'status': raw['status'], 'claimedStatus': raw['status'],
                 'evidenceVerified': True, 'readOnly': raw['mode']=='scan', 'reportRelativePath': f'record/{rid}.json'}
        verified = verify_cultivation_report(event, self.bgi, rid, raw['mode'], reports.TARGET, directory)
        self.assertIsNotNone(verified['cultivation'], verified['reason'])
        self.a.write(directory/'cultivation-report.json', verified['report'])
        result = {'runId': rid, 'gameDate': '2026-10-10', 'cultivationTarget': reports.TARGET,
            'cultivation': verified['cultivation'], 'cultivationMode': raw['mode'], 'triggeredAt': raw['startedAt'],
            'launchedAt': raw['startedAt'], 'executionOutcome': 'exited', 'gameStillRunning': False, 'bettergiPid': 123}
        result['finishedAt'] = raw['finishedAt']
        if authorization: result['cultivationAuthorization']=authorization; result['cultivationLaunchAttempted']=True
        self.a.write(directory/'result.json', result)
        video = directory/'genshin-window.mkv'; video.write_bytes(b'fake retained owned recording')
        self.a.write(directory/'recording.json', {'complete': True, 'frameCoveragePassed': True, 'frameCoverage': .9985,
            'file': str(video), 'startedAt': raw['startedAt'], 'stoppedAt': raw['finishedAt']})
        (directory/'bettergi.log').write_text('read-only probe log', encoding='utf-8')
        return {key: self.a.reference(p) for key,p in {'result': directory/'result.json', 'rawReport': path,
            'archiveReport': directory/'cultivation-report.json', 'log': directory/'bettergi.log',
            'video': video, 'recording': directory/'recording.json'}.items()}

    def test_paid_reconciliation_keeps_old_unknown_bytes_and_full_twenty_charge(self):
        originals = {p: p.read_bytes() for p in [self.raw_paths['paid-run'], self.root/'logs/runs/paid-run/result.json', self.a.path]}
        cfg, summary = self.a.guard()
        self.assertEqual(summary['priorReservedOriginal'], 40)
        self.assertEqual(cfg['policy']['originalResinBudget'], 160)
        self.assertTrue(summary['dailyDomainReady'])
        self.assertEqual(summary['unknownRuns'], [])
        self.assertEqual(summary['reconciledPaidUnknownRuns'], ['paid-run'])
        for path, data in originals.items(): self.assertEqual(path.read_bytes(), data)
        self.assertEqual(summary['paidReconciliationReviews'][0]['releasedOriginalReservation'], 0)

    def test_review_cannot_refund_promote_unknown_change_scope_or_reuse_old_run(self):
        for changes in ({'releasedOriginalReservation':20}, {'historicalOutcomeRetained':'success'},
                        {'scopeId':'other'}, {'inventoryRunId':'paid-run'}, {'videoReviews':[]}):
            self.a.write(self.path, {**self.audit, **changes})
            with self.assertRaises(ValueError): self.a.guard()

    def test_changed_sources_or_native_exit_and_bad_closed_boundary_are_rejected(self):
        log = self.root/'logs/runs/paid-run/bettergi.log'; saved=log.read_bytes()
        log.write_bytes(b'no exit')
        with self.assertRaises(ValueError): self.a.guard()
        log.write_bytes(saved)
        bad = copy.deepcopy(self.audit); bad['probeRuntimeIdentity']['engineDll']['sha256']='0'*64
        self.a.write(self.path,bad)
        with self.assertRaises(ValueError): self.a.guard()

    def test_without_independent_review_unknown_stays_charged_and_blocked(self):
        self.path.rename(self.path.with_suffix('.retained'))
        cfg, summary = self.a.guard()
        self.assertEqual(summary['priorReservedOriginal'],40)
        self.assertEqual(cfg['policy']['originalResinBudget'],0)
        self.assertEqual(summary['unknownRuns'],['paid-run'])

    def test_one_readonly_inventory_then_fresh_resin_probe_is_sufficient(self):
        scan = json.loads(self.raw_paths['inventory-probe'].read_text(encoding='utf-8'))
        scan['metadata'] = {'diagnostic': 'inventory-and-resin'}
        scan['resinObservation'] = self.resin(112, '2026-10-10T02:20:05Z')
        sources = self.persist('inventory-probe', scan)
        log = self.root / 'logs/runs/inventory-probe/bettergi.log'
        log.write_text('[CULTIVATION_RESIN_OBSERVATION] '+json.dumps(scan['resinObservation']), encoding='utf-8')
        sources['log'] = self.a.reference(log)
        audit = copy.deepcopy(self.audit)
        audit.update(resinRunId='inventory-probe', inventorySources=sources, resinSources=sources)
        audit['ownedBoundaries']['probeRuntimes'] = audit['ownedBoundaries']['probeRuntimes'][:1]
        audit['videoReviews'] = audit['videoReviews'][:2]
        self.a.write(self.path, audit)
        cfg, summary = self.a.guard()
        self.assertEqual(cfg['policy']['originalResinBudget'],160)
        self.assertEqual(summary['priorReservedOriginal'],40)

    def test_natural_recovery_does_not_allow_an_extra_claim_or_supplement(self):
        path = self.raw_paths['resin-probe']; original = json.loads(path.read_text(encoding='utf-8'))
        for count in (92, 140):
            changed = copy.deepcopy(original); changed['resinObservation']['originalResin'] = count
            sources = self.persist('resin-probe', changed)
            log = self.root / 'logs/runs/resin-probe/bettergi.log'
            log.write_text('[CULTIVATION_RESIN_OBSERVATION] '+json.dumps(changed['resinObservation']), encoding='utf-8')
            sources['log'] = self.a.reference(log)
            audit = {**self.audit, 'resinSources': sources}
            self.a.write(self.path, audit)
            with self.assertRaisesRegex(ValueError, 'another expense or supplement'): self.a.guard()

    def test_named_iron_below_before_or_known_after_change_never_unlocks(self):
        original = json.loads(self.raw_paths['inventory-probe'].read_text(encoding='utf-8'))
        for values in ([22, 6, 2, 0], [23, 9, 2, 0]):
            changed = copy.deepcopy(original); changed['inventory'] = self.stack_stock(values, changed['startedAt'])
            sources = self.persist('inventory-probe', changed)
            self.a.write(self.path, {**self.audit, 'inventorySources': sources})
            with self.assertRaisesRegex(ValueError, 'known-after continuity'): self.a.guard()

    def test_missing_frame_reviews_and_forged_ownership_do_not_replace_evidence(self):
        audit = copy.deepcopy(self.audit)
        audit['videoReviews'][0]['frames'] = audit['videoReviews'][0]['frames'][:1]
        self.a.write(self.path,audit)
        with self.assertRaises(ValueError): self.a.guard()
        self.a.write(self.path,self.audit)
        ref = self.audit['ownedBoundaries']['probeRuntimes'][0]
        path = self.root / ref['path']; row = json.loads(path.read_text(encoding='utf-8')); row['bettergiPid'] = 999
        self.a.write(path,row)
        audit = copy.deepcopy(self.audit); audit['ownedBoundaries']['probeRuntimes'][0] = self.a.reference(path)
        self.a.write(self.path,audit)
        with self.assertRaisesRegex(ValueError,'actual probe ownership'): self.a.guard()

    def test_microsecond_prelaunch_with_whole_second_trigger_stays_before_launch(self):
        self.assertTrue(_prelaunch_before_trigger('2026-10-10T02:49:41.0912935Z',
            '2026-10-10T02:49:41+00:00', '2026-10-10T02:49:42+00:00'))
        for observed, triggered, launched in (
            ('2026-10-10T02:49:42Z', '2026-10-10T02:49:41Z', '2026-10-10T02:49:43Z'),
            ('2026-10-10T02:49:41.0912935Z', '2026-10-10T02:49:41.050000Z', '2026-10-10T02:49:42Z'),
            ('2026-10-10T02:49:41.0912935Z', '2026-10-10T02:49:41Z', '2026-10-10T02:49:41Z')):
            self.assertFalse(_prelaunch_before_trigger(observed,triggered,launched))

    def test_reconciliation_accepts_only_declared_trigger_precision_without_editing_evidence(self):
        result_path = self.root/'logs/runs/inventory-probe/result.json'
        result = json.loads(result_path.read_text(encoding='utf-8')); result['triggeredAt']='2026-10-10T02:19:59Z'
        self.a.write(result_path,result)
        fresh_path = self.root / self.audit['ownedBoundaries']['newPrelaunch']['path']
        fresh = json.loads(fresh_path.read_text(encoding='utf-8')); fresh['observedAtUTC']='2026-10-10T02:19:59.0912935Z'
        self.a.write(fresh_path,fresh)
        audit=copy.deepcopy(self.audit)
        audit['inventorySources']['result']=self.a.reference(result_path)
        audit['ownedBoundaries']['newPrelaunch']=self.a.reference(fresh_path)
        self.a.write(self.path,audit)
        before=fresh_path.read_bytes()
        cfg,summary=self.a.guard()
        self.assertEqual(cfg['policy']['originalResinBudget'],160)
        self.assertEqual(fresh_path.read_bytes(),before)
