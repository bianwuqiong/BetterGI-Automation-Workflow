import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runCultivation,readNativeList} from '../core/operator.js';
import {parseInputs,readProfile,normalizeCounts,createDomainParam,createBossParam,budgetBlocker,verifiedGain,buildPlan,candidateBosses} from '../core/safe.js';
const data={rulebook:JSON.parse(readFileSync(new URL('../upstream/data/rulebook.json',import.meta.url))),materials:JSON.parse(readFileSync(new URL('../upstream/data/materials.json',import.meta.url))),recipes:JSON.parse(readFileSync(new URL('../upstream/data/crafting-recipes.json',import.meta.url))),allowedBosses:JSON.parse(readFileSync(new URL('../upstream/data/bettergi-boss-catalog.json',import.meta.url))).bosses};
const target={characterName:'梦见月瑞希',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:true,weaponTargetLevel:90};
const raw={CharacterName:'梦见月瑞希',Level:80,LevelLimit:80,WeaponName:'讨龙英杰谭',WeaponLevel:80,WeaponLevelLimit:80,AttackLevel:9,AttackHasBonus:false,SkillLevel:12,SkillHasBonus:true,BurstLevel:12,BurstHasBonus:true};
const settings=(policy={},mode='scan')=>({runId:'test-safe-run',mode,targetConfigJson:JSON.stringify(target),policyJson:JSON.stringify(policy)});
test('daily scope rejects unverified multistep and every supplemental resource path',()=>{
  const policy={dailyMode:true,validationScopeId:'today',originalResinBudget:20,condensedResinBudget:0,maxSteps:1,requireZhongliShieldCast:true};
  assert.equal(parseInputs(settings(policy,'execute')).policy.dailyDomainReady,false);
  for(const change of [{originalResinBudget:40},{maxSteps:2},{allowBoss:true},{allowCrafting:true},
    {condensedResinBudget:1},{domainResin:'condensed'},{validationMode:true},{validationAttemptedSources:['domain']},
    {originalResinBudget:201,dailyDomainReady:true}]) assert.throws(()=>parseInputs(settings({...policy,...change},'execute')));
  assert.equal(parseInputs(settings({...policy,dailyDomainReady:true,maxSteps:8,originalResinBudget:160},'execute')).policy.maxSteps,8);
  assert.equal(parseInputs(settings({...policy,maxSteps:8,originalResinBudget:200},'scan')).mode,'scan');
});
function fakeList(items){return {items:[...items],get Count(){return this.items.length;},Clear(){this.items=[];},Add(v){this.items.push(v);},GetRange(start,count){return fakeList(this.items.slice(start,start+count));}};}
class FakeDomainParam {constructor(){this.OriginalResinUseCount=99;this.OriginalResin20UseCount=99;this.OriginalResin40UseCount=99;this.FragileResinUseCount=99;this.TransientResinUseCount=99;this.CondensedResinUseCount=99;this.AutoArtifactSalvage=true;this.ResinPriorityList=fakeList(['脆弱树脂']);} SetCombatStrategyPath(n){return n;}}
function fake({missing=false,badWrite=false,gain=true,rawProfile=raw}={}) {
  const files={};const events=[];let spending=0;let bossSpending=0;let scanned=0;
  return {files,events,get spending(){return spending;},get bossSpending(){return bossSpending;},get scanned(){return scanned;},now:()=>Date.UTC(2026,9,8,0,0),getCharacter:async()=>rawProfile,
    readResinSnapshot:async()=>({originalResin:200-(spending-bossSpending)*20-bossSpending*40,condensedResin:5,
      observedAt:'2026-10-08T00:00:00.000Z',verified:true,mainUiRestored:true}),
    countItems:async(tab,names)=>{scanned++;return missing?{}:Object.fromEntries(names.map(n=>[n,spending&&gain?100001:100000]));},
    AutoDomainParam:FakeDomainParam,runDomain:async p=>{spending++;assert.equal(p.DomainRoundNum,1);},
    AutoBossParam:class {},runBoss:async(p,remaining)=>{bossSpending++;spending++;assert.equal(p.RunCount,1);assert.equal(p.ReviveRetryCount,0);assert.equal(p.UseFragileResin,false);assert.equal(p.UseTransientResin,false);assert.ok(remaining>0&&remaining<=900000);},
    writeText:async(p,c)=>{files[p]=c;return !badWrite;},readText:p=>files[p],emit:e=>events.push(e)};
}
test('scan never calls spender, even with all execution flags and budgets',async()=>{
  const api=fake();const report=await runCultivation(settings({allowDomain:true,domainValidated:true,domainSingleAttemptVerified:true,originalResinBudget:200,allowBoss:true}),api,data);
  assert.equal(api.spending,0);assert.ok(api.scanned>0);assert.equal(report.status,'success');assert.equal(report.readOnly,true);assert.equal(api.events[0].mode,'scan');assert.equal(report.profile.talents.skill.base,9);assert.ok(api.files['record/test-safe-run.json']);
});
test('full read-only scan also exports fresh actual resin after its inventory without resource calls',async()=>{
  const api=fake();let reads=0;
  const original=api.readResinSnapshot;
  api.readResinSnapshot=async()=>{reads++;return original();};
  const report=await runCultivation(settings(),api,data);
  assert.equal(report.metadata.diagnostic,'inventory-and-resin');
  assert.equal(report.resinObservation.originalResin,200);
  assert.equal(report.resinObservation.condensedResin,5);
  assert.equal(report.resinObservation.verified,true);
  assert.equal(reads,1);assert.equal(api.spending,0);assert.deepEqual(report.steps,[]);
});
test('invalid or stale scan resin remains null and cannot stand in for an actual balance',async()=>{
  const api=fake();api.readResinSnapshot=async()=>({originalResin:200,condensedResin:0,
    observedAt:'2026-10-07T00:00:00Z',verified:true,mainUiRestored:true});
  const report=await runCultivation(settings(),api,data);
  assert.equal(report.resinObservation,null);assert.equal(api.spending,0);
  assert.equal(report.status,'unknown');
  assert.ok(report.blockers.some(b=>b.code==='resin_observation_unknown'));
});
test('verified daily scope executes repeated single20 with a durable checkpoint before each',async()=>{
  const api=fake({rawProfile:{...raw,AttackLevel:1,SkillLevel:1,SkillHasBonus:false,BurstLevel:1,BurstHasBonus:false}});
  api.countItems=async(tab,names)=>Object.fromEntries(names.map(n=>[n,n.includes('浮世')?api.spending:0]));
  const originalRun=api.runDomain;
  api.runDomain=async p=>{
    const checkpoint=JSON.parse(api.files['record/test-safe-run.json']);
    assert.equal(checkpoint.steps.length,api.spending+1);
    assert.equal(checkpoint.steps.at(-1).status,'unknown');
    assert.equal(p.OriginalResin20UseCount,1);
    assert.equal(p.OriginalResin40UseCount,0);
    await originalRun(p);
  };
  const report=await runCultivation(settings({dailyMode:true,dailyDomainReady:true,validationScopeId:'today',
    allowDomain:true,domainValidated:false,domainSingleAttemptVerified:true,requireZhongliShieldCast:true,
    originalResinBudget:40,condensedResinBudget:0,maxSteps:2,domainPartyName:'测试队'},'execute'),api,data);
  assert.equal(api.spending,2);
  assert.equal(report.steps.length,2);
  assert.equal(report.status,'success');
  assert.equal(report.spending.configuredConfirmedClaims.original,40);
});
test('missing/-1/-2 remain unknown and are never zero',()=>{
  for(const counts of [{},{item:-1},{item:-2}]) {const v=normalizeCounts([{id:'1',name:'item'}],counts)['1'];assert.equal(v.status,'unknown');assert.equal(v.count,null);}
});
test('incomplete scan exports unknown report with missing IDs and no spending',async()=>{
  const api=fake({missing:true});const report=await runCultivation(settings(),api,data);
  assert.equal(api.spending,0);assert.equal(report.status,'unknown');assert.ok(report.blockers.some(b=>b.code==='inventory_unknown'));assert.equal(api.events[0].status,'unknown');
});
test('character read failure exports schema-complete unknown report without scanning or spending',async()=>{
  const api=fake();api.getCharacter=async()=>{throw new Error('character unavailable');};
  const report=await runCultivation(settings(),api,data);
  assert.equal(report.status,'unknown');assert.equal(report.profile,null);assert.equal(report.plan,null);
  assert.deepEqual(report.inventory,{});assert.deepEqual(report.requiredScanIds,[]);assert.deepEqual(report.manualInventoryIds,[]);
  assert.equal(api.scanned,0);assert.equal(api.spending,0);assert.equal(api.bossSpending,0);
  assert.equal(report.blockers[0].code,'read_or_execution_failed');assert.equal(report.blockers[0].message,'character unavailable');
  assert.deepEqual(JSON.parse(api.files['record/test-safe-run.json']),report);
  assert.equal(api.events[0].status,'unknown');assert.equal(api.events[0].completedSteps,0);
});
test('wrong character / missing weapon / missing bonus flag block profile',()=>{
  for(const profile of [{...raw,CharacterName:'纳西妲'},{...raw,WeaponName:null},{...raw,SkillHasBonus:null},{...raw,SkillLevel:2}]) assert.throws(()=>readProfile(profile,target,data.rulebook));
});
test('report write false never emits verified success',async()=>{
  const api=fake({badWrite:true});await assert.rejects(()=>runCultivation(settings(),api,data),/写入/);assert.deepEqual(api.events,[]);assert.equal(api.spending,0);
});
test('runId traversal and malformed budgets rejected before API activity',async()=>{
  for(const cfg of [{...settings(),runId:'../outside'},{...settings(),policyJson:'{"originalResinBudget":-1}'},{...settings(),policyJson:'{"maxMinutes":16}'}]) {const api=fake();await assert.rejects(()=>runCultivation(cfg,api,data));assert.equal(api.scanned,0);}
});
test('domain construction clears global counts/salvage and fixes one original20 claim',()=>{
  const policy=parseInputs(settings({domainPartyName:'测试队'})).policy;
  const p=createDomainParam(FakeDomainParam,{domainName:'堇色之庭',sundaySelectedValue:'1'},policy);
  assert.equal(p.DomainRoundNum,1);assert.equal(p.OriginalResin20UseCount,1);for(const key of ['OriginalResinUseCount','OriginalResin40UseCount','CondensedResinUseCount','TransientResinUseCount','FragileResinUseCount']) assert.equal(p[key],0);
  assert.equal(p.AutoArtifactSalvage,false);assert.deepEqual(p.ResinPriorityList.items,['原粹树脂']);
});
test('condensed construction cannot use original or supplemental resin',()=>{
  const p=createDomainParam(FakeDomainParam,{domainName:'堇色之庭',sundaySelectedValue:'1'},parseInputs(settings({domainResin:'condensed'})).policy);
  assert.equal(p.CondensedResinUseCount,1);assert.equal(p.OriginalResin20UseCount,0);assert.equal(p.FragileResinUseCount,0);assert.equal(p.TransientResinUseCount,0);
});
test('boss constructor disables retries and supplemental resin',()=>{
  const p=createBossParam(class {},'灵觉隐修的迷者',{bossPartyName:'测试队'});assert.equal(p.RunCount,1);assert.equal(p.ReviveRetryCount,0);assert.equal(p.UseFragileResin,false);assert.equal(p.UseTransientResin,false);
});
test('budget does not prove preservation: actual recent observation required',()=>{
  const now=Date.UTC(2026,9,8);const p=parseInputs(settings({originalResinBudget:200,reserveOriginalResin:40})).policy;
  assert.match(budgetBlocker(p,{original:0,condensed:0},now),/实际树脂/);
  p.actualOriginalResin=50;p.resinObservedAt=new Date(now).toISOString();assert.match(budgetBlocker(p,{original:0,condensed:0},now),/侵占/);
  p.actualOriginalResin=100;assert.equal(budgetBlocker(p,{original:0,condensed:0},now),null);assert.match(budgetBlocker(p,{original:0,condensed:0},now+120001),/120秒/);
});
test('unknown reward or decreases never success and no reward summation',()=>{
  const before={'1':{status:'exact',count:3}};
  assert.equal(verifiedGain(before,{'1':{status:'unknown',count:null}},['1']).verified,false);
  assert.equal(verifiedGain(before,{'1':{status:'exact',count:2}},['1']).verified,false);
  assert.equal(verifiedGain(before,{'1':{status:'exact',count:3}},['1']).verified,false);
  assert.equal(verifiedGain(before,{'1':{status:'exact',count:4}},['1']).delta['1'],1);
});
const farmProfile={...raw,AttackLevel:1,SkillLevel:4,BurstLevel:4};
function farmFake(options={}) {
  const api=fake({...options,rawProfile:farmProfile});
  api.countItems=async(tab,names)=>Object.fromEntries(names.map(n=>[n,api.spending&&options.gain!==false?1:0]));return api;
}
const execPolicy={allowDomain:true,domainValidated:true,domainSingleAttemptVerified:true,domainPartyName:'测试队',originalResinBudget:20,maxSteps:3};
test('unknown budget prevents all resource operations',async()=>{
  const api=farmFake();const report=await runCultivation(settings({...execPolicy,originalResinBudget:null},'execute'),api,data);assert.equal(api.spending,0);assert.equal(report.status,'unknown');assert.ok(report.blockers.some(b=>b.code==='budget_blocked'));
});
test('execute allows one verified claim, updates by exact delta only, respects budget',async()=>{
  const api=farmFake();const report=await runCultivation(settings(execPolicy,'execute'),api,data);assert.equal(api.spending,1);assert.equal(report.steps.length,1);assert.equal(report.steps[0].status,'success');assert.equal(report.steps[0].maxClaims,1);assert.ok(Object.values(report.steps[0].delta).every(v=>v===1));
});
test('unconfirmed claim stops and does not replay',async()=>{
  const api=farmFake({gain:false});const report=await runCultivation(settings({...execPolicy,originalResinBudget:200},'execute'),api,data);assert.equal(api.spending,1);assert.equal(report.status,'unknown');assert.equal(report.steps[0].status,'unknown');
});
test('unknown related category cannot spend even while other metadata is manual',async()=>{
  const api=farmFake();api.countItems=async()=>({});const report=await runCultivation(settings(execPolicy,'execute'),api,data);assert.equal(api.spending,0);assert.equal(report.status,'unknown');
});
test('boss lacking validated flag, route and weekly remain blocked',async()=>{
  const api=farmFake();const report=await runCultivation(settings({allowBoss:true,allowRoutes:true,allowWeekly:true},'execute'),api,data);assert.equal(api.spending,0);for(const code of ['boss_disabled','routes_disabled','weekly_disabled']) assert.ok(report.blockers.some(b=>b.code===code));
});
test('single-attempt preflight proof cannot be omitted',async()=>{
  const api=farmFake();const report=await runCultivation(settings({...execPolicy,domainSingleAttemptVerified:false},'execute'),api,data);assert.equal(api.spending,0);assert.equal(report.status,'unknown');assert.ok(report.plan.domains.every(t=>!t.executable));
});
test('resource claim has durable unknown checkpoint before spender is entered',async()=>{
  const api=farmFake();let entered=false;api.runDomain=async(p,remaining)=>{
    entered=true;assert.ok(remaining>0&&remaining<=15*60000);const checkpoint=JSON.parse(api.files['record/test-safe-run.json']);assert.equal(checkpoint.steps[0].status,'unknown');assert.equal(checkpoint.status,'unknown');throw new Error('fake interruption');
  };
  const report=await runCultivation(settings(execPolicy,'execute'),api,data);assert.equal(entered,true);assert.equal(report.status,'unknown');assert.equal(report.steps.length,1);
});
test('inventory mutation outside chosen category is not added to reported gains',async()=>{
  const api=farmFake();const report=await runCultivation(settings(execPolicy,'execute'),api,data);const step=report.steps[0];assert.ok(!('101206' in step.delta));assert.equal(report.inventory['101206'].count,0);
});
test('failed checkpoint write prevents resource claim entirely',async()=>{
  const api=farmFake();let writes=0;const normal=api.writeText;api.writeText=async(p,c)=>{writes++;if(writes===2)return false;return normal(p,c);};
  const report=await runCultivation(settings(execPolicy,'execute'),api,data);assert.equal(api.spending,0);assert.equal(report.status,'unknown');assert.ok(report.blockers.some(b=>b.code==='read_or_execution_failed'));
});
test('raw account fields are not propagated into the report',async()=>{
  const api=fake({rawProfile:{...raw,UID:[1,2,3,4,5,6,7,8,9].join(''),Cookie:'secret'}});const cfg=settings();cfg.targetConfigJson=JSON.stringify({...target,UID:[1,2,3,4,5,6,7,8,9].join(''),Cookie:'secret'});
  const report=await runCultivation(cfg,api,data);const text=JSON.stringify(report);assert.ok(!text.includes('123456789'));assert.ok(!text.includes('secret'));assert.ok(!text.includes('Cookie'));
});
test('domain priority clone never mutates inherited global shared list',()=>{
  const globalList=fakeList(['浓缩树脂','原粹树脂','脆弱树脂']);
  class SharedParam extends FakeDomainParam {constructor(){super();this.ResinPriorityList=globalList;}}
  const p=createDomainParam(SharedParam,{domainName:'堇色之庭',sundaySelectedValue:'1'},parseInputs(settings()).policy);
  assert.notEqual(p.ResinPriorityList,globalList);assert.deepEqual(globalList.items,['浓缩树脂','原粹树脂','脆弱树脂']);assert.deepEqual(p.ResinPriorityList.items,['原粹树脂']);
});
test('unknown and lower_bound stock never presents a numerical shortage or crafting recommendation',()=>{
  const requirements=new Map([['high',3]]),materials={high:{name:'高阶',status:'supported'},low:{name:'低阶',status:'supported'}},recipes={high:{resultCount:1,inputs:[{id:'low',count:3}]}};
  for(const state of ['unknown','lower_bound']) {
    const inventory={high:{count:state==='lower_bound'?1:null,status:state},low:{count:9,status:'exact'}};
    const plan=buildPlan(requirements,inventory,materials,recipes);assert.equal(plan.shortages[0].shortage,null);assert.equal(plan.shortages[0].owned,null);assert.equal(plan.shortages[0].inventoryKnown,false);assert.deepEqual(plan.crafting.suggestions,[]);assert.equal(inventory.low.count,9);
  }
});
test('3-to-1 suggestion requires complete chain and never changes actual inventory',()=>{
  const req=new Map([['high',3]]),materials={high:{name:'高阶',status:'supported'},low:{name:'低阶',status:'supported'}},recipes={high:{resultCount:1,inputs:[{id:'low',count:3}]}};
  const inventory={high:{count:1,status:'exact'},low:{count:6,status:'exact'}};const before=JSON.stringify(inventory);const plan=buildPlan(req,inventory,materials,recipes);assert.equal(plan.crafting.suggestions[0].craftCount,2);assert.equal(JSON.stringify(inventory),before);assert.equal(plan.crafting.executed,false);assert.equal(plan.shortages[0].inventoryKnown,true);
});
const bossPolicy={allowBoss:true,bossValidated:true,bossPartyName:'首领队',originalResinBudget:40,maxSteps:3,bossTimeoutSeconds:180};
test('gated boss performs one 40-resin claim and verifies only boss material delta',async()=>{
  const api=farmFake();const report=await runCultivation(settings(bossPolicy,'execute'),api,data);assert.equal(api.bossSpending,1);assert.equal(api.spending,1);assert.equal(report.steps.length,1);
  const step=report.steps[0];assert.equal(step.type,'boss');assert.equal(step.bossName,'灵觉隐修的迷者');assert.equal(step.status,'success');assert.equal(step.confirmedConfiguredResinCost,40);assert.deepEqual(step.mappingEvidence.materialIds,['113071']);assert.equal(step.parameterEvidence.ReviveRetryCount,0);assert.equal(step.parameterEvidence.UseFragileResin,false);assert.equal(report.spending.configuredConfirmedClaims.original,40);
});
test('boss missing budget, fewer than40 cap, missing team or missing validation cannot spend',async()=>{
  for(const patch of [{originalResinBudget:null},{originalResinBudget:39},{bossPartyName:''},{bossValidated:false},{allowBoss:false}]) {
    const api=farmFake();const report=await runCultivation(settings({...bossPolicy,...patch},'execute'),api,data);assert.equal(api.spending,0);assert.equal(report.status,'unknown');
  }
});
test('boss unknown material scan forbids claim, including refreshed preflight unknown',async()=>{
  const api=farmFake();let scans=0;api.countItems=async(tab,names)=>{scans++;return Object.fromEntries(names.filter(n=>scans===1||n!=='谜土的护符').map(n=>[n,0]));};
  const report=await runCultivation(settings(bossPolicy,'execute'),api,data);assert.equal(api.bossSpending,0);assert.equal(report.status,'unknown');assert.ok(report.blockers.some(b=>b.code==='pre_reward_unknown'));
});
test('boss task failure or no post gain stops without retry',async()=>{
  for(const fail of [true,false]) {
    const api=farmFake({gain:false});let attempts=0;api.runBoss=async()=>{attempts++;if(fail)throw new Error('fake boss failure');};const report=await runCultivation(settings({...bossPolicy,originalResinBudget:200},'execute'),api,data);assert.equal(attempts,1);assert.equal(report.status,'unknown');assert.equal(report.steps[0].status,'unknown');
  }
});
test('boss static metadata name must also belong to fixed BGI whitelist',()=>{
  const tasks=candidateBosses(new Map([['1',4]]),{'1':{status:'exact',count:0}},{'1':{executionType:'boss',bossName:'未验证的任意字符串'}},parseInputs(settings(bossPolicy)).policy,data.allowedBosses);assert.equal(tasks[0].executable,false);assert.ok(tasks[0].blockers.some(s=>s.includes('白名单')));
});
test('boss reserve checks actual recent amount and its40 cost, regardless of condensed domain setting',()=>{
  const p=parseInputs(settings({...bossPolicy,domainResin:'condensed',condensedResinBudget:5,reserveOriginalResin:40,actualOriginalResin:60,resinObservedAt:'2026-10-08T00:00:00.000Z'})).policy;
  assert.match(budgetBlocker(p,{original:0,condensed:0},Date.UTC(2026,9,8),'boss'),/侵占/);p.actualOriginalResin=80;assert.equal(budgetBlocker(p,{original:0,condensed:0},Date.UTC(2026,9,8),'boss'),null);
});
test('boss timeout is bounded120-180 and scan never calls boss despite valid flags',async()=>{
  assert.throws(()=>parseInputs(settings({...bossPolicy,bossTimeoutSeconds:181})));const api=farmFake();await runCultivation(settings(bossPolicy,'scan'),api,data);assert.equal(api.bossSpending,0);
});

test('protected cultivation sets observed-hold guard and real reward mode',()=>{
  const policy=parseInputs(settings({requireZhongliShieldCast:true})).policy;
  const p=createDomainParam(FakeDomainParam,{domainName:'菫色之庭',sundaySelectedValue:'1'},policy);
  assert.equal(p.RequireZhongliShieldCast,true);assert.equal(p.CombatOnly,false);
  assert.equal(p.OriginalResin20UseCount,1);assert.equal(p.DomainRoundNum,1);
  assert.throws(()=>parseInputs(settings({requireZhongliShieldCast:'true'})));
});
test('initial durable unknown checkpoint is required before every game API',async()=>{
  for(const mismatch of [false,true]) {
    const api=fake({badWrite:!mismatch});let gameCalls=0;
    for(const method of ['getCharacter','readResinSnapshot','countItems','runBoss','runDomain'])
      api[method]=async()=>{gameCalls++;throw new Error('game API must not run');};
    if(mismatch)api.readText=()=>'{"mismatched":true}';
    await assert.rejects(()=>runCultivation(settings({},'execute'),api,data),/初始unknown/);
    assert.equal(gameCalls,0);assert.deepEqual(api.events,[]);
  }
  const api=fake();const reader=api.getCharacter;
  api.getCharacter=async(...args)=>{
    const record=JSON.parse(api.files['record/test-safe-run.json']);
    assert.equal(record.status,'unknown');assert.equal(record.profile,null);assert.equal(record.plan,null);
    assert.deepEqual(record.steps,[]);assert.deepEqual(record.inventory,{});
    return reader(...args);
  };
  assert.equal((await runCultivation(settings(),api,data)).status,'success');
});
test('boss navigation shares bounded remaining node time while native combat retains180s',async()=>{
  const api=farmFake();let invoked=false;
  const original=api.runBoss;
  api.runBoss=async(param,remaining)=>{
    invoked=true;assert.equal(param.Timeout,180);
    assert.ok(remaining>180000 && remaining<=15*60000);
    return original(param,remaining);
  };
  const report=await runCultivation(settings({...bossPolicy,maxMinutes:15},'execute'),api,data);
  assert.equal(invoked,true);assert.equal(report.steps[0].status,'success');
});
test('unaffordable40 boss does not block eligible20 domain in same daily budget',async()=>{
  const api=farmFake();const report=await runCultivation(settings({...bossPolicy,...execPolicy},'execute'),api,data);
  assert.equal(api.bossSpending,0);assert.equal(api.spending,1);assert.equal(report.steps[0].type,'domain');
  assert.deepEqual(report.steps[0].actualResinDelta,{original:20,condensed:0});
  assert.deepEqual(report.spending.actualResinDelta,{original:20,condensed:0});
});
test('current original balance filters expensive boss while leaving cheaper domain eligible',async()=>{
  const api=farmFake();api.readResinSnapshot=async()=>({originalResin:39-api.spending*20,condensedResin:0,observedAt:'2026-10-08T00:00:00.000Z',verified:true,mainUiRestored:true});
  const report=await runCultivation(settings({...bossPolicy,...execPolicy,originalResinBudget:40},'execute'),api,data);
  assert.equal(api.bossSpending,0);assert.equal(api.spending,1);assert.equal(report.steps[0].type,'domain');
});
test('missing stale or unrestored resin observation forbids claims without trusting configured budget',async()=>{
  for(const patch of [null,{verified:false},{mainUiRestored:false},{observedAt:'2026-10-07T23:57:59.000Z'},{originalResin:null}]) {
    const api=farmFake();const normal=api.readResinSnapshot;
    api.readResinSnapshot=patch===null?undefined:async()=>({...await normal(),...patch});
    const report=await runCultivation(settings(execPolicy,'execute'),api,data);
    assert.equal(api.spending,0);assert.equal(report.status,'unknown');assert.ok(report.blockers.some(b=>b.code==='budget_blocked'));
  }
});
test('post-inventory read-only retry accepts only a fresh successful observation before claim',async()=>{
  const api=farmFake();const normal=api.readResinSnapshot;let reads=0;
  api.readResinSnapshot=async()=>{
    reads++;
    if(reads===2)return {originalResin:null,condensedResin:null,observedAt:null,mainUiRestored:true,reason:'incomplete_map_ocr'};
    return normal();
  };
  const spend=api.runBoss;
  api.runBoss=async(...args)=>{assert.equal(reads,3);return spend(...args);};
  const report=await runCultivation(settings(bossPolicy,'execute'),api,data);
  assert.equal(report.steps[0].status,'success');assert.equal(api.bossSpending,1);
});
test('read-only retries remain bounded and abort on unrestored UI, cancellation or deadline',async()=>{
  for(const mode of ['all-fail','unrestored','cancelled','deadline','missing']) {
    const api=farmFake();let calls=0;const start=api.now();
    if(mode==='missing')api.readResinSnapshot=undefined;
    else api.readResinSnapshot=async()=>{
      calls++;
      if(mode==='cancelled')throw new Error('OperationCanceledException');
      if(mode==='deadline')api.now=()=>start+5*60000-11000;
      return {observedAt:null,mainUiRestored:mode!=='unrestored',reason:'incomplete_map_ocr'};
    };
    const report=await runCultivation(settings({...bossPolicy,maxMinutes:5},'execute'),api,data);
    assert.equal(api.bossSpending,0);assert.equal(api.spending,0);assert.equal(report.status,'unknown');
    assert.equal(calls,mode==='all-fail'?3:mode==='missing'?0:1);
  }
});
test('fresh current balances do not subtract prior claims a second time when preserving reserve',async()=>{
  const api=farmFake();api.readResinSnapshot=async()=>({originalResin:100-api.spending*20,condensedResin:5,observedAt:'2026-10-08T00:00:00.000Z',verified:true,mainUiRestored:true});
  api.countItems=async(tab,names)=>Object.fromEntries(names.map(name=>[name,api.spending]));
  const report=await runCultivation(settings({...execPolicy,originalResinBudget:40,reserveOriginalResin:40,maxSteps:2},'execute'),api,data);
  assert.equal(api.spending,2);assert.deepEqual(report.spending.actualResinDelta,{original:40,condensed:0});
});
test('unverified post-claim resin halts after one commit and retains unknown outcome',async()=>{
  const api=farmFake();const normal=api.readResinSnapshot;api.readResinSnapshot=async()=>api.spending?null:normal();
  const report=await runCultivation(settings({...execPolicy,originalResinBudget:100},'execute'),api,data);
  assert.equal(api.spending,1);assert.equal(report.status,'unknown');assert.equal(report.steps[0].status,'unknown');
  assert.equal(report.steps[0].actualResinDelta,null);assert.equal(report.spending.actualResinDelta,null);
});
test('natural resin recovery is preserved as observed net difference rather than configured cost',async()=>{
  const api=farmFake();api.readResinSnapshot=async()=>({originalResin:100-api.spending*19,condensedResin:5,observedAt:'2026-10-08T00:00:00.000Z',verified:true,mainUiRestored:true});
  const report=await runCultivation(settings(execPolicy,'execute'),api,data);
  assert.equal(report.steps[0].status,'success');assert.equal(report.steps[0].confirmedConfiguredResinCost,20);
  assert.equal(report.steps[0].actualResinDelta.original,19);assert.equal(report.spending.actualResinDelta.original,19);
});
test('unexpected supplemental or mixed resin loss cannot pass verified claim',async()=>{
  const api=farmFake();api.readResinSnapshot=async()=>({originalResin:100-api.spending*20,condensedResin:5-api.spending,observedAt:'2026-10-08T00:00:00.000Z',verified:true,mainUiRestored:true});
  const report=await runCultivation(settings({...execPolicy,originalResinBudget:100},'execute'),api,data);
  assert.equal(api.spending,1);assert.equal(report.status,'unknown');assert.equal(report.steps[0].status,'unknown');
});
test('individual original verification permits a hidden condensed icon without inventing its balance',async()=>{
  const api=farmFake();api.readResinSnapshot=async()=>({originalResin:100-api.spending*20,condensedResin:null,originalVerified:true,condensedVerified:false,
    observedAt:'2026-10-08T00:00:00.000Z',verified:false,mainUiRestored:true});
  const report=await runCultivation(settings(execPolicy,'execute'),api,data);
  assert.equal(api.spending,1);assert.equal(report.steps[0].status,'success');
  assert.deepEqual(report.spending.actualResinDelta,{original:20,condensed:null});
});
const validationPolicy={...bossPolicy,...execPolicy,bossValidated:false,domainValidated:false,validationMode:true,originalResinBudget:60,condensedResinBudget:0,maxSteps:2};
test('first validation permits one40 boss and one20 domain without falsely setting validated flags',async()=>{
  const api=farmFake();api.countItems=async(tab,names)=>Object.fromEntries(names.map(name=>[name,api.spending]));
  const report=await runCultivation(settings(validationPolicy,'execute'),api,data);
  assert.equal(api.bossSpending,1);assert.equal(api.spending,2);assert.deepEqual(report.steps.map(s=>s.type),['boss','domain']);
  assert.ok(report.steps.every(s=>s.validationAttempt===true));assert.equal(report.policy.bossValidated,false);assert.equal(report.policy.domainValidated,false);
  assert.equal(report.spending.configuredConfirmedClaims.original,60);
});
test('initial validation permits only one domain category even with two distinct Sunday rewards',async()=>{
  for(const validationMode of [true,false]) {
    const api=farmFake();const names=[];
    api.now=()=>Date.UTC(2026,9,11,0,0);
    api.getCharacter=async()=>({...farmProfile,WeaponName:'祭礼残章'});
    api.readResinSnapshot=async()=>({originalResin:200-api.spending*20,condensedResin:0,
      observedAt:new Date(api.now()).toISOString(),verified:true,mainUiRestored:true});
    api.countItems=async(tab,items)=>Object.fromEntries(items.map(name=>[name,
      name.includes('浮世')&&api.spending?100000:api.spending>1?1:0]));
    const spend=api.runDomain;
    api.runDomain=async(param,...args)=>{
      const checkpoint=JSON.parse(api.files['record/test-safe-run.json']);
      if(!names.length)assert.equal(checkpoint.plan.domains.filter(t=>t.executable).length,2);
      names.push(param.DomainName);return spend(param,...args);
    };
    const report=await runCultivation(settings({...validationPolicy,validationMode,domainValidated:!validationMode,
      allowBoss:false,maxSteps:2},'execute'),api,data);
    assert.equal(report.status,'success');assert.equal(names.length,validationMode?1:2);
    if(!validationMode)assert.equal(new Set(names).size,2);
  }
});
test('validation cannot repeat same source or exceed60/2 steps/use condensed/enable crafting',async()=>{
  const api=farmFake();const report=await runCultivation(settings({...validationPolicy,allowBoss:false},'execute'),api,data);
  assert.equal(api.spending,1);assert.equal(report.steps.length,1);
  for(const patch of [{originalResinBudget:61},{originalResinBudget:null},{maxSteps:3},{condensedResinBudget:1},{domainResin:'condensed'},{allowCrafting:true}]) assert.throws(()=>parseInputs(settings({...validationPolicy,...patch},'execute')),/初验/);
});
test('validation scope and reserved attempted sources survive canonical policy and cannot replay their categories',async()=>{
  const cfg=settings({...validationPolicy,validationScopeId:'mizuki-20261008-first',validationAttemptedSources:['boss']},'execute');
  const parsed=parseInputs(cfg);assert.equal(parsed.policy.validationScopeId,'mizuki-20261008-first');assert.deepEqual(parsed.policy.validationAttemptedSources,['boss']);
  const api=farmFake();const report=await runCultivation(cfg,api,data);
  assert.equal(api.bossSpending,0);assert.equal(api.spending,1);assert.equal(report.steps[0].type,'domain');
  assert.equal(report.policy.validationScopeId,'mizuki-20261008-first');assert.deepEqual(report.policy.validationAttemptedSources,['boss']);
  assert.ok(report.plan.bosses.every(task=>!task.executable && task.blockers.some(b=>b.includes('scope'))));
  const allReserved=farmFake();const blocked=await runCultivation(settings({...validationPolicy,validationScopeId:'scope',validationAttemptedSources:['boss','domain']},'execute'),allReserved,data);
  assert.equal(allReserved.spending,0);assert.ok(blocked.plan.domains.every(task=>!task.executable && task.blockers.some(b=>b.includes('scope'))));
});
test('validation scope rejects unsafe strings and duplicate or unsupported attempted categories outside initial validation',()=>{
  for(const patch of [{validationScopeId:1},{validationScopeId:'../scope'},{validationScopeId:'a'.repeat(81)},{validationAttemptedSources:'boss'},{validationAttemptedSources:['boss','boss']},{validationAttemptedSources:['crafting']},{validationAttemptedSources:[null]}]) assert.throws(()=>parseInputs(settings({...validationPolicy,...patch},'execute')));
  for(const patch of [{validationScopeId:'scope'},{validationAttemptedSources:['domain']}]) assert.throws(()=>parseInputs(settings({...execPolicy,...patch},'execute')),/仅初验/);
  const normal=parseInputs(settings(execPolicy,'execute')).policy;assert.equal(normal.validationScopeId,'');assert.deepEqual(normal.validationAttemptedSources,[]);
});

function craftFake({bonus=0,refund=false,failure=false,wrongResult=false,noGain=false,mainUiRestored=true}={}) {
  const api=fake({rawProfile:farmProfile}),stock={'「浮世」的教导':117,'「浮世」的指引':129,'「浮世」的哲学':32};
  api.crafts=[];
  api.countItems=async(tab,names)=>Object.fromEntries(names.map(name=>[name,stock[name]??100000]));
  api.runCrafting=async(job,remaining)=>{
    const checkpoint=JSON.parse(api.files['record/test-safe-run.json']);assert.equal(checkpoint.steps.at(-1).status,'unknown');
    assert.ok(remaining>0 && remaining<=15*60000);api.crafts.push(job);
    if(failure)throw new Error('after possible craft commit');
    const source=data.recipes[job.materialId].inputs[0].id,sourceName=data.materials[source].name;
    if(!noGain) {stock[sourceName]-=job.craftCount*3-(refund?1:0);stock[job.materialName]+=job.craftCount+bonus;}
    return {Success:true,MainUiRestored:mainUiRestored,MaterialName:job.materialName,TargetQuantity:job.craftCount,ActualQuantity:job.craftCount+(wrongResult?1:0),Rewards:[{name:job.materialName,count:999999}]};
  };
  return api;
}
const craftingPolicy={allowCrafting:true,craftingValidated:true,maxSteps:2};
test('material crafting performs bounded dependent batches and accounts only exact observed consumption/gain',async()=>{
  const api=craftFake();const report=await runCultivation(settings(craftingPolicy,'execute'),api,data);
  assert.equal(api.crafts.length,2);assert.equal(api.spending,0);assert.equal(report.status,'success');
  assert.deepEqual(report.steps.map(s=>s.materialId),['104321','104322']);assert.deepEqual(report.steps.map(s=>s.craftCount),[36,34]);
  assert.ok(report.steps.every(s=>s.type==='crafting' && s.maxClaims===1 && s.resin==='none'));
  assert.deepEqual(report.steps[0].materialsSpent,{'104320':108});assert.equal(report.inventory['104320'].count,9);
  assert.equal(report.inventory['104321'].count,63);assert.equal(report.inventory['104322'].count,66);
  assert.equal(report.plan.crafting.executed,false);assert.equal(report.plan.crafting.suggestionsOnly,true);
  assert.equal(report.spending.configuredConfirmedClaims.original,0);assert.ok(report.steps[0].moraCostStatus.includes('未读取'));
});
test('scan and unvalidated/disallowed crafting gates cannot spend materials',async()=>{
  for(const [policy,mode] of [[craftingPolicy,'scan'],[{...craftingPolicy,allowCrafting:false},'execute'],[{...craftingPolicy,craftingValidated:false},'execute']]) {
    const api=craftFake();await runCultivation(settings(policy,mode),api,data);assert.equal(api.crafts.length,0);
  }
  assert.throws(()=>parseInputs(settings({...craftingPolicy,craftingCountry:'未知国家'})),/合成台/);
});
test('material crafting ignores reported rewards and accepts only observed bounded bonus output',async()=>{
  const api=craftFake({bonus:1});const report=await runCultivation(settings({...craftingPolicy,maxSteps:1},'execute'),api,data);
  assert.equal(report.steps[0].status,'success');assert.equal(report.steps[0].delta['104321'],37);
  assert.equal(report.inventory['104321'].count,166);assert.ok(!JSON.stringify(report).includes('999999'));
});
test('refunded input, excessive output, wrong batch evidence, zero gain or interrupted crafting never replay',async()=>{
  for(const options of [{refund:true},{bonus:37},{wrongResult:true},{noGain:true},{failure:true}]) {
    const api=craftFake(options);const report=await runCultivation(settings({...craftingPolicy,maxSteps:5},'execute'),api,data);
    assert.equal(api.crafts.length,1);assert.equal(report.status,'unknown');assert.equal(report.steps[0].status,'unknown');
  }
});
test('unknown material chain or failed durable crafting checkpoint prevents entering crafting API',async()=>{
  const api=craftFake();const normal=api.countItems;api.countItems=async(tab,names)=>({...await normal(tab,names),'「浮世」的指引':-1});
  await runCultivation(settings(craftingPolicy,'execute'),api,data);assert.equal(api.crafts.length,0);
  const blocked=craftFake();let writes=0;const write=blocked.writeText;blocked.writeText=async(p,c)=>++writes===2?false:write(p,c);
  const report=await runCultivation(settings(craftingPolicy,'execute'),blocked,data);assert.equal(blocked.crafts.length,0);assert.equal(report.status,'unknown');
});
test('domain checkpoint records actual native parameter fields and the exact recorded instance is executed',async()=>{
  let instance=null,constructions=0;
  function nativeList(values=[]) {
    return {get Count(){return values.length;},get_Item(index){return values[index];},Clear(){values=[];},Add(value){values.push(value);},GetRange(start,count){return nativeList(values.slice(start,start+count));}};
  }
  class NativeParam extends FakeDomainParam {constructor(){super();constructions++;instance=this;this.ResinPriorityList=nativeList(['脆弱树脂']);}}
  const api=farmFake();api.AutoDomainParam=NativeParam;const run=api.runDomain;
  api.runDomain=async(param,remaining)=>{
    assert.equal(param,instance);assert.equal(constructions,1);
    const checkpoint=JSON.parse(api.files['record/test-safe-run.json']),step=checkpoint.steps[0];
    for(const key of ['DomainRoundNum','DomainName','PartyName','SundaySelectedValue','AutoArtifactSalvage','SpecifyResinUse','OriginalResinUseCount','OriginalResin20UseCount','OriginalResin40UseCount','CondensedResinUseCount','TransientResinUseCount','FragileResinUseCount','RewardRecognitionEnabled']) assert.equal(step.parameterEvidence[key],param[key]);
    assert.deepEqual(step.parameterEvidence.ResinPriorityList,['原粹树脂']);
    assert.equal(step.mappingEvidence.domainName,param.DomainName);assert.equal(step.mappingEvidence.sundaySelectedValue,param.SundaySelectedValue);
    assert.equal(step.mappingEvidence.source,'upstream/data/materials.json');
    assert.deepEqual(step.mappingEvidence.materialIds,['104320','104321','104322']);
    return run(param,remaining);
  };
  const report=await runCultivation(settings({...validationPolicy,allowBoss:false},'execute'),api,data);assert.equal(report.steps[0].status,'success');
});
test('native iterable without CLR accessor reads actual single-resin list before the same instance is executed',async()=>{
  let instance=null,constructions=0;
  function nativeList(values=[]) {
    return {get Count(){return values.length;},*[Symbol.iterator](){yield* values;},Clear(){values=[];},
      Add(value){values.push(value);},GetRange(start,count){return nativeList(values.slice(start,start+count));}};
  }
  class NativeParam extends FakeDomainParam {constructor(){super();constructions++;instance=this;this.ResinPriorityList=nativeList(['脆弱树脂']);}}
  const api=farmFake();api.AutoDomainParam=NativeParam;const run=api.runDomain;
  api.runDomain=async(param,remaining)=>{
    assert.equal(param,instance);assert.equal(constructions,1);assert.equal(param.ResinPriorityList.get_Item,undefined);
    assert.deepEqual(readNativeList(param.ResinPriorityList),['原粹树脂']);
    const step=JSON.parse(api.files['record/test-safe-run.json']).steps[0];
    assert.deepEqual(step.parameterEvidence.ResinPriorityList,['原粹树脂']);assert.equal(step.parameterEvidence.OriginalResin20UseCount,1);
    for(const key of ['OriginalResinUseCount','OriginalResin40UseCount','CondensedResinUseCount','FragileResinUseCount','TransientResinUseCount'])assert.equal(step.parameterEvidence[key],0);
    return run(param,remaining);
  };
  const report=await runCultivation(settings({...validationPolicy,allowBoss:false},'execute'),api,data);
  assert.equal(api.spending,1);assert.equal(report.steps[0].status,'success');
});
test('native list Count, iterator, string contents and enumeration failure remain fail closed',()=>{
  const iterable=(values,count=values.length)=>({Count:count,*[Symbol.iterator](){yield* values;}});
  assert.deepEqual(readNativeList(iterable(['原粹树脂'])),['原粹树脂']);
  for(const list of [iterable(['原粹树脂'],0),iterable(['原粹树脂'],2),iterable(['原粹树脂'],-1),iterable(['原粹树脂'],11),
    iterable(['原粹树脂'],true),{*[Symbol.iterator](){yield '原粹树脂';}}, {Count:1},iterable([null]),iterable([1]),
    {get Count(){throw new Error('Count failure');},*[Symbol.iterator](){yield '原粹树脂';}},
    {Count:1,*[Symbol.iterator](){throw new Error('enumeration failure');}},
    {Count:1,get_Item(){throw new Error('accessor failure');}}])assert.throws(()=>readNativeList(list));
});
test('unreadable or foreign actual resin list cannot checkpoint a resource step or call the domain',async()=>{
  for(const mode of ['count-mismatch','no-iterator','foreign-item','non-string','no-count','negative-count','enum-failed']){
    function nativeList(values=[]) {
      const list={Clear(){values=[];},Add(value){values.push(value);},GetRange(){return nativeList();}};
      if(mode!=='no-count')Object.defineProperty(list,'Count',{get:()=>mode==='negative-count'?-1:mode==='count-mismatch'?2:values.length});
      if(mode!=='no-iterator')list[Symbol.iterator]=function*(){if(mode==='enum-failed')throw new Error('native enumeration failed');yield* mode==='foreign-item'?['脆弱树脂']:mode==='non-string'?[true]:values;};
      return list;
    }
    class NativeParam extends FakeDomainParam {constructor(){super();this.ResinPriorityList=nativeList();}}
    const api=farmFake();api.AutoDomainParam=NativeParam;
    const report=await runCultivation(settings({...validationPolicy,allowBoss:false},'execute'),api,data);
    assert.equal(api.spending,0,mode);assert.equal(report.status,'unknown',mode);assert.deepEqual(report.steps,[],mode);
    assert.deepEqual(JSON.parse(api.files['record/test-safe-run.json']).steps,[],mode);
  }
});
test('boss checkpoint reflects its constructed parameters and passes that same instance to engine',async()=>{
  let instance=null,constructions=0;class BossParam {constructor(){constructions++;instance=this;}}
  const api=farmFake();api.AutoBossParam=BossParam;const run=api.runBoss;
  api.runBoss=async(param,remaining)=>{
    assert.equal(param,instance);assert.equal(constructions,1);
    const step=JSON.parse(api.files['record/test-safe-run.json']).steps[0];
    for(const [key,value] of Object.entries(step.parameterEvidence)) assert.equal(value,param[key]);
    assert.equal(step.parameterEvidence.BossName,'灵觉隐修的迷者');assert.equal(step.parameterEvidence.TeamName,'首领队');
    return run(param,remaining);
  };
  const report=await runCultivation(settings(bossPolicy,'execute'),api,data);assert.equal(report.steps[0].status,'success');
});
test('reflected unsafe parameters are rejected before checkpoint/engine entry',async()=>{
  class CorruptedDomain extends FakeDomainParam {constructor(){super();Object.defineProperty(this,'OriginalResin20UseCount',{get:()=>2,set:()=>{}});}}
  const api=farmFake();api.AutoDomainParam=CorruptedDomain;
  const report=await runCultivation(settings(execPolicy,'execute'),api,data);
  assert.equal(api.spending,0);assert.equal(report.status,'unknown');assert.ok(report.blockers.some(b=>b.message?.includes('实际资源参数')));
  class CorruptedBoss {constructor(){Object.defineProperty(this,'ReviveRetryCount',{get:()=>3,set:()=>{}});}}
  const boss=farmFake();boss.AutoBossParam=CorruptedBoss;const bossReport=await runCultivation(settings(bossPolicy,'execute'),boss,data);
  assert.equal(boss.bossSpending,0);assert.equal(bossReport.status,'unknown');
});
test('crafting must report verified main UI restoration and cannot replay even with matching actual material delta',async()=>{
  for(const missing of [false,true]) {
    const api=craftFake({mainUiRestored:false});const run=api.runCrafting;
    api.runCrafting=async(...args)=>{const result=await run(...args);if(missing)delete result.MainUiRestored;return result;};
    const report=await runCultivation(settings({...craftingPolicy,maxSteps:5},'execute'),api,data);
    assert.equal(api.crafts.length,1);assert.equal(report.status,'unknown');assert.equal(report.steps[0].resultEvidence.MainUiRestored,false);
    assert.equal(report.steps[0].delta['104320'],-108);assert.equal(report.steps[0].delta['104321'],36);
  }
});

test('resin-only diagnostic never reads character, inventory or calls a spender',async()=>{
  const api=fake();
  api.getCharacter=async()=>{throw new Error('must not read character');};
  api.countItems=async()=>{throw new Error('must not read inventory');};
  const snapshot={originalResin:143,condensedResin:null,originalVerified:true,condensedVerified:false,
    verified:false,observedAt:'2026-10-08T00:00:00.000Z',mainUiRestored:true,reason:'incomplete_map_ocr'};
  api.readResinSnapshot=async()=>snapshot;
  const report=await runCultivation({...settings(),resinDiagnosticOnly:true},api,data);
  assert.equal(report.status,'unknown');assert.equal(report.metadata.diagnostic,'resin-only');
  assert.deepEqual(report.resinObservation,snapshot);assert.equal(report.profile,null);assert.equal(report.plan,null);
  assert.deepEqual(report.inventory,{});assert.deepEqual(report.steps,[]);assert.equal(api.spending,0);
});
