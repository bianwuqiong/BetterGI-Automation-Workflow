from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import os
import math
import tempfile
import json,shutil,subprocess
import unittest
from scripts.named_inventory import prepare_named_request,verify_named_inventory,verify_bound_mora,named_title_contract,RAW_DETECTOR
from scripts.named_count_model_assets import COUNT_MODEL_ASSETS
from scripts.weekly_inventory import frame_count
from scripts.named_inventory_capture import rectangle_core
from tests.named_inventory_fixture import fixture,mora_fixture,BASE

START=datetime.fromtimestamp(BASE/1000,timezone.utc).isoformat();END=datetime.fromtimestamp((BASE+4000)/1000,timezone.utc).isoformat()
class NamedInventoryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='synthetic-bound-inventory-');self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.packet,self.request,self.context=fixture(self.root)
    def verify(self,packet=None,context=None):return verify_named_inventory(self.packet if packet is None else packet,self.request,START,END,trusted_runtime_root=self.root,trusted_game_context=self.context if context is None else context)
    def test_native_prebinding_failure_is_preserved_without_any_inventory_or_balance_success(self):
        packet=deepcopy(self.packet);packet.update(nativeObservation=None,bindingReceipt=None,reason='synthetic process query denied')
        result=self.verify(packet)
        self.assertEqual(result['status'],'unknown');self.assertFalse(result['rawEvidenceVerified'])
        self.assertIn('synthetic process query denied',result['reason'])
        self.assertTrue(all(v['count'] is None for v in result['inventory'].values()))
        mora=verify_bound_mora(packet,START,END,trusted_runtime_root=self.root,trusted_game_context=self.context)
        self.assertEqual(mora['status'],'unknown');self.assertIsNone(mora['balance'])
        self.assertIn('synthetic process query denied',mora['reason'])
        packet['nativeObservation']={'status':'unknown','primaryReason':'synthetic known-page rejection','reason':'synthetic known-page rejection'}
        named=self.verify(packet);self.assertEqual(named['status'],'unknown');self.assertIn('synthetic known-page rejection',named['reason'])
        mora=verify_bound_mora(packet,START,END,trusted_runtime_root=self.root,trusted_game_context=self.context)
        self.assertEqual(mora['status'],'unknown');self.assertIsNone(mora['balance']);self.assertIn('synthetic known-page rejection',mora['reason'])
    def test_complete_original_png_catalog_models_os_receipt_and_ui_pairs_pass_without_live_or_consumer_claim(self):
        result=self.verify();self.assertEqual(result['status'],'success',result.get('reason'));self.assertEqual(result['inventory']['104301']['count'],7)
        for key in ('liveVerified','sessionAfterVerified','consumptionVerified','targetReached'):self.assertFalse(result[key])
    def test_named_schema2_is_required_while_binding_receipt_remains_schema1(self):
        self.assertEqual(self.packet['nativeObservation']['schemaVersion'],2)
        self.assertEqual(self.packet['bindingReceipt']['schemaVersion'],1)
        for version in (None,1,True,2.0,'2',3):
            with self.subTest(version=version):
                p=deepcopy(self.packet);p['nativeObservation']['schemaVersion']=version
                self.assertEqual(self.verify(p)['status'],'unknown')
        p=deepcopy(self.packet);p['bindingReceipt']['schemaVersion']=2
        self.assertEqual(self.verify(p)['status'],'unknown')
    def test_named_title_method_exact_roi_and_same_six_asset_scope_are_mandatory(self):
        for frame_key in ('first','second'):
            for change in (lambda f:f.pop('nameRegionMethod'),lambda f:f.update(nameRegionMethod=None),
                lambda f:f.update(nameRegionMethod='raw_ocr_without_detector'),lambda f:f.pop('initialNameRegion'),
                lambda f:f['initialNameRegion'].update(x=1309),lambda f:f['initialNameRegion'].update(width=540.0),
                lambda f:f['initialNameRegion'].update(y=True),lambda f:f.pop('nameModelEvidence'),
                lambda f:f['nameModelEvidence'].update(loadMethod='cached_singleton'),
                lambda f:f['nameModelEvidence'].update(rawModel='V4'),lambda f:f['nameModelEvidence'].update(detectorModel='V6'),
                lambda f:f['nameModelEvidence'].update(provider='Cuda'),
                lambda f:f['nameModelEvidence']['rawDetectorAsset'].update(sha256='0'*64),
                lambda f:f['nameModelEvidence']['rawDetectorAsset'].update(length=float(f['nameModelEvidence']['rawDetectorAsset']['length'])),
                lambda f:f['nameModelEvidence']['countModels']['assets'].pop(),
                lambda f:f['nameModelEvidence']['countModels']['assets'][0].update(sha256='0'*64)):
                p=deepcopy(self.packet);change(p['nativeObservation']['observations']['104301']['pair'][frame_key])
                result=self.verify(p);self.assertEqual(result['status'],'unknown');self.assertIsNone(result['inventory']['104301']['count'])
    def test_both_original_frames_initial_and_final_titles_require_one_complete_row(self):
        for frame_key in ('first','second'):
            for stack_key in ('initialStack','stack'):
                for rows_value in ([],None,[{'text':'合成'}],[{'text':'另一完整名字'}],
                    [{'text':'合成教导','x':1300,'y':130,'width':150,'height':25}]*2):
                    with self.subTest(frame=frame_key,stack=stack_key,rows=rows_value):
                        p=deepcopy(self.packet);p['nativeObservation']['observations']['104301']['pair'][frame_key][stack_key]['nameRows']=rows_value
                        result=self.verify(p);self.assertEqual(result['status'],'unknown');self.assertIsNone(result['inventory']['104301']['count'])
                for change in (lambda r:r.update(text='合成'),lambda r:r.update(text='另一完整名字'),
                    lambda r:r.update(width=0),lambda r:r.update(height=-1),lambda r:r.update(x=True),lambda r:r.update(y=130.0)):
                    p=deepcopy(self.packet);change(p['nativeObservation']['observations']['104301']['pair'][frame_key][stack_key]['nameRows'][0])
                    self.assertEqual(self.verify(p)['status'],'unknown')
    def test_four_title_edges_accept_exact_two_pixels_and_reject_touch_cross_or_short_margin(self):
        p=deepcopy(self.packet)
        for f in (p['nativeObservation']['observations']['104301']['pair'][k] for k in ('first','second')):
            for key in ('initialStack','stack'):f[key]['nameRows'][0].update(x=1282,y=112,width=536,height=74)
        self.assertEqual(self.verify(p)['status'],'success')
        for frame_key in ('first','second'):
            for stack_key in ('initialStack','stack'):
                for distance in (1,0,-1,-2):
                    for change in (lambda r,d:r.update(x=1280+d),lambda r,d:r.update(y=110+d),
                        lambda r,d:r.update(width=1820-d-r['x']),lambda r,d:r.update(height=188-d-r['y'])):
                        bad=deepcopy(self.packet);change(bad['nativeObservation']['observations']['104301']['pair'][frame_key][stack_key]['nameRows'][0],distance)
                        self.assertEqual(self.verify(bad)['status'],'unknown')
    def test_scaled_title_roi_uses_source_rounding_and_scaled_two_pixel_margin(self):
        original=self.packet['nativeObservation'];target=original['requestedMaterials'][0];strict=original['strictModels']
        for width,height in ((960,540),(1600,900),(1920,1080),(2560,1440)):
            f=deepcopy(original['observations']['104301']['pair']['first']);f.update(width=width,height=height)
            scale=width/1920;x,y,w,h=(round(v*scale) for v in (1280,110,540,78));margin=math.ceil(2*scale)
            f['initialNameRegion']={'x':x,'y':y,'width':w,'height':h}
            for key in ('initialStack','stack'):
                f[key]['nameRegion']=deepcopy(f['initialNameRegion']);f[key]['nameRows']=[{'text':target['materialName'],'x':x+margin,'y':y+margin,'width':w-2*margin,'height':h-2*margin}]
            named_title_contract(f,target,BASE,BASE+4000,strict)
            f['initialStack']['nameRows'][0]['x']=x+margin-1
            with self.assertRaises(ValueError):named_title_contract(f,target,BASE,BASE+4000,strict)
    def test_bad_initial_quantity_stays_raw_but_geometry_and_complete_conflict_reject(self):
        self.assertEqual(self.verify()['status'],'success')
        p=deepcopy(self.packet);f=p['nativeObservation']['observations']['104301']['pair']['first']
        f['initialStack'].update(rawCountText='8',countRows=[{'text':'8','x':145,'y':432,'width':10,'height':13}])
        self.assertEqual(self.verify(p)['status'],'unknown')
        f['initialStack']['countRows'][0]['text']='7';f['initialStack']['rawCountText']='7'
        self.assertEqual(self.verify(p)['status'],'success')
        for change in (lambda s:s['countRows'][0].update(x=114),lambda s:s['countRows'][0].update(y=427),
            lambda s:s['countRows'][0].update(width=True),lambda s:s['countRegion'].update(width=116),
            lambda s:s.update(selectedItemVerified=1),lambda s:s.update(observedAt=float(s['observedAt']))):
            bad=deepcopy(p);change(bad['nativeObservation']['observations']['104301']['pair']['first']['initialStack'])
            self.assertEqual(self.verify(bad)['status'],'unknown')
    def test_named_optin_preserves_weekly_legacy_initial_roi(self):
        raw=self.packet['nativeObservation'];pair=raw['observations']['104301']['pair'];target=raw['requestedMaterials'][0]
        assets=raw['strictModels']['countModels']['assets'];f=deepcopy(pair['first'])
        with self.assertRaises(ValueError):frame_count(f,target,pair['selection'],BASE,BASE+4000,assets)
        f['initialStack']['nameRegion']={'x':1309,'y':120,'width':491,'height':60}
        f['initialStack']['nameRows'][0]['x']=1320
        self.assertEqual(frame_count(f,target,pair['selection'],BASE,BASE+4000,assets),7)
        with self.assertRaises(ValueError):frame_count(f,target,pair['selection'],BASE,BASE+4000,assets,named_title=True)
    def test_all_six_loaded_model_bytes_are_checked_against_runtime(self):
        for relative in [path for unused,path in COUNT_MODEL_ASSETS]+[RAW_DETECTOR]:
            with self.subTest(asset=relative):
                path=self.root/relative;original=path.read_bytes()
                try:
                    path.write_bytes(original+b'changed');self.assertEqual(self.verify()['status'],'unknown')
                finally:path.write_bytes(original)
    def test_recognized_frame_geometry_must_match_each_original_png(self):
        p=deepcopy(self.packet)
        for key in ('first','second'):
            p['nativeObservation']['observations']['104301']['pair'][key].update(width=960,height=540)
        result=self.verify(p);self.assertEqual(result['status'],'unknown')
        self.assertIn('dimensions differ from original pixels',result['reason'])
    def test_actual_twelve_field_native_rect_keeps_all_metadata_and_rejects_inconsistent_derived_edges(self):
        rectangle=self.packet['bindingReceipt']['gameBinding']['captureRectangle']
        self.assertEqual(len(rectangle),12);self.assertEqual(rectangle_core(rectangle),self.context['captureRectangle'])
        for mutation in (lambda r:r.update(bottom=r['bottom']+1),lambda r:r['location'].update(x=1),
            lambda r:r['bottomRight'].update(y=False),lambda r:r['size'].update(width=1536),
            lambda r:r.update(arbitrary=True),lambda r:r.pop('topLeft')):
            p=deepcopy(self.packet);mutation(p['bindingReceipt']['gameBinding']['captureRectangle'])
            self.assertEqual(self.verify(p)['status'],'unknown')
        p=deepcopy(self.packet);p['nativeObservation']['rawFrames'][2]['actualCapture']['returnedRectangle']=deepcopy(rectangle)
        p['nativeObservation']['rawFrames'][2]['actualCapture']['returnedRectangle']['topLeft']['x']=9
        self.assertEqual(self.verify(p)['status'],'unknown')
        p=deepcopy(self.packet);p['bindingReceipt']['gameBinding']['captureRectangle']=deepcopy(self.context['captureRectangle'])
        self.assertEqual(self.verify(p)['status'],'unknown')
    def test_zero_budget_scope_makes_request_from_catalog_only_and_rejects_stock_cost_binding(self):
        scope={'executionEnabled':False,'policy':{'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3},'materials':self.request['materials']}
        request=prepare_named_request(scope,run_id='synthetic-run',step_id='synthetic-step',trusted_runtime_root=self.root);self.assertEqual(request,self.request)
        for modify in (lambda s:s.update(executionEnabled=True),lambda s:s['policy'].update(originalResinBudget=20),lambda s:s.update(binding=self.context),lambda s:s['materials'][0].update(owned=7),lambda s:s['materials'][0].update(required=3)):
            altered=deepcopy(scope);modify(altered)
            with self.assertRaises(ValueError):prepare_named_request(altered,run_id='synthetic-run',step_id='synthetic-step',trusted_runtime_root=self.root)
    def test_actual_identity_start_window_origin_exe_foreground_and_missing_os_context_stay_unknown(self):
        for modify in (lambda c:c.update(processId=124),lambda c:c.update(windowHandle=457),lambda c:c.update(processStartedUtcTicks='639012345678901235'),lambda c:c['captureRectangle'].update(x=1),lambda c:c.update(executablePath='other.exe'),lambda c:c.update(foregroundWindowHandle=457)):
            context=deepcopy(self.context);modify(context);self.assertEqual(self.verify(context=context)['status'],'unknown')
        result=verify_named_inventory(self.packet,self.request,START,END,trusted_runtime_root=self.root);self.assertEqual(result['status'],'unknown')
    def test_caller_summary_asset_rows_opaque_receipt_click_raw_crop_and_world_bool_cannot_replace_proof(self):
        mutations=(lambda p:p.pop('bindingReceipt'),lambda p:p['nativeObservation'].update(inventory={'104301':8}),
            lambda p:p['nativeObservation']['strictModels'].update(loadMethod='cached_singleton'),lambda p:p['nativeObservation']['requestedMaterials'][0]['csvRow'].update(rowSha256='0'*64),
            lambda p:p['nativeObservation']['observations']['104301']['pair']['selection'].update(x=float('nan')),
            lambda p:p['nativeObservation']['observations']['104301']['pair']['selection'].update(y=1),
            lambda p:p['nativeObservation']['rawFrames'][0].pop('worldEvidence'),lambda p:p['nativeObservation']['rawFrames'][0]['worldEvidence']['anchors'][0].update(fileSha256='0'*64),
            lambda p:p['nativeObservation']['rawFrames'][2]['recognized']['countReading'].update(sourcePixelsSha256='0'*64),
            lambda p:p['nativeObservation']['observations']['104301']['pair']['first']['privateCapture'].update(nativePixelsSha256='0'*64))
        for modify in mutations:
            p=deepcopy(self.packet);modify(p);result=self.verify(p);self.assertEqual(result['status'],'unknown');self.assertIsNone(result['inventory']['104301']['count'])
    def test_original_png_rename_alias_same_file_and_byte_or_pixel_mutation_fail(self):
        p=deepcopy(self.packet);p['nativeObservation']['rawFrames'][1]['privateCapture']['path']=p['nativeObservation']['rawFrames'][0]['privateCapture']['path'];self.assertEqual(self.verify(p)['status'],'unknown')
        p=deepcopy(self.packet);first=Path(p['nativeObservation']['rawFrames'][0]['privateCapture']['path'])
        p['nativeObservation']['rawFrames'][1]['privateCapture']['path']=str(first.parent/'..'/first.parent.name/first.name)
        self.assertEqual(self.verify(p)['status'],'unknown')
        alias=first.with_name('hardlink.png');os.link(first,alias)
        p['nativeObservation']['rawFrames'][1]['privateCapture']['path']=str(alias);self.assertEqual(self.verify(p)['status'],'unknown')
        path=Path(self.packet['nativeObservation']['rawFrames'][0]['privateCapture']['path']);path.write_bytes(path.read_bytes()+b'changed');self.assertEqual(self.verify()['status'],'unknown')
    def test_packet_interval_and_zero_consumer_assertions_fail_closed_for_both_readers(self):
        mora,context=mora_fixture(self.root)
        for original,verify in ((self.packet,self.verify),(mora,lambda p:verify_bound_mora(p,START,END,trusted_runtime_root=self.root,trusted_game_context=context))):
            for change in (lambda p:p.pop('readStartedAt'),lambda p:p.update(readFinishedAt=START),
                lambda p:p.update(completedUpgrades=False),lambda p:p.update(consumptionVerified=True),
                lambda p:p.update(readOnly=False),lambda p:p.update(liveVerified=True),lambda p:p.update(sessionAfterVerified=True),
                lambda p:p['nativeObservation'].update(completedUpgrades=False),
                lambda p:p['bindingReceipt']['gameBinding'].pop('systemInfoGeneration'),
                lambda p:p['bindingReceipt']['gameBinding'].update(backendGeneration='0'),
                lambda p:p['bindingReceipt'].update(captureSession=None)):
                altered=deepcopy(original);change(altered);result=verify(altered);self.assertEqual(result['status'],'unknown')
                self.assertFalse(result['sessionAfterVerified']);self.assertFalse(result['consumptionVerified'])
    def test_bound_mora_has_independent_actual_assets_world_pngs_and_two_complete_original_balances(self):
        p,context=mora_fixture(self.root);result=verify_bound_mora(p,START,END,trusted_runtime_root=self.root,trusted_game_context=context)
        self.assertEqual(result['status'],'success',result.get('reason'));self.assertEqual(result['balance'],123456);self.assertFalse(result['sessionAfterVerified'])
        for change in (lambda p:p['nativeObservation']['readings'][-1].update(rawBalanceText='１２３４５６'),
            lambda p:p['nativeObservation']['readings'][-1].update(iconScore=.74),lambda p:p['nativeObservation'].pop('strictModels'),
            lambda p:p['nativeObservation']['readings'][-1]['balanceRows'][0].update(y=1001)):
            bad=deepcopy(p);change(bad);result=verify_bound_mora(bad,START,END,trusted_runtime_root=self.root,trusted_game_context=context)
            self.assertEqual(result['status'],'unknown');self.assertIsNone(result['balance'])
    @unittest.skipUnless(shutil.which('node'),'actual JS bridge protocol requires Node')
    def test_actual_js_operator_archives_raw_and_host_independently_verifies_controlled_runtime(self):
        self.operator_roundtrip(self.packet,self.context,False)
    @unittest.skipUnless(shutil.which('node'),'actual JS bridge protocol requires Node')
    def test_actual_js_bound_mora_operator_preserves_original_raw_for_independent_host(self):
        packet,context=mora_fixture(self.root)
        self.operator_roundtrip(packet,context,True)
    def operator_roundtrip(self,packet,context,bound_mora):
        from tests import test_cultivation as tc
        from scripts import cultivation
        f=tc.CultivationTests();f.setUp()
        for relative in ('User/Config.json','Assets','GameTask','log'):
            source=self.root/relative;target=f.bgi/relative
            if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True)
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        p=deepcopy(packet)
        for raw in p['nativeObservation']['rawFrames']:raw['privateCapture']['path']=str(f.bgi/Path(raw['privateCapture']['path']).relative_to(self.root))
        # The typed accepted frames reference the same privateCapture dictionaries.
        for observation in p['nativeObservation'].get('observations',{}).values():
            for key in ('first','second'):
                frame=observation['pair'][key];frame['privateCapture']['path']=str(f.bgi/Path(frame['privateCapture']['path']).relative_to(self.root)) if Path(frame['privateCapture']['path']).is_relative_to(self.root) else frame['privateCapture']['path']
        settings={'runId':'synthetic-run','mode':'scan','namedInventoryOnly':not bound_mora,'boundMoraOnly':bound_mora,'namedInventoryStepId':'synthetic-step',
            'targetConfigJson':json.dumps(tc.TARGET),'policyJson':json.dumps({'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3}),
            'namedInventoryScopeJson':json.dumps({'executionEnabled':False,'policy':{'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3},'materials':self.request['materials']})}
        module=(Path(__file__).resolve().parents[1]/'bgi-scripts/AutoGameCultivation/core/operator.js').as_uri()
        reader='readBoundMoraSnapshot' if bound_mora else 'readNamedCultivationInventory'
        code='import {runCultivation} from '+json.dumps(module)+';import {readFileSync} from "node:fs";const raw=JSON.parse(readFileSync(0,"utf8"));let now='+str(BASE)+',event;const files={};const api={now:()=>now,writeText:async(p,t)=>{files[p]=t;return true;},readText:p=>files[p],emit:e=>event=e,'+reader+':async()=>{now+='+str(4000)+';return raw;}};const report=await runCultivation(JSON.parse(process.argv[1]),api,{});console.log(JSON.stringify({report,event}));'
        result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code,json.dumps(settings)],input=json.dumps({'bindingReceipt':p['bindingReceipt'],'nativeObservation':p['nativeObservation']}),capture_output=True,text=True,encoding='utf-8',check=True,timeout=15)
        emitted=json.loads(result.stdout);f.report_path.parent.mkdir(parents=True,exist_ok=True);path=f.report_path.with_name('synthetic-run.json');path.write_text(json.dumps(emitted['report']),encoding='utf-8')
        checked=cultivation.verify_cultivation_report(emitted['event'],f.bgi,'synthetic-run','scan',tc.TARGET,f.run,expected_policy=emitted['report']['policy'],
            expected_named_request=None if bound_mora else self.request,expected_bound_mora=bound_mora,trusted_game_context=context)
        self.assertEqual(checked['status'],'success',checked['reason']);self.assertFalse(checked['report']['hostBoundSnapshotVerification']['sessionAfterVerified'])

if __name__=='__main__':unittest.main()
