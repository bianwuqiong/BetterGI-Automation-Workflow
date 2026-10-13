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
const PINNED_SPLIT_METHOD='pinned_v6_v4_slash_integer_split';
const SPLIT_METADATA=['splitRawModel','splitDetectorModel','splitModelEvidence','splitRawPaddleReadback'];
const SPLIT_ASSETS=[
  ['PpOcrDetV4','Assets/Model/PaddleOCR/Det/V4/PP-OCRv4_mobile_det_infer/slim.onnx'],
  ['PpOcrRecV4','Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/slim.onnx'],
  ['PpOcrRecV6','Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/slim.onnx'],
  ['PpOcrRecV4-labels','Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/inference.yml'],
  ['PpOcrRecV6-labels','Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/inference.yml'],
  ['PpOcrDetV6','Assets/Model/PaddleOCR/Det/V6/PP-OCRv6_small_det_infer/slim.onnx']
];
const modernSplit=q=>q&&typeof q==='object'&&!Array.isArray(q)?SPLIT_METADATA.some(key=>q[key]!=null):fail('talent_quantity_json_object_required');
const quantityChainModern=q=>modernSplit(q)||(q.initialReading!=null&&modernSplit(q.initialReading));
const exactKeys=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const PREVIEW_TIMING_METHOD='capture_read_evaluate_then_private_png_v1';
const READ_TIMING_FIELDS=['captureCallStartedAt','captureReturnedAt','readerStartedAt','readerCompletedAt','pairEvaluatedAt','diagnosticPngCompletedAt','pairAccepted'];
const PRIVATE_CAPTURE_FIELDS=['observedAt','width','height','pixelType','path','pngSha256','nativePixelsSha256','source'];
const FOOTER_METHOD='existing_full_footer_v1',FOOTER_METHOD_V2='existing_full_footer_v2',MARKER_METHOD_V1='whole_marker_required_roles_v1',MARKER_METHOD_V2='whole_marker_required_roles_v2';
const SOURCE31_METHODS={tooltipTimingMethod:PREVIEW_TIMING_METHOD};
const SOURCE31_FRAME_FIELDS=['previewMarkerMethod','tooltipQuantityMethod','tooltipTimingMethod','sourceRegionModelEvidence','markerRoleEvidence','footerQuantityEvidence','originalIdentityReading'];
const FOOTER_FIELDS=['method','oldRegion','sourceRegion','initialReading','initialWholeRawText','initialWholeDetectorText','wholeRawText','wholeDetectorText'];
const ORIGINAL_FOOTER_FIELDS=['originalWholeReading','originalWholeRawText','originalWholeDetectorText'];
const footerMethod=value=>[FOOTER_METHOD,FOOTER_METHOD_V2].includes(value);
const footerRegion=value=>value===FOOTER_METHOD_V2?[882,875,223,80]:[725,890,470,65];
const tooltipSourceRegion=value=>value===FOOTER_METHOD_V2?[730,675,460,80]:[730,690,460,65];
function originalTooltipIdentity(tip,v2){
  if(!v2){if(Object.hasOwn(tip,'originalIdentityReading'))fail('talent_v1_original_identity_diagnostic_forbidden');return;}
  const proof=tip.originalIdentityReading;
  if(!exactKeys(proof,['observedAt','nameRegion','alternateRawName','alternateNameRows','alternateNameScale','alternateNamePreprocessing','sourceRegion','sourceRows'])
      ||!Number.isSafeInteger(proof.observedAt)||proof.observedAt!==tip.observedAt||typeof proof.alternateRawName!=='string'||proof.alternateRawName.length>256
      ||proof.alternateNameScale!==4||proof.alternateNamePreprocessing!=='gray_threshold_210_inverse_cubic_4x')fail('talent_original_identity_diagnostic_scope_invalid');
  sourceRect(proof.nameRegion,[730,168,440,67]);sourceRect(proof.sourceRegion,[730,690,460,65]);
  for(const rows of [proof.alternateNameRows,proof.sourceRows]){
    if(!Array.isArray(rows)||rows.length>16)fail('talent_original_identity_diagnostic_rows_unbounded');
    for(const row of rows){if(!exactKeys(row,['text','bounds'])||typeof row.text!=='string'||row.text.length>256)fail('talent_original_identity_diagnostic_row_invalid');sourceRect(row.bounds);}
  }
}
const MARKER_ROLES=[['attribute_heading','属性变更',[870,295,180,70]],['material_heading','所需材料',[870,575,180,60]],
  ['cancel_label','取消',[620,875,170,70]],['confirm_label','确认',[1170,875,180,70]]];
const markerMethod=value=>[MARKER_METHOD_V1,MARKER_METHOD_V2].includes(value);
function previewTiming(raw,previews,start,finish){
  if(raw.previewTimingMethod==null&&previews.every(p=>p.readTiming==null))return;
  if(raw.previewTimingMethod!==PREVIEW_TIMING_METHOD)fail('talent_modern_preview_timing_method_required');
  if(costMethod(raw)!=='pinned_v6_v4_slash_integer_split'||previews.some(p=>costMethod(p)!=='pinned_v6_v4_slash_integer_split'))fail('talent_modern_preview_timing_cannot_authenticate_legacy_costs');
  retainedPairTiming(raw,previews,start,finish);
}
function retainedPairTiming(raw,previews,start,finish){
  const paths=new Set(),clock=(v)=>{if(!Number.isSafeInteger(v)||v<start||v>finish)fail('talent_preview_actual_clock_invalid');return v;};
  for(let offset=0;offset<previews.length;offset+=2){
    const frames=previews.slice(offset,offset+2),times=[];
    for(const [index,p] of frames.entries()){
      const t=p.readTiming,pixels=p.privateCapture;
      if(!exactKeys(t,READ_TIMING_FIELDS)||!exactKeys(pixels,PRIVATE_CAPTURE_FIELDS))fail('talent_modern_preview_timing_or_original_png_incomplete');
      for(const key of READ_TIMING_FIELDS)if(!['pairEvaluatedAt','pairAccepted'].includes(key))clock(t[key]);
      clock(p.observedAt);
      if(!(t.captureCallStartedAt<=t.captureReturnedAt&&t.captureReturnedAt===p.observedAt&&p.observedAt<=t.readerStartedAt&&t.readerStartedAt<=t.readerCompletedAt))fail('talent_preview_capture_reader_clock_order');
      if(index===0){if(t.pairEvaluatedAt!==null||t.pairAccepted!==null)fail('talent_first_preview_must_not_claim_pair_acceptance');}
      else if(clock(t.pairEvaluatedAt)<start||t.pairAccepted!==true)fail('talent_second_preview_actual_accepted_pair_required');
      if(p.width!==1920||p.height!==1080||pixels.width!==1920||pixels.height!==1080||pixels.observedAt!==p.observedAt
          ||pixels.pixelType!=='CV_8UC3'||pixels.source!=='diagnostic_only_lossless_native_srcmat_no_resize'
          ||typeof pixels.path!=='string'||pixels.path.length>4096||/[\x00-\x1f\x7f]/.test(pixels.path)
          ||!(/^[A-Za-z]:[\\/]/.test(pixels.path)||/^\/(?!\/)/.test(pixels.path))||!pixels.path.toLowerCase().endsWith('.png')
          ||pixels.path.split(/[\\/]/).some(part=>part==='.'||part==='..')||!pixels.path.split(/[\\/]/).includes('log')
          ||[pixels.pngSha256,pixels.nativePixelsSha256].some(v=>typeof v!=='string'||!/^[0-9a-fA-F]{64}$/.test(v)))fail('talent_preview_original_png_origin_or_shape_invalid');
      let path=pixels.path.replaceAll('\\','/').replace(/\/{2,}/g,'/');
      if(/^[A-Za-z]:\//.test(path))path=path.toLowerCase();
      if(paths.has(path))fail('talent_preview_original_png_path_reused');paths.add(path);times.push(t);
    }
    const [a,b]=times;
    if(!(a.readerCompletedAt<b.captureCallStartedAt&&b.readerCompletedAt<=b.pairEvaluatedAt&&b.pairEvaluatedAt<=a.diagnosticPngCompletedAt&&a.diagnosticPngCompletedAt<=b.diagnosticPngCompletedAt)
        ||frames[1].observedAt-frames[0].observedAt<=0||frames[1].observedAt-frames[0].observedAt>5000
        ||b.pairEvaluatedAt-frames[1].observedAt<0||b.pairEvaluatedAt-frames[1].observedAt>1500)fail('talent_preview_actual_pair_freshness_or_evaluate_before_png_invalid');
    const following=raw.evidence.rawFrames.find(f=>f.observedAt>frames[1].observedAt);
    if(following){
      const nextCapture=following.readTiming!=null||'materials' in following&&'current' in following?clock(following.readTiming?.captureCallStartedAt):following.observedAt;
      if(b.diagnosticPngCompletedAt>Math.min(nextCapture,following.observedAt))fail('talent_preview_png_completion_must_precede_next_original_capture');
    }
  }
  // This checks protocol shape only; the Host reads the original PNG and recomputes BGR hashes.
}
function splitModelShape(q){
  if(!modernSplit(q))return false;
  if(q.splitRawModel!=='V6'||q.splitDetectorModel!=='V4'||q.splitRawPaddleReadback!==8||q.slashPixelVerified!==true
      ||q.splitRegionMethod!=='slash_vertical_band'||q.splitOcrScale!==4||q.splitVerticalPaddingReference!==6||(q.prefix??'')!=='')fail('talent_pinned_split_metadata_incomplete');
  sourceModelShape(q.splitModelEvidence);return true;
}
function sourceModelShape(proof){
  if(!exactKeys(proof,['loadMethod','provider','rawModel','detectorModel','countModels','rawDetectorAsset'])
      ||proof.loadMethod!=='new_cpu_uncached_original_onnx_and_labels_under_read_pins'||proof.provider!=='Cpu'
      ||proof.rawModel!=='V6'||proof.detectorModel!=='V4')fail('talent_strict_model_evidence_incomplete');
  const models=proof.countModels;
  if(!exactKeys(models,['rawPaddleConfig','rawPaddleName','fixedDetectorConfig','fixedDetectorName','pinMethod','assets'])
      ||models.rawPaddleConfig!==8||models.rawPaddleName!=='V6'||models.fixedDetectorConfig!==7||models.fixedDetectorName!=='V4'
      ||models.pinMethod!=='actual_bundled_open_read_sha256_hold_session'||!Array.isArray(models.assets)||models.assets.length!==5)fail('talent_original_count_model_pins_incomplete');
  for(const [i,asset] of [...models.assets,proof.rawDetectorAsset].entries()){
    if(!exactKeys(asset,['modelName','relativePath','sha256','length'])||asset.modelName!==SPLIT_ASSETS[i][0]||asset.relativePath!==SPLIT_ASSETS[i][1]
        ||typeof asset.sha256!=='string'||!/^[0-9a-fA-F]{64}$/.test(asset.sha256)||!Number.isInteger(asset.length)||asset.length<=0||asset.length>1024*1024*1024)fail('talent_fixed_six_model_asset_proof_invalid');
  }
  // JavaScript verifies protocol shape only. Host independently hashes the trusted runtime files.
  return true;
}
function sourceRect(value,expected=null){
  const core=['x','y','width','height'],extra=['top','bottom','left','right','location','size','topLeft','bottomRight'];
  if(!exactKeys(value,core)&&!exactKeys(value,[...core,...extra]))fail('talent_source_rect_serializer_fields_invalid');
  for(const key of core)if(!Number.isSafeInteger(value[key]))fail('talent_source_rect_actual_integer_required');
  const r=rect(value);if(!inside(r,{x:0,y:0,width:1920,height:1080})||expected&&core.some((key,i)=>r[key]!==expected[i]))fail('talent_source_rect_not_fixed_reviewed_region');
  if(Object.hasOwn(value,'top')){
    const x=value.x,y=value.y,w=value.width,h=value.height;
    for(const [key,v] of Object.entries({top:y,bottom:y+h,left:x,right:x+w}))if(value[key]!==v)fail('talent_source_rect_derived_edges_changed');
    for(const [key,p] of Object.entries({location:{x,y},size:{width:w,height:h},topLeft:{x,y},bottomRight:{x:x+w,y:y+h}}))
      if(!exactKeys(value[key],Object.keys(p))||Object.entries(p).some(([k,v])=>value[key][k]!==v))fail('talent_source_rect_derived_coordinates_changed');
  }
  return r;
}
function sourceRow(row){if(!exactKeys(row,['text','bounds'])||typeof row.text!=='string'||!clean(row.text))fail('talent_modern_source_row_invalid');return sourceRect(row.bounds);}
function margins(row,box){const r=sourceRow(row);return [r.x-box.x,box.x+box.width-r.x-r.width,r.y-box.y,box.y+box.height-r.y-r.height];}
function sourceRows(rows,box,expected=null){
  if(!Array.isArray(rows)||rows.length!==1||Math.min(...margins(rows[0],box))<2)fail('talent_source_single_row_four_two_pixel_edges_required');
  const result=clean(rows[0].text);if(expected!=null&&result!==expected)fail('talent_independent_source_row_text_mismatch');return result;
}
function markerRoles(p){
  const proof=p.markerRoleEvidence;
  const method=p.previewMarkerMethod,v2=method===MARKER_METHOD_V2;
  if(!markerMethod(method)||!exactKeys(proof,v2?['method','wholeRegion','roles','backgroundRows','legacyMaterialHeading']:['method','wholeRegion','roles','backgroundRows'])||proof.method!==method)fail('talent_modern_marker_role_proof_incomplete');
  sourceModelShape(p.sourceRegionModelEvidence);
  const whole=sourceRect(p.markerRegion,[420,235,1100,750]);sourceRect(proof.wholeRegion,[whole.x,whole.y,whole.width,whole.height]);
  const rows=p.rows,roles=proof.roles,background=proof.backgroundRows;
  if(!Array.isArray(rows)||!rows.length||!Array.isArray(roles)||roles.length!==4||!Array.isArray(background))fail('talent_marker_whole_rows_or_roles_missing');
  rows.forEach(sourceRow);const picked=[];
  for(const [offset,role] of roles.entries()){
    const [kind,text,original]=MARKER_ROLES[offset],expected=v2&&kind==='material_heading'?[885,575,135,60]:original;
    if(!exactKeys(role,['role','region','wholeRowIndex','observedAt','rawText','detectorRows'])||role.role!==kind||!Number.isSafeInteger(role.observedAt)||role.observedAt!==p.observedAt)fail('talent_marker_role_scope_incomplete');
    const index=integer(role.wholeRowIndex,0,rows.length-1),box=sourceRect(role.region,expected),matches=rows.map((row,i)=>clean(row.text)===text?i:null).filter(i=>i!=null);
    if(matches.length!==1||matches[0]!==index||Math.min(...margins(rows[index],whole))<2||Math.min(...margins(rows[index],box))<2)fail('talent_mandatory_marker_duplicated_clipped_or_wrong_role');
    if(typeof role.rawText!=='string'||clean(role.rawText)!==text)fail('talent_marker_independent_raw_mismatch');
    sourceRows(role.detectorRows,box,text);picked.push(index);
  }
  if(v2){
    const diagnostic=proof.legacyMaterialHeading,material=roles[1];
    if(!exactKeys(diagnostic,['role','region','wholeRowIndex','observedAt','rawText','detectorRows'])
        ||diagnostic.role!=='material_heading'||diagnostic.wholeRowIndex!==material.wholeRowIndex
        ||!Number.isSafeInteger(diagnostic.observedAt)||diagnostic.observedAt!==p.observedAt
        ||typeof diagnostic.rawText!=='string'||diagnostic.rawText.length>256||!Array.isArray(diagnostic.detectorRows)
        ||diagnostic.detectorRows.length>32)fail('talent_legacy_material_diagnostic_scope_invalid');
    const old=sourceRect(diagnostic.region,[870,575,180,60]);
    for(const row of diagnostic.detectorRows){
      if(!exactKeys(row,['text','bounds'])||typeof row.text!=='string'||row.text.length>256)fail('talent_legacy_material_diagnostic_row_invalid');
      const box=sourceRect(row.bounds);if(!inside(box,old))fail('talent_legacy_material_diagnostic_row_outside_old_region');
    }
  }
  const remaining=rows.map((row,i)=>i).filter(i=>!picked.includes(i));if(background.length!==remaining.length)fail('talent_marker_background_rows_not_exhaustive');
  for(const [offset,item] of background.entries()){
    if(!exactKeys(item,['wholeRowIndex','insideWholeSource','leftMargin','rightMargin','topMargin','bottomMargin','claimsTitleOrInputEvidence'])||integer(item.wholeRowIndex,0,rows.length-1)!==remaining[offset])fail('talent_marker_background_index_changed');
    const all=margins(rows[remaining[offset]],whole);
    if(typeof item.insideWholeSource!=='boolean'||item.insideWholeSource!==(Math.min(...all)>=0)||item.claimsTitleOrInputEvidence!==false
        ||['leftMargin','rightMargin','topMargin','bottomMargin'].some((key,i)=>!Number.isSafeInteger(item[key])||item[key]!==all[i]))fail('talent_marker_background_original_containment_changed');
  }
}
function footerQuantity(tip,start,finish){
  const proof=tip.footerQuantityEvidence,q=tip.quantity,v2=tip.tooltipQuantityMethod===FOOTER_METHOD_V2;
  if(!footerMethod(tip.tooltipQuantityMethod)||!exactKeys(proof,v2?[...FOOTER_FIELDS,...ORIGINAL_FOOTER_FIELDS]:FOOTER_FIELDS)||proof.method!==tip.tooltipQuantityMethod||!q||typeof q!=='object'||Array.isArray(q))fail('talent_modern_fixed_footer_proof_incomplete');
  sourceModelShape(tip.sourceRegionModelEvidence);
  const old=sourceRect(proof.oldRegion,[885,890,295,65]),box=sourceRect(proof.sourceRegion,footerRegion(tip.tooltipQuantityMethod));sourceRect(tip.footerLabelRegion,footerRegion(tip.tooltipQuantityMethod));sourceRect(q.bounds,footerRegion(tip.tooltipQuantityMethod));
  for(const value of [q,proof.initialReading,...(v2?[proof.originalWholeReading]:[])]){
    if(!value||typeof value!=='object'||Array.isArray(value)||!Number.isSafeInteger(value.observedAt)||value.observedAt!==tip.observedAt||value.width!==1920||value.height!==1080
        ||value.prefix!=='培养需求'||typeof value.complete!=='boolean'||value.initialReading!=null||(value.cropMethod??'fixed_or_initial')!=='fixed_or_initial'
        ||value.sourceCountRow!=null||quantityChainModern(value)||value.slashPixelVerified!==false
        ||['slashBounds','numeratorRegion','denominatorRegion'].some(key=>value[key]!=null)||(value.splitRegionMethod===undefined?'none':value.splitRegionMethod)!=='none')fail('talent_footer_initial_final_image_or_whole_provenance_invalid');
    dimensions(value,start,finish);
  }
  const initial=proof.initialReading;sourceRect(initial.bounds,[old.x,old.y,old.width,old.height]);
  const diagnostics=[[initial,'initialWholeRawText','initialWholeDetectorText',old]];
  if(v2){const original=proof.originalWholeReading,originalBox=sourceRect(original.bounds,[725,890,470,65]);diagnostics.push([original,'originalWholeRawText','originalWholeDetectorText',originalBox]);}
  for(const [values,rawKey,detKey,accepted] of [...diagnostics.map(([value,raw,det])=>[value,raw,det,false]),[q,'wholeRawText','wholeDetectorText',true]]){
    const wholeRaw=proof[rawKey],wholeDetector=proof[detKey];
    if(typeof wholeRaw!=='string'||typeof wholeDetector!=='string'||typeof values.raw!=='string'||typeof values.detectorRaw!=='string'||!Array.isArray(values.ocrRows))fail('talent_footer_original_full_raw_strings_required');
    values.ocrRows.forEach(sourceRow);if(clean(wholeDetector)!==clean(values.ocrRows.map(row=>row.text).join('')))fail('talent_footer_detector_text_not_original_rows');
    const strip=v=>clean(v).startsWith('培养需求')?clean(v).slice('培养需求'.length):'';
    if(strip(wholeRaw)!==clean(values.raw)||strip(wholeDetector)!==clean(values.detectorRaw))fail('talent_footer_original_prefix_removal_changed');
    if(accepted){if(clean(wholeRaw)!==clean(wholeDetector)||!/^培养需求(0|[1-9][0-9]{0,9})\/(0|[1-9][0-9]{0,9})$/.test(clean(wholeRaw)))fail('talent_footer_full_prefix_or_ratio_ambiguous');sourceRows(values.ocrRows,box,clean(wholeRaw));}
  }
  const actual=quantity(q,start,finish,'培养需求');
  if(actual.required<1)fail('talent_modern_footer_aggregate_denominator_positive_required');
  for(const [reading,rawKey,detKey,diagnosticBox] of diagnostics){
    if(!reading.complete){if(reading.owned!=null||reading.required!=null)fail('talent_footer_failed_initial_quantities_not_null');}
    else {
      const whole=clean(proof[rawKey]);
      if(whole!==clean(proof[detKey])||!/^培养需求(0|[1-9][0-9]{0,9})\/(0|[1-9][0-9]{0,9})$/.test(whole))fail('talent_footer_complete_initial_full_prefix_raw_detector_mismatch');
      sourceRows(reading.ocrRows,diagnosticBox,whole);
      if(!same(quantity(reading,start,finish,'培养需求'),actual))fail('talent_footer_initial_complete_conflict');
    }
  }
  originalTooltipIdentity(tip,v2);
  const name=sourceRect(tip.nameRegion,[730,168,440,67]),kind=sourceRect(tip.kindRegion,[730,230,440,65]),source=sourceRect(tip.sourceRegion,tooltipSourceRegion(tip.tooltipQuantityMethod));
  for(const [key,rawKey] of [['nameRows','rawName'],['alternateNameRows','alternateRawName']]){
    const observed=sourceRows(tip[key],name);if(observed!==clean(tip[rawKey])||canonical(observed)!==canonical(tip.name))fail('talent_both_modern_full_name_rows_and_raw_must_match');
  }
  if(tip.alternateNameScale!==4||tip.alternateNamePreprocessing!==(v2?'bgr_cubic_4x':'gray_threshold_210_inverse_cubic_4x'))fail('talent_modern_alternate_name_preprocessing_required');
  sourceRows(tip.kindRows,kind,tip.kind);sourceRows(tip.sourceRows,source,'来源');sourceRows(tip.footerLabelRows,box,clean(proof.wholeRawText));
  if(!same(tip.footerLabelRows,q.ocrRows))fail('talent_modern_footer_label_is_not_final_quantity_original_rows');return actual;
}
function source31Protocol(raw,frames,previews,pinnedProof,start,finish){
  const tips=frames.filter(f=>'kindRows' in f&&'footerLabelRows' in f),active=[...Object.keys(SOURCE31_METHODS),...SOURCE31_FRAME_FIELDS].some(k=>raw[k]!=null)||frames.some(f=>SOURCE31_FRAME_FIELDS.some(k=>f[k]!=null))||tips.some(f=>f.readTiming!=null);
  if(!active)return false;
  if(!markerMethod(raw.previewMarkerMethod)||!footerMethod(raw.tooltipQuantityMethod)||Object.entries(SOURCE31_METHODS).some(([k,v])=>raw[k]!==v)||raw.previewTimingMethod!==PREVIEW_TIMING_METHOD||costMethod(raw)!==PINNED_SPLIT_METHOD||pinnedProof==null)fail('talent_source31_payload_methods_and_pinned_costs_required');
  const pairs=raw.evidence.materialTooltips;
  if(!Array.isArray(pairs)||pairs.some(pair=>!Array.isArray(pair)||pair.length!==2)||!same(pairs.flat(),tips)||!tips.length)fail('talent_modern_tooltip_pairs_must_retain_all_actual_raw_frames');
  const identity=proof=>{sourceModelShape(proof);return [...proof.countModels.assets,proof.rawDetectorAsset].map(a=>[a.modelName,a.relativePath,a.sha256,a.length]);};
  for(const f of [...previews,...tips]){
    if(!Number.isSafeInteger(f.observedAt)||f.width!==1920||f.height!==1080||!same(identity(f.sourceRegionModelEvidence),identity(pinnedProof)))fail('talent_source_regions_same_six_asset_scope_required');
  }
  if(previews.some(p=>p.previewMarkerMethod!==raw.previewMarkerMethod))fail('talent_source31_marker_methods_mixed');
  if(tips.some(tip=>tip.tooltipQuantityMethod!==raw.tooltipQuantityMethod))fail('talent_source31_footer_methods_mixed');
  previews.forEach(markerRoles);tips.forEach(tip=>footerQuantity(tip,start,finish));
  const all=frames.filter(f=>previews.includes(f)||tips.includes(f));
  for(let i=0;i<all.length;i+=2)if(('materials' in all[i])!==('materials' in all[i+1]))fail('talent_original_retained_pair_kinds_mixed');
  retainedPairTiming(raw,all,start,finish);return true;
}
function costMethod(value){const marker=value.costQuantityMethod;if(marker!=null&&!['legacy_observed_ratio',PINNED_SPLIT_METHOD].includes(marker))fail('talent_cost_quantity_method_unreviewed');return marker??'legacy_observed_ratio';}
function previewMaterials(p){if(!Array.isArray(p.materials)||p.materials.length<1||p.materials.length>4||p.materials.some(item=>!item||typeof item!=='object'||!item.quantity||typeof item.quantity!=='object'||Array.isArray(item.quantity)))fail('talent_native_material_quantity_objects_missing');return p.materials;}
export function verifyTalentQuantity(q,start,finish,prefix=''){
  const s=dimensions(q,start,finish),box=rect(q.bounds),owned=integer(q.owned),required=integer(q.required,prefix?0:1);
  splitModelShape(q);
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
  splitModelShape(initial);
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
function entryGlobalHeader(f,n,character,s){
  if(n.nameSource!=='talent_global_header'||n.nameBoxMethod!=='whole_header_ocr_box_contains_name')fail('talent_entry_current_global_header_source_missing');
  const box=rect(n.nameRegion),menu=rect(f.menuRegion),expected={x:roundEven(130*s),y:roundEven(20*s),width:roundEven(320*s),height:roundEven(85*s)},menuExpected={x:roundEven(40*s),y:roundEven(390*s),width:roundEven(320*s),height:roundEven(100*s)};
  if(!same(box,expected)||!same(menu,menuExpected))fail('talent_global_header_menu_outside_exact_geometry');
  if(n.nameRows?.length!==1||f.menuRows?.length!==1)fail('talent_global_header_menu_unique_complete_row_required');
  const header=rowText(n.nameRows,box,s),label=rowText(f.menuRows,menu,s);
  for(const [row,bounds] of [[n.nameRows[0],box],[f.menuRows[0],menu]]){const r=rect(row.bounds);if(Math.min(r.y-bounds.y,bounds.y+bounds.height-r.y-r.height)<2*s)fail('talent_global_header_menu_row_clipped');}
  const match=header.match(/^(火|水|风|雷|草|冰|岩)元素\/([^/]+)$/);
  if(n.headerRaw!==n.nameRows.map(r=>r.text).join('')||!match||match[2]!==clean(character)||n.name!==match[2]||n.headerElement!==match[1]||label!=='天赋')fail('talent_current_element_fullname_not_derived_from_raw_header');
}
function entryObservation(f,character,start,finish,globalHeader=false){
  const s=dimensions(f,start,finish);
  if(f.phase!=='talent_entry_observation'||f.focused!==true||f.overview!==true||f.promptVisible!==false||f.reviveVisible!==false)fail('talent_entry_known_focused_page_required');
  const n=f.character;dimensions(n,start,finish);
  if(n.observedAt!==f.observedAt||n.width!==f.width||n.height!==f.height||n.overview!==true)fail('talent_entry_current_fullname_unverified');
  if(globalHeader)entryGlobalHeader(f,n,character,s);
  else{const nameBox=characterRegion(n);if((n.nameSource??'attribute_right_full_name')!=='attribute_right_full_name'||clean(n.name)!==clean(character)
      ||n.nameRows?.length!==1||rowText(n.nameRows,nameBox,s)!==clean(character))fail('talent_legacy_entry_current_fullname_unverified');
    const name=rect(n.nameRows[0].bounds);if(Math.min(name.y-nameBox.y,nameBox.y+nameBox.height-name.y-name.height)<2*s)fail('talent_entry_fullname_crop_edge');}
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
function entryTriple(all,character,start,finish,globalHeader,completedAt=null){
  const result=all.map(f=>entryObservation(f,character,start,finish,globalHeader));pair(all[0],all[1]);pair(all[1],all[2]);
  if(completedAt!==null&&(completedAt<all[2].observedAt||completedAt-all[1].observedAt>1500||completedAt-all[2].observedAt>1500))fail('talent_entry_triple_stale_at_actual_read_completion');
  for(const [a,b] of [[all[0].character,all[1].character],[all[1].character,all[2].character]])if(a.nameSource!==b.nameSource||clean(a.headerRaw??'')!==clean(b.headerRaw??''))fail('talent_global_header_source_or_raw_changed_between_frames');
  for(let i=0;i<3;i++){
    const [a,b,c]=result.map(values=>rect(values[i].bounds)),cy=r=>r.y+Math.floor(r.height/2),cx=r=>r.x+Math.floor(r.width/2);
    if(Math.abs(cy(a)-cy(b))>6||Math.abs(cy(b)-cy(c))>6||Math.abs(cx(b)-cx(c))>6||new Set(result.map(values=>clean(values[i].text))).size!==1)fail('talent_entry_stable_geometry_or_text_required');
  }
  return result;
}
function entryBinding(e,frames,character,type,start,finish,names,details){
  const selected=e.twoPickedEntryFrames,click=e.entryClickFrame;
  if(!Array.isArray(selected)||selected.length!==2||!click||typeof click!=='object')fail('talent_explicit_entry_pair_click_required');
  const entries=frames.filter(f=>f.phase==='talent_entry_observation'),all=[...selected,click];
  const globalHeader='talentEntryIdentitySource' in e||entries.some(f=>'menuRegion' in f||'menuRows' in f||f.character?.nameSource==='talent_global_header'
    ||f.character?.nameBoxMethod==='whole_header_ocr_box_contains_name'||f.character?.headerRaw||f.character?.headerElement);
  if(globalHeader){if(e.talentEntryIdentitySource!=='talent_global_header')fail('talent_global_header_identity_cannot_downgrade');
    for(const n of e.characterIdentityTrials??names)if(n.nameSource!=='attribute_right_full_name'||n.nameBoxMethod!=='actual_name_ocr_box'
        ||(n.headerRaw??'')!==''||(n.headerElement??'')!=='')fail('talent_initial_attribute_identity_cannot_be_header');}
  if(all.some(f=>!included(f,entries))||same(selected[0],selected[1])||selected.some(f=>same(f,click)))fail('talent_entry_references_not_independent_raw');
  const positions=all.map(f=>entries.findIndex(v=>same(v,f)));
  if(positions[1]!==positions[0]+1||positions[2]!==positions[1]+1)fail('talent_entry_refs_not_original_consecutive_sequence');
  if(selected[0].observedAt<=names.at(-1).observedAt||click.observedAt>=details[0].observedAt||click.observedAt-entries[0].observedAt>12000
      ||entries.some(f=>f.observedAt<names.at(-1).observedAt||f.observedAt>click.observedAt))fail('talent_entry_sequence_or_deadline_invalid');
  const rolling=['talentEntryObservationMethod','talentEntryObservationLimitMs','talentEntryObservationPollMs'].some(k=>k in e);
  if(rolling){
    if(e.talentEntryObservationMethod!=='bounded_contiguous_entry_triple'||e.talentEntryObservationLimitMs!==12000||e.talentEntryObservationPollMs!==300
        ||!globalHeader||entries.length<3||entries.length>41||!same(all,entries.slice(-3))||click.observedAt-entries[0].observedAt>=12000)fail('talent_entry_rolling_method_limits_or_tail_invalid');
    for(const [i,f] of entries.entries()){
      integer(f.readCompletedAt,0,Number.MAX_SAFE_INTEGER);
      if(f.focused!==true||f.promptVisible!==false||f.reviveVisible!==false||f.readCompletedAt<f.observedAt||f.readCompletedAt>finish
          ||i&&f.observedAt-entries[i-1].readCompletedAt<300)fail('talent_entry_rolling_continued_after_abort_or_shortened_poll');
    }
    if(click.readCompletedAt-entries[0].observedAt>=12000)fail('talent_entry_completion_extends_original_deadline');
    for(let i=0;i<entries.length-3;i++){
      let valid=false;try{entryTriple(entries.slice(i,i+3),character,start,finish,globalHeader,entries[i+2].readCompletedAt);valid=true;}catch(error){if(error?.constructor!==Error)throw error;}
      if(valid)fail('talent_entry_rolling_continued_after_first_legal_triple');
    }
  }
  const result=entryTriple(all,character,start,finish,globalHeader,rolling?click.readCompletedAt:null);
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
  if(['previewMarkerMethod','markerRoleEvidence','sourceRegionModelEvidence'].some(k=>p[k]!=null))markerRoles(p);
  else rowText(p.rows,region(p,'markerRegion',[420,235,1100,750]),s,false);
  const labels=p.rows.map(row=>clean(row.text));
  if(['属性变更','所需材料','取消','确认'].some(label=>labels.filter(value=>value===label).length!==1))fail('talent_popup_markers_missing');
  previewMaterials(p);
  const method=costMethod(p);
  if(method===PINNED_SPLIT_METHOD?p.materials.some(item=>!modernSplit(item.quantity)):p.materials.some(item=>quantityChainModern(item.quantity)))fail('talent_popup_method_split_proof_mismatch');
  const materials=p.materials.map(item=>{
    const name=canonical(item.name),card=rect(item.card),icon=rect(item.iconRegion);
    if(!name||number(item.iconScore)<.75||item.iconScore>1||!inside(card,{x:p.width*.2,y:p.height*.5,width:p.width*.6,height:p.height*.25})||!inside(icon,card)
        ||!inside(rect(item.quantity.bounds),card)||item.quantity.observedAt!==p.observedAt)fail('talent_material_card_scope_unverified');
    materialCrop(item,p,start,finish);
    return {name,...quantity(item.quantity,start,finish)};
  });
  if(new Set(materials.map(item=>item.name)).size!==materials.length)fail('talent_duplicate_material');
  if(quantityChainModern(p.mora))fail('talent_material_model_proof_cannot_authenticate_mora');
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
  if(['talentEntryObservationMethod','talentEntryObservationLimitMs','talentEntryObservationPollMs'].some(k=>k in e)||'talentEntryIdentitySource' in e||'characterIdentityMethod' in e||'twoPickedEntryFrames' in e||'entryClickFrame' in e||frames.some(f=>f.phase==='talent_entry_observation'))entryBinding(e,frames,character,type,start,finish,names,details);
  const previews=frames.filter(f=>'materials' in f&&'current' in f);
  if(previews.length<2||previews.length%2||previews[0].observedAt<=details[1].observedAt||!same(e.preview,previews.at(-1)))fail('talent_popup_pair_missing');let costs;
  previewTiming(raw,previews,start,finish);
  if(previews.some(p=>costMethod(p)!==costMethod(raw)))fail('talent_payload_popup_quantity_method_mismatch');
  let pinnedProof=null,pinnedSourceProof=null;
  for(const p of previews)for(const item of previewMaterials(p))for(const reading of [item.quantity,item.quantity.initialReading])if(reading!=null&&modernSplit(reading)){
    splitModelShape(reading);
    // Asset field order is fixed here; JSON object property order carries no provenance.
    const identity=[...reading.splitModelEvidence.countModels.assets,reading.splitModelEvidence.rawDetectorAsset].map(a=>[a.modelName,a.relativePath,a.sha256,a.length]);
    if(pinnedProof!=null&&!same(pinnedProof,identity))fail('talent_all_material_popup_model_proofs_must_match');
    pinnedProof=identity;
    pinnedSourceProof=reading.splitModelEvidence;
  }
  const source31=source31Protocol(raw,frames,previews,pinnedSourceProof,start,finish);
  for(let i=0;i<previews.length;i+=2){pair(previews[i],previews[i+1]);for(const p of previews.slice(i,i+2)){const actual=preview(p,b.base,start,finish);if(costs&&!same(costs,actual))fail('talent_costs_changed');costs=actual;}}
  if(e.materialTooltips?.length!==costs.materials.length)fail('talent_fullnamed_tooltips_missing');
  for(const [i,two] of e.materialTooltips.entries()){
    const item=costs.materials[i];if(two.length!==2)fail('talent_tooltip_pair_missing');pair(two[0],two[1]);
    for(const tip of two){const s=dimensions(tip,start,finish),box=region(tip,'nameRegion',[730,168,440,67]);
      if(!included(tip,frames)||tip.page!==true||canonical(tip.name)!==item.name)fail('talent_tooltip_scope_mismatch');const candidates=[];
      for(const [rowsKey,rawKey,projected] of [['nameRows','rawName',false],['alternateNameRows','alternateRawName',true]]){
        try{const name=rowText(tip[rowsKey],box,s,true,projected);if(name===clean(tip[rawKey])&&(!projected||tip.alternateNameScale===4&&tip.alternateNamePreprocessing===(source31&&tip.tooltipQuantityMethod===FOOTER_METHOD_V2?'bgr_cubic_4x':'gray_threshold_210_inverse_cubic_4x')))candidates.push(canonical(name));}catch{}
      }
      const kind=rowText(tip.kindRows,region(tip,'kindRegion',[730,230,440,65]),s),sourceBox=region(tip,'sourceRegion',source31?tooltipSourceRegion(tip.tooltipQuantityMethod):[730,690,460,65]);
      rowText(tip.sourceRows,sourceBox,s,false);
      if(!candidates.includes(item.name)||kind!==tip.kind||!['角色天赋素材','角色与武器培养素材'].includes(kind)
          ||tip.sourceRows.filter(row=>clean(row.text)==='来源').length!==1)fail('talent_tooltip_fullname_unverified');
      if(!rowText(tip.footerLabelRows,region(tip,'footerLabelRegion',source31?footerRegion(tip.tooltipQuantityMethod):[725,890,470,65]),s,false).startsWith('培养需求'))fail('talent_footer_label_missing');
      let owned;
      if(source31)owned=footerQuantity(tip,start,finish).owned;
      else{region(tip.quantity,'bounds',[885,890,295,65]);owned=quantity(tip.quantity,start,finish,'培养需求').owned;}
      if(owned!==item.owned)fail('talent_popup_tooltip_owned_mismatch');
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
