import test from 'node:test';
import assert from 'node:assert/strict';
import {runMaterialRoute,normalizeHandguards,MATERIALS} from '../operator.js';
const ids=Object.keys(MATERIALS),settings={runId:'test-route',gameDate:'2026-10-09',mode:'material-route',partyName:'待命队伍',strategyName:'木偶星超导',requireZhongliShield:true,maxMinutes:8,
  routeJson:JSON.stringify({relativePath:`auto_game_handguard/${'a'.repeat(40)}/sample.json`,sha256:'b'.repeat(64),catalogCommit:'a'.repeat(40),name:'sample',fightPoints:[{x:1,y:2}]}),originalResinBudget:0,condensedResinBudget:0,fragileResinBudget:0,transientResinBudget:0,allowCrafting:false,allowUpgrade:false};
function fake({missing=false,unstable=false,status='completed',negative=false,zero=false,cleanup=true,badWrite=false}={}) {
  let clock=Date.UTC(2026,9,9,9),scans=0,runs=0;const files={},events=[];
  const api={files,events,get runs(){return runs;},now:()=>clock,sleep:async ms=>{clock+=ms;},
    countItems:async names=>{clock+=1000;scans++;return Object.fromEntries(names.filter((n,i)=>!missing||i!==2).map(n=>[n,scans>2?(negative?9:zero?10:12):unstable&&scans===2?11:10]));},
    runRoute:async request=>{runs++;clock+=1500;return {status,cleanupCompleted:cleanup,mainUiRestored:true,parameterEvidence:request,elapsedMs:1500,completedFightPoints:['a']};},
    writeText:async(p,t)=>{files[p]=t;return !badWrite;},readText:p=>files[p],emit:e=>events.push(e)};return api;
}
test('one pinned route uses two stable inventory reads on both sides and real deltas',async()=>{const api=fake(),r=await runMaterialRoute(settings,api);assert.equal(api.runs,1);assert.equal(r.status,'success');assert.equal(r.materialGains['112044'],2);assert.equal(api.events.filter(e=>e.task==='material-route-inventory').length,2);});
test('missing or changing pre-route inventory prevents execution and never becomes zero',async()=>{for(const options of [{missing:true},{unstable:true}]){const api=fake(options),r=await runMaterialRoute(settings,api);assert.equal(api.runs,0);assert.equal(r.status,'unknown');assert.equal(r.beforeInventory,null);}});
test('negative inventory delta cannot be claimed as gains',async()=>{const r=await runMaterialRoute(settings,fake({negative:true}));assert.equal(r.status,'unknown');assert.equal(r.materialGainsVerified,false);});
test('zero actual gain is preserved without inventing loot',async()=>{const r=await runMaterialRoute(settings,fake({zero:true}));assert.equal(r.status,'success');assert.ok(Object.values(r.materialGains).every(n=>n===0));});
test('native failure and incomplete cleanup cannot become success',async()=>{for(const options of [{status:'failed'},{cleanup:false}])assert.notEqual((await runMaterialRoute(settings,fake(options))).status,'success');});
test('checkpoint failure prevents any game API and success event',async()=>{const api=fake({badWrite:true});await assert.rejects(()=>runMaterialRoute(settings,api),/checkpoint/);assert.equal(api.runs,0);assert.equal(api.events.length,0);});
test('resource spending, path escape and different game date are rejected',async()=>{for(const s of [{...settings,originalResinBudget:20},{...settings,allowCrafting:true},{...settings,gameDate:'2026-10-08'},{...settings,routeJson:JSON.stringify({relativePath:'../escape.json'})}])await assert.rejects(()=>runMaterialRoute(s,fake()));});
test('explicit dictionary zero is kept while missing, failure sentinel and boolean stay unknown',()=>{const r=normalizeHandguards({'破旧的刀镡':0,'影打刀镡':-1,'名刀镡':false});assert.equal(r['112044'].count,0);assert.equal(r['112045'].count,null);assert.equal(r['112046'].count,null);});
test('exact-second bounds and expected slot roster survive native JSON transport',async()=>{
  const roster=['桑多涅','奥黛塔','八重神子','钟离'],api=fake();
  api.runRoute=async request=>({status:'completed',cleanupCompleted:true,mainUiRestored:true,
    parameterEvidence:JSON.parse(JSON.stringify(request)),elapsedMs:1500,completedFightPoints:['a']});
  const r=await runMaterialRoute({...settings,timeoutSeconds:150,maxMinutes:2.5,expectedTeamJson:JSON.stringify(roster)},api);
  assert.equal(r.parameterEvidence.timeoutSeconds,150);assert.deepEqual(r.parameterEvidence.expectedTeam,roster);
});
test('slot roster mismatch cannot be accepted as requested team',async()=>{
  const api=fake(),roster=['桑多涅','奥黛塔','八重神子','钟离'];
  api.runRoute=async request=>({status:'completed',cleanupCompleted:true,mainUiRestored:true,parameterEvidence:{...request,expectedTeam:['钟离','奥黛塔','八重神子','桑多涅']}});
  const r=await runMaterialRoute({...settings,expectedTeamJson:JSON.stringify(roster)},api);
  assert.equal(r.status,'unknown');assert.equal(r.nativeReturnCompleted,false);
});
