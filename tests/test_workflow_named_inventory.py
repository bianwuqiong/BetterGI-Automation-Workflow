"""Fake controller/temporary scope only; never OS query, launch or native read."""
import argparse,contextlib,io,json
from pathlib import Path
import unittest
from unittest.mock import patch
from tests import test_cultivation_workflow as cw
wf,tw=cw.wf,cw.tw
from tests.named_inventory_fixture import setup

class NamedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.base=cw.CultivationWorkflowTests();self.base.setUp();self.root=self.base.root;self.base.source_package()
        setup(self.root/'BetterGI')
        self.scope=self.root/'config/named-synthetic.json';wf.atomic_json(self.scope,{'executionEnabled':False,'policy':{'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3},'materials':[{'materialId':'104301','materialName':'合成教导'}]})
    def run_flow(self,**changes):
        args=argparse.Namespace(root=str(self.root),dry_run=True,task='培养材料',profile='cultivation',cultivation_mode='scan',timeout_minutes=1,no_delay=True,allow_repeat=False,keep_game=False,allow_existing_game=False,graphics_check=False,
            cultivation_named_inventory=True,cultivation_material_scope=str(self.scope),cultivation_bound_mora_check=False)
        for key,value in changes.items():setattr(args,key,value)
        host=cw.CultivationFakeHost(self.root,self.base.make_report);output=io.StringIO()
        with contextlib.redirect_stdout(output),patch.object(wf,'datetime',tw.FixedClock):code=wf.execute(args,host)
        return code,wf.read_json(json.loads(output.getvalue())['resultPath']),host
    def test_dry_named_scope_injects_runner_request_and_zero_budget_without_native_or_game(self):
        code,result,host=self.run_flow();self.assertEqual(code,0,result);self.assertFalse(host.launched)
        group=wf.read_json(Path(result['plannedConfig']).parent/'cultivation-group.json');settings=group['Projects'][0]['JsScriptSettingsObject']
        self.assertTrue(settings['namedInventoryOnly']);self.assertEqual(json.loads(settings['policyJson'])['originalResinBudget'],0)
        self.assertEqual(settings['namedInventoryStepId'],result['runId']+':named-inventory-diagnostic')
    def test_execute_other_diagnostic_profile_or_missing_scope_reject_before_launch(self):
        for changes in ({'cultivation_mode':'execute'},{'cultivation_weekly_inventory':True},{'graphics_check':True},
            {'task':'领取邮件','profile':'full'},{'cultivation_material_scope':None}):
            code,result,host=self.run_flow(**changes);self.assertNotEqual(code,0,result);self.assertFalse(host.launched)
    def test_controller_unique_pid_exe_selects_os_context_and_never_uses_raw_binding(self):
        class Host:
            def processes(self,names):return [123]
            def process_path(self,pid):return self.root/'game.exe'
        host=Host();host.root=self.root;cfg=wf.read_json(self.root/'config/settings.json')
        expected={'source':'runner_windows_os_preflight','processId':123,'processStartedUtcTicks':'639012345678901234'}
        with patch('named_inventory_context.query_game_context',return_value=expected) as query:
            self.assertEqual(wf.fresh_named_inventory_context(self.root,host,cfg),expected);query.assert_called_once_with(123,(self.root/cfg['gameExe']).resolve())

if __name__=='__main__':unittest.main()
