import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runCultivation,sameRunInventoryBefore} from '../core/operator.js';

const load=n=>JSON.parse(readFileSync(new URL(`../upstream/data/${n}.json`,import.meta.url)));
const data={rulebook:load('rulebook'),materials:load('materials'),recipes:load('crafting-recipes'),allowedBosses:load('bettergi-boss-catalog').bosses};
const target={characterName:'梦见月瑞希',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:true,weaponTargetLevel:90};
const profile={CharacterName:target.characterName,Level:60,LevelLimit:60,WeaponName:'祭礼残章',WeaponLevel:1,WeaponLevelLimit:20,AttackLevel:1,AttackHasBonus:false,SkillLevel:1,SkillHasBonus:false,BurstLevel:1,BurstHasBonus:false};
const policy={dailyMode:true,dailyDomainReady:true,validationScopeId:'today',domainResin:'original',allowDomain:true,
  domainSingleAttemptVerified:true,requireZhongliShieldCast:true,originalResinBudget:40,condensedResinBudget:0,
  maxSteps:2,maxMinutes:15,domainPartyName:'测试队'};
const settings={runId:'reuse-test',mode:'execute',targetConfigJson:JSON.stringify(target),policyJson:JSON.stringify(policy)};
const chain=['114009','114010','114011','114012'];
function list(items){return {items:[...items],get Count(){return this.items.length;},Clear(){this.items=[];},Add(v){this.items.push(v);},GetRange(i,n){return list(this.items.slice(i,i+n));}};}
class Param{constructor(){this.ResinPriorityList=list(['脆弱树脂']);}SetCombatStrategyPath(){}}
function fake({expireSelection=false,expireRefresh=false,expireCheckpoint=false,slowAfter=false,sunday=false,startAt}={}) {
  let time=startAt??Date.UTC(2026,9,sunday?11:10,0),claims=0,scans=0,resinReads=0;
  const files={},checkpoints=[],countRequests=[];
  const names=Object.fromEntries(chain.map(id=>[data.materials[id].name,id]));
  const api={now:()=>time,AutoDomainParam:Param,AutoBossParam:class{},getCharacter:async()=>profile,emit(){},
    writeText:async(p,c)=>{files[p]=c;const r=JSON.parse(c);if(r.steps.length&&!r.finishedAt){checkpoints.push(r);if(expireCheckpoint)time+=120001;}return true;},readText:p=>files[p],
    countItems:async(tab,requested)=>{scans++;countRequests.push([...requested]);time+=slowAfter&&claims===1&&scans===2?121000:1000;
      return Object.fromEntries(requested.map(name=>{const id=names[name];return [name,id?
        ({'114009':22+claims*2,'114010':10+claims,'114011':2+claims,'114012':0}[id]):name.includes('浮世')?(claims?100000:0):0];}));},
    readResinSnapshot:async()=>{resinReads++;time+=(expireSelection&&resinReads===1||expireRefresh&&resinReads===2)?120001:5000;
      return {originalResin:150-claims*20,condensedResin:0,observedAt:new Date(time).toISOString(),verified:true,mainUiRestored:true};},
    runDomain:async()=>{claims++;time+=60000;return {'狮牙斗士的铁链':9999};}};
  return {api,files,checkpoints,countRequests,get claims(){return claims;},get scans(){return scans;}};
}
test('daily before links immutable initial and adjacent real after; every after remains a fresh full-chain read',async()=>{
  const f=fake(),r=await runCultivation(settings,f.api,data);
  assert.equal(r.status,'success');assert.equal(f.claims,2);assert.equal(f.scans,3);
  assert.deepEqual(r.steps.map(s=>s.beforeInventoryRead.source),['initial-current-run','previous-step-after']);
  assert.equal(r.steps[1].beforeInventoryRead.previousStepId,r.steps[0].stepId);
  assert.equal(r.initialInventoryRead.inventory['114010'].count,10);
  assert.equal(r.steps[0].before['114010'].count,10);assert.equal(r.steps[0].after['114010'].count,11);
  assert.equal(r.steps[1].before['114010'].count,11);assert.equal(r.steps[1].after['114010'].count,12);
  assert.equal(r.steps[1].delta['114010'],1);assert.equal(r.inventory['114010'].count,12);
  for(const s of r.steps){assert.equal(s.beforeInventoryRead.usedAt,s.startedAt);assert.deepEqual(new Set(Object.keys(s.after)),new Set(chain));}
  assert.deepEqual(f.checkpoints[0].initialInventoryRead,r.initialInventoryRead);
  assert.deepEqual(f.checkpoints[1].steps[0].after,r.steps[0].after);
  r.inventory['114010'].count=999;r.steps[1].before['114010'].count=888;
  assert.equal(r.steps[0].after['114010'].count,11);assert.equal(r.initialInventoryRead.inventory['114010'].count,10);
});
test('oldest scan start, not completion, controls reuse, including resin refresh aging the snapshot',async()=>{
  for(const change of [{expireSelection:true},{expireRefresh:true}]) {
    const f=fake(change),r=await runCultivation({...settings,policyJson:JSON.stringify({...policy,maxSteps:1})},f.api,data);
    assert.equal(f.claims,1);assert.equal(f.scans,3);assert.equal(r.steps[0].beforeInventoryRead.source,'fresh-current-run');
  }
  const f=fake({slowAfter:true}),r=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,2);assert.equal(f.scans,4);assert.equal(r.steps[1].beforeInventoryRead.source,'fresh-current-run');
});
test('a different next family falls back to fresh reads rather than an earlier initial family snapshot',async()=>{
  const f=fake({sunday:true}),r=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,2);assert.notEqual(r.steps[0].domainName,r.steps[1].domainName);
  assert.equal(r.steps[1].beforeInventoryRead.source,'fresh-current-run');assert.equal(f.scans,4);
});
test('checkpoint expiration retains unknown and makes no resource call',async()=>{
  const f=fake({expireCheckpoint:true}),r=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,0);assert.equal(r.steps.length,1);assert.equal(r.steps[0].status,'unknown');
  assert.equal(r.steps[0].beforeInventoryRead.source,'initial-current-run');assert.equal(f.checkpoints.length,1);
});
test('ordinary execute and scan retain their previous protocol and never reuse initial snapshots',async()=>{
  const f=fake(),r=await runCultivation({...settings,policyJson:JSON.stringify({...policy,dailyMode:false,dailyDomainReady:false,validationScopeId:'',domainValidated:true,maxSteps:1})},f.api,data);
  assert.equal(f.scans,4);assert.equal(f.claims,1);assert.equal(r.initialInventoryRead,undefined);assert.equal(r.steps[0].beforeInventoryRead,undefined);
  const probe=fake(),s=await runCultivation({...settings,mode:'scan'},probe.api,data);
  assert.equal(probe.claims,0);assert.equal(s.initialInventoryRead,undefined);assert.deepEqual(s.steps,[]);
});
test('cross-run, missing, unknown, future, non-adjacent and mutating snapshots cannot be reused',()=>{
  const time=Date.UTC(2026,9,10),task={kind:'domain',domainName:'测试域',sundaySelectedValue:'1',scanIds:['114010']};
  const initial={runId:'same',startedAt:new Date(time).toISOString(),finishedAt:new Date(time+100).toISOString(),
    inventory:{'114010':{status:'exact',count:10,evidence:{raw:{text:'10'}}}}};
  const report={runId:'same',startedAt:initial.startedAt,steps:[],initialInventoryRead:initial};
  assert.equal(sameRunInventoryBefore(report,task,policy,time+500).inventory['114010'].count,10);
  const clone=()=>JSON.parse(JSON.stringify(report));
  for(const mutate of [r=>r.initialInventoryRead.runId='other',r=>delete r.initialInventoryRead.inventory['114010'],
    r=>r.initialInventoryRead.inventory['114010'].status='unknown',r=>r.initialInventoryRead.finishedAt=new Date(time+1000).toISOString()]) {
    const r=clone();mutate(r);assert.equal(sameRunInventoryBefore(r,task,policy,time+500),null);
  }
  assert.equal(sameRunInventoryBefore(report,task,policy,time+120001),null);
  for(const change of [{allowCrafting:true},{allowBoss:true},{allowRoutes:true},{dailyMode:false},{domainResin:'condensed'}])
    assert.equal(sameRunInventoryBefore(report,task,{...policy,...change},time+500),null);
  const r=clone();r.steps=[{stepId:'same:step-1',type:'domain',resin:'original',maxClaims:1,status:'success',domainName:'测试域',
    sundaySelectedValue:'1',after:initial.inventory,afterInventoryRead:{runId:'same',startedAt:initial.startedAt,finishedAt:initial.finishedAt}}];
  const packet=sameRunInventoryBefore(r,task,policy,time+500);packet.inventory['114010'].evidence.raw.text='999';
  assert.equal(r.steps[0].after['114010'].evidence.raw.text,'10');
  r.steps[0].stepId='same:step-0';assert.equal(sameRunInventoryBefore(r,task,policy,time+500),null);
});
test('inventory reuse is rejected across UTC+8 04:00 even within120 seconds',()=>{
  const beforeReset=Date.UTC(2026,9,10,19,59,59),afterReset=beforeReset+1000;
  const task={kind:'domain',domainName:'测试域',sundaySelectedValue:'1',scanIds:['114010']};
  const initial={runId:'same',startedAt:new Date(beforeReset).toISOString(),finishedAt:new Date(beforeReset+100).toISOString(),
    inventory:{'114010':{status:'exact',count:10}}};
  const report={runId:'same',startedAt:initial.startedAt,steps:[],initialInventoryRead:initial};
  assert.ok(sameRunInventoryBefore(report,task,policy,beforeReset+500));
  assert.equal(sameRunInventoryBefore(report,task,policy,afterReset),null);
  report.initialInventoryRead.startedAt=new Date(afterReset).toISOString();
  report.initialInventoryRead.finishedAt=new Date(afterReset+100).toISOString();
  assert.equal(sameRunInventoryBefore(report,task,policy,afterReset+500),null);
});
test('daily authorization cannot start a claim after04:00 during inventory/resin preparation',async()=>{
  const f=fake({startAt:Date.UTC(2026,9,10,19,59,50)}),r=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,0);assert.deepEqual(r.steps,[]);
  assert.equal(r.status,'unknown');assert.ok(r.blockers.some(b=>b.code==='game_day_changed'));
  assert.equal(f.checkpoints.length,0);
});
test('daily authorization rollover during checkpoint preserves unknown and never enters resource API',async()=>{
  const f=fake({startAt:Date.UTC(2026,9,10,19,59,30),expireCheckpoint:true}),r=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,0);assert.equal(r.steps.length,1);assert.equal(r.steps[0].status,'unknown');
  assert.ok(r.blockers.some(b=>b.code==='game_day_changed'));
  assert.ok(r.blockers.some(b=>b.code==='reward_unknown'));
});
test('a verified pre-reset claim finishes its new after read and stops before a post-reset claim',async()=>{
  const f=fake({startAt:Date.UTC(2026,9,10,19,59,30)}),r=await runCultivation(settings,f.api,data);
  assert.equal(f.claims,1);assert.equal(r.steps.length,1);assert.equal(r.steps[0].status,'success');
  assert.equal(f.scans,2);assert.equal(r.steps[0].after['114010'].count,11);
  assert.ok(r.blockers.some(b=>b.code==='game_day_changed'));
});
