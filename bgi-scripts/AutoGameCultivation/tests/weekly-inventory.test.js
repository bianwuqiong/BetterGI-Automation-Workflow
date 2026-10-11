import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {verifyWeeklyObservation,createWeeklyInventoryReader,WEEKLY_MATERIALS} from '../core/weekly-inventory.js';
import {runCultivation} from '../core/operator.js';
const BASE=1791734400000,END=BASE+4200;
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/weekly-inventory-synthetic.json',import.meta.url),'utf8'));
test('all four actual-shaped named stacks require category/model/raw numbers/border pixels/world pair',()=>{
  const rows=verifyWeeklyObservation(fixture(),BASE,END);
  assert.deepEqual(Object.keys(rows).sort(),WEEKLY_MATERIALS.map(m=>m.materialId).sort());
  assert.equal(rows['113021'].name,'异梦溶媒');assert.equal(rows['113060'].count,7);
});
test('101016, wrong name/category/header, weak model and OCR method disagreement cannot pass',()=>{
  for(const mutate of [r=>r.inventory['101016']=5,r=>r.observations['113021'].second.category='characterDevelopmentItems',
      r=>r.observations['113060'].second.iconScore=.739,r=>r.observations['113060'].second.iconName='丝织之羽',
      r=>r.observations['113060'].second.headerRows[0].text='培养道具',r=>r.observations['113060'].second.stack.nameRows[0].text='残火',
      r=>r.observations['113060'].second.stack.rawCountText='7万',r=>r.observations['113060'].second.stack.rawCountText='17',
      r=>r.inventory['113060']=true,r=>r.rejectedObservations['101016']=[]]){
    const raw=fixture();mutate(raw);assert.throws(()=>verifyWeeklyObservation(raw,BASE,END));
  }
});
test('all four ROI edges and actual border samples must independently prove complete selection',()=>{
  for(const mutate of [r=>r.observations['113060'].second.stack.nameRows[0].x=1310,
      r=>r.observations['113060'].second.stack.nameRows[0].y=121,r=>r.observations['113060'].second.stack.countRows[0].x=116,
      r=>r.observations['113060'].second.stack.countRows[0].y=429,r=>r.observations['113060'].second.headerRows[0].y=1,
      r=>delete r.observations['113060'].second.stack.selectionEvidence.sides,
      r=>r.observations['113060'].second.stack.selectionEvidence.sides[0].coordinate=400,
      r=>r.observations['113060'].second.stack.selectionEvidence.sides[0].samples[0].x=500,
      r=>r.observations['113060'].second.stack.selectionEvidence.sides[0].samples.forEach(p=>Object.assign(p,{b:0,g:0,r:0}))]){
    const raw=fixture();mutate(raw);assert.throws(()=>verifyWeeklyObservation(raw,BASE,END));
  }
});
test('independent fresh selection and world captures must belong to this read interval and same client',()=>{
  for(const mutate of [r=>r.observations['113060'].second.stack.observedAt=r.observations['113060'].first.stack.observedAt,
      r=>r.observations['113060'].selection.clickedAt=BASE-100,r=>Object.assign(r.observations['113061'].second,{width:1280,height:720}),
      r=>r.worldFrames.at(-1).world=false,r=>r.worldFrames.at(-1).focused=false,
      r=>r.worldFrames.at(-1).observedAt=r.worldFrames.at(-2).observedAt,r=>r.cleanupCompleted=false]){
    const raw=fixture();mutate(raw);assert.throws(()=>verifyWeeklyObservation(raw,BASE,END));
  }
  assert.throws(()=>verifyWeeklyObservation(fixture(),BASE,BASE+6000));
});
test('raw zero only passes with complete independent named zero crops',()=>{
  const raw=fixture();raw.inventory['113060']=0;
  for(const f of [raw.observations['113060'].first,raw.observations['113060'].second]){
    f.stack.rawCountText='0';f.stack.countRows[0].text='0';
  }
  assert.equal(verifyWeeklyObservation(raw,BASE,END)['113060'].count,0);
});
test('bag selection order is independent of ID order while raw selection intervals cannot overlap',()=>{
  const raw=fixture();
  for(const [id,clicked] of [['113060',BASE+2100],['113062',BASE+100]]){
    const pair=raw.observations[id];pair.selection.clickedAt=clicked;pair.first.stack.observedAt=clicked+300;pair.second.stack.observedAt=clicked+550;
  }
  assert.equal(verifyWeeklyObservation(raw,BASE,END)['113060'].count,7);
  raw.observations['113060'].selection.clickedAt=BASE+1600;assert.throws(()=>verifyWeeklyObservation(raw,BASE,END));
});
test('native bridge uses linked CTS, exact empty fixed request, UTF8 byte cap and always disposes',async()=>{
  let serialized=JSON.stringify(fixture()),calls=0,disposed=0;
  const dispatcher={GetLinkedCancellationTokenSource:()=>({Token:'linked',CancelAfter:ms=>assert.equal(ms,5000),Dispose:()=>disposed++}),
    ReadWeeklyConversionInventory:async(request,token)=>{calls++;assert.equal(request,'{}');assert.equal(token,'linked');return serialized;}};
  const read=createWeeklyInventoryReader({dispatcher});await read(5000);
  for(const value of ['bad JSON','x'.repeat(1000001),'汉'.repeat(333334),{}]){serialized=value;await assert.rejects(()=>read(5000));}
  assert.equal(calls,5);assert.equal(disposed,5);await assert.rejects(()=>read(0));assert.equal(calls,5);
});
function harness(change={}){
  let now=BASE,calls=0;const files={};
  const settings={runId:'weekly-inventory-fixture',mode:'scan',weeklyInventoryOnly:true,
    targetConfigJson:JSON.stringify({characterName:'芭芭拉',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:false,weaponTargetLevel:null}),
    policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:0,maxMinutes:3}),...change};
  const forbidden=()=>{throw Error('ordinary scan or spender must not run in weekly diagnostic');};
  const api={now:()=>now,getCharacter:forbidden,countItems:forbidden,readResinSnapshot:forbidden,readMoraSnapshot:forbidden,inspectTalentUpgrade:forbidden,
    runCrafting:forbidden,runBoss:forbidden,runDomain:forbidden,
    readWeeklyConversionInventory:async()=>{calls++;now=END;return fixture();},
    writeText:async(path,text)=>{files[path]=text;return true;},readText:path=>files[path],emit:()=>{}};
  return {settings,api,files,get calls(){return calls;}};
}
test('isolated diagnostic archives original raw with no generic 17 scan/conversion/upgrade',async()=>{
  const h=harness(),r=await runCultivation(h.settings,h.api,{});
  assert.equal(r.status,'success');assert.equal(h.calls,1);assert.equal(r.metadata.diagnostic,'weekly-conversion-inventory-only');
  assert.deepEqual(r.inventory,{});assert.equal(r.profile,null);assert.equal(r.plan,null);assert.deepEqual(r.steps,[]);
  assert.equal(r.targetReached,false);assert.equal(r.weeklyInventory.completedUpgrades,0);
  assert.deepEqual(JSON.parse(h.files['record/weekly-inventory-fixture.json']).weeklyInventory.nativeObservation,fixture());
});
test('execute, mixed diagnostic flags, nonzero budgets, resource adapters and >3min cannot call weekly native',async()=>{
  for(const change of [{mode:'execute'},{talentPreviewOnly:true},{resourceDiagnosticOnly:true},{resinDiagnosticOnly:true},
      {policyJson:JSON.stringify({originalResinBudget:20,condensedResinBudget:0,maxMinutes:3})},
      {policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:1,maxMinutes:3})},
      {policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:0,maxMinutes:4})},
      {policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:0,maxMinutes:3,allowWeekly:true})}]){
    const h=harness(change),r=await runCultivation(h.settings,h.api,{});assert.equal(r.status,'unknown');assert.equal(h.calls,0);
  }
});
test('raw native unknown or weak evidence stays fully retained with all null counts',async()=>{
  for(const mutate of [r=>r.status='unknown',r=>r.observations['113060'].second.iconScore=.739]){
    const h=harness(),raw=fixture();mutate(raw);h.api.readWeeklyConversionInventory=async()=>raw;
    const r=await runCultivation(h.settings,h.api,{});assert.equal(r.status,'unknown');assert.equal(r.weeklyInventory.allVerified,false);
    assert.deepEqual(r.weeklyInventory.nativeObservation,raw);assert.ok(Object.values(r.weeklyInventory.inventory).every(row=>row.count===null&&row.status==='unknown'));
  }
});
