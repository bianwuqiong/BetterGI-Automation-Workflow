import test from 'node:test';
import assert from 'node:assert/strict';
import {parseGuideRatio, verifyWeaponGuideFrames, verifyWeaponGuideSession, readWeaponGuideMaterial, readWeaponGuideInventory, createWeaponGuideBgiApi} from '../core/weapon-guide.js';

const expected = {characterName:'梦见月瑞希', weaponName:'祭礼残章', targetLevel:90,
  materialId:'114010', materialName:'狮牙斗士的铁链', required:9};
const roi = {x:715,y:182,width:492,height:740};
const row = (text,x=730,y=220,width=300,height=28) => ({text,x,y,width,height});
function frame(count=3,time=1000) {
  return {observedAt:time, context:{characterName:'梦见月瑞希',weaponName:'祭礼残章',targetLevel:'升级至90'},
    tooltipRegion:roi, tooltipRows:[row('狮牙斗士的铁链'),row('可合成数量：5',730,700),
      row('培养需求',730,850,100),row(`${count}/9`,1080,850,100)]};
}
function contextFrame(context,time) {return {observedAt:time,contextRows:{characterName:[row(context.characterName)],
  weaponName:[row(context.weaponName),row('Lv.1',730,300)],targetLevel:[row(context.targetLevel)]}};}
const contextEvidence=(a,b)=>({before:[contextFrame(a.context,a.observedAt-500),contextFrame(a.context,a.observedAt-320)],
  after:[contextFrame(b.context,b.observedAt+180),contextFrame(b.context,b.observedAt+360)]});
const verify = (a=frame(), b=frame(3,1180), e=expected, context=contextEvidence(a,b)) => verifyWeaponGuideFrames(a,b,e,context);

test('explicit tooltip inventory accepts owned 3 and keeps craftable 5 separate',()=>{
  assert.equal(verify().count,3); assert.equal(verify().status,'exact');
});
test('explicit zero is accepted only with the same verified tooltip and context',()=>{
  assert.equal(verify(frame(0),frame(0,1180)).count,0);
});
test('combined demand OCR supports full width digits and slash',()=>{
  const a=frame(),b=frame(3,1180);
  for(const f of [a,b]) f.tooltipRows=f.tooltipRows.slice(0,2).concat(row('培养需求：３／９',730,850));
  assert.equal(verify(a,b).count,3);
});
test('missing card or missing explicit demand never becomes zero',()=>{
  const a=frame(),b=frame(3,1180); a.tooltipRows=a.tooltipRows.slice(0,2); b.tooltipRows=b.tooltipRows.slice(0,2);
  assert.equal(verify(a,b).count,null); assert.equal(verify(a,b).status,'unknown');
});
test('craftable count is never an inventory fallback',()=>{
  const a=frame(),b=frame(3,1180); a.tooltipRows[2].text='可合成数量'; b.tooltipRows[2].text='可合成数量';
  assert.equal(verify(a,b).count,null);
});
test('wrong material full name and substring name are rejected',()=>{
  for(const name of ['狮牙斗士的镣铐','狮牙斗士的铁链碎片','']) {
    const a=frame();a.tooltipRows[0].text=name;assert.equal(verify(a).status,'unknown');
  }
});
test('wrong character, weapon, or target context is rejected',()=>{
  for(const [field,value] of [['characterName','钟离'],['weaponName','讨龙英杰谭'],['targetLevel','升级至80']]) {
    const a=frame();a.context[field]=value;assert.equal(verify(a).status,'unknown');
  }
});
test('wrong demand denominator is rejected',()=>{
  const a=frame();a.tooltipRows[3].text='3/4';assert.equal(verify(a).status,'unknown');
});
test('unstable quantities or nonindependent frames are rejected',()=>{
  assert.equal(verify(frame(3),frame(4,1180)).status,'unknown');
  assert.equal(verify(frame(3),frame(3)).status,'unknown');
});
test('ambiguous ratio, ratio on another row, or name below demand row is rejected',()=>{
  const a=frame();a.tooltipRows.push(row('0/9',1000,850,50));assert.equal(verify(a).status,'unknown');
  const b=frame();b.tooltipRows[3].y=810;assert.equal(verify(b).status,'unknown');
  const c=frame();c.tooltipRows[0].y=880;assert.equal(verify(c).status,'unknown');
});
test('short centered popover title is accepted without assuming fixed header height',()=>{
  const a=frame(),b=frame(3,1180);a.tooltipRows[0].y=600;b.tooltipRows[0].y=600;
  assert.equal(verify(a,b).count,3);
});
test('invalid count formats reject approximate, negative, and overflowing quantities',()=>{
  for(const text of ['3.0/9','-1/9','1万/9','9007199254740992/9','3/9可合成5']) assert.equal(parseGuideRatio(text),null);
});
test('popup reader makes two observations without inventing obscured background context',async()=>{
  let calls=0;const frames=[frame(),frame(3,1180)];
  const api={captureOcr:()=>{const f=frames[calls++];return {observedAt:f.observedAt,tooltip:f.tooltipRows,
    characterName:[row(f.context.characterName)],weaponName:[row(f.context.weaponName)],targetLevel:[row(f.context.targetLevel)]};},
    sleep:async ms=>assert.equal(ms,180)};
  const result=await readWeaponGuideMaterial(api,{tooltip:roi});
  assert.equal(result.first.tooltipRows[3].text,'3/9');assert.equal(calls,2);
  assert.equal(result.first.context,undefined);
});
test('native adapter disposes capture and OCR matches even on evidence-save exception',()=>{
  let capturesDisposed=0,matchesDisposed=0;
  const api=createWeaponGuideBgiApi({captureGameRegion:()=>({Width:1920,Height:1080,
    FindMulti:()=>[{Text:'狮牙斗士的铁链',X:730,Y:220,Width:300,Height:28,Dispose:()=>matchesDisposed++}],
    Dispose:()=>capturesDisposed++}),RecognitionObject:{Ocr:()=>({})},sleep:async()=>{},saveEvidence:()=>{throw new Error('save');}});
  assert.throws(()=>api.captureOcr({tooltip:roi}),/save/);assert.equal(capturesDisposed,1);assert.equal(matchesDisposed,1);
});
test('adapter reads and disposes non-Array native iterable collections with no CLR accessor guesses',async()=>{
  let capturesDisposed=0,matchesDisposed=0,clicks=0;
  const nativeRows={Count:1,*[Symbol.iterator](){yield {Text:'武器',X:730,Y:220,Width:300,Height:28,
    Click:()=>clicks++,Dispose:()=>matchesDisposed++};}};
  assert.equal(Array.isArray(nativeRows),false);
  assert.equal(nativeRows.get_Item,undefined);
  const api=createWeaponGuideBgiApi({captureGameRegion:()=>({Width:1920,Height:1080,
    FindMulti:()=>nativeRows,Dispose:()=>capturesDisposed++}),RecognitionObject:{Ocr:()=>({})},sleep:async()=>{}});
  assert.deepEqual(api.captureOcr({tooltip:roi}).tooltip,[{text:'武器',x:730,y:220,width:300,height:28}]);
  await api.clickObservedText('武器',roi);
  assert.equal(clicks,1);assert.equal(matchesDisposed,2);assert.equal(capturesDisposed,2);
});
test('navigation permits observed guide tabs and rejects upgrade actions',async()=>{
  let clicks=0;
  const api=createWeaponGuideBgiApi({captureGameRegion:()=>({FindMulti:()=>[{Text:'武器',Click:()=>clicks++,Dispose(){}}],Dispose(){}}),
    RecognitionObject:{Ocr:()=>({})},sleep:async()=>{}});
  await api.clickObservedText('武器',roi);assert.equal(clicks,1);
  await assert.rejects(()=>api.clickObservedText('升级',roi),/not allowed/);
});

test('old context, missing postcheck, and changed postcheck weapon cannot authorize exact inventory',()=>{
  const a=frame(),b=frame(3,1180),c=contextEvidence(a,b);
  assert.equal(verifyWeaponGuideFrames(a,b,expected).status,'unknown');
  c.after[1].observedAt=130000;assert.equal(verify(a,b,expected,c).status,'unknown');
  const changed=contextEvidence(a,b);changed.after[0].contextRows.weaponName=[row('讨龙英杰谭')];
  assert.equal(verify(a,b,expected,changed).status,'unknown');
});

function fakeNavigator({postWeapon='祭礼残章',missing=false,fragments=false,unstableInitialContext=false}={}) {
  let time=1000,currentName='',scrolled=false,tooltip=false,contextReads=0;const actions=[];
  const names=['狮牙斗士的铁链','狮牙斗士的镣铐','狮牙斗士的理想'],counts=[3,0,0],required=[9,9,4];
  const api={now:()=>time,sleep:async ms=>{time+=ms;},selectCharacter:async name=>actions.push(['selectCharacter',name]),
    waitObservedText:async label=>actions.push(['wait',label]),
    clickObservedText:async label=>actions.push(['text',label]),scrollGuide:async amount=>{actions.push(['scroll',amount]);if(amount<0)scrolled=true;},
    clickObservedRatio:async r=>{currentName=r.name;tooltip=true;actions.push(['ratio',r.text]);},
    closeTooltip:async()=>{tooltip=false;actions.push(['close']);},returnMainUi:async()=>actions.push(['mainUi']),
    captureOcr:regions=>{
      if(regions.tooltip) {
        assert.equal(tooltip,true);const index=names.indexOf(currentName);
        return {observedAt:time,tooltip:[row(currentName),row('可合成数量：2',730,700),
          row(`培养需求${counts[index]}/${required[index]}`,730,850)]};
      }
      if(regions.materialColumn) return {observedAt:time,materialColumn:(missing?[]:(scrolled?[1,2]:[0]))
        .map((i,k)=>({...row(fragments?(i===1?'19':String(counts[i])):`${counts[i]}/${required[i]}`,720,500+k*150,80,28),name:names[i]}))};
      contextReads++;
      if(unstableInitialContext && contextReads===1) return {observedAt:time,characterName:[row('梦见月瑞希')],
        weaponName:[],targetLevel:[row('90')]};
      return {observedAt:time,characterName:[row('梦见月瑞希')],weaponName:[row(contextReads>2?postWeapon:'祭礼残章'),row('Lv.1')],
        targetLevel:[row('升级至90')]};
    }};
  return {api,actions};
}
const materials=[{id:'114010',name:'狮牙斗士的铁链',required:9},{id:'114011',name:'狮牙斗士的镣铐',required:9},
  {id:'114012',name:'狮牙斗士的理想',required:4}];
const request={...expected,materials:materials.map(m=>({materialId:m.id,materialName:m.name,required:m.required}))};
test('automatic navigator selects actual character, reads three named tooltips, and keeps explicit zeros',async()=>{
  const {api,actions}=fakeNavigator();const result=await readWeaponGuideInventory(api,request);
  assert.deepEqual(Object.values(result.inventory).map(item=>item.count),[3,0,0]);
  assert.equal(result.evidence.mainUiRestored,true);
  assert.deepEqual(actions.filter(a=>a[0]==='text').map(a=>a[1]),['提升指南','武器']);
  assert.equal(actions[0][0],'selectCharacter');
});
test('automatic navigator invalidates observations when the weapon context changed',async()=>{
  const {api}=fakeNavigator({postWeapon:'讨龙英杰谭'});
  const result=await readWeaponGuideInventory(api,request);
  assert.ok(Object.values(result.inventory).every(item=>item.status==='unknown'&&item.count===null));
});
test('bounded navigator returns unknown for absent cards and restores main UI',async()=>{
  const {api}=fakeNavigator({missing:true});const result=await readWeaponGuideInventory(api,request,{maxPages:2});
  assert.ok(Object.values(result.inventory).every(item=>item.status==='unknown'&&item.count===null));
  assert.equal(result.evidence.stopReason,'page_limit');assert.equal(result.evidence.mainUiRestored,true);
});
test('session verifier recomputes counts from evidence and rejects forged verified/count fields',async()=>{
  const {api}=fakeNavigator();const result=await readWeaponGuideInventory(api,request);
  result.inventory['114010'].count=999;
  assert.equal(verifyWeaponGuideSession(result,request)['114010'].count,3);
  result.observations['114011'].first.tooltipRows[2].text='可合成数量2';
  assert.equal(verifyWeaponGuideSession(result,request)['114011'].status,'unknown');
});
test('navigation polls transition frames and clicks an observed unique label only once',async()=>{
  let time=1000,captures=0,clicks=0,disposals=0;
  const api=createWeaponGuideBgiApi({now:()=>time,sleep:async ms=>{time+=ms;},RecognitionObject:{Ocr:()=>({})},
    captureGameRegion:()=>({FindMulti:()=>{captures++;return captures<3?[]:[{Text:'武器',X:930,Y:215,Width:100,Height:50,
      Click:()=>clicks++,Dispose:()=>disposals++}];},Dispose(){}})});
  await api.clickObservedText('武器',roi);
  assert.equal(captures,3);assert.equal(clicks,1);assert.equal(disposals,1);
  assert.equal(api.navigation.length,3);assert.equal(api.navigation[0].matchCount,0);
  assert.equal(api.navigation[2].rows[0].text,'武器');assert.equal(api.navigation[2].clicked,true);
});
test('missing or ambiguous navigation label exhausts bounded reads without clicking',async()=>{
  let time=1000,captures=0,clicks=0,disposals=0;
  const api=createWeaponGuideBgiApi({now:()=>time,sleep:async ms=>{time+=ms;},RecognitionObject:{Ocr:()=>({})},
    captureGameRegion:()=>({FindMulti:()=>{captures++;return ['武器','武器'].map(Text=>({Text,
      X:930,Y:215,Width:100,Height:50,Click:()=>clicks++,Dispose:()=>disposals++}));},Dispose(){}})});
  await assert.rejects(()=>api.clickObservedText('武器',roi),/missing or ambiguous/);
  assert.equal(captures,6);assert.equal(clicks,0);assert.equal(disposals,12);assert.ok(time<=5000);
  assert.equal(api.navigation.length,6);assert.equal(api.navigation[5].matchCount,2);
});
test('guide header wait records actual name rows without clicking anything',async()=>{
  let clicks=0;
  const api=createWeaponGuideBgiApi({RecognitionObject:{Ocr:()=>({})},sleep:async()=>{},
    captureGameRegion:()=>({FindMulti:()=>[{Text:'梦见月瑞希',X:765,Y:95,Width:200,Height:50,
      Click:()=>clicks++,Dispose(){}}],Dispose(){}})});
  await api.waitObservedText('梦见月瑞希',roi);
  assert.equal(clicks,0);assert.equal(api.navigation[0].action,'wait');assert.equal(api.navigation[0].found,true);
});
test('count fragments only locate cards; verified inventory still comes from exact named demand tooltip',async()=>{
  const {api}=fakeNavigator({fragments:true});
  const result=await readWeaponGuideInventory(api,request);
  assert.deepEqual(Object.values(result.inventory).map(row=>row.count),[3,0,0]);
  assert.equal(result.observations['114011'].first.tooltipRows[2].text,'培养需求0/9');
});
test('incomplete transition frame is retained in diagnostics while two subsequent full frames authorize context',async()=>{
  const {api}=fakeNavigator({unstableInitialContext:true,fragments:true});
  const result=await readWeaponGuideInventory(api,request);
  assert.deepEqual(Object.values(result.inventory).map(row=>row.count),[3,0,0]);
  const attempts=result.evidence.contextAttempts.filter(attempt=>attempt.phase==='before');
  assert.equal(attempts.length,3);assert.equal(attempts[0].matched,false);
  assert.equal(attempts[0].frame.contextRows.weaponName.length,0);
  assert.equal(result.contextEvidence.before[0].observedAt,attempts[1].frame.observedAt);
});
