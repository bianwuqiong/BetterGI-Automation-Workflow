import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runArtifacts,safeCraftRequest} from '../operator.js';

const base=JSON.parse(readFileSync(new URL('../../../config/artifact-farming.example.json',import.meta.url)));
class List {constructor(items=[]){this.items=items;}GetRange(){return new List();}Add(v){this.items.push(v);}get Count(){return this.items.length;}}
class Param {constructor(){this.ResinPriorityList=new List(['脆弱树脂']);}SetCombatStrategyPath(name){return `C:\\fake\\User\\AutoFight\\${name}.txt`;}}
function harness(options={}) {
  let time=Date.parse('2026-10-11T16:00:00Z'),original=options.original??95,condensed=options.condensed??0,domainCalls=0,craftCalls=0;
  const config=structuredClone(base);
  config.executionEnabled=true;
  Object.assign(config.policy,{domainValidated:true,maxClaims:2,maxMinutes:15,originalResinBudget:100,condensedResinBudget:5,maxCrafts:1,craftingValidated:true,craftOriginalResinCost:60,condensedCapacity:5,validationOnly:false},options.policy);
  const files=new Map(),events=[],craftRequests=[];
  const settings={runId:'run-test',gameDate:'2026-10-11',configJson:JSON.stringify(config),configSha256:'a'.repeat(64),singleAttemptVerified:true,artifactRewardNamesJson:'["梦中的铁花"]'};
  const api={now:()=>time,AutoDomainParam:Param,readText:path=>files.get(path),writeText:async(path,text)=>{files.set(path,text);return !options.writeFailure;},emit:e=>events.push(e),
    async readResinSnapshot(){return {originalResin:original,condensedResin:condensed,originalVerified:true,condensedVerified:!options.unknownBalance,mainUiRestored:true,observedAt:new Date(time).toISOString()};},
    async runCraft(country,count,budget,reserve,timeout){if(budget===0)return {Status:'skipped',OriginalResinSpent:0,CondensedResinCreated:0,MainUiRestored:true,RecipeOriginalResinCost:60,RecipeCostVerified:true,SafeCondensedCapacity:5,CondensedCapacityObserved:false};craftCalls++;craftRequests.push({count,budget,reserve});const before=original,cBefore=condensed,created=Math.min(count,options.partialLimit??count);original-=60*created-(options.badCraftDelta?1:0);condensed+=created;time+=1000;return {Status:'success',OriginalResinBefore:before,OriginalResinAfter:original,CondensedResinBefore:cBefore,CondensedResinAfter:condensed,OriginalResinSpent:60*created,CondensedResinCreated:created+(options.badCreatedCount?1:0),MainUiRestored:true};},
    async runDomain(param){domainCalls++;const saved=JSON.parse(files.get('record/run-test.json'));assert.equal(saved.steps.at(-1).status,'unknown');assert.equal(param.DomainRoundNum,1);assert.equal(param.FragileResinUseCount,0);assert.equal(param.TransientResinUseCount,0);assert.equal(param.AutoArtifactSalvage,false);if(param.CombatOnly)return {};if(param.CondensedResinUseCount)condensed--;else original-=20;time+=60000;if(options.throwAfterSpend)throw Error('native return unknown');return options.emptyReward?{}:options.moraOnly?{摩拉:10000}:{梦中的铁花:3};}};
  return {api,settings,files,events,craftRequests,get domainCalls(){return domainCalls;},get craftCalls(){return craftCalls;}};
}
test('bounded craft-first then single condensed/original claim batch persists every step',async()=>{
  const h=harness(),r=await runArtifacts(h.settings,h.api);assert.equal(r.status,'success');assert.deepEqual(r.steps.map(s=>s.type),['craft','claim','claim']);assert.deepEqual(r.steps.filter(s=>s.type==='claim').map(s=>s.resin),['condensed','original']);assert.deepEqual(r.totals,{originalResinSpent:80,condensedResinSpent:1,crafts:1,claims:2});assert.equal(r.targetReached,false);
});
test('empty actual reward or native exception after spend stays unknown and stops',async()=>{
  for(const options of [{emptyReward:true},{throwAfterSpend:true},{moraOnly:true}]){const h=harness(options),r=await runArtifacts(h.settings,h.api);assert.equal(r.status,'unknown');assert.equal(h.domainCalls,1);assert.equal(r.steps.at(-1).status,'unknown');await assert.rejects(()=>runArtifacts(h.settings,h.api),/checkpoint already exists/);assert.equal(h.domainCalls,1);}
});
test('unknown balance or checkpoint write failure cannot call consumption',async()=>{
  const h=harness({unknownBalance:true}),r=await runArtifacts(h.settings,h.api);assert.equal(r.status,'unknown');assert.equal(h.domainCalls+h.craftCalls,0);
  const f=harness({writeFailure:true});await assert.rejects(()=>runArtifacts(f.settings,f.api));assert.equal(f.domainCalls+f.craftCalls,0);
});
test('reserve and consumed scope budgets stop safely without treating budget as actual stock',async()=>{
  const h=harness({policy:{reserveOriginalResin:90}}),r=await runArtifacts(h.settings,h.api);assert.equal(r.status,'success');assert.equal(h.domainCalls+h.craftCalls,0);
});
test('validation is a zero-spend same-domain challenge, never artifact farming success',async()=>{
  const h=harness({policy:{validationOnly:true,domainValidated:false,maxClaims:1,maxCrafts:0,originalResinBudget:0,condensedResinBudget:0}}),r=await runArtifacts(h.settings,h.api);assert.equal(r.status,'success');assert.equal(r.steps[0].type,'validation');assert.equal(r.steps[0].parameterEvidence.CombatOnly,true);assert.equal(r.totals.claims,0);assert.equal(h.craftCalls,0);
});
test('wrong game day and forbidden refill fail before checkpoint/game APIs',async()=>{
  const h=harness();h.settings.gameDate='2026-10-10';await assert.rejects(()=>runArtifacts(h.settings,h.api));assert.equal(h.domainCalls+h.craftCalls,0);
  const f=harness({policy:{fragileResinBudget:1}});await assert.rejects(()=>runArtifacts(f.settings,f.api));assert.equal(f.domainCalls+f.craftCalls,0);
});
test('explicit authorization deadline cancels remaining resource calls without extending approval',async()=>{
  const h=harness();h.settings.validUntilUTC='2026-10-11T16:00:30Z';const r=await runArtifacts(h.settings,h.api);
  assert.equal(r.status,'unknown');assert.equal(h.domainCalls,1);assert.equal(r.steps.at(-1).status,'unknown');
  const f=harness();f.settings.validUntilUTC='2026-10-11T15:59:59Z';await assert.rejects(()=>runArtifacts(f.settings,f.api));assert.equal(f.domainCalls+f.craftCalls,0);
});
test('two or three items use one bounded native commit and account only actual output',async()=>{
  for(const count of [2,3]){
    const h=harness({original:200,policy:{originalResinBudget:count*60,maxCrafts:count,maxClaims:count}}),r=await runArtifacts(h.settings,h.api);
    assert.equal(r.status,'success');assert.equal(h.craftCalls,1);assert.equal(r.steps[0].requestedCount,count);
    assert.equal(r.steps[0].actualCreated,count);assert.equal(r.steps[0].partialQuantity,false);
    assert.deepEqual(h.craftRequests,[{count,budget:count*60,reserve:0}]);
    assert.equal(r.totals.crafts,count);assert.equal(r.totals.originalResinSpent,count*60);assert.equal(r.totals.condensedResinSpent,count);
  }
});
test('craft request obeys capacity, actual balance, reserve, scope budgets and native ceiling',()=>{
  const p={preferCondensed:true,condensedResinBudget:20,maxCrafts:20,craftOriginalResinCost:60,condensedCapacity:5,reserveOriginalResin:0,originalResinBudget:200};
  const t={crafts:0,originalResinSpent:0,condensedResinSpent:0};
  assert.equal(safeCraftRequest(p,t,{originalResin:200,condensedResin:0}),3);
  assert.equal(safeCraftRequest(p,t,{originalResin:200,condensedResin:4}),1);
  assert.equal(safeCraftRequest({...p,originalResinBudget:120},t,{originalResin:200,condensedResin:0}),2);
  assert.equal(safeCraftRequest({...p,reserveOriginalResin:90},t,{originalResin:200,condensedResin:0}),1);
  assert.equal(safeCraftRequest(p,{...t,originalResinSpent:180},{originalResin:200,condensedResin:0}),0);
  assert.equal(safeCraftRequest({...p,craftOriginalResinCost:20,condensedCapacity:20},t,{originalResin:200,condensedResin:0}),5);
});
test('verified partial actual quantity is explicit and later calls remain bounded',async()=>{
  const h=harness({original:200,partialLimit:2,policy:{maxCrafts:3,maxClaims:3,originalResinBudget:180}}),r=await runArtifacts(h.settings,h.api);
  assert.equal(r.status,'success');assert.deepEqual(h.craftRequests.map(row=>row.count),[3,1]);
  assert.equal(r.steps[0].requestedCount,3);assert.equal(r.steps[0].actualCreated,2);assert.equal(r.steps[0].partialQuantity,true);
  assert.equal(r.totals.crafts,3);assert.equal(r.totals.originalResinSpent,180);
});
test('batch output count or actual balance discrepancy remains unknown without claim or replay',async()=>{
  for(const options of [{badCreatedCount:true},{badCraftDelta:true}]){
    const h=harness({...options,original:200,policy:{maxCrafts:3,maxClaims:3,originalResinBudget:180}}),r=await runArtifacts(h.settings,h.api);
    assert.equal(r.status,'unknown');assert.equal(h.craftCalls,1);assert.equal(h.domainCalls,0);assert.equal(r.steps[0].status,'unknown');
    await assert.rejects(()=>runArtifacts(h.settings,h.api),/checkpoint already exists/);assert.equal(h.craftCalls,1);
  }
});
