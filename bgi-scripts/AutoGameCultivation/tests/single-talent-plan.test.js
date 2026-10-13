import test from 'node:test';
import assert from 'node:assert/strict';
import {deriveSingleTalentStep} from '../core/single-talent-plan.js';
import {buildNamedInventoryRequest} from '../core/named-inventory.js';
const target={characterName:'梦见月瑞希',talentTargets:{normal:9,skill:9,burst:9}};
const costs=()=>({talentName:'梦浮',currentBaseLevel:8,nextBaseLevel:9,
  materials:[{name:'书',owned:4,required:12},{name:'刀镡',owned:50,required:9}],mora:{owned:100000,required:450000}});
const catalog={'104321':{name:'书'},'112045':{name:'刀镡'},'113060':{name:'额外材料'}};
test('only next operation materials enter the existing zero-budget named reader',()=>{
  const plan=deriveSingleTalentStep(target,'元素战技',costs(),catalog);
  assert.deepEqual(plan.materials.map(m=>m.missing),[8,0]);assert.equal(plan.mora.missing,350000);
  const request=buildNamedInventoryRequest(plan.namedInventoryScope,{runId:'new-run',stepId:'one-next',phase:'before'});
  assert.deepEqual(request.materials.map(m=>m.materialId),['104321','112045']);
  assert.equal(plan.executionEnabled,false);assert.equal(plan.targetReached,false);
  assert.equal(plan.status,'awaiting-upgrade-verification');
});
test('a lower target never proposes an extra upgrade or declares the whole target reached',()=>{
  const plan=deriveSingleTalentStep({...target,talentTargets:{normal:9,skill:8,burst:9}},'元素战技',costs(),catalog);
  assert.equal(plan.status,'selected-talent-at-target');assert.equal(plan.nextBaseLevel,null);
  assert.equal(plan.namedInventoryScope,null);assert.equal(plan.targetReached,false);
});
test('ambiguous material names, missing quantities and costs beyond the next level refuse planning',()=>{
  for(const [change,data] of [[{nextBaseLevel:10},catalog],[{mora:{owned:null,required:1}},catalog],
    [{materials:[{name:'书',owned:null,required:1}]},catalog],[{}, {...catalog,'104322':{name:'书'}}],
    [{materials:[{name:'未知',owned:0,required:1}]},catalog]])
    assert.throws(()=>deriveSingleTalentStep(target,'元素战技',{...costs(),...change},data));
});
