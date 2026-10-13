// GPL-3.0-only. Four fixed read-only stacks; never conversion, recipes, costs or spending.
export const WEEKLY_MATERIALS=Object.freeze([
  {materialId:'113060',materialName:'残火灯烛',category:'characterDevelopmentItems'},
  {materialId:'113061',materialName:'丝织之羽',category:'characterDevelopmentItems'},
  {materialId:'113062',materialName:'否定裁断',category:'characterDevelopmentItems'},
  {materialId:'113021',materialName:'异梦溶媒',category:'preciousItems'},
].map(Object.freeze));
const fail=message=>{throw Error(message);};
const clean=v=>typeof v==='string'?v.normalize('NFKC').replace(/\s/g,''):fail('weekly_raw_text_missing');
const num=v=>typeof v==='number'&&Number.isFinite(v)?v:fail('weekly_number_invalid');
const integer=(v,min=0,max=999999999)=>Number.isInteger(v)&&v>=min&&v<=max?v:fail('weekly_integer_invalid');
const rect=r=>r&&['x','y','width','height'].every(k=>Number.isInteger(r[k]))&&r.x>=0&&r.y>=0&&r.width>0&&r.height>0?r:fail('weekly_rect_invalid');
const inside=(a,b)=>a.x>=b.x&&a.y>=b.y&&a.x+a.width<=b.x+b.width&&a.y+a.height<=b.y+b.height;
const equal=(a,b)=>['x','y','width','height'].every(k=>a[k]===b[k]);
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const round=v=>{const n=Math.floor(v),d=v-n;return d===.5?n+(n%2):Math.round(v);}; // .NET midpoint-to-even.
const rows=(values,box,s,margin=true)=>{
  if(!Array.isArray(values)||!values.length)fail('weekly_raw_rows_missing');
  for(const row of values){const r=rect(row);if(!inside(r,box)||margin&&Math.min(r.x-box.x,r.y-box.y,box.x+box.width-r.x-r.width,box.y+box.height-r.y-r.height)<2*s)fail('weekly_raw_row_clipped');}
  return values.map(row=>clean(row.text));
};
const dimensions=(f,start,finish)=>{
  integer(f?.width,800,4096);integer(f?.height,450,2160);
  if(f.width*9!==f.height*16)fail('weekly_client_dimensions_invalid');
  const at=num(f.stack?.observedAt??f.observedAt);if(at<start||at>finish)fail('weekly_frame_outside_current_run');
  return f.width/1920;
};
const count=raw=>/^(0|[1-9][0-9]{0,8})$/.test(clean(raw))?integer(Number(clean(raw))):fail('weekly_complete_raw_quantity_missing');
const headerAliases=category=>category==='preciousItems'?['贵重道具']:['角色培养道具','养成道具'];
const modelAssets=[
  ['PpOcrDetV4','Assets/Model/PaddleOCR/Det/V4/PP-OCRv4_mobile_det_infer/slim.onnx'],
  ['PpOcrRecV4','Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/slim.onnx'],
  ['PpOcrRecV6','Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/slim.onnx'],
  ['PpOcrRecV4-labels','Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/inference.yml'],
  ['PpOcrRecV6-labels','Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/inference.yml'],
];
function modelIdentity(r){
  const m=r.modelEvidence,fixed={rawPaddleConfig:8,rawPaddleName:'V6',fixedDetectorConfig:7,fixedDetectorName:'V4',pinMethod:'actual_bundled_open_read_sha256_hold_session'};
  if(!m||r.rawPaddleReadback!==8||Object.entries(fixed).some(([k,v])=>m[k]!==v)||!Array.isArray(m.assets)||m.assets.length!==5)fail('weekly_fixed_model_config_and_pin_evidence_missing');
  for(const [i,a] of m.assets.entries())if(!a||a.modelName!==modelAssets[i][0]||a.relativePath!==modelAssets[i][1]
      ||typeof a.sha256!=='string'||!/^[0-9a-fA-F]{64}$/.test(a.sha256)||integer(a.length,1,2147483647)!==a.length)fail('weekly_fixed_actual_model_asset_identity_invalid');
}
function border(raw,item,w,h){
  if(raw?.verified!==true||raw.method!=='four_side_neutral_outline'||raw.minimumChannel!==225||raw.maximumSpread!==35||raw.minimumFraction!==.9||raw.sides?.length!==4)fail('weekly_raw_selection_border_missing');
  const radius=Math.max(3,round(item.width*8/125));
  for(const [i,side] of raw.sides.entries()){
    const vertical=i<2,axis=vertical?'x':'y',edge=[item.x,item.x+item.width-1,item.y,item.y+item.height-1][i];
    const begin=vertical?item.y+Math.trunc(item.height*.2):item.x+Math.trunc(item.width*.12);
    const end=vertical?item.y+Math.trunc(item.height*.75):item.x+Math.trunc(item.width*.55);
    if(side.axis!==axis||Math.abs(integer(side.coordinate,0,vertical?w-1:h-1)-edge)>radius
        ||integer(side.sampleCount,1)!==end-begin||integer(side.neutralCount)>side.sampleCount||side.neutralCount/side.sampleCount<.9)fail('weekly_border_side_geometry_or_fraction_invalid');
    const stride=Math.max(1,Math.trunc((end-begin)/12)),positions=[];
    for(let p=begin;p<end;p+=stride)positions.push(p);
    if(side.samples?.length!==positions.length)fail('weekly_border_raw_pixels_incomplete');
    let neutral=0;
    for(const [j,pixel] of side.samples.entries()){
      const x=integer(pixel.x,0,w-1),y=integer(pixel.y,0,h-1);
      if((vertical?x:y)!==side.coordinate||(vertical?y:x)!==positions[j])fail('weekly_border_pixel_position_invalid');
      const channels=['b','g','r'].map(k=>integer(pixel[k],0,255));
      if(Math.min(...channels)>=225&&Math.max(...channels)-Math.min(...channels)<=35)neutral++;
    }
    if(neutral/positions.length<.9||neutral>side.neutralCount||side.neutralCount-neutral>side.sampleCount-positions.length)fail('weekly_border_pixels_contradict_selection');
  }
}
function namedCount(r,item,s){
  const fixed={method:'grid_hsv_foreground_exact_dual_ocr',sourceScale:3,maximumSaturation:140,maximumValue:210,minimumComponentArea:20,
    minimumComponentHeight:12,minimumComponentBottomRatio:.55,maximumComponentAspectRatio:3,glyphHeight:48,horizontalPadding:24,verticalPadding:24,topPaddingReference:8,bottomPaddingReference:8,
    ocrScale:1,detectorModel:'PaddleV4_fixed',rawModel:'configured_native_paddle_without_detector',sourceInterpolation:'linear',glyphInterpolation:'nearest',ocrInterpolation:'nearest'};
  if(!r||Object.entries(fixed).some(([k,v])=>r[k]!==v))fail('weekly_named_count_method_parameters_missing');
  modelIdentity(r);
  const pad=Math.max(1,round(8*item.width/125));
  const source={x:item.x+Math.trunc(item.width*5/125),y:item.y+Math.trunc(item.height*128/153)-pad,
    width:Math.trunc(item.width*120/125)-Math.trunc(item.width*5/125),height:Math.trunc(item.height*150/153)-Math.trunc(item.height*128/153)+2*pad};
  if(!equal(rect(r.sourceRegion),source))fail('weekly_named_count_source_geometry_invalid');
  const all=r.allComponents,mask={x:0,y:0,width:source.width*3,height:source.height*3};
  if(!Array.isArray(all)||all.length<1||all.length>1000||all.some(c=>!inside(rect(c),mask))
      ||!same(all,[...all].sort((a,b)=>a.x-b.x||a.y-b.y)))fail('weekly_original_mask_components_invalid');
  const chosen=all.filter(c=>c.width>1&&c.height>=12&&c.width*c.height>=20&&c.y+c.height>=mask.height*.55&&c.width/c.height<=3);
  if(!chosen.length||!same(r.components,chosen))fail('weekly_filtered_components_not_derived');
  const left=Math.min(...chosen.map(c=>c.x)),top=Math.min(...chosen.map(c=>c.y));
  const f={x:left,y:top,width:Math.max(...chosen.map(c=>c.x+c.width))-left,height:Math.max(...chosen.map(c=>c.y+c.height))-top};
  const glyph=Math.max(1,round(f.width*48/f.height)),canvas={x:0,y:0,width:glyph+48,height:96};
  const fg={x:source.x+Math.floor(f.x/3),y:source.y+Math.floor(f.y/3),width:Math.ceil((f.x+f.width)/3)-Math.floor(f.x/3),height:Math.ceil((f.y+f.height)/3)-Math.floor(f.y/3)};
  if(!equal(rect(r.foregroundBounds),f)||!equal(rect(r.foregroundSourceBounds),fg)||integer(r.glyphWidth,1)!==glyph
      ||integer(r.normalizedWidth,1)!==canvas.width||integer(r.normalizedHeight,1)!==96||integer(r.ocrInputWidth,1)!==canvas.width||integer(r.ocrInputHeight,1)!==96)fail('weekly_foreground_union_or_normalization_invalid');
  if(['sourcePixelsSha256','maskPixelsSha256','normalizedPixelsSha256','ocrInputPixelsSha256'].some(k=>typeof r[k]!=='string'||! /^[0-9a-fA-F]{64}$/.test(r[k])))fail('weekly_preprocessing_pixel_fingerprints_missing');
  if(r.ocrInputPixelsSha256!==r.normalizedPixelsSha256)fail('weekly_dual_models_not_using_same_original_canvas');
  if(r.detectorRows?.length!==1||r.sourceRows?.length!==1)fail('weekly_named_count_dual_ocr_rows_missing');
  const row=r.detectorRows[0],b=rect(row),input=canvas,margin=Math.max(2,2*s*48*3/f.height);
  if(!inside(b,input)||Math.min(b.x,b.y,input.width-b.x-b.width,input.height-b.y-b.height)<margin)fail('weekly_normalized_integer_clipped');
  const x=source.x+Math.floor((f.x+(b.x-24)*f.width/glyph)/3),y=source.y+Math.floor((f.y+(b.y-24)*f.height/48)/3);
  const right=source.x+Math.ceil((f.x+(b.x+b.width-24)*f.width/glyph)/3),bottom=source.y+Math.ceil((f.y+(b.y+b.height-24)*f.height/48)/3);
  if(!equal(rect(r.sourceRows[0]),{x,y,width:right-x,height:bottom-y})||row.text!==r.sourceRows[0].text)fail('weekly_original_source_row_projection_invalid');
  rows(r.sourceRows,source,s);rows([{...fg,text:''}],source,s);
  if(typeof r.raw!=='string'||typeof row.text!=='string'||r.raw.replace(/\s/g,'')!==row.text.replace(/\s/g,'')||!/^(0|[1-9][0-9]{0,8})$/.test(r.raw.replace(/\s/g,'')))fail('weekly_named_count_dual_ocr_disagrees');
  return {value:integer(Number(r.raw.replace(/\s/g,''))),source};
}
function initialStack(f,stack,item){
  const initial=f.initialStack,title={x:Math.trunc(f.width*.682),y:Math.trunc(f.width*.0625),width:Math.trunc(f.width*.256),height:Math.trunc(f.width*.03125)};
  const amount={x:item.x+Math.trunc(item.width*5/125),y:item.y+Math.trunc(item.height*128/153),width:Math.trunc(item.width*120/125)-Math.trunc(item.width*5/125),height:Math.trunc(item.height*150/153)-Math.trunc(item.height*128/153)};
  if(!initial||initial.observedAt!==stack.observedAt||initial.countMethod!=='raw_ocr_without_detector'||!equal(rect(initial.nameRegion),title)
      ||!equal(rect(initial.countRegion),amount)||typeof initial.rawCountText!=='string'
      ||['selectedItemVerified','selectedItemRect','selectionEvidence'].some(k=>!same(initial[k],stack[k])))fail('weekly_initial_stack_scope_or_geometry_changed');
  for(const [key,box] of [['nameRows',title],['countRows',amount]])if(!Array.isArray(initial[key])||initial[key].some(r=>typeof r.text!=='string'||!inside(rect(r),box)))fail('weekly_initial_raw_rows_missing');
  return initial;
}
function frame(f,target,selection,start,finish){
  const s=dimensions(f,start,finish),stack=f.stack,item=rect(selection.itemRect),client={x:0,y:0,width:f.width,height:f.height};
  if(f.gameActive!==true||f.promptVisible!==false||f.tabVerified!==true||f.category!==target.category
      ||f.iconName!==target.materialName||num(f.iconScore)<.75||f.iconScore>1||!inside(item,client))fail('weekly_category_focus_model_unverified');
  const header=rect(f.headerRegion),headerExpected={x:round(100*s),y:0,width:round(350*s),height:round(100*s)};
  if(!equal(header,headerExpected)||rows(f.headerRows,header,s).filter(v=>headerAliases(target.category).includes(v)).length!==1)fail('weekly_complete_category_header_unverified');
  const modern='countReading' in f||'initialStack' in f||stack.countMethod==='grid_hsv_foreground_exact_dual_ocr';
  const initial=modern?initialStack(f,stack,item):null,reading=modern?namedCount(f.countReading,item,s):null;
  const title=rect(stack.nameRegion),titleExpected=modern?{x:round(1280*s),y:round(110*s),width:round(540*s),height:round(78*s)}:{x:Math.trunc(f.width*.682),y:Math.trunc(f.width*.0625),width:Math.trunc(f.width*.256),height:Math.trunc(f.width*.03125)};
  const amount=rect(stack.countRegion),amountExpected=modern?reading.source:{x:item.x+Math.trunc(item.width*5/125),y:item.y+Math.trunc(item.height*128/153),width:Math.trunc(item.width*120/125)-Math.trunc(item.width*5/125),height:Math.trunc(item.height*150/153)-Math.trunc(item.height*128/153)};
  const icon=rect(f.iconRegion),iconExpected={x:item.x,y:item.y,width:item.width,height:round(item.height*125/153)};
  if(!equal(title,titleExpected)||!equal(amount,amountExpected)||!inside(title,client)||!inside(amount,modern?client:item)||!equal(icon,iconExpected)
      ||f.iconMethod!=='cell_resize_125x153_top_125x125'||stack.selectedItemVerified!==true||!equal(rect(stack.selectedItemRect),item)
      ||rows(stack.nameRows,title,s).length!==1||clean(stack.nameRows[0].text)!==target.materialName
      ||stack.countMethod!==(modern?'grid_hsv_foreground_exact_dual_ocr':'raw_ocr_without_detector')||stack.countRows?.length!==1)fail('weekly_named_selected_stack_geometry_unverified');
  const detected=rows(stack.countRows,amount,s)[0],raw=clean(stack.rawCountText);
  if(raw!==detected)fail('weekly_quantity_detector_disagrees');
  if(modern){
    if(!same(stack.countRows,f.countReading.sourceRows)||stack.rawCountText!==f.countReading.raw||count(raw)!==reading.value)fail('weekly_stack_not_bound_to_actual_count_reading');
    const old={...f,stack:initial};delete old.countReading;delete old.initialStack;let oldCount=null;
    try{oldCount=frame(old,target,selection,start,finish);}catch{}
    if(oldCount!==null&&oldCount!==reading.value)fail('weekly_initial_complete_count_conflicts');
  }
  border(stack.selectionEvidence,item,f.width,f.height);
  return count(raw);
}
export function verifyWeeklyObservation(raw,start,finish){
  if(!Number.isFinite(start)||!Number.isFinite(finish)||finish<start||raw?.source!=='weekly_conversion_backpack_selected_stack'||raw.category!=='weeklyConversion'
      ||raw.readOnly!==true||raw.status!=='verified'||raw.mainUiRestored!==true||raw.cleanupCompleted!==true
      ||!raw.inventory||!raw.observations||Object.keys(raw.inventory).sort().join()!==WEEKLY_MATERIALS.map(m=>m.materialId).sort().join()
      ||Object.keys(raw.observations).sort().join()!==WEEKLY_MATERIALS.map(m=>m.materialId).sort().join())fail('weekly_fixed_readonly_scope_or_cleanup_invalid');
  if(raw.rejectedObservations!==undefined&&(!raw.rejectedObservations||typeof raw.rejectedObservations!=='object'||Array.isArray(raw.rejectedObservations)
      ||Object.keys(raw.rejectedObservations).some(id=>!WEEKLY_MATERIALS.some(m=>m.materialId===id))))fail('weekly_rejected_observation_scope_invalid');
  const inventory={},segments=[];let latest=start,client=null;
  for(const target of WEEKLY_MATERIALS){
    const pair=raw.observations[target.materialId],selection=pair?.selection,item=rect(selection?.itemRect);
    const clicked=num(selection.clickedAt),x=num(selection.x),y=num(selection.y),a=pair.first,b=pair.second;
    if(x<item.x||x>item.x+item.width||y<item.y||y>item.y+item.height||clicked<start||clicked>finish
        ||a?.width!==b?.width||a?.height!==b?.height||!a?.stack||!b?.stack||a.stack.observedAt-clicked<100||a.stack.observedAt-clicked>5000
        ||b.stack.observedAt-a.stack.observedAt<100||b.stack.observedAt-a.stack.observedAt>5000)fail('weekly_independent_selected_frames_missing');
    const shape=`${a.width}x${a.height}`;if(client&&client!==shape)fail('weekly_capture_client_changed');client=shape;
    const first=frame(a,target,selection,start,finish),second=frame(b,target,selection,start,finish);
    const aliases=headerAliases(target.category),ha=a.headerRows.map(row=>clean(row.text)).filter(text=>aliases.includes(text)),hb=b.headerRows.map(row=>clean(row.text)).filter(text=>aliases.includes(text));
    if(ha.join()!==hb.join())fail('weekly_actual_reviewed_header_changed_between_frames');
    if(first!==second||integer(raw.inventory[target.materialId])!==second)fail('weekly_raw_pair_or_summary_count_disagrees');
    segments.push({clicked,finished:b.stack.observedAt});latest=Math.max(latest,b.stack.observedAt);
    inventory[target.materialId]={name:target.materialName,count:second,status:'exact',verified:true,source:raw.source,evidence:{materialId:target.materialId,...pair}};
  }
  segments.sort((a,b)=>a.clicked-b.clicked);
  if(segments.some((v,i)=>i&&v.clicked<=segments[i-1].finished))fail('weekly_selected_captures_overlap_or_reused');
  if(Math.abs(Date.parse(raw.observedAt??'')-latest)>1||!Number.isFinite(Date.parse(raw.observedAt??'')))fail('weekly_observed_at_mismatch');
  const worlds=raw.worldFrames;if(!Array.isArray(worlds)||worlds.length<2)fail('weekly_world_pair_missing');
  let previous=latest;
  for(const world of worlds){dimensions(world,start,finish);if(`${world.width}x${world.height}`!==client||world.observedAt<=previous)fail('weekly_cleanup_timeline_invalid');previous=world.observedAt;}
  const [a,b]=worlds.slice(-2);
  if(b.observedAt-a.observedAt<=0||b.observedAt-a.observedAt>5000||finish-b.observedAt>1500
      ||[a,b].some(w=>w.focused!==true||w.world!==true||w.prompt!==false||w.knownBag!==false||w.escapeRequested!==false))fail('weekly_fresh_focused_world_pair_unverified');
  return inventory;
}
export function createWeeklyInventoryReader({dispatcher,log}){
  return async remainingMilliseconds=>{
    if(!Number.isFinite(remainingMilliseconds)||remainingMilliseconds<=0)fail('weekly_deadline_expired');
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try{
      cts.CancelAfter(Math.max(1,Math.min(180000,Math.floor(remainingMilliseconds))));
      const serialized=await dispatcher.ReadWeeklyConversionInventory('{}',cts.Token);
      if(typeof serialized!=='string'||serialized.length>1000000)fail('weekly_native_json_unbounded');
      let bytes=0;for(const ch of serialized){const n=ch.codePointAt(0);bytes+=n<128?1:n<2048?2:n<65536?3:4;}
      if(bytes>1000000)fail('weekly_native_json_unbounded');
      const raw=JSON.parse(serialized);log?.Info('[CULTIVATION_WEEKLY_INVENTORY] {payload}',JSON.stringify(raw));return raw;
    }finally{cts.Dispose();}
  };
}
export async function readWeeklyInventory(api,start,deadline){
  const packet={readOnly:true,targetReached:false,completedUpgrades:0,requestedMaterials:WEEKLY_MATERIALS.map(m=>({...m})),nativeObservation:null,
    inventory:Object.fromEntries(WEEKLY_MATERIALS.map(m=>[m.materialId,{name:m.materialName,count:null,status:'unknown'}])),allVerified:false,
    readStartedAt:new Date(api.now()).toISOString(),readFinishedAt:null};
  try{
    if(api.now()>=deadline)fail('weekly_deadline_expired');
    packet.nativeObservation=await api.readWeeklyConversionInventory(Math.max(1,deadline-api.now()));
    packet.readFinishedAt=new Date(api.now()).toISOString();
    packet.inventory=verifyWeeklyObservation(packet.nativeObservation,Date.parse(packet.readStartedAt),api.now());packet.allVerified=true;
  }catch(error){packet.reason=String(error?.message||error).slice(0,300);}
  packet.readFinishedAt??=new Date(api.now()).toISOString();return packet;
}
