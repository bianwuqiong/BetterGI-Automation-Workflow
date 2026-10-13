import test from 'node:test';
import assert from 'node:assert/strict';
import {runMaterialRouteSession,recoveryCompleted} from '../session.js';
const roster=['桑多涅','奥黛塔','八重神子','钟离'];
const route=(c,x)=>({relativePath:`auto_game_handguard/${'a'.repeat(40)}/${c}.json`,sha256:c.repeat(64),catalogCommit:'a'.repeat(40),name:c,fightPoints:[{x,y:0}]});
const payload={schemaVersion:1,sessionId:'session-test',gameDate:'2026-10-09',partyName:'待命队伍',
  expectedTeam:roster,strategyName:'木偶星超导',requireZhongliShield:true,safeHub:'mondstadt-city',
  segments:[{segmentId:'s1',runId:'session-test-s1',route:route('b',0),timeoutSeconds:120},
    {segmentId:'s2',runId:'session-test-s2',route:route('c',500),timeoutSeconds:150}]};
const settings={runId:payload.sessionId,gameDate:payload.gameDate,mode:'material-route-session',sessionJson:JSON.stringify(payload),
  originalResinBudget:0,condensedResinBudget:0,fragileResinBudget:0,transientResinBudget:0,allowCrafting:false,allowUpgrade:false};
function proof(request) {return {task:'material-route-recovery',status:'completed',runId:request.runId,sessionId:request.sessionId,
  stage:request.stage,parameterEvidence:structuredClone(request),actualTeam:roster,actualPosition:{x:-867.7041015625,y:2281.378173828125},
  elapsedMs:1000,...Object.fromEntries(['loadingObserved','mainUiRestored','grounded','positionVerified','noRevivePrompt','teamVerified',
    'evidenceVerified','scopeRecovered','cleanupCompleted','noResinSpend','noFood','noRevive','noCrafting','noUpgrade'].map(k=>[k,true]))};}
function fake({startupFails=false,routeFails=false,afterFails=false,badWrite=false,corruptRecovery=false}={}) {
  let clock=Date.UTC(2026,9,9,9),scans=0;const files={},events=[],routes=[],recoveries=[];
  return {files,events,routes,recoveries,now:()=>clock,sleep:async ms=>{clock+=ms;},clearTriggers:()=>{},
    countItems:async names=>{clock+=1000;scans++;return Object.fromEntries(names.map(n=>[n,10+Math.floor((scans-1)/2)]));},
    runRoute:async request=>{routes.push(request);clock+=2000;return {status:routeFails?'failed':'completed',
      cleanupCompleted:true,mainUiRestored:true,parameterEvidence:structuredClone(request),elapsedMs:2000,completedFightPoints:['verified']};},
    runRecovery:async request=>{recoveries.push(request);clock+=1000;let result=proof(request);
      if(startupFails&&request.stage==='startup'||afterFails&&request.stage==='after')result={...result,status:'failed',evidenceVerified:false};
      if(corruptRecovery)result.actualPosition={x:0,y:0};events.push(result);return result;},
    writeText:async(p,t)=>{files[p]=t;return !badWrite;},readText:p=>files[p],emit:e=>events.push(e)};
}
test('two routes share one bounded session and preserve segment IDs, scans and exact seconds',async()=>{
  const api=fake(),result=await runMaterialRouteSession(settings,api);
  assert.equal(result.status,'success');assert.equal(api.routes.length,2);assert.equal(api.recoveries.length,3);
  assert.deepEqual(api.routes.map(r=>r.timeoutSeconds),[120,150]);
  assert.deepEqual(api.recoveries.map(r=>[r.runId,r.stage]),[['session-test','startup'],['session-test-s1','after'],['session-test-s2','after']]);
  for(const row of result.segments){const report=JSON.parse(api.files[row.reportRelativePath]);assert.equal(report.sessionId,'session-test');assert.equal(report.segmentId,row.segmentId);assert.equal(report.materialGains['112044'],1);}
  assert.ok(result.wallSeconds>=15);assert.equal(api.events.filter(e=>e.task==='material-route-session').length,1);
});
test('startup failure prevents all inventory scans, route calls and segment records',async()=>{
  const api=fake({startupFails:true}),result=await runMaterialRouteSession(settings,api);
  assert.equal(result.status,'failed');assert.equal(api.routes.length,0);assert.equal(api.recoveries.length,1);
  assert.deepEqual(result.segments.map(r=>r.status),['not-started','not-started']);
  assert.equal(api.events.filter(e=>e.task==='material-route-inventory').length,0);
  assert.deepEqual(Object.keys(api.files),['record/session-test.json']);
});
test('failed native route is never replayed and next route does not start',async()=>{
  const api=fake({routeFails:true}),result=await runMaterialRouteSession(settings,api);
  assert.equal(api.routes.length,1);assert.equal(api.recoveries.length,2);assert.equal(result.status,'failed');
  assert.deepEqual(result.segments.map(r=>r.status),['failed','not-started']);
  assert.equal(JSON.parse(api.files['record/session-test-s1.json']).materialGains['112044'],1);
});
test('after recovery failure retains proved route gains but stops continuation',async()=>{
  const api=fake({afterFails:true}),result=await runMaterialRouteSession(settings,api);
  assert.equal(api.routes.length,1);assert.equal(result.status,'failed');assert.equal(result.segments[0].status,'success');
  assert.equal(result.segments[0].recoveryVerified,false);assert.equal(result.segments[1].status,'not-started');
  assert.equal(JSON.parse(api.files['record/session-test-s1.json']).materialGainsVerified,true);
});
test('completed label without real hub coordinates cannot allow combat',async()=>{
  const api=fake({corruptRecovery:true});assert.equal((await runMaterialRouteSession(settings,api)).status,'failed');assert.equal(api.routes.length,0);
});
test('recovery proof rejects wrong party, stage, scope, missing flag and excessive duration',()=>{
  const request={runId:'session-test',sessionId:'session-test',stage:'startup',partyName:'待命队伍',safeHub:'mondstadt-city',expectedTeam:roster,timeoutSeconds:60};
  const valid=proof(request);assert.equal(recoveryCompleted(valid,request),true);
  for(const edit of [{actualTeam:[...roster].reverse()},{stage:'after'},{sessionId:'other'},{loadingObserved:false},{elapsedMs:65001},
    {parameterEvidence:{...request,timeoutSeconds:480}},{noRevive:false}])assert.equal(recoveryCompleted({...valid,...edit},request),false);
});
test('invalid budgets, duplicate/overlap routes and changed session IDs fail before game APIs',async()=>{
  for(const p of [{...payload,sessionId:'other'},{...payload,segments:[payload.segments[0],{...payload.segments[1],route:route('c',40)}]},
    {...payload,expectedTeam:roster.slice(1)}]){const api=fake();await assert.rejects(()=>runMaterialRouteSession({...settings,sessionJson:JSON.stringify(p)},api));assert.equal(api.routes.length,0);assert.equal(api.recoveries.length,0);}
  await assert.rejects(()=>runMaterialRouteSession({...settings,originalResinBudget:1},fake()));
});
test('initial checkpoint failure prevents native recovery and route execution',async()=>{
  const api=fake({badWrite:true});await assert.rejects(()=>runMaterialRouteSession(settings,api),/checkpoint/);assert.equal(api.recoveries.length,0);assert.equal(api.routes.length,0);
});
