"""Pure post-run yield analysis. No game, inventory changes, or workflow outcome edits."""
from copy import deepcopy
from pathlib import Path
import unittest
from uuid import uuid4

from scripts.artifact_target_yield import build_target_yield


class TargetYieldTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent / '.artifacts' / ('artifact-yield-' + uuid4().hex[:10])
        root.mkdir(parents=True)
        self.table = root / 'item.csv'
        names = ['饮尽你的血泪', '铭记你的功勋', '缅怀你的信仰', '感谢你的奉献', '授予你的年华']
        rows = ['item_class_id,item_name,quality_level']
        rows += [f'relic:15047_{index},{name},{quality}' for index, name in enumerate(names, 1) for quality in (4,5)]
        rows += ['relic:15048_1,熔铸者的雅量,5', 'currency:mora,摩拉,0']
        self.table.write_text('\n'.join(rows), encoding='utf-8')
        self.report = {'runId': 'yield-run', 'mode': 'artifact-farming', 'gameDate': '2026-10-11',
            'targetReached': False, 'target': {'artifactSet': '血红之证'}, 'policy': {'scopeId': 'same-scope'},
            'steps': [{'stepId': 'yield-run:step-1', 'type': 'claim', 'status': 'success',
                'rewards': {'饮尽你的血泪': 2, '熔铸者的雅量': 1, '摩拉': 10000}}]}
        self.result = {'runId': 'yield-run', 'gameDate': '2026-10-11', 'outcome': 'completed',
            'artifactFarming': {'reportVerified': True, 'claims': 1, 'rewards': deepcopy(self.report['steps'][0]['rewards'])}}

    def build(self):
        return build_target_yield(self.result, self.report, self.table, artifact_set='血红之证', class_prefix='relic:15047_')

    def test_target_piece_names_count_with_unknown_actual_quality_and_main_stats(self):
        before = deepcopy((self.result, self.report))
        result = self.build()
        self.assertEqual(result['targetSetPieceDrops'], 2)
        self.assertEqual(result['otherArtifactDrops'], 1)
        self.assertFalse(result['qualityObserved'])
        self.assertIsNone(result['fiveStarDrops'])
        self.assertIsNone(result['mainStatsMatched'])
        self.assertFalse(result['targetReached'])
        self.assertEqual((self.result, self.report), before)

    def test_shared_set_only_means_zero_target_progress_without_downgrading_domain_success(self):
        self.report['steps'][0]['rewards'] = {'熔铸者的雅量': 2}
        self.result['artifactFarming']['rewards'] = deepcopy(self.report['steps'][0]['rewards'])
        result = self.build()
        self.assertEqual(result['targetSetPieceDrops'], 0)
        self.assertEqual(result['targetSetYieldStatus'], 'no-target-piece-observed')
        self.assertEqual(result['originalOutcome'], 'completed')
        self.assertFalse(result['changesRunOutcome'])

    def test_unknown_claim_unverified_summary_wrong_scope_or_count_cannot_gain_target_progress(self):
        self.report['steps'][0]['status'] = 'unknown'
        with self.assertRaises(ValueError): self.build()
        self.report['steps'][0]['status'] = 'success'
        self.result['artifactFarming']['reportVerified'] = False
        with self.assertRaises(ValueError): self.build()
        self.result['artifactFarming']['reportVerified'] = True
        self.report['runId'] = 'other-run'
        with self.assertRaises(ValueError): self.build()

    def test_partial_parent_counts_only_already_verified_successful_claims(self):
        self.result['outcome'] = 'unknown'
        self.report['steps'].append({'stepId': 'yield-run:step-2', 'type': 'claim', 'status': 'unknown',
            'rewards': {'饮尽你的血泪': 9}})
        result = self.build()
        self.assertEqual(result['targetSetPieceDrops'], 2)
        self.assertEqual(result['verifiedClaimStepIds'], ['yield-run:step-1'])
        self.assertEqual(result['originalOutcome'], 'unknown')


if __name__ == '__main__':
    unittest.main()
