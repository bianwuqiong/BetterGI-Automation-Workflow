import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.single_talent_plan import derive_single_talent_step
from scripts.cultivation import verify_cultivation_report

ROOT = Path(__file__).resolve().parents[1]


class SingleTalentPlanTests(unittest.TestCase):
    target = dict(characterName='梦见月瑞希', talentTargets=dict(normal=9, skill=9, burst=9))
    costs = dict(talentName='梦浮', currentBaseLevel=8, nextBaseLevel=9,
        materials=[dict(name='书', owned=4, required=12), dict(name='刀镡', owned=50, required=9)],
        mora=dict(owned=100000, required=450000))
    catalog = {'104321': dict(name='书'), '112045': dict(name='刀镡'), '113060': dict(name='额外材料')}

    def test_next_scope_and_deficits_match_javascript_and_never_enable_spending(self):
        expected = derive_single_talent_step(self.target, '元素战技', self.costs, self.catalog)
        module = (ROOT/'bgi-scripts/AutoGameCultivation/core/single-talent-plan.js').as_uri()
        script = 'import {deriveSingleTalentStep as derive} from ' + json.dumps(module) + ';' + \
                 'const p=JSON.parse(process.argv[1]);console.log(JSON.stringify(derive(p.target,p.type,p.costs,p.catalog)));'
        result = subprocess.run(['node', '--input-type=module', '-e', script,
                                 json.dumps(dict(target=self.target, type='元素战技', costs=self.costs, catalog=self.catalog))],
                                capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertEqual([m['materialId'] for m in expected['namedInventoryScope']['materials']], ['104321','112045'])
        self.assertFalse(expected['executionEnabled'])
        self.assertFalse(expected['targetReached'])

    def test_selected_target_met_does_not_claim_other_talents_or_scan_unrelated_materials(self):
        target = copy.deepcopy(self.target);target['talentTargets']['skill'] = 8
        result = derive_single_talent_step(target, '元素战技', self.costs, self.catalog)
        self.assertIsNone(result['nextBaseLevel'])
        self.assertIsNone(result['namedInventoryScope'])
        self.assertFalse(result['targetReached'])

    def test_ambiguous_mapping_boolean_quantity_and_duplicate_material_are_rejected(self):
        duplicate_catalog = {**self.catalog, '104322': dict(name='书')}
        invalid_cost = copy.deepcopy(self.costs);invalid_cost['mora']['owned'] = True
        duplicate_cost = copy.deepcopy(self.costs);duplicate_cost['materials'].append(duplicate_cost['materials'][0])
        for costs, catalog in ((self.costs,duplicate_catalog),(invalid_cost,self.catalog),(duplicate_cost,self.catalog)):
            with self.subTest(costs=costs, catalog=catalog), self.assertRaises(ValueError):
                derive_single_talent_step(self.target,'元素战技',costs,catalog)

    def test_actual_operator_plan_is_checked_by_host_and_tampered_scope_is_rejected(self):
        operator = (ROOT/'bgi-scripts/AutoGameCultivation/core/operator.js').as_uri()
        fixture = ROOT/'bgi-scripts/AutoGameCultivation/tests/fixtures/talent-preview-synthetic.json'
        script = 'import {runCultivation} from ' + json.dumps(operator) + ';' + """
import {readFileSync} from 'node:fs';
const raw=JSON.parse(readFileSync(process.argv[1],'utf8'));
const catalog=Object.fromEntries(raw.materials.map((m,i)=>[String(104301+i),{name:m.name}]));
const target={characterName:raw.characterName,targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:false,weaponTargetLevel:null};
const settings={runId:'one-preview',mode:'scan',talentPreviewOnly:true,talentPreviewType:raw.talentType,
 targetConfigJson:JSON.stringify(target),policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:0,maxMinutes:3})};
let now=1791734400000,event;const files={};
const forbidden=()=>{throw Error('no other game or spender calls');};
const api={now:()=>now,inspectTalentUpgrade:async()=>{now+=4000;return raw;},getCharacter:forbidden,countItems:forbidden,
 runDomain:forbidden,runBoss:forbidden,runCrafting:forbidden,readResinSnapshot:forbidden,
 writeText:async(p,t)=>{files[p]=t;return true;},readText:p=>files[p],emit:e=>{event=e;}};
const report=await runCultivation(settings,api,{materials:catalog});console.log(JSON.stringify({report,event,catalog}));
"""
        output = subprocess.run(['node','--input-type=module','-e',script,str(fixture)],
                                capture_output=True,text=True,encoding='utf-8',check=True)
        result = json.loads(output.stdout)
        self.assertEqual(result['report']['status'],'success')
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)/'runtime'
            plugin = runtime/'User/JsScript/AutoGameCultivation'
            (plugin/'record').mkdir(parents=True)
            (plugin/'upstream/data').mkdir(parents=True)
            (plugin/'upstream/data/materials.json').write_text(json.dumps(result['catalog']),encoding='utf-8')
            archive = Path(temporary)/'archive';archive.mkdir()
            report_path = plugin/'record/one-preview.json'
            def check(report):
                report_path.write_text(json.dumps(report),encoding='utf-8')
                return verify_cultivation_report(result['event'],runtime,'one-preview','scan',report['target'],archive,
                    expected_policy=result['report']['policy'],expected_talent_type='元素战技')
            self.assertEqual(check(result['report'])['status'],'success')
            for modification in ('foreign-material','allow-spend','boolean-as-number','unverified-preview'):
                report = copy.deepcopy(result['report'])
                if modification == 'foreign-material':
                    report['singleTalentNextStep']['namedInventoryScope']['materials'][0]['materialId']='113060'
                elif modification == 'unverified-preview':
                    report['talentPreview']['evidenceVerified']=False
                    report['talentPreview']['costs']=None
                else:
                    report['singleTalentNextStep']['executionEnabled']=True if modification=='allow-spend' else 0
                with self.subTest(modification=modification):
                    self.assertEqual(check(report)['status'],'unknown')
