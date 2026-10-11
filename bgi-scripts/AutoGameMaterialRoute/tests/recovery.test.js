import test from 'node:test';
import assert from 'node:assert/strict';
import {runMaterialRecovery} from '../recovery.js';
const team=['桑多涅','奥黛塔','八重神子','钟离'];
const request={runId:'recovery-test',sessionId:'recovery-test',partyName:'待命队伍',expectedTeam:team,
  safeHub:'mondstadt-city',stage:'startup',timeoutSeconds:60};
const settings={runId:request.runId,gameDate:'2026-10-09',mode:'material-recovery',recoveryJson:JSON.stringify(request),
  originalResinBudget:0,condensedResinBudget:0,fragileResinBudget:0,transientResinBudget:0,allowCrafting:false,allowUpgrade:false};
function fake({badWrite=false,status='completed',wrongPosition=false}={}) {
  let clock=Date.UTC(2026,9,9,9),calls=0;const files={},events=[];
  const api={files,events,get calls(){return calls;},now:()=>clock,
    countItems:()=>assert.fail('Recovery must not scan inventory'),runRoute:()=>assert.fail('Recovery must not farm'),
    writeText:async(p,t)=>{files[p]=t;return !badWrite;},readText:p=>files[p],emit:e=>events.push(e),
    runRecovery:async r=>{calls++;clock+=1500;return {task:'material-route-recovery',runId:r.runId,sessionId:r.sessionId,stage:r.stage,
      parameterEvidence:JSON.parse(JSON.stringify(r)),actualTeam:team,actualPosition:wrongPosition?{x:0,y:0}:{x:-867.7,y:2281.38},
      elapsedMs:1500,status,...Object.fromEntries(['loadingObserved','mainUiRestored','grounded','positionVerified','noRevivePrompt',
        'teamVerified','scopeRecovered','cleanupCompleted','noResinSpend','noFood','noRevive','noCrafting','noUpgrade'].map(k=>[k,true])),evidenceVerified:status==='completed'};}};
  return api;
}
test('recovery only calls fixed-hub native API once and persists independently verified proof',async()=>{
  const api=fake(),report=await runMaterialRecovery(settings,api);assert.equal(api.calls,1);assert.equal(report.status,'success');
  assert.equal(report.wallSeconds,1.5);assert.deepEqual(report.rewards,{});assert.deepEqual(report.resinEvents,[]);
  assert.equal(api.events.length,1);assert.equal(api.events[0].task,'材料安全恢复');assert.equal(api.events[0].status,'success');
});
test('failed native recovery stays failed without route, inventory or replay',async()=>{
  for(const status of ['failed','cancelled','timeout']){const api=fake({status});assert.equal((await runMaterialRecovery(settings,api)).status,status);assert.equal(api.calls,1);}
});
test('completed label with rejected real position remains unknown',async()=>{
  const api=fake({wrongPosition:true});assert.equal((await runMaterialRecovery(settings,api)).status,'unknown');assert.equal(api.calls,1);
});
test('invalid stage, scope, arbitrary hub or resource allowance fails before native recovery',async()=>{
  for(const edit of [{stage:'after'},{sessionId:'other'},{safeHub:'arbitrary'},{timeoutSeconds:61},{expectedTeam:['钟离']},{extraCoordinate:100}]){
    const api=fake();await assert.rejects(()=>runMaterialRecovery({...settings,recoveryJson:JSON.stringify({...request,...edit})},api));assert.equal(api.calls,0);
  }
  await assert.rejects(()=>runMaterialRecovery({...settings,fragileResinBudget:1},fake()));
});
test('checkpoint failure and another game day prevent any native call',async()=>{
  const api=fake({badWrite:true});await assert.rejects(()=>runMaterialRecovery(settings,api),/checkpoint/);assert.equal(api.calls,0);
  const second=fake();await assert.rejects(()=>runMaterialRecovery({...settings,gameDate:'2026-10-08'},second));assert.equal(second.calls,0);
});
