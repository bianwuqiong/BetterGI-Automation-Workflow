from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.cultivation import (load_cultivation_config, inject_cultivation_task,
    build_cultivation_group, install_cultivation_plugin, verify_cultivation_report,
    normalize_calculator_material)


TARGET = {"characterName": "梦见月瑞希", "targetLevel": 90,
    "talentTargets": {"normal": 9, "skill": 9, "burst": 9},
    "includeEquippedWeapon": True, "weaponTargetLevel": 90}
POLICY = {"maxSteps": 2, "maxMinutes": 10, "originalResinBudget": 40,
    "condensedResinBudget": 0, "allowDomain": True, "domainValidated": True,
    "domainSingleAttemptVerified": True, "domainPartyName": "测试队伍", "domainResin": "original"}


class CultivationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for actual successful operator protocol')
    def test_actual_operator_execute_resin_and_domain_protocol_passes_independent_verifier(self):
        operator = ROOT / 'bgi-scripts/AutoGameCultivation/core/operator.js'
        data_dir = ROOT / 'bgi-scripts/AutoGameCultivation/upstream/data'
        code = f"import {{runCultivation}} from {json.dumps(operator.as_uri())};" + """
import {readFileSync} from 'node:fs';
const dir=process.argv[1];const data={};
for(const [key,file] of [['rulebook','rulebook.json'],['materials','materials.json'],['recipes','crafting-recipes.json']]) data[key]=JSON.parse(readFileSync(dir+'/'+file));
data.allowedBosses=[];
let spent=0,event;const files={};
function list(items=[]){return {GetRange:()=>list(),get Count(){return items.length;},get_Item:i=>items[i],Clear(){items=[];},Add(v){items.push(v);}};}
const api={now:()=>Date.UTC(2026,9,8,1),
getCharacter:async()=>({CharacterName:'梦见月瑞希',Level:80,LevelLimit:80,WeaponName:'讨龙英杰谭',WeaponLevel:80,WeaponLevelLimit:80,
AttackLevel:1,AttackHasBonus:false,SkillLevel:1,SkillHasBonus:false,BurstLevel:1,BurstHasBonus:false}),
countItems:async(tab,names)=>Object.fromEntries(names.map(n=>[n,n.includes('浮世')?spent:0])),
readResinSnapshot:async()=>({originalResin:100-20*spent,condensedResin:null,originalVerified:true,condensedVerified:false,
verified:false,mainUiRestored:true,observedAt:'2026-10-08T01:00:00Z'}),
AutoDomainParam:class{constructor(){this.ResinPriorityList=list();}},runDomain:async()=>{spent++;},
writeText:async(p,t)=>{files[p]=t;return true;},readText:p=>files[p],emit:e=>{event=e;}};
const report=await runCultivation(JSON.parse(process.argv[2]),api,data);
console.log(JSON.stringify({report,event}));
"""
        settings = {'runId': 'test-run', 'mode': 'execute', 'targetConfigJson': json.dumps(TARGET),
                    'policyJson': json.dumps({**POLICY, 'maxSteps': 1, 'originalResinBudget': 20})}
        process = subprocess.run([shutil.which('node'), '--input-type=module', '-e', code,
            str(data_dir), json.dumps(settings)], capture_output=True, text=True, encoding='utf-8', timeout=15, check=True)
        emitted = json.loads(process.stdout)
        result = self.verify(emitted['report'], emitted['event'], mode='execute')
        self.assertEqual(result['status'], 'success', result['reason'])
        self.assertEqual(result['cultivation']['actualResinDelta'], {'original': 20, 'condensed': None})
        self.assertEqual(result['cultivation']['configuredConfirmedClaims'], {'original': 20, 'condensed': 0})

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the actual plugin/verifier contract")
    def test_actual_plugin_character_read_failure_verifies_unknown_report(self):
        operator = ROOT / "bgi-scripts/AutoGameCultivation/core/operator.js"
        code = f"import {{runCultivation}} from {json.dumps(operator.as_uri())};" + """
const files = new Map(); let event;
const settings = JSON.parse(process.argv[1]);
const api = {now:()=>Date.UTC(2026,9,8),
  getCharacter:async()=>{throw new Error('character unavailable');},
  countItems:async()=>{throw new Error('unexpected inventory scan');},
  runDomain:async()=>{throw new Error('unexpected resource operation');},
  runBoss:async()=>{throw new Error('unexpected resource operation');},
  writeText:async(p,text)=>{files.set(p,text);return true;},
  readText:p=>files.get(p),emit:value=>{event=value;}};
const report = await runCultivation(settings,api,{});
console.log(JSON.stringify({report,event}));
"""
        settings = {"runId": "test-run", "mode": "scan",
                    "targetConfigJson": json.dumps(TARGET), "policyJson": "{}"}
        process = subprocess.run([shutil.which("node"), "--input-type=module", "-e", code,
                                  json.dumps(settings)], capture_output=True, text=True,
                                 encoding="utf-8", timeout=15, check=True)
        emitted = json.loads(process.stdout)
        verified = self.verify(emitted["report"], emitted["event"])
        self.assertEqual(verified["status"], "unknown")
        self.assertIs(verified["cultivation"]["reportVerified"], True)
        self.assertEqual(verified["report"]["blockers"][0]["code"], "read_or_execution_failed")
        self.assertEqual(verified["report"]["requiredScanIds"], [])
        self.assertEqual(verified["report"]["manualInventoryIds"], [])
        self.assertEqual(verified["cultivation"]["observedGains"], {})
        self.assertIs(verified["cultivation"]["targetReached"], False)

    def setUp(self):
        self.root = ROOT / "tests/.artifacts" / ("cultivation-" + uuid4().hex[:12])
        self.root.mkdir(parents=True)
        self.cfg = self.root / "config.json"
        self.bgi = self.root / "fake-bgi"
        self.bgi.mkdir()
        self.run = self.root / "run-test-run"
        self.run.mkdir()
        self.report_path = self.bgi / "User/JsScript/AutoGameCultivation/record/test-run.json"
        self.report_path.parent.mkdir(parents=True)
        data = self.report_path.parent.parent / 'upstream/data'
        data.mkdir(parents=True)
        for filename in ('materials.json', 'crafting-recipes.json', 'bettergi-boss-catalog.json'):
            shutil.copyfile(ROOT / 'bgi-scripts/AutoGameCultivation/upstream/data' / filename, data / filename)

    def write_config(self, mode="scan", **changes):
        cfg = {"target": copy.deepcopy(TARGET), "policy": {}, "executionEnabled": mode == "execute"}
        if mode == "execute":
            cfg["policy"] = copy.deepcopy(POLICY)
        cfg.update(changes)
        self.cfg.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        return cfg

    def report(self, mode="scan"):
        stock = {"104320": {"name": "测试材料", "count": 2, "status": "exact"}}
        return {"schemaVersion": 1, "runId": "test-run", "mode": mode,
            "target": copy.deepcopy(TARGET), "profile": {
                "characterName": TARGET["characterName"], "character": {"level": 70, "limit": 80},
                "talents": {name: {"display": 6, "base": 6, "hasBonus": False} for name in ("normal", "skill", "burst")},
                "weapon": {"name": "测试武器", "level": 70, "limit": 80}},
            "inventory": stock, "requiredScanIds": ["104320"], "manualInventoryIds": [],
            "plan": {"requirements": {"104320": 9}, "shortages": [],
                "crafting": {"suggestionsOnly": True, "executed": False, "suggestions": [], "unknownMaterialIds": [], "farmRequirements": {"104320": 7}},
                "manualResources": [], "domains": []},
            "blockers": [], "warnings": [], "steps": [], "status": "success", "readOnly": mode == "scan",
            "policy": copy.deepcopy(POLICY)}

    def event(self, mode="scan", status="success"):
        return {"task": "培养材料", "runId": "test-run", "mode": mode,
            "status": status, "claimedStatus": status, "evidenceVerified": True,
            "readOnly": mode == "scan", "reportRelativePath": "record/test-run.json", "targetReached": False}

    def verify(self, report=None, event=None, mode="scan"):
        if report is not None:
            self.report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return verify_cultivation_report(event or self.event(mode), self.bgi, "test-run", mode, TARGET, self.run)

    def execution_report(self):
        report = self.report("execute")
        for identifier in ('104321', '104322'):
            report['inventory'][identifier] = {'name': '测试材料', 'count': 0, 'status': 'exact'}
        report['requiredScanIds'] = ['104320', '104321', '104322']
        before = copy.deepcopy(report["inventory"])
        report["inventory"]["104320"]["count"] = 4
        report["steps"] = [{"stepId": "test-run:step-1", "type": "domain", "domainName": "菫色之庭", "sundaySelectedValue": "1",
            "maxClaims": 1, "resin": "original", "before": before, "after": copy.deepcopy(report["inventory"]),
            "delta": {"104320": 2, '104321': 0, '104322': 0}, "status": "success", "startedAt": "2026-10-08T01:00:00Z",
            "finishedAt": "2026-10-08T01:01:00Z", "confirmedConfiguredResinCost": 20,
            "resinCostEvidence": "single configured claim and verified gain",
            'resinBefore': {'originalResin': 100, 'condensedResin': 0, 'originalVerified': True,
                'condensedVerified': True, 'verified': True, 'mainUiRestored': True, 'observedAt': '2026-10-08T01:00:00Z'},
            'resinAfter': {'originalResin': 80, 'condensedResin': 0, 'originalVerified': True,
                'condensedVerified': True, 'verified': True, 'mainUiRestored': True, 'observedAt': '2026-10-08T01:01:00Z'},
            'actualResinDelta': {'original': 20, 'condensed': 0}}]
        return report

    def test_scan_config_needs_no_execution_permission_and_has_safe_defaults(self):
        self.write_config()
        cfg = load_cultivation_config(self.cfg, "scan")
        self.assertFalse(cfg["executionEnabled"])
        self.assertFalse(cfg["policy"]["allowDomain"])
        self.assertFalse(cfg["policy"]["allowBoss"])
        self.assertIsNone(cfg["policy"]["originalResinBudget"])
        self.assertFalse(cfg['policy']['validationMode'])
        self.assertFalse(cfg['policy']['allowCrafting'])
        self.assertEqual(cfg['policy']['validationScopeId'], '')
        self.assertEqual(cfg['policy']['validationAttemptedSources'], [])

    def test_validation_config_is_bounded_and_never_claims_already_validated(self):
        policy = {**POLICY, 'validationMode': True, 'domainValidated': False,
                  'originalResinBudget': 60, 'validationScopeId': 'first', 'maxSteps': 2}
        self.write_config('execute', policy=policy)
        self.assertFalse(load_cultivation_config(self.cfg, 'execute')['policy']['domainValidated'])
        for changes in ({'originalResinBudget': 61}, {'condensedResinBudget': 1}, {'domainResin': 'condensed'},
                        {'maxSteps': 3}, {'allowCrafting': True}, {'validationAttemptedSources': ['domain', 'domain']},
                        {'validationAttemptedSources': ['routes']}, {'validationScopeId': '../scope'}):
            self.write_config('execute', policy={**policy, **changes})
            with self.assertRaises(ValueError):
                load_cultivation_config(self.cfg, 'execute')

    def test_initial_validation_requires_marker_real_single_claim_parameters_and_no_source_replay(self):
        report = self.execution_report()
        report['policy'].update(validationMode=True, validationScopeId='first', domainValidated=False)
        step = report['steps'][0]
        step['validationAttempt'] = True
        step['parameterEvidence'] = {'DomainRoundNum': 1, 'SpecifyResinUse': True,
            'AutoArtifactSalvage': False, 'RewardRecognitionEnabled': True, 'DomainName': '菫色之庭',
            'PartyName': POLICY['domainPartyName'], 'SundaySelectedValue': '1',
            'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 1, 'OriginalResin40UseCount': 0,
            'CondensedResinUseCount': 0, 'TransientResinUseCount': 0, 'FragileResinUseCount': 0}
        result = self.verify(report, mode='execute')
        self.assertEqual(result['status'], 'success', result['reason'])
        self.assertFalse(result['report']['policy']['domainValidated'])
        for key, value in (('DomainRoundNum', 2), ('FragileResinUseCount', 1), ('OriginalResin20UseCount', True)):
            malformed = copy.deepcopy(report)
            malformed['steps'][0]['parameterEvidence'][key] = value
            self.assertNotEqual(self.verify(malformed, mode='execute')['status'], 'success')
        report['policy']['validationAttemptedSources'] = ['domain']
        self.assertNotEqual(self.verify(report, mode='execute')['status'], 'success')

    def test_actual_resin_requires_fresh_independent_flags_and_real_matching_delta(self):
        for name, changes in (('resinBefore', {'observedAt': '2026-10-08T00:57:59Z'}),
                              ('resinAfter', {'mainUiRestored': False}),
                              ('resinAfter', {'originalVerified': False}),
                              ('resinAfter', {'originalResin': 100}),
                              ('resinAfter', {'condensedResin': 1}),
                              ('resinAfter', {'verified': False})):
            report = self.execution_report()
            report['steps'][0][name].update(changes)
            self.assertNotEqual(self.verify(report, mode='execute')['status'], 'success')
        report = self.execution_report()
        report['steps'][0]['resinAfter']['originalResin'] = 82
        report['steps'][0]['actualResinDelta']['original'] = 18
        result = self.verify(report, mode='execute')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['cultivation']['actualResinDelta']['original'], 18)
        report['steps'][0]['resinAfter']['originalResin'] = 83
        report['steps'][0]['actualResinDelta']['original'] = 17
        self.assertNotEqual(self.verify(report, mode='execute')['status'], 'success')

    def test_unneeded_condensed_unknown_does_not_hide_verified_original_usage(self):
        report = self.execution_report()
        for key in ('resinBefore', 'resinAfter'):
            report['steps'][0][key].update(condensedResin=None, condensedVerified=False, verified=False)
        report['steps'][0]['actualResinDelta']['condensed'] = None
        result = self.verify(report, mode='execute')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['cultivation']['actualResinDelta'], {'original': 20, 'condensed': None})

    def test_crafting_verifies_real_recipe_full_chain_and_extra_output_without_inventing_mora(self):
        report = self.execution_report()
        report['policy'].update(allowCrafting=True, craftingValidated=True)
        before = copy.deepcopy(report['inventory'])
        before['104320']['count'] = 12
        before['104321']['count'] = 1
        after = copy.deepcopy(before)
        after['104320']['count'] = 6
        after['104321']['count'] = 4
        report['inventory'] = after
        report['steps'] = [{'stepId': 'test-run:step-1', 'type': 'crafting', 'status': 'success',
            'maxClaims': 1, 'resin': 'none', 'before': before, 'after': after,
            'delta': {'104320': -6, '104321': 3, '104322': 0}, 'materialId': '104321',
            'materialName': '「浮世」的指引', 'craftCount': 2, 'craftingCountry': '蒙德', 'materialType': None,
            'recipeEvidence': {'resultCount': 1, 'inputs': [{'id': '104320', 'count': 3}]},
            'resultEvidence': {'Success': True, 'MaterialName': '「浮世」的指引', 'TargetQuantity': 2, 'ActualQuantity': 2, 'MainUiRestored': True},
            'materialsSpent': {'104320': 6}, 'moraCostStatus': 'unverified:未读余额',
            'startedAt': '2026-10-08T01:00:00Z', 'finishedAt': '2026-10-08T01:01:00Z'}]
        result = self.verify(report, mode='execute')
        self.assertEqual(result['status'], 'success', result['reason'])
        self.assertEqual(result['cultivation']['observedGains'], {'104321': 3})
        self.assertEqual(result['cultivation']['materialsSpent'], {'104320': 6})
        self.assertEqual(result['cultivation']['configuredConfirmedClaims'], {'original': 0, 'condensed': 0})
        for changes in ({'materialsSpent': {'104320': 5}}, {'moraCostStatus': 'verified'},
                        {'materialName': 'wrong'}, {'craftingCountry': '璃月'},
                        {'recipeEvidence': {'resultCount': 1, 'inputs': [{'id': '104320', 'count': 2}]}}):
            malformed = copy.deepcopy(report)
            malformed['steps'][0].update(changes)
            self.assertNotEqual(self.verify(malformed, mode='execute')['status'], 'success')
        for restored in (False, None):
            malformed = copy.deepcopy(report)
            malformed['steps'][0]['resultEvidence']['MainUiRestored'] = restored
            self.assertNotEqual(self.verify(malformed, mode='execute')['status'], 'success')
        malformed = copy.deepcopy(report)
        for field in ('before', 'after', 'delta'):
            del malformed['steps'][0][field]['104322']
        self.assertNotEqual(self.verify(malformed, mode='execute')['status'], 'success')

    def test_execute_requires_explicit_permission_and_budgets(self):
        for changed in ({"executionEnabled": False}, {"policy": {}},
            {"policy": {**POLICY, "originalResinBudget": None}}):
            self.write_config("execute", **changed)
            with self.assertRaises(ValueError):
                load_cultivation_config(self.cfg, "execute")
        self.write_config("execute")
        self.assertEqual(load_cultivation_config(self.cfg, "execute")["policy"]["originalResinBudget"], 40)

    def test_config_rejects_unbounded_nonfinite_and_boolean_numbers(self):
        for key, value in (("originalResinBudget", 201), ("condensedResinBudget", 6),
            ("originalResinBudget", -1), ("maxSteps", True), ("maxSteps", 21), ("maxMinutes", 16),
            ("domainResin", "fragile"), ("allowDomain", 1), ("maxMinutes", float("inf"))):
            with self.subTest(key=key, value=value):
                self.write_config("execute", policy={**POLICY, key: value})
                with self.assertRaises(ValueError):
                    load_cultivation_config(self.cfg, "execute")

    def test_fragile_transient_routes_weekly_are_forbidden(self):
        for key, value in (("fragileResinBudget", 1), ("transientResinBudget", 1),
            ("allowFragileResin", True), ("allowTransientResin", True),
            ("allowRoutes", True), ("allowWeekly", True)):
            self.write_config("execute", policy={**POLICY, key: value})
            with self.assertRaises(ValueError):
                load_cultivation_config(self.cfg, "execute")

    def test_target_rejects_missing_privacy_fields_and_bool_level(self):
        for target in ({**TARGET, "uid": "private"}, {**TARGET, "targetLevel": True},
            {**TARGET, "talentTargets": {"normal": 9, "skill": 9}},
            {**TARGET, "includeEquippedWeapon": 1}, {**TARGET, "weaponTargetLevel": 100}):
            self.write_config(target=target)
            with self.assertRaises(ValueError):
                load_cultivation_config(self.cfg, "scan")

    def test_no_weapon_scope_normalizes_level_to_null(self):
        self.write_config(target={**TARGET, "includeEquippedWeapon": False})
        self.assertIsNone(load_cultivation_config(self.cfg, "scan")["target"]["weaponTargetLevel"])

    def test_inject_is_pure_and_idempotent_after_mail(self):
        base = {"TaskDefinitions": {"mail": "领取邮件", "daily": "领取每日奖励"},
            "TaskEnabledList": {"mail": True, "daily": True}, "TaskOrder": ["mail", "daily"]}
        injected = inject_cultivation_task(base)
        self.assertEqual(injected["TaskOrder"], ["mail", "auto-game-cultivation", "daily"])
        self.assertEqual(injected, inject_cultivation_task(injected))
        self.assertEqual(base["TaskOrder"], ["mail", "daily"])

    def test_group_uses_only_strict_global_single_attempt_fact(self):
        self.write_config("execute")
        cfg = load_cultivation_config(self.cfg, "execute")
        for count, expected in ((1, True), (True, False), (2, False), (None, False)):
            group = build_cultivation_group("test-run", cfg, "execute", {"autoDomainConfig": {
                "reviveRetryCount": count, "originalResinUseCount": 999, "useFragileResin": True}})
            project = group["Projects"][0]
            policy = json.loads(project["JsScriptSettingsObject"]["policyJson"])
            self.assertIs(policy["domainSingleAttemptVerified"], expected)
            self.assertEqual(policy["originalResinBudget"], 40)
            self.assertNotIn("useFragileResin", policy)
            self.assertFalse(project["AllowJsNotification"])
        self.assertFalse(cfg["policy"]["domainSingleAttemptVerified"])

    def test_boss_is_opt_in_and_team_alias_is_canonical(self):
        self.write_config("execute", policy={**POLICY, "allowBoss": True, "bossValidated": True,
            "bossTeamName": "首领队伍", "bossTimeoutSeconds": 120})
        policy = load_cultivation_config(self.cfg, "execute")["policy"]
        self.assertTrue(policy["allowBoss"])
        self.assertEqual(policy["bossPartyName"], "首领队伍")
        self.assertNotIn("bossTeamName", policy)
        self.write_config("execute", policy={**POLICY, "bossTimeoutSeconds": 181})
        with self.assertRaises(ValueError):
            load_cultivation_config(self.cfg, "execute")

    def test_install_preserves_records_and_refuses_unbacked_upgrade(self):
        source = self.root / "package"
        source.mkdir()
        (source / "manifest.json").write_text('{}', encoding="utf-8")
        (source / "main.js").write_text('// package', encoding="utf-8")
        (source / "record").mkdir()
        (source / "record/private.json").write_text('{}', encoding="utf-8")
        fresh = self.root / "fresh-bgi"
        fresh.mkdir()
        result = install_cultivation_plugin(source, fresh)
        destination = Path(result["pluginDirectory"])
        self.assertTrue(result["installed"])
        self.assertFalse((destination / "record").exists())
        (destination / "record").mkdir()
        record = destination / "record/retained.json"
        record.write_text('retained', encoding="utf-8")
        mtime = (destination / "main.js").stat().st_mtime_ns
        self.assertTrue(install_cultivation_plugin(source, fresh)["unchanged"])
        self.assertEqual(mtime, (destination / "main.js").stat().st_mtime_ns)
        (source / "main.js").write_text('// upgrade', encoding="utf-8")
        with self.assertRaises(ValueError):
            install_cultivation_plugin(source, fresh)
        self.assertEqual((destination / "main.js").read_text(), '// package')
        self.assertEqual(record.read_text(), 'retained')

    def test_existing_empty_plugin_is_not_overwritten(self):
        source = self.root / "package"
        source.mkdir()
        (source / "manifest.json").write_text('{}')
        (source / "main.js").write_text('// package')
        with self.assertRaises(ValueError):
            install_cultivation_plugin(source, self.bgi)

    def test_calculator_import_distinguishes_exact_and_lower_bound(self):
        self.assertEqual(normalize_calculator_material({"id": 104320, "num": 10, "lack_num": 3}),
            {"id": 104320, "count": 7, "status": "exact"})
        self.assertEqual(normalize_calculator_material({"id": 104320, "num": 10, "lack_num": 0})["status"], "lower_bound")
        for row in ({"id": 1, "num": 2, "lack_num": 3}, {"id": True, "num": 2, "lack_num": 0},
            {"id": 1, "num": -1, "lack_num": 0}):
            with self.assertRaises(ValueError):
                normalize_calculator_material(row)

    def test_scan_export_success_is_not_target_completion_and_does_not_write(self):
        report = self.report()
        result = self.verify(report)
        before = self.report_path.read_bytes()
        result = self.verify()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["cultivation"]["scope"], "scan")
        self.assertFalse(result["cultivation"]["targetReached"])
        self.assertEqual(before, self.report_path.read_bytes())
        self.assertEqual(list(self.run.iterdir()), [])

    def test_scan_unknown_or_lower_bound_stock_never_upgrades_success(self):
        for status, count in (("unknown", None), ("lower_bound", 2)):
            report = self.report()
            report["inventory"]["104320"].update(status=status, count=count)
            result = self.verify(report)
            self.assertEqual(result["status"], "unknown")
            self.assertTrue(result["cultivation"]["reportVerified"])

    def test_manual_resources_may_remain_unknown_in_scan_export(self):
        report = self.report()
        report["inventory"]["202"] = {"name": "摩拉", "count": None, "status": "unknown", "reason": "manual:unsupported"}
        report["manualInventoryIds"] = ["202"]
        report["plan"]["requirements"]["202"] = 100
        self.assertEqual(self.verify(report)["status"], "success")

    def test_scope_target_path_and_status_mismatches_fail_closed(self):
        for event in ({**self.event(), "runId": "other"}, {**self.event(), "mode": "execute"},
            {**self.event(), "readOnly": 1}, {**self.event(), "evidenceVerified": False},
            {**self.event(), "reportRelativePath": "record/../outside.json"}):
            self.assertEqual(self.verify(self.report(), event)["status"], "unknown")
        for changes in ({"runId": "other"}, {"readOnly": False}, {"schemaVersion": True},
            {"status": "unknown"}, {"target": {**TARGET, "targetLevel": 80}}):
            result = self.verify({**self.report(), **changes})
            self.assertIsNone(result["report"])

    def test_missing_report_malformed_json_and_duplicate_keys_fail_closed(self):
        self.assertIsNone(self.verify()["report"])
        for text in ('{bad', '{"runId":"one","runId":"two"}', '{"num":NaN}'):
            self.report_path.write_text(text)
            self.assertIsNone(self.verify()["report"])

    def test_verified_step_gains_preserve_configured_cost_scope(self):
        result = self.verify(self.execution_report(), mode="execute")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["cultivation"]["observedGains"], {"104320": 2})
        self.assertEqual(result["cultivation"]["configuredConfirmedClaims"], {"original": 20, "condensed": 0})
        self.assertEqual(result["cultivation"]["actualResinDelta"], {'original': 20, 'condensed': 0})
        self.assertFalse(result["cultivation"]["targetReached"])

    def test_expected_policy_mismatch_cannot_verify_report(self):
        report = self.execution_report()
        self.verify(report, mode="execute")
        self.assertEqual(verify_cultivation_report(self.event("execute"), self.bgi, "test-run", "execute",
            TARGET, self.run, expected_policy=POLICY)["status"], "success")
        result = verify_cultivation_report(self.event("execute"), self.bgi, "test-run", "execute",
            TARGET, self.run, expected_policy={**POLICY, "originalResinBudget": 20})
        self.assertIsNone(result["report"])

    def test_protected_domain_requires_actual_shield_flag_and_reward_mode(self):
        report = self.execution_report()
        report['policy']['requireZhongliShieldCast'] = True
        self.assertIsNone(self.verify(report, mode='execute')['report'])
        report['steps'][0]['parameterEvidence'] = {'DomainRoundNum': 1, 'SpecifyResinUse': True,
            'AutoArtifactSalvage': False, 'RewardRecognitionEnabled': True, 'DomainName': '菫色之庭',
            'PartyName': POLICY['domainPartyName'], 'SundaySelectedValue': '1',
            'OriginalResinUseCount': 0, 'OriginalResin20UseCount': 1, 'OriginalResin40UseCount': 0,
            'CondensedResinUseCount': 0, 'TransientResinUseCount': 0, 'FragileResinUseCount': 0,
            'RequireZhongliShieldCast': True, 'CombatOnly': False}
        self.assertEqual(self.verify(report, mode='execute')['status'], 'success')
        for flag, bad in (('RequireZhongliShieldCast', False), ('CombatOnly', True)):
            changed = copy.deepcopy(report)
            changed['steps'][0]['parameterEvidence'][flag] = bad
            self.assertIsNone(self.verify(changed, mode='execute')['report'])

    def test_partial_execution_keeps_verified_subtotal_and_unknown_total(self):
        for outcome in ("unknown", "failed", "blocked"):
            report = self.execution_report()
            report["status"] = outcome
            report["steps"].append({"stepId": "test-run:step-2", "type": "domain",
                "maxClaims": 1, "resin": "original", "status": "unknown"})
            # A later uncertain claim can change this family; it must not
            # erase the independently observed first-step gain.
            report["inventory"]["104320"]["count"] = 6
            result = self.verify(report, self.event("execute", outcome), "execute")
            self.assertEqual(result["status"], "failed" if outcome == "failed" else "unknown", result["reason"])
            evidence = result["cultivation"]
            self.assertEqual(evidence["observedGains"], {"104320": 2})
            self.assertEqual(evidence["configuredConfirmedClaims"], {"original": 20, "condensed": 0})
            self.assertIsNone(evidence["actualResinDelta"])
            self.assertTrue(evidence["confirmedSubtotalOnly"])
            self.assertEqual(evidence["verifiedStepResinDelta"], {"original": 20, "condensed": 0})
            self.assertEqual(evidence["verifiedStepIds"], ["test-run:step-1"])
            self.assertEqual(evidence["unverifiedStepIds"], ["test-run:step-2"])

    def test_unknown_single_attempt_does_not_present_zero_as_complete_accounting(self):
        report = self.execution_report()
        report["status"] = "unknown"
        report["steps"][0]["status"] = "unknown"
        result = self.verify(report, self.event("execute", "unknown"), "execute")
        self.assertEqual(result["status"], "unknown")
        evidence = result["cultivation"]
        self.assertEqual(evidence["configuredConfirmedClaims"], {"original": 0, "condensed": 0})
        self.assertTrue(evidence["confirmedSubtotalOnly"])
        self.assertIsNone(evidence["actualResinDelta"])
        self.assertIsNone(evidence["verifiedStepResinDelta"])
        self.assertEqual(evidence["unverifiedStepIds"], ["test-run:step-1"])

    def test_partial_claim_cannot_bypass_success_step_evidence_or_continue_after_unknown(self):
        report = self.execution_report()
        report["status"] = "unknown"
        report["steps"][0]["delta"]["104320"] = 9
        self.assertIsNone(self.verify(report, self.event("execute", "unknown"), "execute")["report"])
        report = self.execution_report()
        second = copy.deepcopy(report["steps"][0])
        second["stepId"] = "test-run:step-2"
        report["steps"][0]["status"] = "unknown"
        report["steps"].append(second)
        report["status"] = "unknown"
        self.assertIsNone(self.verify(report, self.event("execute", "unknown"), "execute")["report"])

    def test_boss_step_requires_static_mapping_and_zero_retry_parameters(self):
        report = self.execution_report()
        report["policy"].update(allowBoss=True, bossValidated=True, bossPartyName="首领队伍")
        report["requiredScanIds"] = ["113071"]
        report["plan"]["requirements"] = {"113071": 46}
        report["inventory"] = {"113071": {"name": "谜土的护符", "count": 4, "status": "exact"}}
        step = report["steps"][0]
        step.update(type="boss", bossName="灵觉隐修的迷者", confirmedConfiguredResinCost=40,
            before={"113071": {"name": "谜土的护符", "count": 2, "status": "exact"}},
            after=copy.deepcopy(report["inventory"]), delta={"113071": 2},
            parameterEvidence={"SpecifyRunCount": True, "RunCount": 1, "UseFragileResin": False,
                "UseTransientResin": False, "ReviveRetryCount": 0, "ReturnToStatueAfterEachRound": False,
                "RewardRecognitionEnabled": True, "Timeout": 180},
            mappingEvidence={"source": "upstream/data/materials.json", "sourceCommit": "3f1e938a6dcd5a34642dad03a91488db8d2da40c",
                "materialIds": ["113071"], "bossName": "灵觉隐修的迷者"})
        data = self.bgi / "User/JsScript/AutoGameCultivation/upstream/data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "materials.json").write_text(json.dumps({"113071": {"executionType": "boss", "bossName": "灵觉隐修的迷者"}}))
        (data / "bettergi-boss-catalog.json").write_text(json.dumps({"bosses": ["灵觉隐修的迷者"]}))
        step['resinAfter']['originalResin'] = 60
        step['actualResinDelta']['original'] = 40
        result = self.verify(report, mode="execute")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["cultivation"]["configuredConfirmedClaims"]["original"], 40)
        for key, value in (("ReviveRetryCount", 1), ("UseFragileResin", True), ("RunCount", True)):
            malformed = copy.deepcopy(report)
            malformed["steps"][0]["parameterEvidence"][key] = value
            self.assertIsNone(self.verify(malformed, mode="execute")["report"])
        malformed = copy.deepcopy(report)
        malformed["steps"][0]["mappingEvidence"]["bossName"] = "错误首领"
        self.assertIsNone(self.verify(malformed, mode="execute")["report"])
        report["policy"]["bossValidated"] = False
        self.assertIsNone(self.verify(report, mode="execute")["report"])

    def test_execution_missing_negative_or_fabricated_delta_is_never_success(self):
        for change in ({"delta": {"104320": 8}}, {"before": {}}, {"status": "unknown"},
            {"maxClaims": 2}, {"confirmedConfiguredResinCost": 40},
            {"after": {"104320": {"name": "测试材料", "count": None, "status": "unknown"}}}):
            report = self.execution_report()
            report["steps"][0].update(change)
            self.assertNotEqual(self.verify(report, mode="execute")["status"], "success")
        report = self.execution_report()
        report["steps"][0]["after"]["104320"]["count"] = 0
        report["steps"][0]["delta"]["104320"] = -2
        self.assertIsNone(self.verify(report, mode="execute")["report"])

    def test_repeated_gain_evidence_and_over_budget_steps_are_rejected(self):
        report = self.execution_report()
        second = copy.deepcopy(report["steps"][0])
        second["stepId"] = "test-run:step-2"
        report["steps"].append(second)
        self.assertNotEqual(self.verify(report, mode="execute")["status"], "success")
        report = self.execution_report()
        report["policy"]["originalResinBudget"] = 0
        self.assertNotEqual(self.verify(report, mode="execute")["status"], "success")

    def test_unknown_checkpoint_and_failed_reports_remain_terminal_claims(self):
        for status, expected in (("unknown", "unknown"), ("blocked", "unknown"), ("failed", "failed")):
            report = self.report()
            report.update(status=status, profile=None, plan=None, inventory={})
            result = self.verify(report, self.event(status=status))
            self.assertEqual(result["status"], expected)
            self.assertTrue(result["cultivation"]["reportVerified"])

    def test_scan_with_steps_target_claim_or_profile_bonus_mismatch_rejects(self):
        reports = [self.execution_report(), self.report(), self.report()]
        reports[0].update(mode="scan", readOnly=True)
        reports[1]["targetReached"] = True
        reports[2]["profile"]["talents"]["skill"]["hasBonus"] = True
        for report in reports:
            self.assertIsNone(self.verify(report)["report"])

    def test_report_does_not_export_private_account_fields(self):
        report = self.report()
        report["uid"] = "private"
        report["profile"]["cookie"] = "private"
        report["plan"]["account"] = {"id": "private"}
        result = self.verify(report)
        self.assertNotIn("private", json.dumps(result, ensure_ascii=False))

    @unittest.skipUnless(sys.platform == "win32", "Windows junction test")
    def test_junction_report_parent_is_rejected_without_reading_outside_file(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "test-run.json").write_text(json.dumps(self.report()))
        junction_bgi = self.root / "junction-bgi"
        parent = junction_bgi / "User/JsScript/AutoGameCultivation"
        parent.mkdir(parents=True)
        link = parent / "record"
        def quote(path):
            return "'" + str(path).replace("'", "''") + "'"
        command = f"New-Item -ItemType Junction -Path {quote(link)} -Target {quote(outside)} | Out-Null"
        created = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True)
        if created.returncode:
            self.skipTest("junction creation unavailable")
        result = verify_cultivation_report(self.event(), junction_bgi, "test-run", "scan", TARGET, self.run)
        self.assertIsNone(result["report"])
        self.assertIn("junction", result["reason"])


if __name__ == "__main__":
    unittest.main()
