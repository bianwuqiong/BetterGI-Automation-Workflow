// Copyright 2026 BetterGI Automation Workflow contributors. GPL-3.0-only.
import { runCultivation } from './core/operator.js';
import { createWeaponGuideBgiApi, readWeaponGuideInventory } from './core/weapon-guide.js';
import { createBackpackInventoryReader } from './core/backpack-reader.js';

const data={rulebook:JSON.parse(file.ReadTextSync('upstream/data/rulebook.json')),
  materials:JSON.parse(file.ReadTextSync('upstream/data/materials.json')),
  recipes:JSON.parse(file.ReadTextSync('upstream/data/crafting-recipes.json')),
  allowedBosses:JSON.parse(file.ReadTextSync('upstream/data/bettergi-boss-catalog.json')).bosses};
const api={
  now:()=>Date.now(),
  getCharacter:(name,categories)=>characterDevelopmentTask.GetCharacter(name,categories),
  async readResinSnapshot() {
    const r=await dispatcher.ReadResinSnapshot();
    const observation={originalResin:r.originalResin,condensedResin:r.condensedResin,
      originalVerified:r.originalVerified===true,condensedVerified:r.condensedVerified===true,
      verified:r.verified===true,observedAt:r.observedAt,mainUiRestored:r.mainUiRestored===true,
      source:r.source,reason:r.reason};
    log.Info('[CULTIVATION_RESIN_OBSERVATION] {payload}',JSON.stringify(observation));
    return observation;
  },
  async countItems(tab,names) {
    const p=new CountInventoryItemParam();
    p.IconRecognitionMode=ItemIconRecognitionMode.Item;
    p.GridScreenName=tab==='Materials'?GridScreenName.Materials:GridScreenName.CharacterDevelopmentItems;
    for (const name of names) p.ItemNames.Add(name);
    return dispatcher.RunCountInventoryItemTask(p);
  },
  readBackpackInventory:createBackpackInventoryReader({dispatcher,log}),
  async readWeaponGuideInventory(request) {
    const reader=createWeaponGuideBgiApi({captureGameRegion,RecognitionObject,sleep,
      characterDevelopmentTask,genshin,moveMouseTo,verticalScroll,keyPress});
    const result=await readWeaponGuideInventory(reader,request);
    log.Info('[CULTIVATION_WEAPON_GUIDE] {payload}',JSON.stringify({
      requested:request.materials.map(m=>m.materialId),reason:result.reason,
      mainUiRestored:result.mainUiRestored,
      observed:Object.fromEntries(Object.entries(result.inventory).map(([id,row])=>[id,{count:row.count,status:row.status}]))}));
    return result;
  },
  AutoDomainParam,
  AutoBossParam,
  async runDomain(param,remainingMilliseconds) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {cts.CancelAfter(Math.max(1,Math.floor(remainingMilliseconds)));return await dispatcher.RunAutoDomainTask(param,cts.Token);}
    finally {cts.Dispose();}
  },
  async runBoss(param,remainingMilliseconds) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {cts.CancelAfter(Math.max(1,Math.floor(remainingMilliseconds)));return await dispatcher.RunAutoBossTask(param,cts.Token);}
    finally {cts.Dispose();}
  },
  async runCrafting(job,remainingMilliseconds) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {
      cts.CancelAfter(Math.max(1,Math.floor(remainingMilliseconds)));
      const r=await dispatcher.RunCultivationCraftTask(job.materialName,job.craftCount,job.craftingCountry,cts.Token);
      return {Success:r.Success===true,MaterialName:r.MaterialName,
        TargetQuantity:r.TargetQuantity,ActualQuantity:r.ActualQuantity,MainUiRestored:r.MainUiRestored===true};
    } finally {cts.Dispose();}
  },
  writeText:(path,content)=>file.CreateDirectory('record') ? file.WriteText(path,content,false) : Promise.resolve(false),
  readText:path=>file.ReadTextSync(path),
  emit:event=>log.Info('[AUTO_GAME_EVENT] {payload}',JSON.stringify(event)),
};
await runCultivation(settings,api,data);
