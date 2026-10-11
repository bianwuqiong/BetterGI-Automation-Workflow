import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runCultivation} from '../core/operator.js';

const load=n=>JSON.parse(readFileSync(new URL(`../upstream/data/${n}.json`,import.meta.url)));
const data={rulebook:load('rulebook'),materials:load('materials'),recipes:load('crafting-recipes'),allowedBosses:load('bettergi-boss-catalog').bosses};
const target={characterName:'梦见月瑞希',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:true,weaponTargetLevel:90};
const profile={CharacterName:target.characterName,Level:60,LevelLimit:60,WeaponName:'祭礼残章',WeaponLevel:1,WeaponLevelLimit:20,AttackLevel:1,AttackHasBonus:false,SkillLevel:1,SkillHasBonus:false,BurstLevel:1,BurstHasBonus:false};
const policy={dailyMode:true,dailyDomainReady:true,validationScopeId:'today',allowDomain:true,
  domainSingleAttemptVerified:true,requireZhongliShieldCast:true,originalResinBudget:40,
  condensedResinBudget:0,maxSteps:1,maxMinutes:15,domainPartyName:'测试队'};
const settings={runId:'routing-test',mode:'execute',targetConfigJson:JSON.stringify(target),policyJson:JSON.stringify(policy)};
const rect=(x,y,width,height)=>({x,y,width,height}),row=(text,r)=>({text,...r});
function list(items) {return {items:[...items],get Count(){return this.items.length;},Clear(){this.items=[];},Add(v){this.items.push(v);},GetRange(i,n){return list(this.items.slice(i,i+n));}};}
class Param {constructor(){this.ResinPriorityList=list(['脆弱树脂']);} SetCombatStrategyPath(){}}
function fake({nativeFailure,slowStage,slowCheckpoint=false,guideFailure,guideGoldChanges=false,
  genericGoldCount,ironGeneric=false,nativeGoldMissing=false}={}) {
  let time=Date.UTC(2026,9,10,0),claims=0,bagCalls=0,scans=0,resinReads=0;
  const files={},guideRequests=[],bagRequests=[],countRequests=[],writes=[];
  const api={now:()=>time,getCharacter:async()=>profile,AutoDomainParam:Param,AutoBossParam:class{},
    writeText:async(p,c)=>{files[p]=c;const r=JSON.parse(c);writes.push(r);
      if(slowCheckpoint && r.steps.length && !r.finishedAt)time+=700000;return true;},readText:p=>files[p],emit(){},
    countItems:async(tab,names)=>{scans++;countRequests.push([...names]);if(slowStage==='initial'&&scans===1)time+=661000;
      if(slowStage==='before'&&scans===2)time+=661000;
      return Object.fromEntries(names.filter(n=>(ironGeneric || n!==data.materials['114010'].name)
        && (genericGoldCount!==undefined && scans>1 || n!==data.materials['114012'].name))
        .map(n=>[n,n===data.materials['114009'].name?22+claims:n===data.materials['114010'].name?10+claims
          :n===data.materials['114011'].name?2:n===data.materials['114012'].name?genericGoldCount:0]));},
    // These routing tests deliberately expire initial inventory so they continue
    // exercising fresh-before guide/native transitions rather than snapshot reuse.
    readResinSnapshot:async()=>{resinReads++;if(resinReads===1)time+=120001;
      if(slowStage==='resin'&&resinReads===2)time+=661000;
      return {originalResin:150-claims*20,condensedResin:0,observedAt:new Date(time).toISOString(),verified:true,mainUiRestored:true};},
    readWeaponGuideInventory:async request=>{
      guideRequests.push(request);const base=time;time+=2000;
      if(guideRequests.length>1 && guideFailure==='error')throw new Error('guide_read_failed');
      const context=observedAt=>({observedAt,contextRows:{characterName:[row(target.characterName,rect(730,220,300,28))],weaponName:[row(profile.WeaponName,rect(730,220,300,28))],targetLevel:[row('升级至90',rect(730,220,300,28))]}});
      const observations={};for(const m of request.materials)if(m.materialId==='114012'
        && !(guideRequests.length>1 && guideFailure)) {
        const frame=observedAt=>({observedAt,tooltipRegion:rect(700,140,530,840),tooltipRows:[row(m.materialName,rect(730,220,300,28)),row(`培养需求${guideGoldChanges?claims:0}/${m.required}`,rect(730,850,300,28))]});
        observations[m.materialId]={first:frame(base+500),second:frame(base+680)};
      }
      return {readOnly:true,source:'character_weapon_guide_tooltip',mainUiRestored:!(guideRequests.length>1&&guideFailure==='cleanup'),observations,
        contextEvidence:{before:[context(base),context(base+180)],after:[context(base+1500),context(base+1680)]},reason:'page_limit'};
    },
    readBackpackInventory:async request=>{
      bagRequests.push(request);bagCalls++;const base=time;time+=2000;
      if(bagCalls>1 && nativeFailure)return {readOnly:true,source:'backpack_selected_stack',mainUiRestored:nativeFailure!=='cleanup',observations:{}};
      const observations={};for(const m of request.materials) {
        if(nativeGoldMissing && m.materialId==='114012')continue;
        const item=rect(110,300,125,150),count=String(9+bagCalls);
        const frame=observedAt=>({observedAt,nameRegion:rect(1300,90,500,80),nameRows:[row(m.materialName,rect(1320,110,300,28))],
          selectedItemVerified:true,selectedItemRect:item,countRegion:rect(110,415,125,35),countRows:[row(count,rect(160,420,30,28))],countMethod:'raw_ocr_without_detector',rawCountText:count});
        observations[m.materialId]={selection:{itemRect:item,x:172,y:365,clickedAt:base},first:frame(base+400),second:frame(base+600)};
      }
      return {readOnly:true,source:'backpack_selected_stack',mainUiRestored:true,observations};
    },runDomain:async()=>{claims++;time+=60000;}};
  return {api,guideRequests,bagRequests,countRequests,writes,get claims(){return claims;}};
}
test('same-run identities route fresh before/after backpack reads without copying a prior count',async()=>{
  const f=fake(),report=await runCultivation(settings,f.api,data);
  assert.equal(report.status,'success');assert.equal(f.claims,1);
  assert.equal(report.steps[0].before['114010'].count,11);assert.equal(report.steps[0].after['114010'].count,12);
  assert.equal(report.steps[0].delta['114010'],1);assert.equal(report.inventory['114010'].count,12);
  assert.deepEqual(f.guideRequests.map(r=>r.materials.map(m=>m.materialId)),[['114010','114012'],['114012'],['114012']]);
  assert.ok(f.bagRequests.every(r=>r.materials.length===1&&r.materials[0].materialId==='114010'&&Object.keys(r.materials[0]).length===2));
  assert.deepEqual(new Set(report.requiredScanIds),new Set(['114009','114010','114011','114012']));
  assert.equal(report.profile.weapon.name,profile.WeaponName);assert.ok(Object.keys(report.plan.requirements).length>4);
});
test('unverified fresh native frames never reuse the hinted count or permit a claim',async()=>{
  for(const nativeFailure of ['missing','cleanup']) {
    const f=fake({nativeFailure}),report=await runCultivation(settings,f.api,data);
    assert.equal(f.claims,0);assert.deepEqual(report.steps,[]);assert.equal(report.status,'unknown');
    if(nativeFailure==='missing')assert.equal(report.inventory['114010'].count,null);
    else assert.ok(report.blockers.some(b=>b.code==='read_or_execution_failed'));
    assert.ok(f.writes.every(r=>r.steps.length===0));
  }
});
test('insufficient daily closing reserve before scan, after scan, or after resin creates no attempted step',async()=>{
  for(const slowStage of ['initial','before','resin']) {
    const f=fake({slowStage}),report=await runCultivation(settings,f.api,data);
    assert.equal(f.claims,0);assert.deepEqual(report.steps,[]);assert.ok(f.writes.every(r=>r.steps.length===0));
    assert.ok(report.blockers.some(b=>b.code==='time_limit'));
  }
});
test('a slow durable checkpoint keeps the unknown attempt and forbids a resource call',async()=>{
  const f=fake({slowCheckpoint:true}),report=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,0);assert.equal(report.steps.length,1);assert.equal(report.steps[0].status,'unknown');
  assert.ok(f.writes.some(r=>r.steps.length===1));assert.ok(report.blockers.some(b=>b.code==='reward_unknown'));
});

test('fresh same-run guide zero becomes one after the claim and excludes only observed rows from bag requests',async()=>{
  const f=fake({ironGeneric:true,guideGoldChanges:true}),report=await runCultivation(settings,f.api,data);
  const gold=data.materials['114012'].name,chain=['114009','114010','114011','114012'];
  assert.equal(report.status,'success');assert.equal(f.claims,1);
  assert.deepEqual(f.countRequests.map(names=>names.length),[4,3,3]);
  assert.equal(f.countRequests[0].includes(gold),true);
  assert.ok(f.countRequests.slice(1).every(names=>!names.includes(gold)));
  assert.equal(report.steps[0].before['114012'].count,0);assert.equal(report.steps[0].after['114012'].count,1);
  assert.equal(report.steps[0].delta['114012'],1);assert.equal(report.inventory['114012'].count,1);
  assert.ok(report.steps[0].after['114012'].evidence.tooltip[0].observedAt>report.steps[0].before['114012'].evidence.tooltip[1].observedAt);
  assert.deepEqual(new Set(Object.keys(report.steps[0].before)),new Set(chain));
  assert.deepEqual(new Set(Object.keys(report.steps[0].after)),new Set(chain));
  assert.equal(f.bagRequests.length,0);
});
test('missing or failed fresh guide observations restore the full bag request and cannot reuse old zero',async()=>{
  for(const guideFailure of ['missing','error']) {
    const f=fake({ironGeneric:true,guideFailure,genericGoldCount:1}),report=await runCultivation(settings,f.api,data);
    assert.equal(f.claims,1);assert.equal(report.steps[0].before['114012'].count,1);
    assert.ok(f.countRequests[1].includes(data.materials['114012'].name));
    assert.equal(report.steps[0].before['114012'].source,undefined);
  }
  const f=fake({ironGeneric:true,guideFailure:'missing',nativeGoldMissing:true}),report=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,0);assert.deepEqual(report.steps,[]);assert.equal(report.inventory['114012'].count,null);
  assert.equal(report.status,'unknown');assert.ok(f.countRequests[1].includes(data.materials['114012'].name));
});
test('unrestored guide-first UI stops before generic fallback or any resource attempt',async()=>{
  const f=fake({ironGeneric:true,guideFailure:'cleanup'}),report=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,0);assert.deepEqual(report.steps,[]);assert.equal(f.countRequests.length,1);
  assert.equal(report.status,'unknown');assert.ok(f.writes.every(r=>r.steps.length===0));
});

test('native material attempts share a two-read cap across hint and final fallback routes',async()=>{
  const f=fake({nativeFailure:'missing'}),report=await runCultivation(settings,f.api,data);
  // One initial scan success, then two failed fresh reads in the next scan; no fourth fallback read.
  assert.equal(f.bagRequests.length,3);assert.equal(f.claims,0);assert.deepEqual(report.steps,[]);
  assert.equal(report.inventory['114010'].count,null);assert.equal(report.status,'unknown');
  const native=report.inventoryReadDiagnostics.filter(d=>d.source==='backpack_selected_stack');
  assert.deepEqual(native.map(d=>d.attempts['114010']),[1,1,2]);
});
test('cleanup failure, exception, or invalid native source never triggers an extra retry',async()=>{
  for(const failure of ['cleanup','exception','source']) {
    const f=fake();let calls=0;const read=f.api.readBackpackInventory;
    f.api.readBackpackInventory=async request=>{
      calls++;if(calls===1)return read(request);
      if(failure==='exception')throw new Error('native capture exception');
      return {source:failure==='source'?'unsupported':'backpack_selected_stack',readOnly:true,
        mainUiRestored:failure!=='cleanup',observations:{}};
    };
    const report=await runCultivation(settings,f.api,data);
    assert.equal(calls,2);assert.equal(f.claims,0);assert.deepEqual(report.steps,[]);
    assert.equal(report.status,'unknown');
  }
});
