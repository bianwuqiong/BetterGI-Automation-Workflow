from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import os
import tempfile
import json,shutil,subprocess
import unittest
from scripts.named_inventory import prepare_named_request,verify_named_inventory,verify_bound_mora
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
