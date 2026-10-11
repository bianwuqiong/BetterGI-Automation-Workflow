// GPL-3.0-only. Read-only UI evidence; no final-confirmation executor exists here.
export const TALENT_TYPES=['普通攻击','元素战技','元素爆发'];
export function createTalentPreviewReader({dispatcher,log}){
  return async(characterName,talentType,remainingMilliseconds)=>{
    if(typeof characterName!=='string'||!characterName||characterName!==characterName.trim()||characterName.length>80
        ||/[\x00-\x1f]/.test(characterName)||!TALENT_TYPES.includes(talentType)||!Number.isFinite(remainingMilliseconds)||remainingMilliseconds<=0)throw Error('talent_preview_request_invalid');
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try{
      cts.CancelAfter(Math.max(1,Math.min(180000,Math.floor(remainingMilliseconds))));
      const serialized=await dispatcher.InspectTalentUpgrade(characterName,talentType,cts.Token);
      if(typeof serialized!=='string'||serialized.length>1000000)throw Error('talent_preview_native_json_invalid_or_unbounded');
      const result=JSON.parse(serialized);log?.Info('[CULTIVATION_TALENT_PREVIEW] {payload}',JSON.stringify(result));return result;
    }finally{cts.Dispose();}
  };
}
const clean=v=>typeof v==='string'?v.normalize('NFKC').replace(/\s/g,''):'';
const canonical=v=>clean(v).replaceAll('[','「').replaceAll(']','」');
const fail=reason=>{throw Error(reason);};
const integer=(v,min=0,max=2147483647)=>Number.isInteger(v)&&v>=min&&v<=max?v:fail('talent_integer_invalid');
const number=v=>typeof v==='number'&&Number.isFinite(v)?v:fail('talent_numeric_invalid');
const rect=r=>r&&['x','y','width','height'].every(k=>Number.isFinite(r[k]))&&r.x>=0&&r.y>=0&&r.width>0&&r.height>0?r:fail('talent_rectangle_invalid');
const inside=(a,b)=>a.x>=b.x&&a.y>=b.y&&a.x+a.width<=b.x+b.width&&a.y+a.height<=b.y+b.height;
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const included=(value,values)=>values.some(item=>same(value,item));
const dimensions=(f,start,finish)=>{integer(f?.width,800,4096);integer(f?.height,450,2160);if(f.width*9!==f.height*16||number(f.observedAt)<start||f.observedAt>finish)fail('talent_frame_time_or_size_invalid');return f.width/1920;};
const region=(f,key,ref)=>{const r=rect(f[key]),s=f.width/1920;if(['x','y','width','height'].some((k,i)=>Math.abs(r[k]-ref[i]*s)>1))fail('talent_region_scope_invalid');return r;};
const characterRegion=f=>{for(const ref of [[1466,131,244,38],[1460,124,264,52],[1420,110,360,68]]){try{return region(f,'nameRegion',ref);}catch{}}return fail('talent_character_roi_outside_inspection14_15_16_whitelist');};
const rowText=(rows,box,s,full=true,projected=false)=>{
  if(!Array.isArray(rows)||!rows.length)fail('talent_raw_ocr_missing');
  for(const row of rows){const r=rect(row.bounds);if(!inside(r,box)||full&&Math.min(r.x-box.x,box.x+box.width-r.x-r.width)<2*s-(projected?1:0))fail('talent_ocr_crop_edge');}
  return rows.map(row=>clean(row.text)).join('');
};
const pair=(a,b)=>{if(a.width!==b.width||a.height!==b.height||number(b.observedAt)-number(a.observedAt)<=0||b.observedAt-a.observedAt>5000)fail('talent_fresh_pair_missing');};
const digits=raw=>/^(0|[1-9][0-9]{0,9})$/.test(clean(raw))?integer(Number(clean(raw))):fail('talent_complete_integer_missing');
export function verifyTalentQuantity(q,start,finish,prefix=''){
  const s=dimensions(q,start,finish),box=rect(q.bounds),owned=integer(q.owned),required=integer(q.required,prefix?0:1);
  if(q.complete!==true||(q.prefix??'')!==prefix||!inside(box,{x:0,y:0,width:q.width,height:q.height}))fail('talent_complete_ratio_missing');
  if(q.slashPixelVerified===true){
    const slash=rect(q.slashBounds),left=rect(q.numeratorRegion),right=rect(q.denominatorRegion);
    const method=q.splitRegionMethod;let top,bottom;
    if(method==null){top=box.y;bottom=box.y+box.height;}
    else if(method==='slash_vertical_band'&&q.splitVerticalPaddingReference===6){const pad=Math.max(3,roundEven(6*s));top=Math.max(box.y,slash.y-pad);bottom=Math.min(box.y+box.height,slash.y+slash.height+pad);}
    else fail('talent_split_method_or_padding_not_reviewed');
    if(prefix||q.splitOcrScale!==4||box.width>=200*s||!inside(slash,box)||slash.width<2||slash.height<6
        ||slash.height/slash.width<1.5||slash.height/slash.width>5||integer(q.slashInkPixels)<6||number(q.slashCorrelation)<-1||q.slashCorrelation>-.75
        ||slash.x-box.x<=8||box.x+box.width-slash.x-slash.width<=8||slash.x-box.x<box.width*.2||slash.x+slash.width>box.x+box.width*.85
        ||left.x!==box.x||left.y!==top||left.width!==slash.x-box.x-1||left.height!==bottom-top
        ||right.x!==slash.x+slash.width+1||right.y!==top||right.width!==box.x+box.width-slash.x-slash.width-1||right.height!==bottom-top
        ||q.numeratorRows?.length!==1||q.denominatorRows?.length!==1)fail('talent_actual_slash_geometry_missing');
    const num=rowText(q.numeratorRows,left,s,true,method==null),den=rowText(q.denominatorRows,right,s,true,method==null);
    if(method!=null)for(const [values,bounds] of [[q.numeratorRows,left],[q.denominatorRows,right]])if(values.some(row=>Math.min(row.bounds.y-bounds.y,bounds.y+bounds.height-row.bounds.y-row.bounds.height)<2*s))fail('talent_slash_band_integer_crop_edge');
    if(num!==clean(q.numeratorRaw)||den!==clean(q.denominatorRaw)||digits(num)!==owned||digits(den)!==required)fail('talent_split_integer_mismatch');
  }else{
    const raw=clean(q.raw);let detected=rowText(q.ocrRows,box,s);
    if(prefix){if(!detected.startsWith(prefix))fail('talent_tooltip_prefix_missing');detected=detected.slice(prefix.length);}
    if(raw!==clean(q.detectorRaw)||raw!==detected||!/^(0|[1-9][0-9]{0,9})\/(0|[1-9][0-9]{0,9})$/.test(raw))fail('talent_whole_ratio_ambiguous');
    const parts=raw.split('/');if(digits(parts[0])!==owned||digits(parts[1])!==required)fail('talent_ratio_declared_mismatch');
  }
  return {owned,required};
}
const quantity=verifyTalentQuantity;
const roundEven=v=>{const floor=Math.floor(v);return v-floor===.5?(floor%2?floor+1:floor):Math.round(v);};
const rectSame=(a,b)=>['x','y','width','height'].every(k=>a[k]===b[k]);
function retainedInitial(q,parent,start,finish){
  const initial=q.initialReading;dimensions(initial,start,finish);
  if(initial.observedAt!==parent.observedAt||initial.width!==parent.width||initial.height!==parent.height
      ||typeof initial.complete!=='boolean'||typeof initial.raw!=='string'||typeof initial.detectorRaw!=='string'||!Array.isArray(initial.ocrRows)
      ||initial.initialReading!=null||(initial.prefix??'')!=='')fail('talent_initial_raw_frame_missing');
  const box=rect(initial.bounds);
  for(const row of initial.ocrRows)if(typeof row.text!=='string'||!inside(rect(row.bounds),box))fail('talent_initial_rows_outside_actual_crop');
  if(!initial.complete&&(initial.owned!=null||initial.required!=null))fail('talent_initial_failed_quantities_not_null');
  return initial;
}
function materialCrop(item,parent,start,finish){
  const q=item.quantity,s=parent.width/1920;if(q.initialReading==null){if((q.cropMethod??'fixed_or_initial')!=='fixed_or_initial'||q.sourceCountRow!=null)fail('talent_derived_material_initial_missing');return;}
  if(q.cropMethod!=='source_count_row_pad20x5_intersect_card')fail('talent_material_crop_method_unknown');
  const initial=retainedInitial(q,parent,start,finish),source=q.sourceCountRow,b=rect(source?.bounds),band={x:440*s,y:690*s,width:1040*s,height:100*s};
  if(!/^[0-9/]{2,20}$/.test(clean(source.text))||!inside(b,band)||Math.min(b.x-band.x,band.x+band.width-b.x-b.width)<2*s)fail('talent_material_source_row_unverified');
  const expected={x:b.x-roundEven(8*s),y:b.y-roundEven(5*s),width:b.width+roundEven(16*s),height:b.height+roundEven(10*s)};
  const card=rect(item.card),center=b.x+Math.floor(b.width/2),expectedCard={x:center-roundEven(58*s),y:b.y+b.height-roundEven(138*s),width:roundEven(116*s),height:roundEven(146*s)};
  if(!rectSame(rect(initial.bounds),expected)||!rectSame(card,expectedCard))fail('talent_material_initial_pad8_or_card_not_actual_source');
  const left=Math.max(card.x,b.x-roundEven(20*s)),right=Math.min(card.x+card.width,b.x+b.width+roundEven(20*s));
  const top=Math.max(card.y,b.y-roundEven(5*s)),bottom=Math.min(card.y+card.height,b.y+b.height+roundEven(5*s));
  if(!rectSame(rect(q.bounds),{x:left,y:top,width:right-left,height:bottom-top}))fail('talent_material_pad20_not_intersected_card');
  if(initial.complete&&!same(quantity(initial,start,finish),quantity(q,start,finish)))fail('talent_initial_complete_material_conflict');
}
function moraCrop(q,parent,start,finish){
  if(q.initialReading==null){if((q.cropMethod??'fixed_or_initial')!=='fixed_or_initial'||q.sourceCountRow!=null)fail('talent_derived_mora_initial_missing');region(q,'bounds',[903,797,275,55]);return;}
  if(q.cropMethod!=='unique_initial_detector_row_pad12')fail('talent_mora_crop_method_unknown');
  const initial=retainedInitial(q,parent,start,finish);region(initial,'bounds',[903,797,275,55]);
  const numeric=initial.ocrRows.filter(row=>/^(0|[1-9][0-9]{0,9})\/(0|[1-9][0-9]{0,9})$/.test(clean(row.text)));
  if(numeric.length!==1||!same(q.sourceCountRow,numeric[0]))fail('talent_mora_source_not_unique_initial_ratio');
  const s=parent.width/1920,b=rect(numeric[0].bounds),pad=roundEven(12*s);rowText(numeric,rect(initial.bounds),s);
  const expected={x:b.x-pad,y:b.y-pad,width:b.width+2*pad,height:b.height+2*pad};
  if(!rectSame(rect(q.bounds),expected)||expected.x<parent.width*.44||expected.x+expected.width>parent.width*.65
      ||expected.y<parent.height*.7||expected.y+expected.height>parent.height*.81)fail('talent_mora_box_not_actual_detector_pad12');
  if(initial.complete&&!same(quantity(initial,start,finish),quantity(q,start,finish)))fail('talent_initial_complete_mora_conflict');
}
function coinIdentity(p){
  const variant=p.coinVariant??'tight_37';
  if(variant==='tight_37')region(p,'coinRegion',[853,799,37,37]);
  else if(variant==='real_background_padding_8_reference_53'){
    region(p,'coinRegion',[845,791,53,53]);region(p,'initialCoinRegion',[853,799,37,37]);
    const score=number(p.initialCoinScore);
    if(score<0||score>1||typeof p.initialCoinName!=='string'||score>=.75&&p.initialCoinName!=='摩拉')fail('talent_initial_high_confidence_currency_conflict');
  }else fail('talent_coin_variant_not_explicit_fixed_selection');
  if(p.coinName!=='摩拉'||number(p.coinScore)<.75||p.coinScore>1)fail('talent_primary_mora_model_missing');
}
function entryObservation(f,character,start,finish){
  const s=dimensions(f,start,finish);
  if(f.phase!=='talent_entry_observation'||f.focused!==true||f.overview!==true||f.promptVisible!==false||f.reviveVisible!==false)fail('talent_entry_known_focused_page_required');
  const n=f.character;dimensions(n,start,finish);const nameBox=characterRegion(n);
  if(n.observedAt!==f.observedAt||n.width!==f.width||n.height!==f.height||n.overview!==true||clean(n.name)!==clean(character)
      ||n.nameRows?.length!==1||rowText(n.nameRows,nameBox,s)!==clean(character))fail('talent_entry_current_fullname_unverified');
  const name=rect(n.nameRows[0].bounds);if(Math.min(name.y-nameBox.y,nameBox.y+nameBox.height-name.y-name.height)<2*s)fail('talent_entry_fullname_crop_edge');
  const box=region(f,'region',[1536,0,384,900]);if(!Array.isArray(f.rows))fail('talent_entry_original_rows_missing');
  const derived=[];
  for(const row of f.rows){if(typeof row.text!=='string'||!inside(rect(row.bounds),box))fail('talent_entry_raw_row_outside_roi');const match=clean(row.text).match(/^(?:Lv\.?|等级)?([0-9]{1,2})$/i);if(match&&Number(match[1])>=1&&Number(match[1])<=15)derived.push(row);}
  derived.sort((a,b)=>a.bounds.y-b.bounds.y);
  if(derived.length!==3||!same(f.candidates,derived))fail('talent_entry_exact_three_raw_derived_candidates_required');
  for(const row of derived){const b=rect(row.bounds);if(Math.min(b.x-box.x,b.y-box.y,box.x+box.width-b.x-b.width,box.y+box.height-b.y-b.height)<2*s)fail('talent_entry_four_edge_candidate_required');}
  if(derived.some((row,i)=>i<2&&row.bounds.y+row.bounds.height>=derived[i+1].bounds.y))fail('talent_entry_candidates_overlap');
  return derived;
}
function rollingIdentity(e,frames,names,character,start,finish){
  if(e.characterIdentityMethod!=='bounded_rolling_exact_triple'||e.characterIdentityObservationLimitMs!==12000||e.characterIdentityPollMs!==300)fail('talent_rolling_identity_method_or_limits_invalid');
  const trials=e.characterIdentityTrials,originals=frames.filter(f=>f.phase==='character_identity_observation');
  if(!Array.isArray(trials)||trials.length<3||trials.length>41||!same(trials,originals)||!same(names,trials.slice(-3))
      ||!same(frames.slice(0,trials.length),trials)||trials.at(-1).observedAt-trials[0].observedAt>=12000)fail('talent_rolling_raw_prefix_or_last_triple_missing');
  const valid=[];
  for(const [i,n] of trials.entries()){
    const s=dimensions(n,start,finish),box=rect(n.nameRegion),expected={x:roundEven(1420*s),y:roundEven(110*s),width:roundEven(360*s),height:roundEven(68*s)},values=n.nameRows;
    if(!same(box,expected)||typeof n.overview!=='boolean'||typeof n.name!=='string'||!Array.isArray(values)
        ||values.some(r=>typeof r.text!=='string'||!inside(rect(r.bounds),box))||clean(n.name)!==values.map(r=>clean(r.text)).join('')
        ||i&&n.observedAt-trials[i-1].observedAt<300)fail('talent_rolling_original_name_rows_or_poll_invalid');
    let exact=n.overview&&values.length===1&&clean(n.name)===clean(character);
    if(exact){const r=rect(values[0].bounds);exact=Math.min(r.x-box.x,r.y-box.y,box.x+box.width-r.x-r.width,box.y+box.height-r.y-r.height)>=2*s;}
    valid.push(exact);
    if(i>=2&&valid.slice(-3).every(Boolean)&&n.observedAt-trials[i-2].observedAt<=5000&&[i-1,i].every(j=>trials[j].observedAt-trials[j-1].observedAt<=5000)){
      if(i!==trials.length-1)fail('talent_rolling_continued_after_first_verified_triple');return;
    }
  }
  fail('talent_rolling_final_triple_unverified');
}
function entryBinding(e,frames,character,type,start,finish,names,details){
  const selected=e.twoPickedEntryFrames,click=e.entryClickFrame;
  if(!Array.isArray(selected)||selected.length!==2||!click||typeof click!=='object')fail('talent_explicit_entry_pair_click_required');
  const entries=frames.filter(f=>f.phase==='talent_entry_observation'),all=[...selected,click];
  if(all.some(f=>!included(f,entries))||same(selected[0],selected[1])||selected.some(f=>same(f,click)))fail('talent_entry_references_not_independent_raw');
  const positions=all.map(f=>entries.findIndex(v=>same(v,f)));
  if(positions[1]!==positions[0]+1||positions[2]!==positions[1]+1)fail('talent_entry_refs_not_original_consecutive_sequence');
  if(selected[0].observedAt<=names.at(-1).observedAt||click.observedAt>=details[0].observedAt||click.observedAt-entries[0].observedAt>12000
      ||entries.some(f=>f.observedAt<names.at(-1).observedAt||f.observedAt>click.observedAt))fail('talent_entry_sequence_or_deadline_invalid');
  const result=all.map(f=>entryObservation(f,character,start,finish));pair(selected[0],selected[1]);pair(selected[1],click);
  for(let i=0;i<3;i++){
    const [a,b,c]=result.map(values=>rect(values[i].bounds)),cy=r=>r.y+Math.floor(r.height/2),cx=r=>r.x+Math.floor(r.width/2);
    if(Math.abs(cy(a)-cy(b))>6||Math.abs(cy(b)-cy(c))>6||Math.abs(cx(b)-cx(c))>6||new Set(result.map(values=>clean(values[i].text))).size!==1)fail('talent_entry_stable_geometry_or_text_required');
  }
  const match=clean(result.at(-1)[TALENT_TYPES.indexOf(type)].text).match(/^(?:Lv\.?|等级)?([0-9]{1,2})$/i);
  if(Number(match[1])!==integer(details[0].displayLevel,1,13))fail('talent_requested_index_does_not_bind_detail_level');
}
function detail(d,type,start,finish){
  const s=dimensions(d,start,finish);if(d.page!==true||d.type!==type)fail('talent_detail_page_type_mismatch');
  const title=rowText(d.titleRows,region(d,'titleRegion',[20,120,540,52]),s),actualType=rowText(d.typeRows,region(d,'typeRegion',[242,13,98,36]),s,false);
  const raw=rowText(d.levelRows,region(d,'levelRegion',[240,160,100,52]),s,false),match=raw.match(/^(?:等级|Lv\.?)?([1-9]|1[0-3])$/i);
  const display=integer(d.displayLevel,1,13),base=integer(d.baseLevel,1,9);
  if(!title||title!==clean(d.title)||actualType!==type||raw!==clean(d.levelRaw)||!match||Number(match[1])!==display)fail('talent_detail_full_raw_mismatch');
  const glyph=rect(d.glyphRegion),sample=rect(d.colorSampleRegion),level=rect(d.levelRegion);
  if(d.levelRows.length!==1||!inside(glyph,sample)||!inside(level,sample)||['x','y','width','height'].some(k=>glyph[k]!==d.levelRows[0].bounds[k]))fail('talent_glyph_geometry_invalid');
  const min=Math.max(20,Math.ceil(glyph.width*glyph.height*.08)),bright=integer(d.brightPixels),neutral=integer(d.neutralPixels),cyan=integer(d.cyanPixels),dark=integer(d.darkConflicts);
  const bonus=clean(d.bonusRaw),explicit=/^天赋等级\+3$/.test(bonus);region(d,'bonusRegion',[35,285,146,30]);let plus;
  if(d.glyphColor==='Neutral'&&bright>=min&&neutral<=bright&&neutral/bright>=.95&&cyan===0&&dark<min){plus=false;if(explicit||/[+]|天赋|等级/.test(bonus))fail('talent_neutral_bonus_conflict');}
  else if(d.glyphColor==='Cyan'&&bright>=min&&cyan<=bright&&cyan/bright>=.95&&neutral/bright<=.01&&explicit&&display>=4)plus=true;
  else fail('talent_bonus_glyph_unverified');
  if(d.hasFixedPlusThree!==plus||base!==display-(plus?3:0))fail('talent_base_level_mismatch');
  return {title,base,display,plus};
}
function preview(p,current,start,finish){
  const s=dimensions(p,start,finish);if(p.page!==true||p.current!==current||p.next!==current+1)fail('talent_next_base_level_mismatch');
  if(rowText(p.currentLevelRows,region(p,'currentLevelRegion',[760,245,160,65]),s,false)!==`等级${current}`
      ||rowText(p.nextLevelRows,region(p,'nextLevelRegion',[1000,245,170,65]),s,false)!==`等级${current+1}`
      ||clean(p.currentLevelRaw)!==`等级${current}`||clean(p.nextLevelRaw)!==`等级${current+1}`)fail('talent_next_level_raw_mismatch');
  rowText(p.rows,region(p,'markerRegion',[420,235,1100,750]),s,false);const labels=p.rows.map(row=>clean(row.text));
  if(['属性变更','所需材料','取消','确认'].some(label=>labels.filter(value=>value===label).length!==1))fail('talent_popup_markers_missing');
  if(!Array.isArray(p.materials)||p.materials.length<1||p.materials.length>4)fail('talent_material_cards_missing');
  const materials=p.materials.map(item=>{
    const name=canonical(item.name),card=rect(item.card),icon=rect(item.iconRegion);
    if(!name||number(item.iconScore)<.75||item.iconScore>1||!inside(card,{x:p.width*.2,y:p.height*.5,width:p.width*.6,height:p.height*.25})||!inside(icon,card)
        ||!inside(rect(item.quantity.bounds),card)||item.quantity.observedAt!==p.observedAt)fail('talent_material_card_scope_unverified');
    materialCrop(item,p,start,finish);
    return {name,...quantity(item.quantity,start,finish)};
  });
  if(new Set(materials.map(item=>item.name)).size!==materials.length)fail('talent_duplicate_material');
  coinIdentity(p);moraCrop(p.mora,p,start,finish);
  if(p.mora.observedAt!==p.observedAt)fail('talent_actual_mora_identity_missing');
  return {materials,mora:quantity(p.mora,start,finish)};
}
export function verifyTalentObservation(raw,character,type,start,finish){
  if(raw?.schemaVersion!==1||raw.task!=='talent-upgrade-inspection'||raw.status!=='success'||raw.readOnly!==true||raw.evidenceVerified!==true
      ||raw.mainUiRestored!==true||raw.confirmationSubmitted!==false||raw.characterName!==character||raw.talentType!==type||!TALENT_TYPES.includes(type))fail('talent_readonly_scope_cleanup_mismatch');
  const e=raw.evidence,frames=e?.rawFrames,names=e?.characterIdentity;
  if(e?.characterSelectionAfterIdentity!==false||e.tooltipRequirementUsedAsUpgradeCost!==false||!Array.isArray(frames)||names?.length!==3)fail('talent_identity_raw_missing');
  for(const [i,f] of frames.entries()){dimensions(f,start,finish);if(i&&(f.observedAt<=frames[i-1].observedAt||f.width!==frames[0].width||f.height!==frames[0].height))fail('talent_raw_timeline_or_client_changed');}
  if(['characterIdentityMethod','characterIdentityTrials','characterIdentityObservationLimitMs','characterIdentityPollMs'].some(k=>k in e)||frames.some(f=>f.phase==='character_identity_observation'))rollingIdentity(e,frames,names,character,start,finish);
  for(const n of names){const s=dimensions(n,start,finish),box=characterRegion(n);if(!included(n,frames)||n.overview!==true||clean(n.name)!==clean(character)
      ||rowText(n.nameRows,box,s)!==clean(character)||n.nameRows.some(row=>Math.min(row.bounds.y-box.y,box.y+box.height-row.bounds.y-row.bounds.height)<2*s))fail('talent_official_name_incomplete');}
  pair(names[0],names[1]);pair(names[1],names[2]);if(names[2].observedAt-names[0].observedAt>5000)fail('talent_character_triple_stale');
  const details=frames.filter(f=>'displayLevel' in f);
  if(details.length!==2||details[0].observedAt<=names[2].observedAt)fail('talent_detail_pair_missing');pair(details[0],details[1]);
  const a=detail(details[0],type,start,finish),b=detail(details[1],type,start,finish);
  if(!same(a,b)||!same(e.detailIdentityCarryover,details[1])||raw.talentName!==b.title)fail('talent_identity_carryover_mismatch');
  if('characterIdentityMethod' in e||'twoPickedEntryFrames' in e||'entryClickFrame' in e||frames.some(f=>f.phase==='talent_entry_observation'))entryBinding(e,frames,character,type,start,finish,names,details);
  const previews=frames.filter(f=>'materials' in f&&'current' in f);
  if(previews.length<2||previews.length%2||previews[0].observedAt<=details[1].observedAt||!same(e.preview,previews.at(-1)))fail('talent_popup_pair_missing');let costs;
  for(let i=0;i<previews.length;i+=2){pair(previews[i],previews[i+1]);for(const p of previews.slice(i,i+2)){const actual=preview(p,b.base,start,finish);if(costs&&!same(costs,actual))fail('talent_costs_changed');costs=actual;}}
  if(e.materialTooltips?.length!==costs.materials.length)fail('talent_fullnamed_tooltips_missing');
  for(const [i,two] of e.materialTooltips.entries()){
    const item=costs.materials[i];if(two.length!==2)fail('talent_tooltip_pair_missing');pair(two[0],two[1]);
    for(const tip of two){const s=dimensions(tip,start,finish),box=region(tip,'nameRegion',[730,168,440,67]);
      if(!included(tip,frames)||tip.page!==true||canonical(tip.name)!==item.name)fail('talent_tooltip_scope_mismatch');const candidates=[];
      for(const [rowsKey,rawKey,projected] of [['nameRows','rawName',false],['alternateNameRows','alternateRawName',true]]){
        try{const name=rowText(tip[rowsKey],box,s,true,projected);if(name===clean(tip[rawKey])&&(!projected||tip.alternateNameScale===4&&tip.alternateNamePreprocessing==='gray_threshold_210_inverse_cubic_4x'))candidates.push(canonical(name));}catch{}
      }
      const kind=rowText(tip.kindRows,region(tip,'kindRegion',[730,230,440,65]),s),sourceBox=region(tip,'sourceRegion',[730,690,460,65]);
      rowText(tip.sourceRows,sourceBox,s,false);
      if(!candidates.includes(item.name)||kind!==tip.kind||!['角色天赋素材','角色与武器培养素材'].includes(kind)
          ||tip.sourceRows.filter(row=>clean(row.text)==='来源').length!==1)fail('talent_tooltip_fullname_unverified');
      if(!rowText(tip.footerLabelRows,region(tip,'footerLabelRegion',[725,890,470,65]),s,false).startsWith('培养需求'))fail('talent_footer_label_missing');
      region(tip.quantity,'bounds',[885,890,295,65]);if(quantity(tip.quantity,start,finish,'培养需求').owned!==item.owned)fail('talent_popup_tooltip_owned_mismatch');
    }
    if(two[0].observedAt<=previews[1].observedAt||two[1].observedAt>=previews.at(-1).observedAt)fail('talent_tooltip_read_order_invalid');
  }
  const worlds=frames.filter(f=>f.phase==='world_restore');if(worlds.length<2)fail('talent_cleanup_pair_missing');pair(worlds.at(-2),worlds.at(-1));
  for(const world of worlds.slice(-2)){dimensions(world,start,finish);if(world.focused!==true||world.worldVerified!==true||world.observedAt<=previews.at(-1).observedAt)fail('talent_world_cleanup_unverified');}
  if(!same(raw.materials,costs.materials)||!same(raw.mora,costs.mora)||raw.currentBaseLevel!==b.base||raw.nextBaseLevel!==b.base+1
      ||!Number.isFinite(Date.parse(raw.observedAt))||Math.abs(Date.parse(raw.observedAt)-previews.at(-1).observedAt)>1)fail('talent_summary_raw_mismatch');
  return {talentName:b.title,currentBaseLevel:b.base,nextBaseLevel:b.base+1,...costs};
}
export async function readTalentPreview(api,character,type,start,deadline){
  const result={readOnly:true,targetReached:false,completedUpgrades:0,selectedTalentType:type,nativeObservation:null,costs:null,evidenceVerified:false};
  try{if(!TALENT_TYPES.includes(type))fail('single combat talent type required');
    if(api.now()>=deadline)fail('talent_preview_deadline_expired');
    result.nativeObservation=await api.inspectTalentUpgrade(character,type,Math.max(1,deadline-api.now()));
    result.costs=verifyTalentObservation(result.nativeObservation,character,type,start,api.now());result.evidenceVerified=true;
  }catch(error){result.reason=String(error?.message||error).slice(0,300);}
  return result;
}
