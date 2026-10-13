"""Synthetic selected-stack and Mora crops; no game, inventory writes, or upgrade claims."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest

from scripts.resource_coverage import EXPERIENCE, mora_count, verify_resource_coverage

START, FINISH = '2026-10-11T16:00:00Z', '2026-10-11T16:00:05Z'
BASE = int(datetime(2026, 10, 11, 16, tzinfo=timezone.utc).timestamp()*1000)


def rect(x, y, width, height):
    return {'x': x, 'y': y, 'width': width, 'height': height}


def coverage_fixture():
    def mora_frame(at):
        return {'observedAt': BASE+at, 'width': 1920, 'height': 1080, 'backpackTabVerified': True, 'promptVisible': False,
            'headerRows': [{'text': '贵重道具', **rect(120,25,170,35)}], 'iconName': '摩拉', 'iconScore': .91,
            'iconRegion': rect(354,1000,37,37), 'balanceRegion': rect(397,1000,140,40),
            'balanceRows': [{'text': '125000', **rect(410,1008,95,25)}], 'rawBalanceText': '125000'}
    mora = {'source': 'precious_items_bottom_mora', 'materialId': '202', 'materialName': '摩拉', 'readOnly': True,
        'status': 'verified', 'balance': 125000, 'verified': True, 'observedAt': '2026-10-11T16:00:00.700Z',
        'mainUiRestored': True, 'cleanupCompleted': True, 'first': mora_frame(400), 'second': mora_frame(700)}
    observations, inventory = {}, {'202': {'name': '摩拉', 'count': 125000, 'status': 'exact', 'verified': True,
        'source': 'precious_items_bottom_mora', 'evidence': deepcopy(mora)}}
    for index, (identifier, name) in enumerate(EXPERIENCE.items()):
        selection = {'itemRect': rect(110,300,125,150), 'x': 172, 'y': 365, 'clickedAt': BASE+2000+index*500}
        def frame(at):
            return {'observedAt': at, 'nameRegion': rect(1300,90,500,80), 'selectedItemVerified': True,
                'selectedItemRect': deepcopy(selection['itemRect']), 'countMethod': 'raw_ocr_without_detector',
                'rawCountText': '12', 'nameRows': [{'text': name, **rect(1320,110,300,30)}],
                'countRegion': rect(110,415,125,35), 'countRows': [{'text': '12', **rect(160,420,30,25)}]}
        pair = {'selection': selection, 'first': frame(selection['clickedAt']+200), 'second': frame(selection['clickedAt']+400)}
        observations[identifier] = deepcopy(pair)
        inventory[identifier] = {'name': name, 'count': 12, 'status': 'exact', 'verified': True,
            'source': 'backpack_selected_stack', 'evidence': {'materialId': identifier, **deepcopy(pair)}}
    ores = {'category': 'weaponExperience', 'source': 'backpack_selected_stack', 'readOnly': True,
        'mainUiRestored': True, 'cleanupCompleted': True, 'observations': observations}
    return {'moraObservation': mora, 'weaponExperienceObservation': ores, 'inventory': inventory,
        'allVerified': True, 'readOnly': True, 'upgradeBudgetComplete': False, 'levelExperienceObserved': False}


class ResourceCoverageEvidenceTests(unittest.TestCase):
    def test_independent_coin_model_full_integer_and_three_named_stacks_verify(self):
        packet = coverage_fixture()
        self.assertTrue(verify_resource_coverage(packet, START, FINISH))
        self.assertEqual(mora_count(packet['moraObservation'], START, FINISH), 125000)
        self.assertFalse(packet['upgradeBudgetComplete'])

    def test_mora_wrong_coin_weak_score_truncated_integer_or_stale_frame_cannot_be_exact(self):
        mutations = [lambda r: r['second'].update(iconName='原石'), lambda r: r['second'].update(iconScore=.431),
            lambda r: r['second'].update(rawBalanceText='125,000'), lambda r: r['second']['balanceRows'][0].update(x=397),
            lambda r: r['second'].update(observedAt=r['first']['observedAt']), lambda r: r.update(balance=True)]
        for mutate in mutations:
            packet = coverage_fixture()
            mutate(packet['moraObservation'])
            packet['inventory']['202']['evidence'] = deepcopy(packet['moraObservation'])
            with self.assertRaises(ValueError): verify_resource_coverage(packet, START, FINISH)

    def test_unknown_keeps_null_and_success_summary_cannot_hide_missing_resource(self):
        packet = coverage_fixture()
        packet['inventory']['104012'] = {'name': EXPERIENCE['104012'], 'count': None, 'status': 'unknown'}
        packet['allVerified'] = False
        self.assertFalse(verify_resource_coverage(packet, START, FINISH))
        packet['allVerified'] = True
        with self.assertRaises(ValueError): verify_resource_coverage(packet, START, FINISH)

    def test_mineral_raw_packet_category_name_count_and_cleanup_cannot_be_forged(self):
        for mutate in (lambda p: p['weaponExperienceObservation'].update(category='weaponAscension'),
                       lambda p: p['weaponExperienceObservation'].update(cleanupCompleted=False),
                       lambda p: p['inventory']['104013'].update(count=999),
                       lambda p: p['inventory']['104013'].update(name='其他矿石')):
            packet = coverage_fixture();mutate(packet)
            with self.assertRaises(ValueError): verify_resource_coverage(packet, START, FINISH)


if __name__ == '__main__':
    unittest.main()
