import copy
import unittest
from scripts.backpack_inventory_evidence import verify_backpack_inventory
from tests import test_cultivation as cultivation_fixtures

NAME = '狮牙斗士的铁链'
START = '2026-10-10T02:00:00Z'
FINISH = '2026-10-10T02:00:10Z'
BASE = 1791597600000


def evidence(count=9):
    item = {'x': 110, 'y': 300, 'width': 125, 'height': 150}
    def frame(at):
        return {'observedAt': BASE + at, 'selectedItemVerified': True, 'selectedItemRect': item.copy(),
            'nameRegion': {'x': 1300, 'y': 90, 'width': 500, 'height': 80},
            'nameRows': [{'text': NAME, 'x': 1320, 'y': 110, 'width': 300, 'height': 30}],
            'countRegion': {'x': 110, 'y': 415, 'width': 125, 'height': 35},
            'countRows': [{'text': str(count), 'x': 160, 'y': 420, 'width': 30, 'height': 25}],
            'countMethod': 'raw_ocr_without_detector', 'rawCountText': str(count)}
    return {'name': NAME, 'count': count, 'status': 'exact', 'verified': True,
        'source': 'backpack_selected_stack', 'evidence': {'materialId': '114010',
            'selection': {'itemRect': item.copy(), 'x': 172, 'y': 365, 'clickedAt': BASE + 1000},
            'first': frame(1400), 'second': frame(1600)}}


class BackpackEvidenceTests(unittest.TestCase):
    def verify(self, row):
        return verify_backpack_inventory({'114010': row}, materials={'114010': {'name': NAME}},
                                        started_at=START, finished_at=FINISH)

    def test_named_dual_stack_frames_support_zero_and_positive_stock(self):
        for count in (0, 9, 12):
            self.verify(evidence(count))

    def test_forged_qty_and_ambiguous_title_or_craftable_count_rejected(self):
        for field, value in (('nameRows', []), ('rawCountText', '1'), ('countMethod', 'structural_digit_repair'),
                             ('countRows', [{'text': '可合成数量9', 'x': 160, 'y': 420, 'width': 30, 'height': 25}])):
            row = evidence(); row['evidence']['first'][field] = value
            with self.assertRaises(ValueError): self.verify(row)
        row = evidence(); row['count'] = 999
        with self.assertRaises(ValueError): self.verify(row)

    def test_wrong_name_ambiguous_name_and_unstable_second_count_rejected(self):
        for mutate in (lambda p: p['first']['nameRows'][0].update(text=NAME+'碎片'),
                       lambda p: p['first']['nameRows'].append(p['first']['nameRows'][0].copy()),
                       lambda p: p['second']['countRows'][0].update(text='10')):
            row = evidence(); mutate(row['evidence'])
            with self.assertRaises(ValueError): self.verify(row)

    def test_outside_click_unselected_stack_and_count_outside_item_rejected(self):
        for mutate in (lambda p: p['selection'].update(x=1000),
                       lambda p: p['first'].update(selectedItemVerified=False),
                       lambda p: p['second']['selectedItemRect'].update(x=400),
                       lambda p: p['first']['countRegion'].update(x=400),
                       lambda p: p['first']['nameRows'][0].update(x=0)):
            row = evidence(); mutate(row['evidence'])
            with self.assertRaises(ValueError): self.verify(row)

    def test_stale_simultaneous_outside_run_and_boolean_timestamps_rejected(self):
        for mutate in (lambda p: p['selection'].update(clickedAt=BASE-1),
                       lambda p: p['first'].update(observedAt=True),
                       lambda p: p['second'].update(observedAt=p['first']['observedAt']),
                       lambda p: p['second'].update(observedAt=BASE+11000)):
            row = evidence(); mutate(row['evidence'])
            with self.assertRaises(ValueError): self.verify(row)

    def test_cultivation_report_rechecks_raw_selected_stack_and_rejects_fabricated_stock(self):
        helper = cultivation_fixtures.CultivationTests(); helper.setUp()
        report = helper.report('scan')
        report.update(startedAt=START, finishedAt=FINISH)
        report['requiredScanIds'].append('114010')
        report['inventory']['114010'] = evidence()
        verified = helper.verify(report)
        self.assertEqual(verified['status'], 'success', verified['reason'])
        report['inventory']['114010']['evidence']['second']['selectedItemVerified'] = False
        self.assertNotEqual(helper.verify(report)['status'], 'success')
