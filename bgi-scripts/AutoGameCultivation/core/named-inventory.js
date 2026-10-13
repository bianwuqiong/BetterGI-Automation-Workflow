// GPL-3.0-only. Bounded readonly native snapshots; never a consumer or Session After proof.
const fail=m=>{throw Error(m);};
const exactKeys=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join()===keys.sort().join();
// Complete raw timelines remain bounded; over-limit responses are rejected, never truncated.
export const NAMED_INVENTORY_MAX_UTF8_BYTES=16000000;
export function buildNamedInventoryRequest(scope,context){
  if(!exactKeys(scope,['executionEnabled','policy','materials'])||scope.executionEnabled!==false
      ||!exactKeys(scope.policy,['originalResinBudget','condensedResinBudget','maxMinutes'])
      ||scope.policy.originalResinBudget!==0||scope.policy.condensedResinBudget!==0
      ||!Number.isInteger(scope.policy.maxMinutes)||scope.policy.maxMinutes<1||scope.policy.maxMinutes>3)fail('named_inventory_requires_readonly_zero_budget_scope');
  if(!context||typeof context.runId!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(context.runId)
      ||typeof context.stepId!=='string'||!context.stepId||context.stepId.length>128||context.stepId.trim()!==context.stepId||/[\x00-\x1f\x7f-\x9f]/.test(context.stepId)
      ||!['diagnostic','before','after'].includes(context.phase))fail('named_inventory_runner_run_step_phase_invalid');
  if(!Array.isArray(scope.materials)||scope.materials.length<1||scope.materials.length>8)fail('named_inventory_one_to_eight_scope_pairs_required');
  for(const m of scope.materials)if(!exactKeys(m,['materialId','materialName'])||typeof m.materialId!=='string'||!/^(104|112|113|114)[0-9]{3}$/.test(m.materialId)
      ||typeof m.materialName!=='string'||!m.materialName||m.materialName.length>80||m.materialName.trim()!==m.materialName||/[\x00-\x1f\x7f-\x9f]/.test(m.materialName))fail('named_inventory_exact_pairs_only_no_caller_stock_cost_binding');
  if(new Set(scope.materials.map(m=>m.materialId)).size!==scope.materials.length||new Set(scope.materials.map(m=>m.materialName)).size!==scope.materials.length)fail('named_inventory_duplicate_pair');
  return {runId:context.runId,stepId:context.stepId,phase:context.phase,materials:scope.materials.map(m=>({...m}))};
}
const boundedJson=(s,max)=>{
  if(typeof s!=='string'||s.length>max)fail('named_inventory_native_json_unbounded');
  let bytes=0;for(const c of s){const v=c.codePointAt(0);bytes+=v<128?1:v<2048?2:v<65536?3:4;}if(bytes>max)fail('named_inventory_native_utf8_unbounded');
  return JSON.parse(s);
};
export function createNamedInventoryReader({dispatcher,log}){
  return async(scope,context,remainingMilliseconds)=>{
    const request=buildNamedInventoryRequest(scope,context);
    if(!Number.isFinite(remainingMilliseconds)||remainingMilliseconds<=0)fail('named_inventory_deadline_expired');
    const serialized=JSON.stringify(request);boundedJson(serialized,8192);
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try{
      cts.CancelAfter(Math.max(1,Math.min(scope.policy.maxMinutes*60000,180000,Math.floor(remainingMilliseconds))));
      const bindingReceipt=boundedJson(await dispatcher.ReadNamedInventoryBinding(cts.Token),64000);
      const raw=boundedJson(await dispatcher.ReadNamedCultivationInventory(serialized,cts.Token),NAMED_INVENTORY_MAX_UTF8_BYTES);
      log?.Info('[CULTIVATION_NAMED_INVENTORY_RAW] {payload}',JSON.stringify({bindingReceipt,nativeObservation:raw}));return {bindingReceipt,nativeObservation:raw};
    }finally{cts.Dispose();}
  };
}
export function createBoundMoraReader({dispatcher,log}){
  return async remainingMilliseconds=>{
    if(!Number.isFinite(remainingMilliseconds)||remainingMilliseconds<=0)fail('bound_mora_deadline_expired');
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try{
      cts.CancelAfter(Math.max(1,Math.min(180000,Math.floor(remainingMilliseconds))));
      const bindingReceipt=boundedJson(await dispatcher.ReadNamedInventoryBinding(cts.Token),64000);
      const raw=boundedJson(await dispatcher.ReadBoundMoraSnapshot('{}',cts.Token),8000000);
      log?.Info('[CULTIVATION_BOUND_MORA_RAW] {payload}',JSON.stringify({bindingReceipt,nativeObservation:raw}));return {bindingReceipt,nativeObservation:raw};
    }finally{cts.Dispose();}
  };
}
export async function readNamedInventory(api,scope,context,deadline){
  const request=buildNamedInventoryRequest(scope,context),packet={readOnly:true,targetReached:false,completedUpgrades:0,consumptionVerified:false,sessionAfterVerified:false,
    request,bindingReceipt:null,nativeObservation:null,rawEvidenceVerified:false,liveVerified:false,
    inventory:Object.fromEntries(request.materials.map(m=>[m.materialId,{name:m.materialName,count:null,status:'unknown'}])),
    readStartedAt:new Date(api.now()).toISOString(),readFinishedAt:null};
  try{const read=await api.readNamedCultivationInventory(scope,context,deadline-api.now());packet.bindingReceipt=read.bindingReceipt;packet.nativeObservation=read.nativeObservation;}
  catch(error){packet.reason=String(error?.message||error).slice(0,300);}
  packet.readFinishedAt=new Date(api.now()).toISOString();
  // Trusted runtime assets, OS context and original private PNGs are checked by the Host.
  return packet;
}
export async function readBoundMora(api,deadline){
  const packet={readOnly:true,targetReached:false,completedUpgrades:0,consumptionVerified:false,sessionAfterVerified:false,rawEvidenceVerified:false,liveVerified:false,
    bindingReceipt:null,nativeObservation:null,balance:null,readStartedAt:new Date(api.now()).toISOString(),readFinishedAt:null};
  try{const read=await api.readBoundMoraSnapshot(deadline-api.now());packet.bindingReceipt=read.bindingReceipt;packet.nativeObservation=read.nativeObservation;}
  catch(error){packet.reason=String(error?.message||error).slice(0,300);}
  packet.readFinishedAt=new Date(api.now()).toISOString();return packet;
}
