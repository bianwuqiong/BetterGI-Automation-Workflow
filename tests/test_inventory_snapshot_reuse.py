"""Same-run observed stock snapshots are checked independently of operator intent."""
import copy
from datetime import datetime, timedelta
import unittest
from tests import test_cultivation as fixtures


class InventorySnapshotReuseTests(unittest.TestCase):
    def setUp(self):
        self.helper=fixtures.CultivationTests();self.helper.setUp()
        self.raw=self.helper.execution_report()
        self.raw.update(startedAt='2026-10-08T00:59:00Z',finishedAt='2026-10-08T01:02:10Z')
        self.raw['policy'].update(dailyMode=True,dailyDomainReady=True,validationMode=False,
            validationScopeId='test-daily',requireZhongliShieldCast=True,domainValidated=False)
        step=self.raw['steps'][0]
        step['parameterEvidence']={'DomainRoundNum':1,'SpecifyResinUse':True,'AutoArtifactSalvage':False,
            'RewardRecognitionEnabled':True,'DomainName':step['domainName'],'PartyName':fixtures.POLICY['domainPartyName'],
            'SundaySelectedValue':'1','OriginalResinUseCount':0,'OriginalResin20UseCount':1,'OriginalResin40UseCount':0,
            'CondensedResinUseCount':0,'TransientResinUseCount':0,'FragileResinUseCount':0,
            'RequireZhongliShieldCast':True,'CombatOnly':False,'ResinPriorityList':['原粹树脂']}
        self.raw['initialInventoryRead']={'runId':'test-run','startedAt':'2026-10-08T00:59:10Z',
            'finishedAt':'2026-10-08T00:59:50Z','inventory':copy.deepcopy(step['before'])}
        step['beforeInventoryRead']={'source':'initial-current-run','runId':'test-run',
            'readStartedAt':'2026-10-08T00:59:10Z','readFinishedAt':'2026-10-08T00:59:50Z','usedAt':step['startedAt']}
        step['afterInventoryRead']={'runId':'test-run','startedAt':'2026-10-08T01:00:10Z','finishedAt':'2026-10-08T01:00:50Z'}

    def verify(self,raw=None):
        return self.helper.verify(raw or self.raw,mode='execute')

    def second_step(self):
        first=self.raw['steps'][0];second=copy.deepcopy(first)
        second.update(stepId='test-run:step-2',startedAt='2026-10-08T01:01:05Z',finishedAt='2026-10-08T01:02:05Z',
            before=copy.deepcopy(first['after']),after=copy.deepcopy(first['after']))
        second['after']['104320']['count']+=2
        second['resinBefore'].update(originalResin=80,observedAt=second['startedAt'])
        second['resinAfter'].update(originalResin=60,observedAt=second['finishedAt'])
        second['beforeInventoryRead']={'source':'previous-step-after','runId':'test-run','previousStepId':first['stepId'],
            'readStartedAt':first['afterInventoryRead']['startedAt'],'readFinishedAt':first['afterInventoryRead']['finishedAt'],
            'usedAt':second['startedAt']}
        second['afterInventoryRead']={'runId':'test-run','startedAt':'2026-10-08T01:01:20Z','finishedAt':'2026-10-08T01:01:50Z'}
        self.raw['steps'].append(second);self.raw['inventory']=copy.deepcopy(second['after'])
        return second

    def test_initial_and_adjacent_actual_after_support_two_verified_single20_claims(self):
        self.second_step();result=self.verify()
        self.assertEqual(result['status'],'success',result['reason'])
        self.assertEqual(result['cultivation']['configuredConfirmedClaims']['original'],40)
        self.assertEqual(result['cultivation']['observedGains'],{'104320':4})

    def test_cross_run_oldest_over120_or_raw_source_changed_cannot_reuse(self):
        for mutate in (lambda r:r['initialInventoryRead'].update(runId='other-run'),
            lambda r:r['initialInventoryRead'].update(startedAt='2026-10-08T00:57:00Z'),
            lambda r:r['steps'][0]['beforeInventoryRead'].update(readStartedAt='2026-10-08T00:57:00Z'),
            lambda r:r['initialInventoryRead']['inventory']['104320'].update(count=999),
            lambda r:r['initialInventoryRead']['inventory']['104320'].update(source='reward-drops')):
            raw=copy.deepcopy(self.raw);mutate(raw)
            self.assertIsNone(self.verify(raw)['report'])
        raw=copy.deepcopy(self.raw);raw['startedAt']='2026-10-08T00:57:00Z'
        raw['initialInventoryRead']['startedAt']=raw['steps'][0]['beforeInventoryRead']['readStartedAt']='2026-10-08T00:57:00Z'
        self.assertIn('exceeds120',self.verify(raw)['reason'])

    def test_previous_requires_adjacent_success_matching_full_actual_chain(self):
        self.second_step()
        for mutate in (lambda r:r['steps'][1]['beforeInventoryRead'].update(previousStepId='other-run:step-1'),
            lambda r:r['steps'][0].update(status='unknown'),
            lambda r:r['steps'][0]['after'].pop('104321'),
            lambda r:r['steps'][1]['before']['104320'].update(count=999)):
            raw=copy.deepcopy(self.raw);mutate(raw)
            self.assertIsNone(self.verify(raw)['report'])

    def test_mutator_flags_ordinary_policy_and_invalid_used_at_are_rejected(self):
        for mutate in (lambda r:r['policy'].update(allowCrafting=True),lambda r:r['policy'].update(allowBoss=True),
            lambda r:r['policy'].update(dailyMode=False,dailyDomainReady=False,validationScopeId=''),
            lambda r:r['steps'][0]['beforeInventoryRead'].update(usedAt='2026-10-08T01:00:00.001Z'),
            lambda r:r['steps'][0]['afterInventoryRead'].update(finishedAt='2026-10-08T01:02:00Z')):
            raw=copy.deepcopy(self.raw);mutate(raw)
            self.assertIsNone(self.verify(raw)['report'])

    def test_fresh_fallback_preserves_existing_full_scan_even_if_more_than120seconds(self):
        self.raw['startedAt']='2026-10-08T00:55:00Z'
        self.raw['initialInventoryRead'].update(startedAt='2026-10-08T00:55:00Z',finishedAt='2026-10-08T00:56:00Z')
        self.raw['steps'][0]['beforeInventoryRead'].update(source='fresh-current-run',
            readStartedAt='2026-10-08T00:57:00Z',readFinishedAt='2026-10-08T00:59:50Z')
        result=self.verify();self.assertEqual(result['status'],'success',result['reason'])

    def test_metadata_cannot_hide_old_raw_frame_under_new_read_start(self):
        self.raw['initialInventoryRead']['inventory']['104320']['evidence']={'observedAt':1791411540000}
        self.assertIn('declared read window',self.verify()['reason'])

    def test_metadata_is_not_ignored_when_missing_a_declared_read(self):
        self.raw['steps'][0].pop('beforeInventoryRead')
        self.assertIsNone(self.verify()['report'])

    def shift_read_times(self, seconds):
        def shift(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ('startedAt', 'finishedAt', 'readStartedAt', 'readFinishedAt', 'usedAt', 'observedAt') and isinstance(item, str):
                        value[key] = (datetime.fromisoformat(item.replace('Z', '+00:00')) + timedelta(seconds=seconds)).isoformat()
                    else:
                        shift(item)
            elif isinstance(value, list):
                for item in value:
                    shift(item)
        shift(self.raw)

    def test_fresh_or_reused_before_cannot_cross_four_am_even_under120seconds(self):
        # Move the 00:59:10Z scan to 19:59:10Z and its use to 20:00:00Z.
        self.shift_read_times(19 * 3600)
        for source in ('initial-current-run', 'fresh-current-run'):
            raw = copy.deepcopy(self.raw)
            raw['steps'][0]['beforeInventoryRead']['source'] = source
            result = self.verify(raw)
            self.assertIsNone(result['report'])
            self.assertIn('game-day boundary', result['reason'])

    def test_previous_after_cannot_authorize_new_day_claim(self):
        self.second_step()
        # First claim starts at 03:58:55 UTC+8; the second starts at 04:00.
        self.shift_read_times(19 * 3600 - 65)
        result = self.verify()
        self.assertIsNone(result['report'])
        self.assertIn('game-day boundary', result['reason'])

    def test_before_within_day_remains_valid_when_after_finishes_past_reset(self):
        # A fresh post-claim observation may finish after reset; it never
        # authorizes a subsequent claim and does not erase the actual receipt.
        self.shift_read_times(19 * 3600 - 20)
        result = self.verify()
        self.assertEqual(result['status'], 'success', result['reason'])
