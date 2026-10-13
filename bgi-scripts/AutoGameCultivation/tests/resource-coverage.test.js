import test from 'node:test';
import assert from 'node:assert/strict';
import {runCultivation} from '../core/operator.js';
import {verifyMoraObservation,experienceRequest} from '../core/resource-coverage.js';
import {createBackpackInventoryReader} from '../core/backpack-reader.js';
const BASE=Date.UTC(2026,9,11,16),rect=(x,y,width,height)=>({x,y,width,height}),row=(text,r)=>({text,...r});
function mora(score=.91) {
  const frame=at=>({observedAt:BASE+at,width:1920,height:1080,backpackTabVerified:true,promptVisible:false,
    headerRows:[row('贵重道具',rect(120,25,170,35))],iconName:'摩拉',iconScore:score,
    iconRegion:rect(354,1000,37,37),balanceRegion:rect(397,1000,140,40),
    balanceRows:[row('125000',rect(410,1008,95,25))],rawBalanceText:'125000'});
  return {source:'precious_items_bottom_mora',materialId:'202',materialName:'摩拉',readOnly:true,status:'verified',balance:125000,
    verified:true,observedAt:new Date(BASE+700).toISOString(),mainUiRestored:true,cleanupCompleted:true,first:frame(400),second:frame(700)};
}
function ores() {
  const observations={};
  for(const [i,material] of experienceRequest().materials.entries()) {
    const selection={itemRect:rect(110,300,125,150),x:172,y:365,clickedAt:BASE+2000+i*500};
    const frame=at=>({observedAt:at,nameRegion:rect(1300,90,500,80),selectedItemVerified:true,selectedItemRect:{...selection.itemRect},
      countMethod:'raw_ocr_without_detector',rawCountText:'12',nameRows:[row(material.materialName,rect(1320,110,300,30))],
      countRegion:rect(110,415,125,35),countRows:[row('12',rect(160,420,30,25))]});
    observations[material.materialId]={selection,first:frame(selection.clickedAt+200),second:frame(selection.clickedAt+400)};
  }
  return {category:'weaponExperience',source:'backpack_selected_stack',readOnly:true,mainUiRestored:true,cleanupCompleted:true,observations};
}
function harness(options={}) {
  let now=BASE,moraCalls=0,oreCalls=0;const files={};
  const settings={runId:'coverage-test',mode:'scan',resourceDiagnosticOnly:true,
    targetConfigJson:JSON.stringify({characterName:'梦见月瑞希',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:true,weaponTargetLevel:90}),
    policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:0})};
  const forbidden=async()=>{throw Error('normal profile/inventory/spend API must not run');};
  const api={now:()=>now,getCharacter:forbidden,countItems:forbidden,runDomain:forbidden,runBoss:forbidden,runCrafting:forbidden,
    readMoraSnapshot:async budget=>{moraCalls++;assert.ok(budget>0);now=BASE+1000;const r=mora(options.score??.91);if(options.badCleanup){r.mainUiRestored=false;r.cleanupCompleted=false;}return r;},
    readBackpackInventory:async(request,budget)=>{oreCalls++;assert.deepEqual(request,experienceRequest());assert.ok(budget>0);now=BASE+4000;const r=ores();if(options.missing)delete r.observations['104012'];return r;},
    writeText:async(path,text)=>{files[path]=text;return true;},readText:path=>files[path],emit:()=>{}};
  return {settings,api,files,get moraCalls(){return moraCalls;},get oreCalls(){return oreCalls;}};
}
test('separate zero-budget resource coverage preserves raw frames without normal material inventory',async()=>{
  const h=harness(),report=await runCultivation(h.settings,h.api,{});
  assert.equal(report.status,'success');assert.equal(report.metadata.diagnostic,'resource-coverage-only');
  assert.equal(report.resourceCoverage.inventory['202'].count,125000);
  assert.deepEqual(Object.keys(report.resourceCoverage.inventory).sort(),['104011','104012','104013','202']);
  assert.equal(report.resourceCoverage.inventory['104013'].count,12);assert.deepEqual(report.inventory,{});
  assert.equal(report.profile,null);assert.equal(report.plan,null);assert.deepEqual(report.steps,[]);assert.equal(report.targetReached,false);
  assert.equal(report.resourceCoverage.upgradeBudgetComplete,false);assert.equal(h.moraCalls,1);assert.equal(h.oreCalls,1);
  assert.ok(JSON.parse(h.files['record/coverage-test.json']).resourceCoverage.moraObservation.first);
});
test('weak Mora model, missing mineral or unverified cleanup stays overall unknown with nullable counts',async()=>{
  for(const options of [{score:.431},{missing:true},{badCleanup:true}]){
    const h=harness(options),r=await runCultivation(h.settings,h.api,{});assert.equal(r.status,'unknown');
    if(options.score||options.badCleanup)assert.equal(r.resourceCoverage.inventory['202'].count,null);
    if(options.missing)assert.equal(r.resourceCoverage.inventory['104012'].count,null);
    if(options.badCleanup)assert.equal(h.oreCalls,0);
  }
});
test('Mora full integer/page/model two-frame proof rejects identity and quantity ambiguity',()=>{
  for(const mutate of [r=>r.second.iconName='原石',r=>r.second.rawBalanceText='125,000',r=>r.second.balanceRows[0].x=397,
    r=>r.second.observedAt=r.first.observedAt,r=>r.second.balanceRows[0].text='125001',r=>r.second.headerRows[0].text='角色培养道具']){
    const r=mora();mutate(r);assert.equal(verifyMoraObservation(r,BASE,BASE+4000).status,'unknown');
  }
});
test('weapon experience JSON bridge is fixed-name/category only and keeps linked cancellation bounded',async()=>{
  let calls=0,disposed=0;
  const dispatcher={GetLinkedCancellationTokenSource:()=>({Token:'token',CancelAfter:ms=>assert.equal(ms,5000),Dispose:()=>disposed++}),
    ReadBackpackInventory:async(json,token)=>{calls++;assert.deepEqual(JSON.parse(json),experienceRequest());assert.equal(token,'token');return JSON.stringify(ores());}};
  const reader=createBackpackInventoryReader({dispatcher});
  await reader(experienceRequest(),5000);assert.equal(calls,1);assert.equal(disposed,1);
  for(const request of [{materials:experienceRequest().materials}, {category:'weaponExperience',materials:[{materialId:'104013',materialName:'其他矿石'}]},
      {category:'weaponExperience',materials:[{materialId:'104014',materialName:'精锻用魔矿'}]}])await assert.rejects(()=>reader(request,5000));
  assert.equal(calls,1);
});
test('execute, mixed diagnostic and nonzero budget cannot reach resource readers',async()=>{
  for(const change of [{mode:'execute'},{resinDiagnosticOnly:true},{policyJson:JSON.stringify({originalResinBudget:20,condensedResinBudget:0})}]){
    const h=harness();Object.assign(h.settings,change);const r=await runCultivation(h.settings,h.api,{});
    assert.equal(r.status,'unknown');assert.equal(h.moraCalls+h.oreCalls,0);
  }
});
