// GPL-3.0-only. Derived after strict preview verification; never a spending permit.
const KEYS={'普通攻击':'normal','元素战技':'skill','元素爆发':'burst'};
const count=(v,min=0)=>Number.isInteger(v)&&v>=min&&v<=999999999;
export function deriveSingleTalentStep(target,type,costs,catalog) {
  const key=KEYS[type],goal=target?.talentTargets?.[key];
  if(!key||!Number.isInteger(goal)||goal<1||goal>10||!costs
      ||!Number.isInteger(costs.currentBaseLevel)||costs.currentBaseLevel<1||costs.currentBaseLevel>9
      ||costs.nextBaseLevel!==costs.currentBaseLevel+1||typeof costs.talentName!=='string'||!costs.talentName)
    throw Error('single_talent_target_or_verified_cost_invalid');
  const reached=costs.currentBaseLevel>=goal;
  const plan={kind:'single-talent-next-step',readOnly:true,executionEnabled:false,targetReached:false,
    characterName:target.characterName,talentType:type,talentName:costs.talentName,
    currentBaseLevel:costs.currentBaseLevel,nextBaseLevel:reached?null:costs.nextBaseLevel,targetBaseLevel:goal,
    status:reached?'selected-talent-at-target':'awaiting-upgrade-verification',materials:[],mora:null,namedInventoryScope:null};
  if(reached)return plan;
  if(!Array.isArray(costs.materials)||!costs.materials.length||costs.materials.length>8
      ||!catalog||typeof catalog!=='object')throw Error('single_talent_material_scope_missing');
  for(const material of costs.materials){
    const matches=Object.entries(catalog).filter(([,row])=>row?.name===material.name);
    if(matches.length!==1||!/^(104|112|113|114)[0-9]{3}$/.test(matches[0][0])
        ||!count(material.owned)||!count(material.required,1))throw Error('single_talent_exact_material_mapping_or_quantity_missing');
    plan.materials.push({materialId:matches[0][0],materialName:material.name,owned:material.owned,
      required:material.required,missing:Math.max(0,material.required-material.owned)});
  }
  if(new Set(plan.materials.map(m=>m.materialId)).size!==plan.materials.length
      ||!count(costs.mora?.owned)||!count(costs.mora?.required,1))throw Error('single_talent_duplicate_material_or_mora_invalid');
  plan.mora={...costs.mora,missing:Math.max(0,costs.mora.required-costs.mora.owned)};
  plan.namedInventoryScope={executionEnabled:false,policy:{originalResinBudget:0,condensedResinBudget:0,maxMinutes:3},
    materials:plan.materials.map(({materialId,materialName})=>({materialId,materialName}))};
  return plan;
}
