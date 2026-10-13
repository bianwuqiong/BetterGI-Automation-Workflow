import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyBackpackInventory} from '../core/backpack-evidence.js';

const material={materialId:'114010',materialName:'狮牙斗士的铁链'};
const request={materials:[material]};
const rect=(x,y,width,height)=>({x,y,width,height});
const row=(text,r)=>({text,...r});
function snapshot(count=9) {
  const selection={itemRect:rect(110,300,125,150),x:172,y:365,clickedAt:1000};
  const frame=observedAt=>({observedAt,nameRegion:rect(1300,90,500,80),
    selectedItemVerified:true,selectedItemRect:{...selection.itemRect},
    countMethod:'raw_ocr_without_detector',rawCountText:String(count),
    nameRows:[row(material.materialName,rect(1320,110,300,30))],
    countRegion:rect(110,415,125,35),countRows:[row(String(count),rect(160,420,30,25))]});
  return {readOnly:true,source:'backpack_selected_stack',mainUiRestored:true,
    observations:{'114010':{selection,first:frame(1400),second:frame(1600)}}};
}
const verify=s=>verifyBackpackInventory(s,request)['114010'];
test('full material name and selected stack count in two independent captures support exact stock',()=>{
  for(const count of [0,9,12]) {
    const s=snapshot(count);s.inventory={'114010':{count:999,verified:true}};
    assert.equal(verify(s).count,count);assert.equal(verify(s).source,'backpack_selected_stack');
  }
});
test('missing saturated material, forged count, and craftable count never fill actual inventory',()=>{
  for(const mutate of [s=>s.observations={},s=>s.observations['114010'].first.nameRows=[],
    s=>s.observations['114010'].first.countRows[0].text='可合成数量9',
    s=>s.observations['114010'].first.rawCountText='1',
    s=>s.observations['114010'].first.countMethod='structural_digit_repair',
    s=>s.observations['114010'].first.countRows[0].text='9/9']) {
    const s=snapshot();s.inventory={'114010':{count:9,status:'exact',verified:true}};mutate(s);
    assert.equal(verify(s).count,null);assert.equal(verify(s).status,'unknown');
  }
});
test('different material titles, ambiguous titles or quantities, and unstable counts stay unknown',()=>{
  for(const mutate of [p=>p.first.nameRows[0].text='狮牙斗士的镣铐',
    p=>p.first.nameRows[0].text='狮牙斗士的铁链碎片',p=>p.first.nameRows.push(p.first.nameRows[0]),
    p=>p.first.countRows.push(p.first.countRows[0]),p=>p.second.countRows[0].text='10']) {
    const s=snapshot();mutate(s.observations['114010']);assert.equal(verify(s).status,'unknown');
  }
});
test('only the quantity region within the clicked stack can authorize a named inventory count',()=>{
  for(const mutate of [p=>p.selection.x=1000,p=>p.selection.itemRect.width=1,
    p=>p.first.selectedItemVerified=false,p=>p.second.selectedItemRect.x=400,
    p=>p.first.countRegion.x=400,p=>p.first.nameRows[0].x=0,
    p=>p.first.countRows[0].y=300,p=>p.second.countRegion.width=120]) {
    const s=snapshot();mutate(s.observations['114010']);assert.equal(verify(s).status,'unknown');
  }
});
test('stale selection, simultaneous frames, and failed restoration reject exact stock',()=>{
  for(const mutate of [s=>s.mainUiRestored=false,s=>s.readOnly=false,s=>s.source='reward_drop',
    s=>s.observations['114010'].selection.clickedAt=-10000,
    s=>s.observations['114010'].second.observedAt=1400,
    s=>s.observations['114010'].first.observedAt=999]) {
    const s=snapshot();mutate(s);assert.equal(verify(s).status,'unknown');
  }
});
