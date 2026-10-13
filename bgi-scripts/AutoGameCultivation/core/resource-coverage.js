// GPL-3.0-only. Read-only coverage; no upgrading or alteration of ordinary material inventory.
import {verifyBackpackInventory} from './backpack-evidence.js';
export const WEAPON_EXPERIENCE={104011:'精锻用杂矿',104012:'精锻用良矿',104013:'精锻用魔矿'};
export const experienceRequest=()=>({category:'weaponExperience',materials:Object.entries(WEAPON_EXPERIENCE)
  .map(([materialId,materialName])=>({materialId,materialName}))});
const text=value=>typeof value==='string'?value.normalize('NFKC').trim():'';
const number=value=>Number.isFinite(value)&&typeof value==='number';
const rect=r=>r&&['x','y','width','height'].every(k=>number(r[k]))&&r.x>=0&&r.y>=0&&r.width>0&&r.height>0;
const inside=(a,b)=>rect(a)&&rect(b)&&a.x>=b.x&&a.y>=b.y&&a.x+a.width<=b.x+b.width&&a.y+a.height<=b.y+b.height;
const same=(a,b)=>rect(a)&&rect(b)&&['x','y','width','height'].every(k=>a[k]===b[k]);
const balance=raw=>/^(0|[1-9][0-9]{0,9})$/.test(text(raw))&&Number(text(raw))<=2147483647?Number(text(raw)):null;
function moraFrame(frame,start,finish) {
  const w=frame?.width,h=frame?.height,s=w/1920,icon=frame?.iconRegion,amount=frame?.balanceRegion;
  if(!Number.isInteger(w)||w<800||!Number.isInteger(h)||w*9!==h*16||!number(frame.observedAt)
      ||frame.observedAt<start||frame.observedAt>finish||frame.backpackTabVerified!==true||frame.promptVisible!==false
      ||!Array.isArray(frame.headerRows)||frame.headerRows.filter(row=>text(row.text)==='贵重道具').length!==1
      ||frame.headerRows.some(row=>!inside(row,{x:100*s,y:0,width:350*s,height:100*s}))
      ||frame.iconName!=='摩拉'||!number(frame.iconScore)||frame.iconScore<.75||frame.iconScore>1
      ||!rect(icon)||!rect(amount)||icon.x<330*s-1||icon.y<970*s-1||icon.x+icon.width>420*s+1||icon.y+icon.height>1070*s+1
      ||amount.x<390*s-1||amount.y<970*s-1||amount.x+amount.width>750*s+1||amount.y+amount.height>1070*s+1
      ||icon.x+icon.width>amount.x||amount.x-icon.x-icon.width>25*s+1
      ||!Array.isArray(frame.balanceRows)||frame.balanceRows.length!==1)return null;
  const row=frame.balanceRows[0];
  if(!inside(row,amount)||row.x-amount.x<2*s||amount.x+amount.width-row.x-row.width<2*s)return null;
  const a=balance(frame.rawBalanceText),b=balance(row.text);return a!==null&&a===b?a:null;
}
export function verifyMoraObservation(raw,start,finish) {
  const unknown=reason=>({name:'摩拉',count:null,status:'unknown',reason});
  if(raw?.source!=='precious_items_bottom_mora'||raw.readOnly!==true||raw.materialId!=='202'||raw.materialName!=='摩拉'
      ||raw.verified!==true||raw.status!=='verified'||raw.mainUiRestored!==true||raw.cleanupCompleted!==true)return unknown('mora_identity_or_cleanup_unverified');
  const {first,second}=raw,at=Date.parse(raw.observedAt??'');
  if(!first||!second||first.width!==second.width||first.height!==second.height
      ||!same(first.iconRegion,second.iconRegion)||!same(first.balanceRegion,second.balanceRegion)
      ||!number(second.observedAt)||!number(first.observedAt)||second.observedAt-first.observedAt<100
      ||second.observedAt-first.observedAt>5000||!number(at)||Math.abs(at-second.observedAt)>1)return unknown('mora_independent_frames_missing');
  const a=moraFrame(first,start,finish),b=moraFrame(second,start,finish);
  return a!==null&&a===b&&Number.isInteger(raw.balance)&&raw.balance===a
    ?{name:'摩拉',count:a,status:'exact',verified:true,source:raw.source,evidence:raw}
    :unknown('mora_model_or_full_integer_pair_unverified');
}
export async function readResourceCoverage(api,start,deadline) {
  const raw={moraObservation:null,weaponExperienceObservation:null},inventory={};
  try {raw.moraObservation=await api.readMoraSnapshot(Math.max(1,deadline-api.now()));}
  catch(error){raw.moraError=String(error?.message||error).slice(0,250);}
  inventory['202']=verifyMoraObservation(raw.moraObservation,start,api.now());
  if(raw.moraObservation?.mainUiRestored===true&&raw.moraObservation?.cleanupCompleted===true&&api.now()<deadline) {
    try {raw.weaponExperienceObservation=await api.readBackpackInventory(experienceRequest(),Math.max(1,deadline-api.now()));}
    catch(error){raw.weaponExperienceError=String(error?.message||error).slice(0,250);}
  }
  Object.assign(inventory,verifyBackpackInventory(raw.weaponExperienceObservation,experienceRequest()));
  return {...raw,inventory,allVerified:Object.values(inventory).every(row=>row.status==='exact'),
    readOnly:true,upgradeBudgetComplete:false,levelExperienceObserved:false};
}
