import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildPlan,candidateDomains} from '../core/safe.js';

const load=name=>JSON.parse(readFileSync(new URL(`../upstream/data/${name}.json`,import.meta.url)));
const materials=load('materials'),recipes=load('crafting-recipes');
const policy={allowDomain:true,domainValidated:true,domainSingleAttemptVerified:true,domainPartyName:'fixture-party'};
const books=new Map([['104320',9],['104321',63],['104322',66]]);
const exact=count=>({count,status:'exact'});
// Synthetic stock values exercise independent chains without publishing account inventory.
const bookStock={'104320':exact(110),'104321':exact(130),'104322':exact(32)};

test('synthetic books keep feasible suggestions despite three unknown weapon tiers',()=>{
  const req=new Map([...books,['114009',3],['114010',9],['114011',9],['114012',4]]);
  const inventory={...bookStock,'114009':exact(17),'114010':{status:'unknown',count:null},'114011':{status:'unknown',count:null},'114012':{status:'unknown',count:null}};
  const before=JSON.stringify(inventory),plan=buildPlan(req,inventory,materials,recipes);
  assert.equal(JSON.stringify(inventory),before);
  assert.deepEqual(plan.crafting.suggestions.map(c=>[c.materialId,c.craftCount]),[['104321',33],['104322',33]]);
  assert.deepEqual(new Set(plan.crafting.unknownMaterialIds),new Set(['114010','114011','114012']));
  assert.equal(plan.shortages.find(r=>r.materialId==='104322').shortage,34);
  const chain=plan.crafting.chains.find(c=>c.materialIds.includes('104322'));
  assert.equal(chain.afterCraftingShortages['104322'],1);
  assert.equal(chain.farmShortages['104320'],4);
  assert.equal(plan.crafting.farmShortages['114012'],null);
  assert.equal(plan.crafting.executed,false);
  const domain=candidateDomains(req,inventory,materials,recipes,policy,4).find(t=>t.domainName==='菫色之庭');
  assert.equal(domain.executable,true);assert.equal(domain.farmShortages['104320'],4);
});

test('craftable stock stops farming without claiming required actual stock is satisfied',()=>{
  const stock={...bookStock,'104320':exact(114)};
  const plan=buildPlan(books,stock,materials,recipes);
  const domain=candidateDomains(books,stock,materials,recipes,policy,4)[0];
  assert.equal(domain.needed,false);assert.equal(domain.executable,false);assert.equal(domain.actualRequiredStockSatisfied,false);
  assert.equal(plan.shortages.find(r=>r.materialId==='104322').shortage,34);
  assert.equal(plan.crafting.chains[0].afterCraftingShortages['104322'],0);
  assert.equal(plan.crafting.farmShortages['104320'],0);
  assert.equal(stock['104322'].count,32);
});

test('unknown or lower-bound tier blocks only its own complete-chain task',()=>{
  for(const status of ['unknown','lower_bound']) {
    const stock={...bookStock,'104321':{status,count:129}};
    const plan=buildPlan(books,stock,materials,recipes),task=candidateDomains(books,stock,materials,recipes,policy,4)[0];
    assert.deepEqual(plan.crafting.suggestions,[]);
    assert.equal(plan.crafting.chains[0].afterCraftingShortages['104322'],null);
    assert.equal(task.executable,false);assert.ok(task.blockers.some(b=>b.includes('unknown')));
    assert.ok(Object.values(task.farmShortages).every(n=>n===null));
  }
});

test('closed book day supplies no unrelated farming candidate',()=>{
  const tasks=candidateDomains(books,bookStock,materials,recipes,policy,3);
  assert.equal(tasks.length,1);assert.equal(tasks[0].domainName,'菫色之庭');
  assert.equal(tasks[0].executable,false);assert.ok(tasks[0].blockers.includes('本游戏日不开放'));
});

test('shared lower-tier demand is reserved and suggestions cannot spend it twice',()=>{
  const req=new Map([['104320',9],['104321',63],['104322',66]]);
  const stock={'104320':exact(9),'104321':exact(64),'104322':exact(32)};
  const plan=buildPlan(req,stock,materials,recipes);
  assert.deepEqual(plan.crafting.suggestions,[]);
  assert.equal(plan.crafting.chains[0].afterCraftingShortages['104322'],34);
  assert.equal(plan.crafting.farmShortages['104320'],303);
  assert.deepEqual(stock,{'104320':exact(9),'104321':exact(64),'104322':exact(32)});
});

test('high-tier surplus cannot be converted downwards to meet lower-tier shortages',()=>{
  const stock={'104320':exact(0),'104321':exact(0),'104322':exact(999)};
  const plan=buildPlan(books,stock,materials,recipes);
  assert.deepEqual(plan.crafting.suggestions,[]);
  assert.equal(plan.crafting.farmShortages['104320'],198);
  assert.equal(candidateDomains(books,stock,materials,recipes,policy,4)[0].needed,true);
});

test('non3:1, branching, self-referential and cyclic recipes never authorize farming from a simulation',()=>{
  const badRecipes=[
    {high:{resultCount:2,inputs:[{id:'low',count:3}]}},
    {high:{resultCount:1,inputs:[{id:'low',count:2}]}},
    {high:{resultCount:1,inputs:[{id:'high',count:3}]}},
    {high:{resultCount:1,inputs:[{id:'low',count:3}]},low:{resultCount:1,inputs:[{id:'high',count:3}]}},
    {high:{resultCount:1,inputs:[{id:'low',count:3}]},other:{resultCount:1,inputs:[{id:'low',count:3}]}},
  ];
  const meta=Object.fromEntries(['high','low','other'].map(id=>[id,{name:id,status:'supported',executionType:'domain',domainName:'fixture-domain',openDays:[4],sundaySelectedValue:'1'}]));
  for(const recipe of badRecipes) {
    const req=new Map([['high',3],...(recipe.other?[['other',3]]:[])]),stock={high:exact(0),low:exact(100),other:exact(0)};
    const plan=buildPlan(req,stock,meta,recipe),task=candidateDomains(req,stock,meta,recipe,policy,4)[0];
    assert.deepEqual(plan.crafting.suggestions,[]);assert.equal(task.executable,false);
    assert.ok(task.blockers.some(b=>b.includes('3:1')));
  }
});

test('malformed exact count cannot authorize a related domain',()=>{
  for(const count of [null,-1,NaN,1.5]) {
    const task=candidateDomains(books,{...bookStock,'104320':{status:'exact',count}},materials,recipes,policy,4)[0];
    assert.equal(task.executable,false);assert.ok(task.blockers.some(b=>b.includes('unknown')));
  }
});

test('chain deficits agree with exhaustive legal crafting schedules and reserve every target tier',()=>{
  const req=new Map([['104320',1],['104321',2],['104322',2]]);
  for(let low=0;low<=6;low+=2) for(let mid=0;mid<=4;mid+=2) for(let high=0;high<=3;high++) {
    const stock={'104320':exact(low),'104321':exact(mid),'104322':exact(high)};
    let minimum=null;
    // Independent oracle: enumerate every legal integer craft schedule after
    // adding only low-tier books, preserving all three direct requirements.
    for(let added=0;added<=25 && minimum===null;added++) {
      for(let makeMid=0;makeMid<=10;makeMid++) for(let makeHigh=0;makeHigh<=3;makeHigh++) {
        if(low+added-3*makeMid>=1 && mid+makeMid-3*makeHigh>=2 && high+makeHigh>=2) minimum=added;
      }
    }
    const plan=buildPlan(req,stock,materials,recipes);
    assert.equal(plan.crafting.farmShortages['104320'],minimum,`stock ${low}/${mid}/${high}`);
    const simulated={low,mid,high};
    for(const craft of plan.crafting.suggestions) {
      if(craft.materialId==='104321') {simulated.low-=3*craft.craftCount;simulated.mid+=craft.craftCount;assert.ok(simulated.low>=1);}
      else {simulated.mid-=3*craft.craftCount;simulated.high+=craft.craftCount;assert.ok(simulated.mid>=2);}
    }
    if(minimum===0) assert.ok(simulated.low>=1 && simulated.mid>=2 && simulated.high>=2);
  }
});
