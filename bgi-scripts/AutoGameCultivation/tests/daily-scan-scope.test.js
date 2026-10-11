import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initialScanIds} from '../core/operator.js';
import {collectCraftingMaterialIds} from '../upstream/core/crafting.js';
const materials=JSON.parse(readFileSync(new URL('../upstream/data/materials.json',import.meta.url)));
const recipes=JSON.parse(readFileSync(new URL('../upstream/data/crafting-recipes.json',import.meta.url)));
const data={materials,recipes};
const requirements=new Map([['114012',4],['104323',9],['113074',1],['202',10000]]);
const policy={dailyMode:true,allowDomain:true,domainSingleAttemptVerified:true,
  domainPartyName:'待命队伍',requireZhongliShieldCast:true};
const saturday=Date.UTC(2026,9,10,0,0);
test('daily initial scan reads the full open weapon chain without closed talent/boss/mora',()=> {
  const ids=initialScanIds({mode:'execute',policy},requirements,data,saturday);
  assert.deepEqual(new Set(ids),new Set(['114009','114010','114011','114012']));
  assert.equal(requirements.get('104323'),9); // The complete cultivation goal remains intact.
});
test('full scan and ordinary execute retain all required recipe inputs',()=> {
  const all=collectCraftingMaterialIds(requirements,recipes);
  assert.deepEqual(initialScanIds({mode:'scan',policy},requirements,data,saturday),all);
  assert.deepEqual(initialScanIds({mode:'execute',policy:{...policy,dailyMode:false}},requirements,data,saturday),all);
});
test('daily scan scope excludes a domain lacking executable policy or Sunday reward selection',()=> {
  for(const change of [{allowDomain:false},{domainSingleAttemptVerified:false},
    {domainPartyName:''},{requireZhongliShieldCast:false}])
    assert.deepEqual(initialScanIds({mode:'execute',policy:{...policy,...change}},requirements,data,saturday),[]);
  const invalidSunday={...data,materials:{...materials,'114012':{...materials['114012'],sundaySelectedValue:''}}};
  assert.deepEqual(initialScanIds({mode:'execute',policy},new Map([['114012',4]]),invalidSunday,Date.UTC(2026,9,11,0,0)),[]);
});
test('game-day rollover keeps the prior domain schedule before UTC+8 04:00',()=> {
  const beforeReset=Date.UTC(2026,9,9,19,59);
  assert.equal(initialScanIds({mode:'execute',policy},new Map([['114012',4]]),data,beforeReset).length,0);
  assert.equal(initialScanIds({mode:'execute',policy},new Map([['114012',4]]),data,beforeReset+60000).length,4);
});
