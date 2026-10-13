import copy
from datetime import datetime, timezone
import unittest

from scripts.route_selection import MATERIAL_IDS, game_date_at, preview_route_selection


def stock(a=0, b=0, c=0):
    return {key: {'status': 'exact', 'count': n} for key, n in zip(MATERIAL_IDS, (a, b, c))}


def demand(a=0, b=0, c=0):
    return dict(zip(MATERIAL_IDS, (a, b, c)))


NOW = datetime(2026, 10, 11, 0, tzinfo=timezone.utc)


def candidate(name, gains=(0, 0, 0), *, seconds=60, x=0, actual=False):
    row = {'candidateId': name, 'sha256': 'a' * 64, 'catalogCommit': 'b' * 40,
           'status': 'unattempted', 'eligibilityVerified': True,
           'availableGameDate': game_date_at(NOW), 'fightPoints': [{'x': x, 'y': 0}],
           'estimatedDurationSeconds': seconds, 'reliability': {'successfulRuns': 3, 'attemptedRuns': 4}}
    evidence = {'candidateId': name, 'sha256': row['sha256'], 'catalogCommit': row['catalogCommit'],
                'verified': True, 'recordedAtUTC': '2026-10-10T00:00:00Z'}
    if actual:
        evidence.update(source='actual_net_inventory', outcome='completed', before=stock(10, 10, 10),
                        after=stock(*(10 + n for n in gains)))
    else:
        evidence.update(source='explicit_material_count_estimate', basisType='material_count',
                        basis='explicit three-tier material forecast, independent of enemy annotations',
                        materialCounts=demand(*gains))
    row['yieldEvidence'] = evidence
    return row


class RouteSelectionTests(unittest.TestCase):
    def preview(self, inventory, requirements, candidates, **kwargs):
        return preview_route_selection(inventory, requirements, candidates, now=NOW, **kwargs)

    def test_useful_total_precedes_speed_and_keeps_inputs_unchanged(self):
        inventory, requirements = stock(), demand(100)
        candidates = [candidate('fast-small', (10, 0, 0), seconds=20, x=1000),
                      candidate('slow-large', (30, 0, 0), seconds=300, x=2000)]
        original = copy.deepcopy((inventory, requirements, candidates))
        result = self.preview(inventory, requirements, candidates)
        self.assertEqual([r['candidateId'] for r in result['ranked']], ['slow-large', 'fast-small'])
        self.assertEqual([r['usefulMaterialEquivalent'] for r in result['ranked']], [30, 10])
        self.assertEqual((inventory, requirements, candidates), original)
        self.assertTrue(result['previewOnly'])
        self.assertFalse(result['executionAuthorized'])
        self.assertFalse(result['inventoryChanged'])
        self.assertFalse(result['ledgerChanged'])

    def test_speed_then_observed_reliability_only_break_equal_useful_totals(self):
        rows = [candidate('slow-reliable', (10, 0, 0), seconds=200, x=1000),
                candidate('fast-unreliable', (10, 0, 0), seconds=20, x=2000),
                candidate('fast-reliable', (10, 0, 0), seconds=20, x=3000)]
        rows[0]['reliability'] = rows[2]['reliability'] = {'successfulRuns': 4, 'attemptedRuns': 4}
        result = self.preview(stock(), demand(100), rows)
        self.assertEqual([r['candidateId'] for r in result['ranked']],
                         ['fast-reliable', 'fast-unreliable', 'slow-reliable'])

    def test_unrelated_high_tier_surplus_cannot_satisfy_low_tier(self):
        rows = [candidate('high-surplus', (0, 0, 100)), candidate('useful-low', (5, 0, 0), x=1000)]
        result = self.preview(stock(0, 0, 10), demand(5), rows)
        self.assertEqual([r['candidateId'] for r in result['ranked']], ['useful-low'])
        self.assertEqual(result['ranked'][0]['usefulMaterialEquivalent'], 5)
        self.assertIn('no shortage-limited', result['excluded'][0]['reason'])

    def test_gains_beyond_required_materials_do_not_inflate_score(self):
        result = self.preview(stock(), demand(1, 1, 1), [candidate('huge', (100, 100, 100))])
        self.assertEqual(result['ranked'][0]['usefulMaterialEquivalent'], 13)
        self.assertEqual(result['ranked'][0]['hypotheticalAllocation']['remainingMaterialEquivalent'], 0)

    def test_direct_low_tier_demand_is_reserved_before_mid_promotion(self):
        result = self.preview(stock(5), demand(3, 1), [candidate('last-low', (1, 0, 0))])
        current = result['currentAllocation']
        self.assertEqual(current['actualShortages'], demand(0, 1))
        self.assertEqual(current['shortagesAfterLegalPromotions'], demand(0, 1))
        self.assertEqual(current['suggestedPromotions'], [])
        self.assertEqual(current['remainingMaterialEquivalent'], 1)
        row = result['ranked'][0]
        self.assertEqual(row['usefulMaterialEquivalent'], 1)
        self.assertEqual(row['hypotheticalAllocation']['suggestedPromotions'],
                         [{'from': MATERIAL_IDS[0], 'to': MATERIAL_IDS[1], 'count': 1}])

    def test_direct_mid_tier_demand_is_reserved_before_high_promotion(self):
        result = self.preview(stock(0, 3), demand(0, 1, 1), [candidate('mid', (0, 1, 0))])
        self.assertEqual(result['currentAllocation']['suggestedPromotions'], [])
        self.assertEqual(result['currentAllocation']['remainingMaterialEquivalent'], 3)
        row = result['ranked'][0]
        self.assertEqual(row['usefulMaterialEquivalent'], 3)
        self.assertEqual(row['hypotheticalAllocation']['suggestedPromotions'],
                         [{'from': MATERIAL_IDS[1], 'to': MATERIAL_IDS[2], 'count': 1}])

    def test_partial_inputs_count_only_the_new_progress_without_fractional_output(self):
        result = self.preview(stock(8), demand(0, 0, 1), [candidate('one-low', (1, 0, 0))])
        self.assertEqual(result['currentAllocation']['shortagesAfterLegalPromotions'], demand(0, 0, 1))
        self.assertEqual(result['currentAllocation']['remainingMaterialEquivalent'], 1)
        row = result['ranked'][0]
        self.assertEqual(row['usefulMaterialEquivalent'], 1)
        self.assertEqual(row['hypotheticalAllocation']['suggestedPromotions'],
                         [{'from': MATERIAL_IDS[0], 'to': MATERIAL_IDS[1], 'count': 3},
                          {'from': MATERIAL_IDS[1], 'to': MATERIAL_IDS[2], 'count': 1}])

    def test_unknown_missing_lower_bound_or_malformed_stock_makes_preview_unrankable(self):
        mutations = [lambda s: s.pop(MATERIAL_IDS[1]),
                     lambda s: s[MATERIAL_IDS[1]].update(status='unknown', count=None),
                     lambda s: s[MATERIAL_IDS[1]].update(status='lower_bound', count=99),
                     lambda s: s[MATERIAL_IDS[1]].update(count=True),
                     lambda s: s[MATERIAL_IDS[1]].update(count=-1)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                inventory = stock()
                mutate(inventory)
                result = self.preview(inventory, demand(99), [candidate('good', (10, 0, 0))])
                self.assertFalse(result['rankable'])
                self.assertEqual(result['ranked'], [])

    def test_unpinned_unverified_filename_enemy_and_fight_counts_are_unrankable(self):
        rows = [candidate(str(n), (99, 0, 0), x=n * 1000) for n in range(6)]
        rows[0].pop('sha256')
        rows[1]['yieldEvidence']['verified'] = False
        rows[2]['yieldEvidence']['source'] = 'filename_count'
        rows[3]['yieldEvidence']['basisType'] = 'enemy_count'
        rows[4]['yieldEvidence']['basisType'] = 'fight_action_count'
        rows[5]['yieldEvidence']['materialCounts'] = {'enemyCount': 99}
        result = self.preview(stock(), demand(100), rows)
        self.assertFalse(result['rankable'])
        self.assertEqual(len(result['excluded']), 6)

    def test_duplicate_identity_does_not_choose_an_arbitrary_first_pin(self):
        first = candidate('duplicated', (10, 0, 0))
        second = candidate('duplicated', (99, 0, 0), x=1000)
        second['sha256'] = second['yieldEvidence']['sha256'] = 'c' * 64
        result = self.preview(stock(), demand(100), [first, second])
        self.assertFalse(result['rankable'])
        self.assertEqual(len(result['excluded']), 2)
        self.assertTrue(all('duplicate' in r['reason'] for r in result['excluded']))

    def test_complete_existing_materials_and_zero_yield_do_not_select_any_farming(self):
        result = self.preview(stock(9), demand(0, 0, 1), [candidate('unneeded', (100, 0, 0))])
        self.assertFalse(result['rankable'])
        self.assertEqual(result['currentAllocation']['remainingMaterialEquivalent'], 0)
        self.assertFalse(self.preview(stock(), demand(100), [candidate('zero')])['rankable'])

    def test_actual_delta_is_recomputed_and_remains_a_future_hypothesis(self):
        row = candidate('measured', (4, 1, 0), actual=True)
        row['yieldEvidence']['materialCounts'] = demand(99999, 99999, 99999)
        result = self.preview(stock(), demand(100), [row])
        self.assertEqual(result['ranked'][0]['yieldMaterialCounts'], demand(4, 1, 0))
        self.assertEqual(result['ranked'][0]['usefulMaterialEquivalent'], 4)
        self.assertEqual(result['ranked'][0]['yieldEvidenceSource'], 'actual_net_inventory')
        self.assertTrue(result['futureYieldIsHypothetical'])

    def test_actual_negative_unknown_or_foreign_evidence_is_excluded(self):
        rows = [candidate(str(n), (4, 0, 0), actual=True, x=1000 * n) for n in range(4)]
        rows[0]['yieldEvidence']['after'][MATERIAL_IDS[0]]['count'] = 9
        rows[1]['yieldEvidence']['outcome'] = 'unknown'
        rows[2]['yieldEvidence']['sha256'] = 'c' * 64
        rows[3]['yieldEvidence']['recordedAtUTC'] = '2026-10-12T00:00:00Z'
        result = self.preview(stock(), demand(99), rows)
        self.assertFalse(result['rankable'])
        self.assertEqual(len(result['excluded']), 4)

    def test_cleared_or_unknown_physical_points_exclude_changed_author_and_hash(self):
        rows = [candidate('new-author-new-file', (50, 0, 0), x=79),
                candidate('independent', (10, 0, 0), x=1000)]
        records = [{'candidateId': 'old-author-old-file', 'gameDate': game_date_at(NOW),
                    'status': 'completed', 'fightPoints': [{'x': 0, 'y': 0}]}]
        result = self.preview(stock(), demand(99), rows, day_records=records)
        self.assertEqual([r['candidateId'] for r in result['ranked']], ['independent'])
        self.assertIn('overlaps', result['excluded'][0]['reason'])
        records[0]['gameDate'] = '2026-10-10'
        records[0]['status'] = 'unknown'
        result = self.preview(stock(), demand(99), rows, day_records=records)
        self.assertEqual([r['candidateId'] for r in result['ranked']], ['independent'])

    def test_all_attempted_statuses_exclude_current_day_even_after_point_change(self):
        for status in ('started', 'completed', 'partial', 'failed', 'unknown', 'cancelled', 'timeout'):
            with self.subTest(status=status):
                row = candidate('same', (20, 0, 0), x=2000)
                records = [{'candidateId': 'same', 'gameDate': game_date_at(NOW),
                            'status': status, 'fightPoints': [{'x': 0, 'y': 0}]}]
                self.assertFalse(self.preview(stock(), demand(99), [row], day_records=records)['rankable'])
                row['status'] = status
                self.assertFalse(self.preview(stock(), demand(99), [row])['rankable'])

    def test_overlapping_alternatives_keep_the_highest_useful_total(self):
        rows = [candidate('small-fast', (10, 0, 0), seconds=10, x=50),
                candidate('large-slow', (30, 0, 0), seconds=500, x=0)]
        result = self.preview(stock(), demand(99), rows)
        self.assertEqual([r['candidateId'] for r in result['ranked']], ['large-slow'])
        self.assertIn('higher-ranked', result['excluded'][0]['reason'])

    def test_four_am_game_day_and_verified_new_day_eligibility_are_independent(self):
        before = datetime(2026, 10, 10, 19, 59, 59, tzinfo=timezone.utc)
        after = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(game_date_at(before), '2026-10-10')
        self.assertEqual(game_date_at(after), '2026-10-11')
        row = candidate('new-day', (10, 0, 0))
        self.assertFalse(preview_route_selection(stock(), demand(99), [row], now=before)['rankable'])
        self.assertTrue(preview_route_selection(stock(), demand(99), [row], now=after)['rankable'])
        row['eligibilityVerified'] = False
        self.assertFalse(preview_route_selection(stock(), demand(99), [row], now=after)['rankable'])

    def test_previous_completed_day_is_not_cleared_today_but_needs_separate_eligibility(self):
        row = candidate('today', (10, 0, 0))
        records = [{'candidateId': 'today', 'gameDate': '2026-10-10', 'status': 'completed',
                    'fightPoints': [{'x': 0, 'y': 0}]}]
        self.assertTrue(self.preview(stock(), demand(99), [row], day_records=records)['rankable'])
        row['eligibilityVerified'] = False
        self.assertFalse(self.preview(stock(), demand(99), [row], day_records=records)['rankable'])

    def test_missing_speed_or_reliability_remains_unknown_without_assuming_zero(self):
        row = candidate('unknown-time', (10, 0, 0))
        row.pop('estimatedDurationSeconds')
        row.pop('reliability')
        result = self.preview(stock(), demand(99), [row])
        self.assertTrue(result['rankable'])
        self.assertIsNone(result['ranked'][0]['estimatedDurationSeconds'])
        self.assertIsNone(result['ranked'][0]['reliability'])

    def test_naive_clock_invalid_day_records_and_excessive_candidates_fail_closed(self):
        with self.assertRaises(ValueError):
            preview_route_selection(stock(), demand(), [], now=datetime(2026, 10, 11))
        with self.assertRaises(ValueError):
            self.preview(stock(), demand(99), [candidate('x', (1, 0, 0))] * 101)
        with self.assertRaises(ValueError):
            self.preview(stock(), demand(99), [], day_records=[{'status': 'not-a-recognized-state'}])


if __name__ == '__main__':
    unittest.main()
