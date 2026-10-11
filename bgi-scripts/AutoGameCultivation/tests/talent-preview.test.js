import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {verifyTalentObservation,createTalentPreviewReader} from '../core/talent-preview.js';
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
test('actual-shaped synthetic readonly target replacement verifies next cost not aggregate tooltip requirement',()=>{
  const raw=fixture(),result=verifyTalentObservation(raw,'芭芭拉','元素战技',BASE,BASE+4000);
  assert.equal(result.currentBaseLevel,1);assert.equal(result.nextBaseLevel,2);
  assert.equal(result.materials[0].required,3);assert.equal(raw.evidence.materialTooltips[0][0].quantity.required,99);
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
