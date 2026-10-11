import test from 'node:test';
import assert from 'node:assert/strict';
import {runRehearsal} from '../probe.js';
const settings={runId:'probe-run',domainName:'逆悬的冰河',partyName:'已核实队伍',strategyName:'木偶星超导',maxMinutes:5};
function host({badField=false,rewardCount=0,throwTask=false,failWrite=false}={}) {
  let calls=0;const files={};let event;
  class Param {constructor(){this.ResinPriorityList={Count:2,Clear(){this.Count=0;}};}SetCombatStrategyPath(n){return 'X:\\Engine\\User\\AutoFight\\'+n+'.txt';}}
  if(badField)Object.defineProperty(Param.prototype,'CombatOnly',{get(){return false;},set(){}});
  return {api:{now:()=>Date.UTC(2026,0,1),AutoDomainParam:Param,
    runDomain:async p=>{calls++;assert.equal(p.CombatOnly,true);assert.equal(p.RequireZhongliShieldCast,true);assert.equal(p.ResinPriorityList.Count,0);if(throwTask)throw Error('cast unverified');return {rewardCount};},
    writeText:async(p,t)=>{files[p]=t;return !failWrite;},readText:p=>files[p],emit:e=>event=e},calls:()=>calls,event:()=>event};
}
test('exact no-claim parameters checkpoint before one native invocation',async()=>{const h=host();const r=await runRehearsal(settings,h.api);assert.equal(h.calls(),1);assert.equal(r.status,'success');assert.equal(r.noRewardClaim,true);assert.equal(r.nativeReturnCompleted,true);assert.deepEqual(r.rewards,{});assert.equal(r.targetReached,false);});
test('unsupported engine flag blocks before invoking native task',async()=>{const h=host({badField:true});const r=await runRehearsal(settings,h.api);assert.equal(h.calls(),0);assert.equal(r.status,'failed');});
test('unexpected rewards cannot count as rehearsal success',async()=>{const h=host({rewardCount:1});const r=await runRehearsal(settings,h.api);assert.equal(r.status,'failed');assert.equal(r.nativeReturnCompleted,false);});
test('native cast failure is terminal and never replayed',async()=>{const h=host({throwTask:true});const r=await runRehearsal(settings,h.api);assert.equal(h.calls(),1);assert.equal(r.status,'failed');assert.equal(h.event().status,'failed');});
test('failed checkpoint prevents native operation and successful final event',async()=>{const h=host({failWrite:true});await assert.rejects(runRehearsal(settings,h.api));assert.equal(h.calls(),0);assert.equal(h.event(),undefined);});
test('unverified domain and excessive timeout are rejected',async()=>{for(const bad of [{domainName:'其他秘境'},{maxMinutes:6},{strategyName:'其他队伍'}]){const h=host();await assert.rejects(runRehearsal({...settings,...bad},h.api));assert.equal(h.calls(),0);}});
