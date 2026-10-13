// GPL-3.0-only. JSON bridge to the bounded native reader; no caller-selected coordinates or resource actions.
import {verifyBackpackInventory} from './backpack-evidence.js';

export function createBackpackInventoryReader({dispatcher,log}) {
  return async (request,remainingMilliseconds)=> {
    const materials=request?.materials;
    const experience={104011:'精锻用杂矿',104012:'精锻用良矿',104013:'精锻用魔矿'};
    const category=request?.category??'weaponAscension';
    if(!['weaponAscension','weaponExperience'].includes(category))throw new Error('backpack_invalid_bounded_material_request');
    if(!Array.isArray(materials) || materials.length<1 || materials.length>8
      || materials.some(m=> typeof m.materialId!=='string' || (category==='weaponExperience'
          ?experience[m.materialId]!==m.materialName:!/^114\d+$/.test(m.materialId))
        || typeof m.materialName!=='string' || !m.materialName.trim() || m.materialName.length>100)
      || new Set(materials.map(m=>m.materialId)).size!==materials.length
      || new Set(materials.map(m=>m.materialName)).size!==materials.length)
      throw new Error('backpack_invalid_bounded_material_request');
    const clean={materials:materials.map(({materialId,materialName})=>({materialId,materialName}))};
    if(category==='weaponExperience')clean.category=category;
    let serialized;
    if(remainingMilliseconds!==undefined) {
      if(!Number.isFinite(remainingMilliseconds)||remainingMilliseconds<=0)throw Error('backpack_read_time_budget_invalid');
      const cts=dispatcher.GetLinkedCancellationTokenSource();
      try{cts.CancelAfter(Math.max(1,Math.floor(remainingMilliseconds)));serialized=await dispatcher.ReadBackpackInventory(JSON.stringify(clean),cts.Token);}
      finally{cts.Dispose();}
    } else serialized=await dispatcher.ReadBackpackInventory(JSON.stringify(clean));
    if(typeof serialized!=='string' || serialized.length>1000000)
      throw new Error('backpack_native_json_invalid_or_unbounded');
    const result=JSON.parse(serialized);
    if(!result || Array.isArray(result) || typeof result!=='object') throw new Error('backpack_native_json_not_object');
    // Preserve raw frames for the operator to revalidate; reported native counts are never trusted.
    const verified=verifyBackpackInventory(result,clean);
    log?.Info('[CULTIVATION_BACKPACK_INVENTORY] {payload}',JSON.stringify({
      requested:clean.materials.map(m=>m.materialId),reason:result.reason,
      mainUiRestored:result.mainUiRestored,
      observed:Object.fromEntries(Object.entries(verified).map(([id,row])=>[id,{count:row.count,status:row.status}]))}));
    return result;
  };
}
