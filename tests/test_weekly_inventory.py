"""Pure raw-frame evidence regressions for four weekly inventory stacks."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from scripts.weekly_inventory import verified_observation, verify_weekly_inventory
from scripts.named_count_model_assets import COUNT_MODEL_ASSETS,read_named_count_model_assets
from tests.weekly_inventory_fixture import packet, native_fixture, make_unknown, START, FINISH, BASE


class WeeklyInventoryTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory(prefix='synthetic-weekly-models-');self.addCleanup(directory.cleanup)
        self.runtime=Path(directory.name);cfg=self.runtime/'User/Config.json';cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({'otherConfig':{'ocrConfig':{'paddleOcrModelConfig':8}}}),encoding='utf-8')
        for name,path in COUNT_MODEL_ASSETS:
            asset=self.runtime/path;asset.parent.mkdir(parents=True,exist_ok=True);asset.write_bytes(('synthetic-'+name).encode())
        self.model_evidence=read_named_count_model_assets(self.runtime);self.model_evidence['pinMethod']='actual_bundled_open_read_sha256_hold_session'
        for a in self.model_evidence['assets']:a['sha256']=a['sha256'].upper()
    def modern20(self):
        from tests.weekly_inventory_fixture import rect
        raw=native_fixture()
        for pair in raw['observations'].values():
            for key in ('first','second'):
                f=pair[key];s=f['stack'];initial=deepcopy(s);initial.update(rawCountText='~'+s['rawCountText'],countRows=[])
                f['initialStack']=initial
                text=s['rawCountText'];source=rect(115,420,115,38);component=rect(50,48,30,42)
                projected=dict(text=text,**rect(132,436,10,14))
                r=dict(method='grid_hsv_foreground_exact_dual_ocr',sourceScale=3,maximumSaturation=140,maximumValue=210,
                    minimumComponentArea=20,minimumComponentHeight=12,minimumComponentBottomRatio=.55,maximumComponentAspectRatio=3,
                    glyphHeight=48,horizontalPadding=24,verticalPadding=24,topPaddingReference=8,bottomPaddingReference=8,sourceRegion=source,
                    ocrScale=1,detectorModel='PaddleV4_fixed',rawModel='configured_native_paddle_without_detector',sourceInterpolation='linear',glyphInterpolation='nearest',ocrInterpolation='nearest',ocrInputWidth=82,ocrInputHeight=96,
                    allComponents=[rect(0,100,345,1),component],components=[component],foregroundBounds=component,
                    foregroundSourceBounds=rect(131,436,11,14),glyphWidth=34,normalizedWidth=82,normalizedHeight=96,raw=text,
                    detectorRows=[dict(text=text,**rect(26,26,30,44))],sourceRows=[projected],
                    sourcePixelsSha256='a'*64,maskPixelsSha256='b'*64,normalizedPixelsSha256='c'*64,ocrInputPixelsSha256='c'*64)
                f['countReading']=r;s.update(nameRegion=rect(1280,110,540,78),countRegion=source,countRows=[projected],countMethod=r['method'])
                r.update(modelEvidence=deepcopy(self.model_evidence),rawPaddleReadback=8)
        return raw

    def test_modern20_geometry_dual_ocr_projects_real_source_and_retains_failed_original(self):
        raw=self.modern20();snapshot=deepcopy(raw)
        self.assertEqual(verified_observation(raw,START,FINISH,trusted_runtime_root=self.runtime)['113060']['count'],7)
        self.assertEqual(raw,snapshot);self.assertEqual(raw['observations']['113060']['first']['initialStack']['rawCountText'],'~7')

    def test_modern20_missing_initial_forged_contours_projection_crop_hash_or_raw_cannot_pass(self):
        for mutate in (lambda f:f.pop('initialStack'),lambda f:f.pop('countReading'),
            lambda f:f['initialStack'].update(observedAt=BASE),lambda f:f['countReading'].update(maximumSaturation=141),
            lambda f:f['countReading']['sourceRegion'].update(height=31),lambda f:f['countReading'].update(allComponents=[]),
            lambda f:f['countReading'].update(ocrScale=4),lambda f:f['countReading'].update(topPaddingReference=0),
            lambda f:f['countReading'].update(detectorModel='choose_highest'),lambda f:f['countReading'].update(rawModel='PaddleV4_fixed'),
            lambda f:f['countReading'].update(ocrInterpolation='linear'),lambda f:f['countReading'].update(ocrInputWidth=328),
            lambda f:f['countReading'].update(ocrInputPixelsSha256='d'*64),
            lambda f:f['countReading'].pop('ocrInputPixelsSha256'),
            lambda f:f['countReading']['components'].append(f['countReading']['allComponents'][0]),
            lambda f:f['countReading']['foregroundBounds'].update(width=31),lambda f:f['countReading']['foregroundSourceBounds'].update(x=132),
            lambda f:f['countReading'].update(glyphWidth=35),lambda f:f['countReading']['sourceRows'][0].update(x=133),
            lambda f:f['countReading']['detectorRows'][0].update(x=1),lambda f:f['countReading'].update(raw='17'),
            lambda f:f['countReading'].update(raw='７'),lambda f:f['stack'].update(rawCountText='７'),
            lambda f:f['countReading'].update(normalizedPixelsSha256='missing'),lambda f:f['stack'].update(countMethod='raw_ocr_without_detector'),
            lambda f:f['stack']['nameRows'][0].update(y=111)):
            raw=self.modern20();mutate(raw['observations']['113060']['second'])
            with self.assertRaises(ValueError):verified_observation(raw,START,FINISH,trusted_runtime_root=self.runtime)
        raw=self.modern20();initial=raw['observations']['113060']['second']['initialStack']
        initial.update(rawCountText='8',countRows=[dict(text='8',x=130,y=433,width=20,height=12)])
        with self.assertRaisesRegex(ValueError,'initial weekly count conflicts'):verified_observation(raw,START,FINISH,trusted_runtime_root=self.runtime)

    def test_modern20_trusted_runtime_model_files_config_and_native_pin_cannot_be_forged(self):
        raw=self.modern20()
        with self.assertRaisesRegex(ValueError,'trusted runtime root'):verified_observation(raw,START,FINISH)
        for mutate in (lambda r:r.pop('modelEvidence'),lambda r:r.update(rawPaddleReadback=7),
            lambda r:r['modelEvidence'].update(pinMethod='guessed_models'),lambda r:r['modelEvidence'].update(rawPaddleConfig=True),
            lambda r:r['modelEvidence']['assets'][0].update(relativePath='../secret'),
            lambda r:r['modelEvidence']['assets'][0].update(sha256='0'*64),lambda r:r['modelEvidence']['assets'][0].update(length=1),
            lambda r:r['modelEvidence']['assets'].reverse()):
            bad=deepcopy(raw);mutate(bad['observations']['113060']['second']['countReading'])
            with self.assertRaises(ValueError):verified_observation(bad,START,FINISH,trusted_runtime_root=self.runtime)
        asset=self.runtime/COUNT_MODEL_ASSETS[0][1];asset.write_bytes(b'changed synthetic model')
        with self.assertRaisesRegex(ValueError,'trusted runtime'):verified_observation(raw,START,FINISH,trusted_runtime_root=self.runtime)
        asset.unlink()
        with self.assertRaisesRegex(ValueError,'assets unavailable'):verified_observation(raw,START,FINISH,trusted_runtime_root=self.runtime)
    def test_exact_new_header_alias_is_stable_but_partial_duplicate_mixed_and_precious_aliases_reject(self):
        raw=native_fixture()
        for identifier in ('113060','113061','113062'):
            for key in ('first','second'):raw['observations'][identifier][key]['headerRows'][0]['text']='养成道具'
        self.assertEqual(verified_observation(raw,START,FINISH)['113060']['count'],7)
        for mutate in (lambda r:r['observations']['113060']['second']['headerRows'][0].update(text='养成道具栏'),
                lambda r:r['observations']['113060']['first']['headerRows'][0].update(text='角色培养道具'),
                lambda r:r['observations']['113021']['second']['headerRows'][0].update(text='养成道具'),
                lambda r:r['observations']['113060']['second']['headerRows'].append({**r['observations']['113060']['second']['headerRows'][0],'text':'角色培养道具'})):
            changed=deepcopy(raw);mutate(changed)
            with self.assertRaises(ValueError):verified_observation(changed,START,FINISH)
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for actual JS/Python protocol round trip')
    def test_actual_js_operator_weekly_report_is_independently_verified_in_python(self):
        from tests import test_cultivation as tc
        from scripts import cultivation as helper
        fixture=tc.CultivationTests();fixture.setUp()
        root=Path(__file__).resolve().parents[1]
        settings={'runId':'test-run','mode':'scan','weeklyInventoryOnly':True,'targetConfigJson':json.dumps(tc.TARGET),
                  'policyJson':json.dumps({'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3})}
        for relative in ['User/Config.json',*(path for name,path in COUNT_MODEL_ASSETS)]:
            target=fixture.bgi/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((self.runtime/relative).read_bytes())
        code='import {runCultivation} from '+json.dumps((root/'bgi-scripts/AutoGameCultivation/core/operator.js').as_uri())+';import {readFileSync} from "node:fs";const raw=JSON.parse(readFileSync(0,"utf8"));'+'''
const settings=JSON.parse(process.argv[1]);
let now=1791734400000,event;const files={};
const forbidden=()=>{throw Error('ordinary scan and spenders are forbidden');};
const api={now:()=>now,getCharacter:forbidden,countItems:forbidden,readResinSnapshot:forbidden,
runDomain:forbidden,runBoss:forbidden,runCrafting:forbidden,
readWeeklyConversionInventory:async()=>{now+=4200;return raw;},
writeText:async(p,t)=>{files[p]=t;return true;},readText:p=>files[p],emit:e=>event=e};
const report=await runCultivation(settings,api,{});console.log(JSON.stringify({report,event}));
'''
        for native in (native_fixture(),self.modern20()):
            with self.subTest(modern='countReading' in native['observations']['113060']['first']):
                process=subprocess.run([shutil.which('node'),'--input-type=module','-e',code,json.dumps(settings)],input=json.dumps(native),
                    capture_output=True,text=True,encoding='utf-8',timeout=15,check=True)
                emitted=json.loads(process.stdout);fixture.report_path.write_text(json.dumps(emitted['report'],ensure_ascii=False),encoding='utf-8')
                verified=helper.verify_cultivation_report(emitted['event'],fixture.bgi,'test-run','scan',tc.TARGET,fixture.run,
                    expected_policy=emitted['report']['policy'],expected_weekly_inventory=True)
                self.assertEqual(verified['status'],'success',verified['reason']);self.assertEqual(verified['cultivation']['completedUpgrades'],0)
                self.assertEqual(verified['report']['weeklyInventory']['nativeObservation'],native)

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
