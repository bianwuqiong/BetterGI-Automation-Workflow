"""Pure raw-frame evidence regressions for four weekly inventory stacks."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from scripts.weekly_inventory import verified_observation, verify_weekly_inventory
from tests.weekly_inventory_fixture import packet, native_fixture, make_unknown, START, FINISH, BASE


class WeeklyInventoryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for actual JS/Python protocol round trip')
    def test_actual_js_operator_weekly_report_is_independently_verified_in_python(self):
        from tests import test_cultivation as tc
        import cultivation as helper
        fixture=tc.CultivationTests();fixture.setUp()
        root=Path(__file__).resolve().parents[1]
        settings={'runId':'test-run','mode':'scan','weeklyInventoryOnly':True,'targetConfigJson':json.dumps(tc.TARGET),
                  'policyJson':json.dumps({'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3})}
        code='import {runCultivation} from '+json.dumps((root/'bgi-scripts/AutoGameCultivation/core/operator.js').as_uri())+';'+"import {readFileSync} from 'node:fs';const raw=JSON.parse(readFileSync(new URL("+json.dumps((root/'bgi-scripts/AutoGameCultivation/tests/fixtures/weekly-inventory-synthetic.json').as_uri())+"),'utf8'));"+'''
const settings=JSON.parse(process.argv[1]);
let now=1791734400000,event;const files={};
const forbidden=()=>{throw Error('ordinary scan and spenders are forbidden');};
const api={now:()=>now,getCharacter:forbidden,countItems:forbidden,readResinSnapshot:forbidden,
runDomain:forbidden,runBoss:forbidden,runCrafting:forbidden,
readWeeklyConversionInventory:async()=>{now+=4200;return raw;},
writeText:async(p,t)=>{files[p]=t;return true;},readText:p=>files[p],emit:e=>event=e};
const report=await runCultivation(settings,api,{});console.log(JSON.stringify({report,event}));
'''
        process=subprocess.run([shutil.which('node'),'--input-type=module','-e',code,json.dumps(settings)],
            capture_output=True,text=True,encoding='utf-8',timeout=15,check=True)
        emitted=json.loads(process.stdout);fixture.report_path.write_text(json.dumps(emitted['report'],ensure_ascii=False),encoding='utf-8')
        verified=helper.verify_cultivation_report(emitted['event'],fixture.bgi,'test-run','scan',tc.TARGET,fixture.run,
            expected_policy=emitted['report']['policy'],expected_weekly_inventory=True)
        self.assertEqual(verified['status'],'success',verified['reason']);self.assertEqual(verified['cultivation']['completedUpgrades'],0)
        self.assertEqual(verified['report']['weeklyInventory']['nativeObservation'],native_fixture())

    def test_four_actual_shaped_named_stacks_model_quantity_pixels_and_world_pair(self):
        p = packet()
        self.assertTrue(verify_weekly_inventory(p, START, FINISH))
        self.assertEqual(p['inventory']['113021']['name'], '异梦溶媒')
        self.assertEqual(p['inventory']['113060']['count'], 7)
        self.assertFalse(p['targetReached']); self.assertEqual(p['completedUpgrades'], 0)

    def test_wrong_id_category_model_header_name_or_quantity_cannot_be_relabelled(self):
        changes = [lambda r:r['inventory'].update({'101016':5}), lambda r:r['observations']['113021']['second'].update(category='characterDevelopmentItems'),
            lambda r:r['observations']['113060']['second'].update(iconScore=.739), lambda r:r['observations']['113060']['second'].update(iconName='丝织之羽'),
            lambda r:r['observations']['113060']['second']['headerRows'][0].update(text='培养道具'),
            lambda r:r['observations']['113060']['second']['stack']['nameRows'][0].update(text='残火'),
            lambda r:r['observations']['113060']['second']['stack'].update(rawCountText='7万'),
            lambda r:r['observations']['113060']['second']['stack'].update(rawCountText='17'),
            lambda r:r['inventory'].update({'113060':True})]
        for change in changes:
            with self.subTest(change=change):
                raw=native_fixture();change(raw)
                with self.assertRaises(ValueError):verified_observation(raw,START,FINISH)

    def test_every_title_count_and_header_edge_requires_two_scaled_pixels(self):
        for key, rowkey, field in [('nameRegion','nameRows','x'),('nameRegion','nameRows','y'),('countRegion','countRows','x'),('countRegion','countRows','y')]:
            raw=native_fixture();stack=raw['observations']['113060']['second']['stack'];stack[rowkey][0][field]=stack[key][field]+1
            with self.assertRaises(ValueError):verified_observation(raw,START,FINISH)
        raw=native_fixture();raw['observations']['113060']['second']['headerRows'][0]['y']=1
        with self.assertRaises(ValueError):verified_observation(raw,START,FINISH)

    def test_raw_border_boolean_alone_cannot_replace_pixels_or_real_edge_geometry(self):
        for change in [lambda b:b.pop('sides'),lambda b:b['sides'][0].update(coordinate=400),
            lambda b:b['sides'][0]['samples'][0].update(x=500),
            lambda b:[pixel.update(b=0,g=0,r=0) for pixel in b['sides'][0]['samples']],
            lambda b:b['sides'][0].update(neutralCount=1)]:
            raw=native_fixture();change(raw['observations']['113060']['second']['stack']['selectionEvidence'])
            with self.assertRaises(ValueError):verified_observation(raw,START,FINISH)

    def test_duplicate_stale_foreign_run_client_and_false_cleanup_are_rejected(self):
        for change in [lambda r:r['observations']['113060']['second']['stack'].update(observedAt=r['observations']['113060']['first']['stack']['observedAt']),
            lambda r:r['observations']['113060']['selection'].update(clickedAt=BASE-100),
            lambda r:r['observations']['113061']['second'].update(width=1280,height=720),
            lambda r:r['worldFrames'][-1].update(world=False),lambda r:r['worldFrames'][-1].update(focused=False),
            lambda r:r['worldFrames'][-1].update(observedAt=r['worldFrames'][-2]['observedAt']),lambda r:r.update(cleanupCompleted=False)]:
            raw=native_fixture();change(raw)
            with self.assertRaises(ValueError):verified_observation(raw,START,FINISH)
        with self.assertRaises(ValueError):verified_observation(native_fixture(),START,'2026-10-11T16:00:06Z')

    def test_unknown_retains_entire_native_raw_with_null_counts_and_no_fabricated_zero(self):
        p=make_unknown(packet());p['nativeObservation']['observations']['113060']['second']['iconScore']=.739
        snapshot=deepcopy(p['nativeObservation']);self.assertFalse(verify_weekly_inventory(p,START,FINISH))
        self.assertEqual(p['nativeObservation'],snapshot)
        p['inventory']['113060']['count']=0
        with self.assertRaises(ValueError):verify_weekly_inventory(p,START,FINISH)

    def test_summary_scope_raw_count_and_read_interval_cannot_be_forged(self):
        for change in [lambda p:p.update(completedUpgrades=1),lambda p:p.update(targetReached=True),
            lambda p:p['requestedMaterials'][-1].update(materialId='101016'),lambda p:p['inventory']['113021'].update(count=100),
            lambda p:p.update(readStartedAt='2026-10-11T15:59:00Z'),lambda p:p['nativeObservation'].update(observations=[]),
            lambda p:p['nativeObservation']['observations']['113060'].update(first=None)]:
            p=packet();change(p)
            with self.assertRaises(ValueError):verify_weekly_inventory(p,START,FINISH)

    def test_explicit_raw_zero_is_valid_when_title_model_pixels_and_both_complete_zeros_exist(self):
        raw=native_fixture();raw['inventory']['113060']=0
        for f in (raw['observations']['113060']['first'],raw['observations']['113060']['second']):
            f['stack']['rawCountText']='0';f['stack']['countRows'][0]['text']='0'
        self.assertEqual(verified_observation(raw,START,FINISH)['113060']['count'],0)

    def test_real_bag_selection_order_can_differ_from_id_order_but_capture_intervals_cannot_overlap(self):
        raw=native_fixture()
        for identifier,clicked in (('113060',BASE+2100),('113062',BASE+100)):
            pair=raw['observations'][identifier];pair['selection']['clickedAt']=clicked
            pair['first']['stack']['observedAt']=clicked+300;pair['second']['stack']['observedAt']=clicked+550
        self.assertEqual(verified_observation(raw,START,FINISH)['113060']['count'],7)
        raw['observations']['113060']['selection']['clickedAt']=BASE+1600
        with self.assertRaises(ValueError):verified_observation(raw,START,FINISH)


if __name__=='__main__':unittest.main()
