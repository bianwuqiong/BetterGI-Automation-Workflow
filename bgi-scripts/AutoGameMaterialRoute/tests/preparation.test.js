import test from 'node:test';
import assert from 'node:assert/strict';
import {runPartyPreparation} from '../preparation.js';
const team=['桑多涅','奥黛塔','八重神子','钟离'];
const request={runId:'preparation-test',expectedTeam:team,allowStatueRevival:true,timeoutSeconds:120};
const settings={runId:request.runId,gameDate:'2026-10-10',mode:'party-preparation',preparationJson:JSON.stringify(request),
  originalResinBudget:0,condensedResinBudget:0,fragileResinBudget:0,transientResinBudget:0,allowCrafting:false,allowUpgrade:false};
function fake({badWrite=false,status='completed',mutate=()=>{},boundary=false}={}) {
  let clock=Date.UTC(2026,9,10,9),calls=0;const files={},events=[];
  const api={files,events,get calls(){return calls;},now:()=>clock,
    countItems:()=>assert.fail('Preparation must not scan inventory'),runRoute:()=>assert.fail('Preparation must not farm'),
    runRecovery:()=>assert.fail('Preparation must not invoke city recovery'),
    writeText:async(p,t)=>{files[p]=t;return !badWrite;},readText:p=>files[p],emit:e=>events.push(e),
    runPreparation:async r=>{calls++;clock+=boundary?86400000:1500;
      const result={task:'party-preparation',runId:r.runId,parameterEvidence:structuredClone(r),actualTeam:team,
        statue:{id:'4',country:'蒙德',area:'风起地',x:-1265.917,y:1928.381,arrivalX:-1266.3422,arrivalY:1934.3658},
        actualPosition:{x:-1265.917,y:1928.381},elapsedMs:1500,status,activeSlotRestored:4,teamObservationCount:2,
        statueProximityVerified:true,statueProximityObservationCount:2,statueApproachPerformed:true,
        slotHealthEvidence:team.map((name,i)=>({slot:i+1,name,hp:8000,maxHp:10000,ratio:.8,observations:2,
          identityVerified:true,identityObservations:2,ocrMatchingObservations:2})),
        ...Object.fromEntries(['loadingObserved','mainUiRestored','grounded','positionVerified','noRevivePrompt',
          'teamVerified','cleanupCompleted','revivalMayHaveOccurred','noItemConsumption','noRevivalItemConsumption',
          'noResinSpend','noFood','noCrafting','noUpgrade'].map(k=>[k,true])),evidenceVerified:status==='completed'};
      mutate(result);return result;}};
  return api;
}
test('free statue preparation calls native once, declares revival allowance and zero items',async()=>{
  const api=fake(),report=await runPartyPreparation(settings,api);assert.equal(api.calls,1);assert.equal(report.status,'success');
  assert.equal(report.allowStatueRevival,true);assert.equal(report.noItemConsumption,true);assert.equal(report.noRevivalItemConsumption,true);
  assert.equal('noRevive' in report,false);assert.equal(report.targetReached,false);assert.deepEqual(report.rewards,{});
  assert.equal(api.events.length,1);assert.equal(api.events[0].task,'队伍免费恢复');
});
test('failed cancelled timeout native statuses remain terminal with no replay',async()=>{
  for(const status of ['failed','cancelled','timeout']){const api=fake({status});assert.equal((await runPartyPreparation(settings,api)).status,status);assert.equal(api.calls,1);}
});
test('dead low uncertain HP or identity evidence remains unknown',async()=>{
  for(const change of [{hp:0,ratio:0},{hp:7999,ratio:.7999},{hp:null},{hp:true},{ratio:1},{maxHp:0},
    {observations:1},{identityObservations:1},{ocrMatchingObservations:1},{identityVerified:false},{name:'钟离'},{slot:4}]){
    const api=fake({mutate:r=>Object.assign(r.slotHealthEvidence[1],change)});
    assert.equal((await runPartyPreparation(settings,api)).status,'unknown');assert.equal(api.calls,1);
  }
});
test('item revival popup wrong statue or absent cleanup never passes completion',async()=>{
  for(const change of [{noRevivePrompt:false},{noRevive:true},{noRevivalItemConsumption:false},{noItemConsumption:false},
    {noFood:false},{loadingObserved:false},{cleanupCompleted:false},{revivalMayHaveOccurred:false},{teamObservationCount:1},
    {activeSlotRestored:1},{actualPosition:{x:0,y:0}},{actualTeam:team.toReversed()},{statue:{id:'5'}}]){
    const api=fake({mutate:r=>Object.assign(r,change)});assert.equal((await runPartyPreparation(settings,api)).status,'unknown');
  }
});
test('caller cannot choose coordinates item or resin budget or alternate timeout',async()=>{
  for(const change of [{allowStatueRevival:false},{allowStatueRevival:1},{timeoutSeconds:121},{expectedTeam:['钟离']},
    {runId:'foreign'},{statue:{x:0,y:0}},{allowRevivalItems:true}]){
    const api=fake();await assert.rejects(()=>runPartyPreparation({...settings,preparationJson:JSON.stringify({...request,...change})},api));assert.equal(api.calls,0);
  }
  for(const change of [{fragileResinBudget:1},{originalResinBudget:false},{condensedResinBudget:null},{allowCrafting:true},{allowUpgrade:undefined}]){
    const api=fake();await assert.rejects(()=>runPartyPreparation({...settings,...change},api));assert.equal(api.calls,0);
  }
});
test('checkpoint or wrong day stops before native operation, crossed day cannot succeed',async()=>{
  const api=fake({badWrite:true});await assert.rejects(()=>runPartyPreparation(settings,api),/checkpoint/);assert.equal(api.calls,0);
  const second=fake();await assert.rejects(()=>runPartyPreparation({...settings,gameDate:'2026-10-09'},second));assert.equal(second.calls,0);
  assert.equal((await runPartyPreparation(settings,fake({boundary:true}))).status,'unknown');
});
test('new proximity requires real two-frame proof inside five units while legacy failed stays failed',async()=>{
  for(const change of [{statueProximityVerified:false},{statueProximityVerified:1},{statueProximityObservationCount:1},
    {statueProximityObservationCount:true},{statueApproachPerformed:'true'},
    {actualPosition:{x:-1266.3422,y:1934.3658}},{noItemConsumption:false},{noResinSpend:false},{noRevive:null}]){
    const api=fake({mutate:r=>Object.assign(r,change)});assert.equal((await runPartyPreparation(settings,api)).status,'unknown');
    assert.equal(api.calls,1);
  }
  for(const key of ['statueProximityVerified','statueProximityObservationCount']){
    const api=fake({mutate:r=>delete r[key]});assert.equal((await runPartyPreparation(settings,api)).status,'unknown');
  }
  const old=fake({status:'failed',mutate:r=>{delete r.statueProximityVerified;delete r.statueProximityObservationCount;delete r.statueApproachPerformed;}});
  assert.equal((await runPartyPreparation(settings,old)).status,'failed');assert.equal(old.calls,1);
});
