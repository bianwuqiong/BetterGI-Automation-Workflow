// GPL-3.0-only. Read-only weapon guide tooltip inventory; never derives absence as zero.
export const normalizeGuideText = text => String(text ?? '').normalize('NFKC').replace(/\s+/g, '');

export function parseGuideRatio(text) {
  const match = /^(\d+)\/(\d+)$/.exec(normalizeGuideText(text));
  if (!match) return null;
  const owned = Number(match[1]), required = Number(match[2]);
  return Number.isSafeInteger(owned) && Number.isSafeInteger(required) ? {owned, required} : null;
}

// Only a locator for opening a card. A colored count may OCR as "3" or "19" after losing the slash.
// It is never interpreted as inventory; the named tooltip and its labeled ratio remain authoritative.
export const isGuideCountFragment=text=>/^\d{1,7}$/.test(normalizeGuideText(text));

function demandRatio(rows) {
  const labels = rows.filter(row => /^培养需求(?::)?(?:\d+\/\d+)?$/.test(normalizeGuideText(row.text)));
  if (labels.length !== 1) return null;
  const label = labels[0], text = normalizeGuideText(label.text);
  const combined = parseGuideRatio(text.replace(/^培养需求:?/, ''));
  if (combined) return {...combined, bounds: label};
  // OCR may separate the label and ratio. Associate only a unique number to its right on the same row.
  const candidates = rows.filter(row => parseGuideRatio(row.text)
    && Number.isFinite(row.x) && Number.isFinite(row.y) && row.width > 0 && row.height > 0
    && Number.isFinite(label.x) && Number.isFinite(label.y) && label.width > 0 && label.height > 0
    && row.x >= label.x + label.width
    && Math.abs((row.y + row.height / 2) - (label.y + label.height / 2))
      <= Math.min(row.height, label.height) * 0.75);
  return candidates.length === 1 ? {...parseGuideRatio(candidates[0].text), bounds: candidates[0]} : null;
}

function contextMatches(frame, expected) {
  const rows = frame?.contextRows;
  if (!rows || !['characterName','weaponName','targetLevel'].every(key=>Array.isArray(rows[key]))) return false;
  const characterRows = rows.characterName.filter(row => normalizeGuideText(row.text) === normalizeGuideText(expected.characterName));
  const weaponRows = rows.weaponName.filter(row => normalizeGuideText(row.text) === normalizeGuideText(expected.weaponName));
  const targetText = normalizeGuideText(rows.targetLevel.sort((a,b)=>a.y-b.y || a.x-b.x).map(row=>row.text).join(''));
  return characterRows.length === 1 && weaponRows.length === 1
    && new RegExp(`^升级至(?:Lv\\.?)?${expected.targetLevel}(?:级)?$`, 'i').test(targetText);
}

function frameObservation(frame, expected) {
  const rows = frame.tooltipRows ?? [];
  const roi = frame.tooltipRegion;
  if (!roi || !rows.length || rows.some(row =>
    !['x', 'y', 'width', 'height'].every(k => Number.isFinite(row[k]))
    || row.width <= 0 || row.height <= 0 || row.x < roi.x || row.y < roi.y
    || row.x + row.width > roi.x + roi.width || row.y + row.height > roi.y + roi.height)) return null;
  const names = rows.filter(row =>
    normalizeGuideText(row.text) === normalizeGuideText(expected.materialName));
  if (names.length !== 1) return null;
  // Search ROI covers popovers of different heights. The exact unique title must precede the demand row.
  const ratio = demandRatio(rows);
  if (!ratio || ratio.required !== expected.required || names[0].y + names[0].height > ratio.bounds.y) return null;
  return {name: expected.materialName, count: ratio.owned, required: ratio.required,
    ratioBounds: ratio.bounds, titleBounds: names[0]};
}

export function verifyWeaponGuideFrames(first, second, expected, contextEvidence) {
  const unknown = reason => ({name: expected.materialName, count: null, status: 'unknown', reason,
    source: 'character_weapon_guide_tooltip', evidence: {first, second, contextEvidence}});
  if (!expected.characterName || !expected.weaponName || !expected.materialName || !expected.materialId
      || !Number.isInteger(expected.targetLevel) || expected.targetLevel < 1 || expected.targetLevel > 90
      || !Number.isSafeInteger(expected.required) || expected.required < 0)
    return unknown('invalid_expected_guide_context');
  const before = contextEvidence?.before, after = contextEvidence?.after;
  if (!before || !after || before.length !== 2 || after.length !== 2
      || [...before,...after].some(frame => !contextMatches(frame, expected))
      || before[1].observedAt-before[0].observedAt < 100 || after[1].observedAt-after[0].observedAt < 100
      || before[1].observedAt-before[0].observedAt > 5000 || after[1].observedAt-after[0].observedAt > 5000
      || before[1].observedAt > first?.observedAt || second?.observedAt > after[0].observedAt
      || after[1].observedAt-before[0].observedAt > 120000
      || [...before,...after].some(frame => !Number.isFinite(frame.observedAt)))
    return unknown('guide_context_before_and_after_unverified_or_expired');
  if (!Number.isFinite(first?.observedAt) || !Number.isFinite(second?.observedAt)
      || second.observedAt - first.observedAt < 100 || second.observedAt - first.observedAt > 5000)
    return unknown('independent_frames_missing');
  const a = frameObservation(first, expected), b = frameObservation(second, expected);
  if (!a || !b) return unknown('guide_context_title_or_demand_ratio_unverified');
  if (a.count !== b.count) return unknown('guide_inventory_changed_or_ocr_disagreed');
  return {name: expected.materialName, count: a.count, status: 'exact', verified: true,
    source: 'character_weapon_guide_tooltip', evidence: {first, second,
      contextEvidence,
      session: {before:contextEvidence.before,after:contextEvidence.after,
        characterName:expected.characterName,weaponName:expected.weaponName,targetLevel:expected.targetLevel},
      tooltip:[first,second],
      characterName: expected.characterName, weaponName: expected.weaponName,
      targetLevel: expected.targetLevel, materialId: expected.materialId, required: expected.required}};
}

function validateRect(rect) {
  if (!rect || !['x', 'y', 'width', 'height'].every(k => Number.isFinite(rect[k]))
      || rect.x < 0 || rect.y < 0 || rect.width <= 0 || rect.height <= 0)
    throw new Error('Invalid observed guide OCR region');
}

// Uses existing BetterGI capture/OCR APIs. No engine deployment or game resource APIs are needed.
export function createWeaponGuideBgiApi({captureGameRegion, RecognitionObject, sleep, now = () => Date.now(), saveEvidence,
  characterDevelopmentTask, genshin, moveMouseTo, verticalScroll, keyPress}) {
  const navigation=[];
  const rawRow=match=>({text:String(match.Text??''),x:Number(match.X),y:Number(match.Y),
    width:Number(match.Width),height:Number(match.Height)});
  async function pollObservedText(text,region,clickOnce) {
    validateRect(region);
    const deadline=now()+4000;
    for(let attempt=1;attempt<=6;attempt++) {
      if(attempt>1 && now()>=deadline) break;
      const capture=captureGameRegion();let matches=[],found=false;
      const observation={action:clickOnce?'click':'wait',label:text,attempt,region:{...region},observedAt:now(),rows:[]};
      navigation.push(observation);
      try {
        matches=Array.from(capture.FindMulti(RecognitionObject.Ocr(region.x,region.y,region.width,region.height)));
        observation.rows=matches.map(rawRow);
        observation.observedAt=now();
        if(saveEvidence) observation.screenshotPath=saveEvidence(capture);
        const selected=matches.filter(match=>normalizeGuideText(match.Text)===normalizeGuideText(text));
        observation.matchCount=selected.length;
        if(selected.length===1 && now()<=deadline) {
          if(clickOnce) selected[0].Click();
          observation.clicked=clickOnce;
          observation.found=true;
          found=true;
        }
      } catch(error) {
        observation.error=String(error?.message||error);
        throw error;
      } finally {
        for(const match of matches) match.Dispose();
        capture.Dispose();
      }
      if(found) {await sleep(clickOnce?600:180);return;}
      const remaining=deadline-now();
      if(remaining<=0) break;
      if(attempt<6) await sleep(Math.min(500,remaining));
    }
    throw new Error(`Guide label missing or ambiguous: ${text}`);
  }
  function captureOcr(regions) {
    Object.values(regions).forEach(validateRect);
    const capture = captureGameRegion();
    try {
      const result = {};
      for (const [key, rect] of Object.entries(regions)) {
        if (rect.x + rect.width > capture.Width || rect.y + rect.height > capture.Height)
          throw new Error('Observed guide OCR region exceeds actual capture');
        // ClearScript exposes IEnumerable<T> as a native JS iterable, not a get_Item method.
        const matches = Array.from(capture.FindMulti(RecognitionObject.Ocr(rect.x, rect.y, rect.width, rect.height)));
        try {
          result[key] = [];
          for (const match of matches) {
            result[key].push({text: String(match.Text ?? ''), x: Number(match.X), y: Number(match.Y),
              width: Number(match.Width), height: Number(match.Height)});
          }
        } finally {
          for (const match of matches) match.Dispose();
        }
      }
      if (saveEvidence) result.screenshotPath = saveEvidence(capture);
      return {...result, observedAt: now()};
    } finally {capture.Dispose();}
  }
  return {
    captureOcr, sleep, now, navigation,
    waitObservedText:(text,region)=>pollObservedText(text,region,false),
    selectCharacter: name => characterDevelopmentTask.GetCharacterForDevelopmentGuide(name),
    returnMainUi: () => genshin.ReturnMainUi(),
    async scrollGuide(amount, point) {
      if (!Number.isInteger(amount) || Math.abs(amount)>32 || !Number.isFinite(point.x) || !Number.isFinite(point.y))
        throw new Error('Unbounded guide scroll');
      moveMouseTo(point.x,point.y);
      for(let i=0;i<Math.abs(amount);i++) {verticalScroll(Math.sign(amount)); await sleep(40);}
      await sleep(400);
    },
    async closeTooltip() {keyPress('VK_ESCAPE'); await sleep(300);},
    async clickObservedRatio(row, region) {
      if ((!parseGuideRatio(row.text) && !isGuideCountFragment(row.text)) || row.x<region.x || row.y<region.y
          || row.x+row.width>region.x+region.width || row.y+row.height>region.y+region.height)
        throw new Error('Material ratio is not inside the observed material column');
      const capture=captureGameRegion();let clickRegion;
      try {clickRegion=capture.DeriveCrop(row.x,row.y,row.width,row.height);clickRegion.Click();}
      finally {clickRegion?.Dispose();capture.Dispose();}
      await sleep(350);
    },
    // Navigation is allowed only for a unique, actually observed exact UI label.
    async clickObservedText(text, region) {
      if (!['提升指南', '武器'].includes(text)) throw new Error('Read-only guide navigation label is not allowed');
      return pollObservedText(text,region,true);
    }
  };
}

export const DEFAULT_WEAPON_GUIDE_LAYOUT = {
  guideButton:{x:110,y:965,width:280,height:90}, characterName:{x:765,y:95,width:550,height:85},
  weaponTab:{x:930,y:215,width:340,height:85}, weaponName:{x:765,y:360,width:550,height:105},
  targetLevel:{x:1600,y:355,width:95,height:110}, materialColumn:{x:690,y:320,width:130,height:705},
  tooltip:{x:700,y:140,width:530,height:840}, scrollPoint:{x:1580,y:830}
};

async function readContextFrames(api,layout,expected,evidence,phase) {
  const read=()=>{
    const r=api.captureOcr({characterName:layout.characterName,weaponName:layout.weaponName,targetLevel:layout.targetLevel});
    return {observedAt:r.observedAt,screenshotPath:r.screenshotPath,
      contextRows:{characterName:r.characterName,weaponName:r.weaponName,targetLevel:r.targetLevel}};
  };
  const deadline=api.now()+8000;
  let previous=null;
  evidence.contextAttempts??=[];
  for(let attempt=1;attempt<=6;attempt++) {
    if(attempt>1 && api.now()>=deadline) break;
    const frame=read();
    const matched=contextMatches(frame,expected);
    evidence.contextAttempts.push({phase,attempt,matched,frame});
    if(matched) {
      if(previous && frame.observedAt-previous.observedAt>=100 && frame.observedAt-previous.observedAt<=5000)
        return [previous,frame];
      previous=frame;
    } else previous=null;
    if(attempt<6 && api.now()<deadline) await api.sleep(180);
  }
  throw new Error(`weapon_guide_${phase}_context_unstable`);
}

// Tooltip covers the background weapon/target. Keep tooltip observations separate from nonmodal context.
export async function readWeaponGuideMaterial(api, layout) {
  const read=()=>{
    const r=api.captureOcr({tooltip:layout.tooltip});
    return {observedAt:r.observedAt,screenshotPath:r.screenshotPath,tooltipRows:r.tooltip,tooltipRegion:layout.tooltip};
  };
  const first=read();await api.sleep(180);return {first,second:read()};
}

// Complete bounded read-only navigation; a missing card stays unknown. No upgrade, crafting, or resin API is used.
export async function readWeaponGuideInventory(api, request,
  {layout=DEFAULT_WEAPON_GUIDE_LAYOUT,maxMilliseconds=120000,maxPages=8}={}) {
  const expected={characterName:request.characterName,weaponName:request.weaponName,targetLevel:request.targetLevel};
  const materials=(request.materials??[]).map(material=>({id:material.materialId,name:material.materialName,required:material.required}));
  if(!Number.isInteger(maxPages) || maxPages<1 || maxPages>12 || !Number.isFinite(maxMilliseconds)
     || maxMilliseconds<1000 || maxMilliseconds>120000 || !materials.length || materials.length>12)
    throw new Error('Invalid bounded weapon guide scan');
  const startedAt=api.now(), items={}, observations={}, evidence={startedAt,readOnly:true,before:[],after:[],pages:[],navigation:api.navigation??[]};
  for(const material of materials) items[material.id]={name:material.name,count:null,status:'unknown',reason:'guide_material_not_observed'};
  const checkTime=()=>{if(api.now()-startedAt>maxMilliseconds) throw new Error('weapon_guide_deadline');};
  let tooltipOpen=false;
  try {
    await api.selectCharacter(expected.characterName);checkTime();
    await api.clickObservedText('提升指南',layout.guideButton);
    if(typeof api.waitObservedText!=='function') throw new Error('weapon_guide_header_wait_api_missing');
    await api.waitObservedText(expected.characterName,layout.characterName);
    await api.clickObservedText('武器',layout.weaponTab);
    await api.scrollGuide(32,layout.scrollPoint);checkTime();
    evidence.before=await readContextFrames(api,layout,expected,evidence,'before');
    if(evidence.before.some(frame=>!contextMatches(frame,expected))) throw new Error('weapon_guide_initial_context_unverified');
    // Exclude the real weapon/Lv.1 card above the material list; this lower boundary comes from live context OCR.
    const materialMinY=Math.max(...evidence.before.flatMap(frame=>frame.contextRows.weaponName.map(row=>row.y+row.height)))+20;
    evidence.materialCandidateMinY=materialMinY;
    for(let page=0;page<maxPages;page++) {
      checkTime();
      const r=api.captureOcr({materialColumn:layout.materialColumn});
      const candidates=r.materialColumn.filter(row=>{
        const ratio=parseGuideRatio(row.text);
        return row.y>=materialMinY && (ratio ? materials.some(material=>material.required===ratio.required)
          : isGuideCountFragment(row.text));
      }).sort((a,b)=>a.y-b.y).slice(0,8);
      evidence.pages.push({page,observedAt:r.observedAt,rows:r.materialColumn});
      for(const candidate of candidates) {
        checkTime();
        await api.clickObservedRatio(candidate,layout.materialColumn);tooltipOpen=true;
        const pair=await readWeaponGuideMaterial(api,layout);
        if(!demandRatio(pair.first.tooltipRows) || !demandRatio(pair.second.tooltipRows))
          throw new Error('weapon_guide_material_tooltip_not_observed');
        for(const material of materials) {
          const target={...expected,materialId:material.id,materialName:material.name,required:material.required};
          const first=frameObservation(pair.first,target),second=frameObservation(pair.second,target);
          if(first && second && first.count===second.count) observations[material.id]=pair;
        }
        await api.closeTooltip();tooltipOpen=false;
        if(materials.every(material=>observations[material.id])) break;
      }
      if(materials.every(material=>observations[material.id])) {evidence.stopReason='all_requested_tooltips_observed';break;}
      if(page+1<maxPages) await api.scrollGuide(-3,layout.scrollPoint);
    }
    checkTime();await api.scrollGuide(32,layout.scrollPoint);
    evidence.after=await readContextFrames(api,layout,expected,evidence,'after');checkTime();
    for(const material of materials) {
      const pair=observations[material.id];
      if(pair) items[material.id]=verifyWeaponGuideFrames(pair.first,pair.second,
        {...expected,materialId:material.id,materialName:material.name,required:material.required},
        {before:evidence.before,after:evidence.after});
    }
    evidence.stopReason??='page_limit';
  } catch(error) {
    evidence.stopReason=String(error?.message||error);
    for(const item of Object.values(items)) {item.count=null;item.status='unknown';item.reason=evidence.stopReason;}
  } finally {
    try {if(tooltipOpen) await api.closeTooltip();await api.returnMainUi();evidence.mainUiRestored=true;}
    catch(error) {evidence.mainUiRestored=false;evidence.cleanupError=String(error?.message||error);}
    evidence.finishedAt=api.now();
  }
  evidence.tooltipObservations=observations;
  const result={inventory:items,contextEvidence:{before:evidence.before,after:evidence.after},observations,
    mainUiRestored:evidence.mainUiRestored,reason:evidence.stopReason,evidence,readOnly:true,
    source:'character_weapon_guide_tooltip'};
  result.inventory=verifyWeaponGuideSession(result,request);
  return result;
}

// Recompute all inventory from raw session evidence; never trust the caller's count or verified flag.
export function verifyWeaponGuideSession(result,request) {
  const inventory={};
  const expected={characterName:request.characterName,weaponName:request.weaponName,targetLevel:request.targetLevel};
  for(const material of request.materials??[]) {
    const target={...expected,materialId:material.materialId,materialName:material.materialName,required:material.required};
    const pair=result.observations?.[material.materialId];
    inventory[material.materialId]=result.readOnly===true && result.source==='character_weapon_guide_tooltip' && pair
      ? verifyWeaponGuideFrames(pair.first,pair.second,target,result.contextEvidence)
      : {name:material.materialName,count:null,status:'unknown',reason:result.reason??'guide_material_not_observed'};
  }
  return inventory;
}
