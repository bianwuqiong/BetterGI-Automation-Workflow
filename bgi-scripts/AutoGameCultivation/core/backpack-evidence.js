// GPL-3.0-only. Revalidate named selected stacks; a missing stack remains unknown.
import {normalizeGuideText} from './weapon-guide.js';

const rectValid=r=>r && ['x','y','width','height'].every(k=>Number.isFinite(r[k]))
  && r.x>=0 && r.y>=0 && r.width>0 && r.height>0;
const inside=(a,b)=>rectValid(a) && rectValid(b) && a.x>=b.x && a.y>=b.y
  && a.x+a.width<=b.x+b.width && a.y+a.height<=b.y+b.height;
const sameRect=(a,b)=>rectValid(a) && rectValid(b) && ['x','y','width','height'].every(k=>a[k]===b[k]);
function frameCount(frame,name,selection) {
  if(!frame || !Number.isFinite(frame.observedAt) || !rectValid(frame.nameRegion)
    || frame.selectedItemVerified!==true || !sameRect(frame.selectedItemRect,selection.itemRect)
    || !inside(frame.countRegion,selection.itemRect) || !Array.isArray(frame.nameRows)
    || !Array.isArray(frame.countRows) || frame.nameRows.some(row=>!inside(row,frame.nameRegion))
    || frame.countRows.some(row=>!inside(row,frame.countRegion))) return null;
  // The selected item's complete name and its stack quantity must both exist in this capture.
  if(frame.nameRows.filter(row=>normalizeGuideText(row.text)===normalizeGuideText(name)).length!==1
    || frame.countRows.length!==1) return null;
  const text=normalizeGuideText(frame.countRows[0].text);
  if(frame.countMethod!=='raw_ocr_without_detector' || typeof frame.rawCountText!=='string'
    || normalizeGuideText(frame.rawCountText)!==text || !/^\d{1,9}$/.test(text)) return null;
  const count=Number(text);
  return Number.isSafeInteger(count) && count>=0 && count<=999999999 ? count : null;
}

export function verifyBackpackInventory(result,request) {
  const inventory={};
  const experience={104011:'精锻用杂矿',104012:'精锻用良矿',104013:'精锻用魔矿'};
  const category=request.category??'weaponAscension';
  for(const material of request.materials??[]) {
    const unknown=reason=>({name:material.materialName,count:null,status:'unknown',reason});
    const pair=result?.observations?.[material.materialId], selection=pair?.selection;
    const identityOk=category==='weaponExperience'?experience[material.materialId]===material.materialName:
      category==='weaponAscension'&&/^114\d+$/.test(String(material.materialId));
    if(!identityOk || !normalizeGuideText(material.materialName)
      || result?.readOnly!==true || result.source!=='backpack_selected_stack'
      ||category==='weaponExperience'&&(result.category!==category||result.cleanupCompleted!==true)
      || result.mainUiRestored!==true || !selection || !rectValid(selection.itemRect)
      || !Number.isFinite(selection.clickedAt) || !Number.isFinite(selection.x)
      || !Number.isFinite(selection.y) || selection.x<selection.itemRect.x
      || selection.x>selection.itemRect.x+selection.itemRect.width
      || selection.y<selection.itemRect.y || selection.y>selection.itemRect.y+selection.itemRect.height) {
      inventory[material.materialId]=unknown('backpack_selection_or_cleanup_unverified');continue;
    }
    const {first,second}=pair;
    if(!Number.isFinite(first?.observedAt) || !Number.isFinite(second?.observedAt)
      || first.observedAt-selection.clickedAt<100 || first.observedAt-selection.clickedAt>5000
      || second.observedAt-first.observedAt<100 || second.observedAt-first.observedAt>5000
      || !sameRect(first.nameRegion,second.nameRegion) || !sameRect(first.countRegion,second.countRegion)) {
      inventory[material.materialId]=unknown('backpack_independent_frames_missing');continue;
    }
    const a=frameCount(first,material.materialName,selection),b=frameCount(second,material.materialName,selection);
    inventory[material.materialId]=a!==null && a===b
      ? {name:material.materialName,count:a,status:'exact',verified:true,source:'backpack_selected_stack',
        evidence:{materialId:material.materialId,selection,first,second}}
      : unknown('backpack_full_name_or_stack_count_unverified');
  }
  return inventory;
}
