import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {verifyTalentObservation,createTalentPreviewReader,verifyTalentQuantity} from '../core/talent-preview.js';
import {runCultivation} from '../core/operator.js';
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/talent-preview-synthetic.json',import.meta.url),'utf8'));
const BASE=1791734400000;
function variant17(){
  const raw=fixture(),previews=[...raw.evidence.rawFrames.filter(f=>'materials' in f),raw.evidence.preview];
  for(const p of previews){
    Object.assign(p,{coinVariant:'real_background_padding_8_reference_53',coinRegion:{x:845,y:791,width:53,height:53},
      initialCoinRegion:{x:853,y:799,width:37,height:37},initialCoinName:'摩拉',initialCoinScore:.52});
    const item=p.materials[0],initial=structuredClone(item.quantity);
    Object.assign(initial,{complete:false,owned:null,required:null,raw:'3213'});
    item.card={x:741,y:602,width:116,height:146};item.iconRegion={x:741,y:602,width:116,height:112};
    Object.assign(item.quantity,{bounds:{x:742,y:710,width:114,height:35},initialReading:initial,
      cropMethod:'source_count_row_pad20x5_intersect_card',sourceCountRow:{text:'32/3',bounds:{x:762,y:715,width:74,height:25}}});
    const initialMora=structuredClone(p.mora);Object.assign(initialMora,{complete:false,owned:null,required:null,raw:'123456112500'});
    Object.assign(p.mora,{bounds:{x:899,y:792,width:283,height:65},initialReading:initialMora,
      cropMethod:'unique_initial_detector_row_pad12',sourceCountRow:structuredClone(initialMora.ocrRows[0])});
  }
  return raw;
}
function entry19(){
  const raw=fixture(),e=raw.evidence;
  function shift(v){if(!v||typeof v!=='object')return;if(Number.isInteger(v.observedAt)&&v.observedAt>=BASE+800)v.observedAt+=1200;for(const item of Object.values(v))shift(item);}
  shift(e);raw.observedAt=new Date(BASE+4200).toISOString();
  const entries=[800,1100,1400].map(at=>{
    const character=structuredClone(e.characterIdentity[0]);character.observedAt=BASE+at;
    const candidates=[{text:'Lv.2',bounds:{x:1600,y:220,width:70,height:25}},{text:'Lv.1',bounds:{x:1600,y:330,width:70,height:25}},{text:'Lv.3',bounds:{x:1600,y:440,width:70,height:25}}];
    return {phase:'talent_entry_observation',observedAt:BASE+at,width:1920,height:1080,focused:true,overview:true,promptVisible:false,reviveVisible:false,
      character,region:{x:1536,y:0,width:384,height:900},rows:structuredClone(candidates),candidates,failureReason:'verified_entries'};
  });
  e.rawFrames.splice(3,0,...entries);e.twoPickedEntryFrames=entries.slice(0,2);e.entryClickFrame=entries[2];return raw;
}
test('actual-shaped synthetic readonly target replacement verifies next cost not aggregate tooltip requirement',()=>{
  const raw=fixture(),result=verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000);
  assert.equal(result.currentBaseLevel,1);assert.equal(result.nextBaseLevel,2);
  assert.equal(result.materials[0].required,3);assert.equal(raw.evidence.materialTooltips[0][0].quantity.required,99);
});
function rolling20(){
  const raw=entry19(),e=raw.evidence,seen=new WeakSet();
  function shift(v){if(!v||typeof v!=='object'||seen.has(v))return;seen.add(v);if(Number.isInteger(v.observedAt))v.observedAt+=600;for(const item of Object.values(v))shift(item);}
  shift(e);
  for(const [i,n] of e.characterIdentity.entries())Object.assign(n,{observedAt:BASE+[400,700,1000][i],phase:'character_identity_observation',nameRegion:{x:1420,y:110,width:360,height:68}});
  const bad=structuredClone(e.characterIdentity[0]);bad.observedAt=BASE+100;bad.name='芭芭拉。';bad.nameRows[0].text='芭芭拉。';
  e.rawFrames.splice(0,3,bad,...e.characterIdentity);
  Object.assign(e,{characterIdentityMethod:'bounded_rolling_exact_triple',characterIdentityObservationLimitMs:12000,characterIdentityPollMs:300,characterIdentityTrials:e.rawFrames.slice(0,4)});
  raw.observedAt=new Date(BASE+4800).toISOString();return raw;
}
test('rolling20 preserves bad original punctuation and accepts only first consecutive exact final triple',()=>{
  const raw=rolling20(),snapshot=structuredClone(raw);
  assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800).currentBaseLevel,1);
  assert.deepEqual(raw,snapshot);assert.equal(raw.evidence.characterIdentityTrials[0].name,'芭芭拉。');
});
function global21(){
  const raw=rolling20(),e=raw.evidence;e.talentEntryIdentitySource='talent_global_header';
  for(const n of e.characterIdentityTrials)Object.assign(n,{nameSource:'attribute_right_full_name',nameBoxMethod:'actual_name_ocr_box'});
  for(const f of e.rawFrames.filter(v=>v.phase==='talent_entry_observation')){
    Object.assign(f.character,{name:'芭芭拉',nameSource:'talent_global_header',nameBoxMethod:'whole_header_ocr_box_contains_name',
      nameRegion:{x:130,y:20,width:320,height:85},nameRows:[{text:'水元素 / 芭芭拉',bounds:{x:150,y:40,width:260,height:35}}],headerRaw:'水元素 / 芭芭拉',headerElement:'水'});
    f.menuRegion={x:40,y:390,width:320,height:100};f.menuRows=[{text:'天赋',bounds:{x:80,y:410,width:100,height:30}}];
  }
  return raw;
}
test('global21 name comes from complete current element/header row and leaves attribute triple unchanged',()=>{
  const raw=global21(),snapshot=structuredClone(raw);
  assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800).currentBaseLevel,1);
  assert.deepEqual(raw,snapshot);assert.equal(raw.evidence.characterIdentity[0].nameRegion.x,1420);
});
function rollingEntry22(){
  const raw=global21(),e=raw.evidence,seen=new WeakSet();
  function shift(v){if(!v||typeof v!=='object'||seen.has(v))return;seen.add(v);if(Number.isInteger(v.observedAt)&&v.observedAt>=BASE+2600)v.observedAt+=1500;for(const child of Object.values(v))shift(child);}
  shift(e);const entries=e.rawFrames.filter(f=>f.phase==='talent_entry_observation');
  entries.forEach((f,i)=>{f.observedAt=BASE+[1400,1740,2080][i];f.readCompletedAt=f.observedAt+40;f.character.observedAt=f.observedAt;});
  const more=[2420,2760,3100].map(at=>{const f=structuredClone(entries[1]);f.observedAt=BASE+at;f.readCompletedAt=f.observedAt+40;f.character.observedAt=f.observedAt;return f;});
  entries[2].rows.at(-1).text='Lv.';entries[2].candidates.pop();entries[2].failureReason='wrong_candidate_count';
  e.rawFrames.splice(7,0,...more);e.twoPickedEntryFrames=more.slice(0,2);e.entryClickFrame=more[2];
  Object.assign(e,{talentEntryObservationMethod:'bounded_contiguous_entry_triple',talentEntryObservationLimitMs:12000,talentEntryObservationPollMs:300});
  raw.observedAt=new Date(BASE+6300).toISOString();return raw;
}
test('entry22 retains bad third raw row and accepts first later contiguous complete triple within original window',()=>{
  const raw=rollingEntry22(),snapshot=structuredClone(raw);
  assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+7300).currentBaseLevel,1);assert.deepEqual(raw,snapshot);
  const entries=raw.evidence.rawFrames.filter(f=>f.phase==='talent_entry_observation');assert.equal(entries.length,6);assert.equal(entries[2].rows.at(-1).text,'Lv.');assert.equal(entries[2].candidates.length,2);
});
test('entry22 rejects old pair selection, extended completion deadline, missing method and continuation after abort or first valid triple',()=>{
  const entries=e=>e.rawFrames.filter(f=>f.phase==='talent_entry_observation');
  for(const mutate of [e=>delete e.talentEntryObservationMethod,e=>e.talentEntryObservationLimitMs=15000,e=>e.talentEntryObservationPollMs=200,
      e=>e.twoPickedEntryFrames=entries(e).slice(0,2),e=>delete e.entryClickFrame.readCompletedAt,
      e=>entries(e)[2].focused=false,e=>entries(e)[2].promptVisible=true,e=>entries(e)[2].reviveVisible=true,
      e=>Object.assign(entries(e)[2],{observedAt:BASE+2000,readCompletedAt:BASE+2100}),e=>e.entryClickFrame.readCompletedAt=BASE+4800,
      e=>entries(e)[2].readCompletedAt=BASE+2079]){
    const raw=rollingEntry22();mutate(raw.evidence);assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+7300));
  }
  const raw=rollingEntry22(),bad=entries(raw.evidence)[2];bad.rows.at(-1).text='Lv.3';bad.candidates=structuredClone(bad.rows);
  assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+7300),/first_legal/);
  const deadline=rollingEntry22(),e=deadline.evidence;
  entries(e).slice(-3).forEach((f,i)=>{f.observedAt=BASE+[12700,13040,13380][i];f.readCompletedAt=f.observedAt+40;f.character.observedAt=f.observedAt;});
  for(const f of e.rawFrames.slice(10))f.observedAt+=12000;
  e.detailIdentityCarryover.observedAt+=12000;
  assert.throws(()=>verifyTalentObservation(deadline,'芭芭拉','元素战技',BASE,BASE+20000),/completion_extends/);
});
test('global21 cannot copy caller name, invent substring box, trim punctuation, downgrade source or swap attribute proof',()=>{
  for(const mutate of [e=>delete e.talentEntryIdentitySource,e=>e.talentEntryIdentitySource='previous_attribute',
      e=>e.entryClickFrame.character.nameSource='attribute_right_full_name',e=>e.entryClickFrame.character.nameBoxMethod='substring_estimated_box',
      e=>e.entryClickFrame.character.headerElement='火',e=>e.entryClickFrame.character.headerRaw='水元素/芭芭拉',
      e=>e.entryClickFrame.character.nameRows[0].text='水元素 / 丽莎',e=>e.entryClickFrame.character.nameRows[0].text='水元素 / 芭芭拉。',
      e=>e.entryClickFrame.character.nameRows[0].bounds.x=131,e=>e.entryClickFrame.character.nameRows[0].bounds.y=21,
      e=>e.entryClickFrame.character.nameRegion.width=380,e=>e.entryClickFrame.character.nameRows.push({text:'Q',bounds:{x:420,y:40,width:20,height:30}}),
      e=>delete e.entryClickFrame.menuRows,e=>e.entryClickFrame.menuRows[0].text='天赋详情',e=>e.entryClickFrame.menuRows[0].bounds.x=41,
      e=>e.entryClickFrame.menuRegion.width=200,e=>e.entryClickFrame.character.observedAt=BASE+100,
      e=>e.characterIdentityTrials[0].nameSource='talent_global_header',e=>e.characterIdentityTrials[0].nameBoxMethod='whole_header_ocr_box_contains_name']){
    const raw=global21();mutate(raw.evidence);assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800));
  }
  for(const text of ['水元素｜芭芭拉','水元素/芭芭拉/额外','合成测试天赋','水元素/芭芭拉。']){
    const raw=global21(),n=raw.evidence.entryClickFrame.character;n.headerRaw=text;n.nameRows[0].text=text;
    assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800));
  }
  const raw=global21(),n=raw.evidence.entryClickFrame.character;n.headerRaw='火元素 / 芭芭拉';n.headerElement='火';n.nameRows[0].text=n.headerRaw;
  assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800),/raw_changed/);
});
test('rolling20 cannot drop failed trials, select old triple, trim punctuation or downgrade method and timing',()=>{
  for(const mutate of [e=>delete e.characterIdentityMethod,e=>e.characterIdentityObservationLimitMs=15000,e=>e.characterIdentityPollMs=200,
      e=>delete e.characterIdentityTrials,e=>e.characterIdentityTrials=e.characterIdentity,e=>e.characterIdentityTrials[0].name='芭芭拉',
      e=>e.characterIdentity[0].nameRows[0].bounds.x=1421,e=>e.characterIdentityTrials[0].observedAt=BASE+200,
      e=>e.characterIdentity=e.characterIdentityTrials.slice(0,3),e=>e.rawFrames.shift(),e=>delete e.characterIdentityTrials[0].phase,
      e=>e.characterSelectionAfterIdentity=true]){
    const raw=rolling20();mutate(raw.evidence);assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800));
  }
  const raw=rolling20();raw.evidence.characterIdentityTrials[0].name='芭芭拉';raw.evidence.characterIdentityTrials[0].nameRows[0].text='芭芭拉';
  assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5800),/first_verified/);
});
test('fixed actual cyan +3 is removed once from the display level without altering popup next cost',()=>{
  const raw=fixture();
  for(const d of [...raw.evidence.rawFrames.filter(f=>'displayLevel' in f),raw.evidence.detailIdentityCarryover]){
    Object.assign(d,{displayLevel:4,glyphColor:'Cyan',neutralPixels:0,cyanPixels:120,bonusRaw:'天赋等级+3',hasFixedPlusThree:true,levelRaw:'等级4'});
    d.levelRows[0].text='等级4';
  }
  assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000).currentBaseLevel,1);
  raw.evidence.detailIdentityCarryover.bonusRaw='天赋等级+2';
  assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000));
});
test('inspection15 full official-name ROI is the only added shape and still requires all four margins',()=>{
  const raw=fixture(),names=[...raw.evidence.characterIdentity,...raw.evidence.rawFrames.filter(f=>'overview' in f)];
  for(const n of names)n.nameRegion={x:1460,y:124,width:264,height:52};
  assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000).currentBaseLevel,1);
  names[0].nameRegion.width=300;assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000));
  const edge=fixture();for(const n of [...edge.evidence.characterIdentity,...edge.evidence.rawFrames.filter(f=>'overview' in f)])n.nameRows[0].bounds.y=131;
  assert.throws(()=>verifyTalentObservation(edge,'芭芭拉','元素战技',BASE,BASE+4000));
});
test('inspection16 observed wide name ROI is whitelisted with the same strict left edge',()=>{
  const raw=fixture(),names=[...raw.evidence.characterIdentity,...raw.evidence.rawFrames.filter(f=>'overview' in f)];
  for(const n of names)n.nameRegion={x:1420,y:110,width:360,height:68};
  assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000).currentBaseLevel,1);
  for(const n of names)n.nameRows[0].bounds.x=1421;
  assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000));
});
test('variant17 fixed53 model and actual padded/clamped rows preserve initial failures',()=>{
  const raw=variant17(),result=verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000);
  assert.equal(result.mora.required,12500);assert.equal(raw.evidence.preview.mora.initialReading.owned,null);
  assert.equal(raw.evidence.preview.mora.initialReading.raw,'123456112500');
  assert.equal(raw.evidence.preview.materials[0].quantity.initialReading.raw,'3213');
});
test('variant17 crop/source-row forgery and high-confidence initial currency conflict cannot choose a higher score',()=>{
  for(const mutate of [p=>Object.assign(p,{initialCoinName:'原石',initialCoinScore:.95}),
      p=>Object.assign(p,{coinScore:.52,initialCoinScore:.99}),p=>p.coinVariant='highest_score_search',
      p=>p.mora.sourceCountRow.bounds.x=900,p=>p.mora.initialReading.ocrRows[0].bounds.x=903,
      p=>p.mora.initialReading.observedAt=BASE,p=>p.mora.bounds.width=275,p=>p.mora.ocrRows[0].bounds.x=899,
      p=>p.materials[0].quantity.bounds.width=116,p=>p.materials[0].quantity.cropMethod='unclamped_pad20',
      p=>delete p.materials[0].quantity.initialReading,p=>delete p.mora.initialReading]){
    const raw=variant17();for(const p of [...raw.evidence.rawFrames.filter(f=>'materials' in f),raw.evidence.preview])mutate(p);
    assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000));
  }
});
test('explicit slash glyph band has exact natural pad6 regions and complete four-edge integer rows',()=>{
  const rect=(x,y,width,height)=>({x,y,width,height}),row=(text,x,y,w,h)=>({text,bounds:rect(x,y,w,h)});
  const q={observedAt:BASE+1400,width:1920,height:1080,bounds:rect(754,710,90,35),complete:true,
    owned:32,required:3,prefix:'',slashPixelVerified:true,raw:'3213',detectorRaw:'3213',ocrRows:[],splitOcrScale:4,
    splitRegionMethod:'slash_vertical_band',splitVerticalPaddingReference:6,slashBounds:rect(794,720,4,10),slashCorrelation:-.9,slashInkPixels:12,
    numeratorRegion:rect(754,714,39,22),denominatorRegion:rect(799,714,45,22),numeratorRaw:'32',denominatorRaw:'3',
    numeratorRows:[row('32',760,717,26,16)],denominatorRows:[row('3',810,717,18,16)]};
  assert.deepEqual(verifyTalentQuantity(q,BASE,BASE+4000),{owned:32,required:3});assert.equal(q.raw,'3213');
  for(const mutate of [r=>r.splitVerticalPaddingReference=4,r=>r.splitRegionMethod='guess',r=>Object.assign(r.numeratorRegion,{y:710,height:35}),
      r=>r.numeratorRows[0].bounds.y=715,r=>r.denominatorRows[0].text='3万',r=>r.slashCorrelation=-.74,
      r=>Object.assign(r,{complete:false,owned:null,required:null})]){
    const bad=structuredClone(q);mutate(bad);assert.throws(()=>verifyTalentQuantity(bad,BASE,BASE+4000));
  }
});
test('explicit picked entry pair and actual third click frame bind the requested talent index',()=>{
  const raw=entry19();assert.equal(verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5200).currentBaseLevel,1);
});
test('new entry methods cannot downgrade, forge raw rows, substitute references, change fullname or incomplete boxes',()=>{
  for(const mutate of [e=>delete e.twoPickedEntryFrames,e=>e.twoPickedEntryFrames=[],e=>e.entryClickFrame.focused=false,
      e=>e.entryClickFrame.promptVisible=true,e=>e.entryClickFrame.character.name='别的角色',e=>e.entryClickFrame.rows[1].text='Lv.2',
      e=>e.entryClickFrame.candidates[1].bounds.x=1537,e=>e.entryClickFrame.candidates[1].bounds.y=340,
      e=>e.entryClickFrame=structuredClone(e.twoPickedEntryFrames[1]),e=>e.entryClickFrame.region.width=400,
      e=>e.characterIdentity=e.characterIdentity.slice(0,2)]){
    const raw=entry19();mutate(raw.evidence);assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5200));
  }
  const raw=entry19();for(const f of [...raw.evidence.twoPickedEntryFrames,raw.evidence.entryClickFrame]){f.rows[1].text='Lv.2';f.candidates[1].text='Lv.2';}
  assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+5200));
});
test('weak Mora, crop truncation, stale frame, partial name, missing raw header and changed target stay unknown',()=>{
  for(const mutate of [r=>r.evidence.preview.coinScore=.52,r=>r.evidence.preview.mora.ocrRows[0].bounds.x=903,
      r=>r.evidence.rawFrames.at(-1).observedAt=r.evidence.rawFrames.at(-2).observedAt,r=>r.evidence.materialTooltips[0][1].nameRows[0].text='自由',
      r=>r.characterName='梦见月瑞希',r=>delete r.evidence.preview.nextLevelRaw,r=>delete r.observedAt]){
    const raw=fixture();mutate(raw);assert.throws(()=>verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000));
  }
});
test('bounded native JSON bridge checks type/name and disposes linked CTS even on invalid JSON',async()=>{
  let calls=0,disposed=0,serialized=JSON.stringify(fixture());
  const dispatcher={GetLinkedCancellationTokenSource:()=>({Token:'linked',CancelAfter:ms=>assert.equal(ms,5000),Dispose:()=>disposed++}),
    InspectTalentUpgrade:async(name,type,token)=>{calls++;assert.equal(name,'芭芭拉');assert.equal(type,'元素战技');assert.equal(token,'linked');return serialized;}};
  const read=createTalentPreviewReader({dispatcher});await read('芭芭拉','元素战技',5000);
  for(const raw of ['bad JSON','x'.repeat(1000001),{}]){serialized=raw;await assert.rejects(()=>read('芭芭拉','元素战技',5000));}
  assert.equal(calls,4);assert.equal(disposed,4);
  await assert.rejects(()=>read('芭芭拉','全部',5000));assert.equal(calls,4);
});
function harness(change={}){
  let now=BASE,calls=0;const files={};
  const settings={runId:'talent-preview-fixture',mode:'scan',talentPreviewOnly:true,talentPreviewType:'元素战技',
    targetConfigJson:JSON.stringify({characterName:'芭芭拉',targetLevel:90,talentTargets:{normal:9,skill:9,burst:9},includeEquippedWeapon:false,weaponTargetLevel:null}),
    policyJson:JSON.stringify({originalResinBudget:0,condensedResinBudget:0,maxMinutes:3}),...change};
  const forbidden=()=>{throw Error('normal scan/upgrade/spend API must not run');};
  const api={now:()=>now,getCharacter:forbidden,countItems:forbidden,readResinSnapshot:forbidden,runCrafting:forbidden,runBoss:forbidden,runDomain:forbidden,
    inspectTalentUpgrade:async(name,type)=>{calls++;assert.equal(name,'芭芭拉');assert.equal(type,'元素战技');now=BASE+4000;return fixture();},
    writeText:async(path,text)=>{files[path]=text;return true;},readText:path=>files[path],emit:()=>{}};
  return {settings,api,files,get calls(){return calls;}};
}
test('single readonly skill preview saves raw evidence with zero upgrades, no normal profile/scan/spenders',async()=>{
  const h=harness(),r=await runCultivation(h.settings,h.api,{});
  assert.equal(r.status,'success');assert.equal(h.calls,1);assert.deepEqual(r.inventory,{});assert.equal(r.profile,null);assert.equal(r.plan,null);
  assert.deepEqual(r.steps,[]);assert.equal(r.targetReached,false);assert.equal(r.talentPreview.completedUpgrades,0);
  assert.ok(JSON.parse(h.files['record/talent-preview-fixture.json']).talentPreview.nativeObservation.evidence.rawFrames.length);
});
test('execute, mixed diagnostic, nonzero budget and invalid type cannot reach readonly preview',async()=>{
  for(const change of [{mode:'execute'},{resourceDiagnosticOnly:true},{resinDiagnosticOnly:true},{talentPreviewType:'全部'},
      {policyJson:JSON.stringify({originalResinBudget:20,condensedResinBudget:0})}]){
    const h=harness(change),r=await runCultivation(h.settings,h.api,{});assert.equal(r.status,'unknown');assert.equal(h.calls,0);
  }
});
test('native success without independent Mora identity remains raw unknown/null',async()=>{
  const h=harness();h.api.inspectTalentUpgrade=async()=>{const r=fixture();r.evidence.preview.coinScore=.52;return r;};
  const r=await runCultivation(h.settings,h.api,{});assert.equal(r.status,'unknown');assert.equal(r.talentPreview.costs,null);
  assert.ok(r.talentPreview.nativeObservation.evidence.rawFrames.length);
});
