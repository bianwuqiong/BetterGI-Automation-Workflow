import test from 'node:test';
import assert from 'node:assert/strict';
import {buildNamedInventoryRequest,createNamedInventoryReader,createBoundMoraReader,readNamedInventory,NAMED_INVENTORY_MAX_UTF8_BYTES} from '../core/named-inventory.js';
const scope=()=>({executionEnabled:false,policy:{originalResinBudget:0,condensedResinBudget:0,maxMinutes:3},materials:[{materialId:'104301',materialName:'合成教导'}]});
const context={runId:'synthetic-run',stepId:'synthetic-step',phase:'diagnostic'};
test('runner context is injected into bounded frozen pairs and caller cost/stock/binding/execution cannot enter',()=>{
  const s=scope(),r=buildNamedInventoryRequest(s,context);s.materials[0].materialName='修改';assert.equal(r.materials[0].materialName,'合成教导');
  for(const modify of [s=>s.executionEnabled=true,s=>s.policy.originalResinBudget=20,s=>s.binding={},s=>s.materials[0].owned=7,s=>s.materials[0].required=3,s=>s.materials.push({...s.materials[0]})]){
    const bad=scope();modify(bad);assert.throws(()=>buildNamedInventoryRequest(bad,context));
  }
});
test('actual native pre-binding receipt is obtained separately with linked CTS and no fabricated result binding',async()=>{
  let disposed=0,called=[];const cts={Token:{},CancelAfter:n=>assert.equal(n,180000),Dispose:()=>disposed++};
  const dispatcher={GetLinkedCancellationTokenSource:()=>cts,ReadNamedInventoryBinding:async token=>{assert.equal(token,cts.Token);called.push('binding');return JSON.stringify({source:'native-binding'});},
    ReadNamedCultivationInventory:async(json,token)=>{called.push('snapshot');assert.deepEqual(JSON.parse(json),buildNamedInventoryRequest(scope(),context));return JSON.stringify({source:'native-raw'});}};
  const result=await createNamedInventoryReader({dispatcher})(scope(),context,180000);assert.deepEqual(called,['binding','snapshot']);assert.equal(disposed,1);assert.equal(result.bindingReceipt.source,'native-binding');
});
test('Mora accepts only fixed empty request and CTS disposes on malformed/unbounded/native exception',async()=>{
  for(const value of ['{bad','x'.repeat(8000001),null]){
    let disposed=0;const cts={Token:{},CancelAfter:()=>{},Dispose:()=>disposed++};
    const dispatcher={GetLinkedCancellationTokenSource:()=>cts,ReadNamedInventoryBinding:async()=>'{"readOnly":true}',ReadBoundMoraSnapshot:async json=>{assert.equal(json,'{}');return value;}};
    await assert.rejects(createBoundMoraReader({dispatcher})(30000));assert.equal(disposed,1);
  }
});
test('raw archive preserves independent receipt, keeps counts null and never claims live or Session After',async()=>{
  let now=1000;const raw={status:'verified',inventory:{104301:7}};const api={now:()=>now,readNamedCultivationInventory:async()=>{now+=100;return {bindingReceipt:{source:'native'},nativeObservation:raw};}};
  const p=await readNamedInventory(api,scope(),context,5000);assert.equal(p.nativeObservation,raw);assert.equal(p.inventory['104301'].count,null);
  assert.equal(p.rawEvidenceVerified,false);assert.equal(p.liveVerified,false);assert.equal(p.sessionAfterVerified,false);assert.equal(p.completedUpgrades,0);
});
test('complete named timelines at the fixed byte limit survive; over-limit ASCII and UTF8 never truncate',async()=>{
  const max=NAMED_INVENTORY_MAX_UTF8_BYTES;
  const overhead=JSON.stringify({pad:''}).length;
  const read=async value=>{
    let disposed=0;
    const cts={Token:{},CancelAfter:()=>{},Dispose:()=>disposed++};
    const dispatcher={GetLinkedCancellationTokenSource:()=>cts,ReadNamedInventoryBinding:async()=>'{"readOnly":true}',
      ReadNamedCultivationInventory:async()=>value};
    try{return await createNamedInventoryReader({dispatcher})(scope(),context,30000);}
    finally{assert.equal(disposed,1);}
  };
  const ascii='x'.repeat(max-overhead);
  assert.equal((await read(JSON.stringify({pad:ascii}))).nativeObservation.pad.length,ascii.length);
  await assert.rejects(read(JSON.stringify({pad:ascii+'x'})),/named_inventory_native_json_unbounded/);
  const count=Math.floor((max-overhead)/3),remainder=(max-overhead)%3;
  const unicode='你'.repeat(count)+'x'.repeat(remainder);
  assert.equal((await read(JSON.stringify({pad:unicode}))).nativeObservation.pad,unicode);
  await assert.rejects(read(JSON.stringify({pad:unicode+'你'})),/named_inventory_native_utf8_unbounded/);
});
