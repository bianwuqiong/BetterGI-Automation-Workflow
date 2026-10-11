import test from 'node:test';
import assert from 'node:assert/strict';
import {createBackpackInventoryReader} from '../core/backpack-reader.js';

const request={materials:[{materialId:'114010',materialName:'狮牙斗士的铁链'}]};
test('native reader receives only bounded material identity JSON and returns unchanged raw evidence',async()=>{
  const response={readOnly:true,source:'backpack_selected_stack',mainUiRestored:true,observations:{},reason:'not_found'};
  const logged=[];let calls=0;
  const read=createBackpackInventoryReader({dispatcher:{ReadBackpackInventory:async json=>{
    calls++;assert.deepEqual(JSON.parse(json),request);return JSON.stringify(response);}},
    log:{Info:(message,payload)=>logged.push(JSON.parse(payload))}});
  assert.deepEqual(await read({...request,originalResinBudget:200,clickX:123}),response);
  assert.equal(calls,1);assert.deepEqual(logged[0].observed,{'114010':{count:null,status:'unknown'}});
});
test('invalid and duplicate material requests never reach native navigation',async()=>{
  let calls=0;const read=createBackpackInventoryReader({dispatcher:{ReadBackpackInventory:async()=>calls++}});
  for(const materials of [[],Array(9).fill(request.materials[0]),[...request.materials,...request.materials],
    [{materialId:'112001',materialName:'史莱姆凝液'}],[{materialId:114010,materialName:'狮牙斗士的铁链'}],
    [{materialId:'114010',materialName:''}]]) await assert.rejects(()=>read({materials}),/invalid_bounded/);
  assert.equal(calls,0);
});
test('malformed, unexpected, or oversized native payloads cannot become an inventory result',async()=>{
  for(const response of ['null','[]','false','{',{},'x'.repeat(1000001)]) {
    const read=createBackpackInventoryReader({dispatcher:{ReadBackpackInventory:async()=>response}});
    await assert.rejects(()=>read(request));
  }
});
