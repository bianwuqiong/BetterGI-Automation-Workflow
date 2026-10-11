import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runCultivation} from '../core/operator.js';

const load=name=>JSON.parse(readFileSync(new URL(`../upstream/data/${name}.json`,import.meta.url)));
const data={rulebook:load('rulebook'),materials:load('materials'),recipes:load('crafting-recipes'),allowedBosses:load('bettergi-boss-catalog').bosses};
const target={characterName:'梦见月瑞希',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:true,weaponTargetLevel:90};
const raw={CharacterName:'梦见月瑞希',Level:60,LevelLimit:60,WeaponName:'祭礼残章',WeaponLevel:1,WeaponLevelLimit:20,AttackLevel:1,AttackHasBonus:false,SkillLevel:1,SkillHasBonus:false,BurstLevel:1,BurstHasBonus:false};
const missing=new Set(['114010','114011','114012'].map(id=>data.materials[id].name));
const base=Date.UTC(2026,9,9,6,0),row=(text,x=730,y=220,width=300)=>({text,x,y,width,height:28});
function result(request) {
  const context=time=>({observedAt:time,contextRows:{characterName:[row(request.characterName)],weaponName:[row(request.weaponName)],targetLevel:[row(`升级至${request.targetLevel}`)]}});
  const observations={};
  for(const material of request.materials) {
    const frame=time=>({observedAt:time,tooltipRegion:{x:700,y:140,width:530,height:840},tooltipRows:[row(material.materialName),row('可合成数量：5',730,700),row('培养需求',730,850,100),row(`${material.materialId==='114010'?3:0}/${material.required}`,1080,850,100)]});
    observations[material.materialId]={first:frame(base+500),second:frame(base+680)};
  }
  return {readOnly:true,source:'character_weapon_guide_tooltip',mainUiRestored:true,inventory:{},observations,contextEvidence:{before:[context(base),context(base+180)],after:[context(base+1500),context(base+1680)]}};
}
function fake() {
  const files={},api={calls:0,now:()=>base,getCharacter:async()=>raw,
    countItems:async(tab,names)=>Object.fromEntries(names.filter(n=>!missing.has(n)).map(n=>[n,100000])),
    writeText:async(p,c)=>{files[p]=c;return true;},readText:p=>files[p],emit:()=>{},
    readWeaponGuideInventory:async request=>{api.calls++;return result(request);}};
  return api;
}
const settings={runId:'test-inventory-fallback',mode:'scan',targetConfigJson:JSON.stringify(target),policyJson:'{}'};

test('unknown weapon materials use same-run guide evidence, including explicit zero',async()=>{
  const api=fake(),report=await runCultivation(settings,api,data);
  assert.equal(api.calls,1);assert.equal(report.status,'success');assert.equal(report.inventory['114010'].count,3);
  assert.equal(report.inventory['114011'].count,0);assert.equal(report.inventory['114012'].source,'character_weapon_guide_tooltip');
  assert.deepEqual(report.steps,[]);
});
test('reader-returned verified counts cannot replace missing actual tooltip evidence',async()=>{
  const api=fake();api.readWeaponGuideInventory=async request=>({...result(request),observations:{},inventory:Object.fromEntries(request.materials.map(m=>[m.materialId,{count:0,status:'exact',verified:true}]))});
  const report=await runCultivation(settings,api,data);assert.equal(report.status,'unknown');assert.equal(report.inventory['114011'].count,null);
});
test('changed post-read weapon keeps materials unknown',async()=>{
  const api=fake();api.readWeaponGuideInventory=async request=>{const r=result(request);r.contextEvidence.after[1].contextRows.weaponName=[row('讨龙英杰谭')];return r;};
  const report=await runCultivation(settings,api,data);assert.equal(report.status,'unknown');assert.equal(report.inventory['114010'].count,null);
});
test('failed return to main UI stops scan before planning execution',async()=>{
  const api=fake();api.readWeaponGuideInventory=async request=>({...result(request),mainUiRestored:false});
  const report=await runCultivation(settings,api,data);assert.equal(report.status,'unknown');assert.equal(report.plan,null);
  assert.ok(report.blockers.some(b=>b.code==='read_or_execution_failed'));assert.deepEqual(report.steps,[]);
});
test('known backpack inventory does not open guide',async()=>{
  const api=fake();api.countItems=async(tab,names)=>Object.fromEntries(names.map(n=>[n,100000]));
  const report=await runCultivation(settings,api,data);assert.equal(api.calls,0);assert.equal(report.status,'success');
});
test('missing guide capability and navigation failure preserve unknown inventory',async()=>{
  for(const absent of [true,false]) {
    const api=fake();if(absent) delete api.readWeaponGuideInventory;else api.readWeaponGuideInventory=async()=>{throw new Error('guide unavailable');};
    const report=await runCultivation(settings,api,data);assert.equal(report.status,'unknown');assert.equal(report.inventory['114012'].count,null);
  }
});

function backpackResult(request) {
  return {readOnly:true,source:'backpack_selected_stack',mainUiRestored:true,
    observations:Object.fromEntries(request.materials.map(material=> {
      const frame=observedAt=>({observedAt,nameRegion:{x:1300,y:90,width:500,height:80},
        selectedItemVerified:true,selectedItemRect:{x:110,y:300,width:125,height:150},
        countMethod:'raw_ocr_without_detector',rawCountText:'9',
        nameRows:[row(material.materialName,1320,110,300)],countRegion:{x:110,y:415,width:125,height:35},
        countRows:[row('9',160,420,30)]});
      return [material.materialId,{selection:{itemRect:{x:110,y:300,width:125,height:150},
        x:172,y:365,clickedAt:base+1000},first:frame(base+1400),second:frame(base+1600)}];
    }))};
}
test('saturated guide card stays unknown until named backpack frames independently read actual stock',async()=>{
  const api=fake();api.readWeaponGuideInventory=async request=>{
    const r=result(request);delete r.observations['114010'];r.reason='page_limit';return r;
  };
  const requested=[];api.readBackpackInventory=async request=>{requested.push(request);return backpackResult(request);};
  const report=await runCultivation(settings,api,data);
  assert.equal(report.status,'success');assert.equal(report.inventory['114010'].count,9);
  assert.equal(report.inventory['114010'].source,'backpack_selected_stack');
  assert.equal(report.inventory['114012'].count,0);assert.deepEqual(report.steps,[]);
  assert.deepEqual(requested[0].materials.map(m=>m.materialId),['114010']);
});
test('hidden guide materials never become target stock or observed drops when backpack frames are absent',async()=>{
  const api=fake();api.readWeaponGuideInventory=async request=>({...result(request),observations:{},reason:'page_limit'});
  api.readBackpackInventory=async()=>({readOnly:true,source:'backpack_selected_stack',mainUiRestored:true,
    observations:{},inventory:{'114010':{count:9,verified:true}},observedDrop:{'114010':2}});
  const report=await runCultivation(settings,api,data);
  assert.equal(report.status,'unknown');assert.equal(report.inventory['114010'].count,null);
});
test('backpack cleanup failure stops scan before a resource task can be planned',async()=>{
  const api=fake();api.readWeaponGuideInventory=async request=>({...result(request),observations:{},reason:'page_limit'});
  api.readBackpackInventory=async request=>({...backpackResult(request),mainUiRestored:false});
  const report=await runCultivation(settings,api,data);
  assert.equal(report.status,'unknown');assert.equal(report.plan,null);assert.deepEqual(report.steps,[]);
});
test('daily read-only probe binds all positive weapon stacks to names while retaining guide zero',async()=>{
  const api=fake(),requested=[];
  api.countItems=async(tab,names)=>Object.fromEntries(names.filter(n=>
    !['114010','114012'].some(id=>n===data.materials[id].name)).map(n=>[n,
      n===data.materials['114009'].name?22:n===data.materials['114011'].name?2:100000]));
  api.readWeaponGuideInventory=async request=>{const r=result(request);delete r.observations['114010'];return r;};
  api.readBackpackInventory=async request=> {
    requested.push(request);const r=backpackResult(request);
    for(const [id,pair] of Object.entries(r.observations)) for(const key of ['first','second']) {
      const text=String({'114009':22,'114010':10,'114011':2}[id]);
      pair[key].rawCountText=text;pair[key].countRows[0].text=text;
    }
    return r;
  };
  const report=await runCultivation({...settings,policyJson:JSON.stringify({dailyMode:true,
    validationScopeId:'test-day',originalResinBudget:0,condensedResinBudget:0,requireZhongliShieldCast:true})},api,data);
  assert.deepEqual(new Set(requested[0].materials.map(m=>m.materialId)),new Set(['114009','114010','114011']));
  assert.deepEqual(['114009','114010','114011','114012'].map(id=>report.inventory[id].count),[22,10,2,0]);
  assert.equal(report.inventory['114009'].source,'backpack_selected_stack');
  assert.equal(report.inventory['114011'].source,'backpack_selected_stack');
  assert.equal(report.inventory['114012'].source,'character_weapon_guide_tooltip');
  assert.deepEqual(report.steps,[]);
});
test('daily named-stack diagnostic stays unknown when only generic icon counts are available',async()=>{
  for(const nativeAvailable of [false,true]) {
    const api=fake();api.countItems=async(tab,names)=>Object.fromEntries(names.map(n=>[n,100000]));
    api.readWeaponGuideInventory=async request=>({...result(request),observations:{}});
    if(nativeAvailable) api.readBackpackInventory=async()=>({readOnly:true,source:'backpack_selected_stack',
      mainUiRestored:true,observations:{}});
    const report=await runCultivation({...settings,policyJson:JSON.stringify({dailyMode:true,
      validationScopeId:'test-day',originalResinBudget:0,condensedResinBudget:0,requireZhongliShieldCast:true})},api,data);
    assert.equal(report.status,'unknown');assert.equal(report.inventory['114010'].count,null);
    assert.equal(report.inventory['114010'].status,'unknown');assert.deepEqual(report.steps,[]);
  }
});

test('a restored read-only native scan retries only the rejected material with new raw frames',async()=>{
  const api=fake(),requested=[],responses=[];
  api.countItems=async(tab,names)=>Object.fromEntries(names.map(n=>[n,100000]));
  api.readBackpackInventory=async request=>{
    requested.push(request);const r=backpackResult(request);responses.push(r);
    if(requested.length===1)delete r.observations['114011'];
    else for(const pair of Object.values(r.observations)) {
      pair.selection.clickedAt+=3000;
      for(const key of ['first','second']) {
        pair[key].observedAt+=3000;pair[key].rawCountText='3';pair[key].countRows[0].text='3';
      }
    }
    return r;
  };
  const report=await runCultivation({...settings,policyJson:JSON.stringify({dailyMode:true,
    validationScopeId:'test-day',originalResinBudget:0,condensedResinBudget:0,requireZhongliShieldCast:true})},api,data);
  assert.equal(requested.length,2);assert.deepEqual(requested[1].materials.map(m=>m.materialId),['114011']);
  assert.equal(report.inventory['114011'].count,3);assert.equal(report.inventory['114010'].count,9);
  assert.deepEqual(report.inventory['114010'].evidence.first,responses[0].observations['114010'].first);
  assert.deepEqual(report.inventory['114011'].evidence.first,responses[1].observations['114011'].first);
  assert.deepEqual(report.steps,[]);assert.equal(report.status,'success');
});

test('two clean native misses use one new named guide pair for the failed diagnostic material',async()=>{
  const api=fake(),nativeRequests=[],guideRequests=[];
  api.countItems=async(tab,names)=>Object.fromEntries(names.filter(n=>n!==data.materials['114012'].name)
    .map(n=>[n,n===data.materials['114011'].name?3:22]));
  api.readWeaponGuideInventory=async request=>{
    guideRequests.push(request);const r=result(request);
    if(guideRequests.length>1)for(const pair of Object.values(r.observations)) {
      for(const key of ['first','second'])pair[key].tooltipRows[3].text='3/9';
    }
    return r;
  };
  api.readBackpackInventory=async request=>{
    nativeRequests.push(request);const r=backpackResult(request);delete r.observations['114011'];return r;
  };
  const report=await runCultivation({...settings,policyJson:JSON.stringify({dailyMode:true,
    validationScopeId:'test-day',originalResinBudget:0,condensedResinBudget:0,requireZhongliShieldCast:true})},api,data);
  assert.equal(report.status,'success');assert.deepEqual(report.steps,[]);
  assert.deepEqual(nativeRequests[1].materials.map(m=>m.materialId),['114011']);assert.equal(nativeRequests.length,2);
  assert.deepEqual(guideRequests.map(r=>r.materials.map(m=>m.materialId)),[['114012'],['114011']]);
  assert.equal(report.inventory['114011'].count,3);assert.equal(report.inventory['114011'].source,'character_weapon_guide_tooltip');
  assert.equal(report.inventory['114012'].count,0);assert.equal(report.inventory['114010'].source,'backpack_selected_stack');
  assert.equal(report.inventory['114011'].evidence.tooltip[0].tooltipRows[3].text,'3/9');
});
test('uncertified native state forbids the extra guide UI even after an earlier clean miss',async()=>{
  for(const failure of ['exception','late_exception','source','readonly','cleanup']) {
    const api=fake();let nativeCalls=0,guideCalls=0;
    api.countItems=async(tab,names)=>Object.fromEntries(names.map(n=>[n,100000]));
    api.readWeaponGuideInventory=async request=>{guideCalls++;return result(request);};
    api.readBackpackInventory=async()=>{
      nativeCalls++;
      if(failure==='exception' || failure==='late_exception'&&nativeCalls===2)throw new Error('native unavailable');
      return {source:failure==='source'?'other_source':'backpack_selected_stack',readOnly:failure!=='readonly',
        mainUiRestored:failure!=='cleanup',observations:{}};
    };
    const report=await runCultivation({...settings,policyJson:JSON.stringify({dailyMode:true,
      validationScopeId:'test-day',originalResinBudget:0,condensedResinBudget:0,requireZhongliShieldCast:true})},api,data);
    assert.equal(guideCalls,0);assert.equal(nativeCalls,failure==='late_exception'?2:1);
    assert.equal(report.status,'unknown');assert.deepEqual(report.steps,[]);
  }
});
