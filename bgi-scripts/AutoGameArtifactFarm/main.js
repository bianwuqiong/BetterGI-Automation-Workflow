// Copyright 2026 BetterGI Automation Workflow contributors. GPL-3.0-only.
import {runArtifacts} from './operator.js';
const withTimeout=async(milliseconds,action)=>{
  const cts=dispatcher.GetLinkedCancellationTokenSource();
  try{cts.CancelAfter(Math.max(1,Math.floor(milliseconds)));return await action(cts.Token);}
  finally{cts.Dispose();}
};
await runArtifacts(settings,{
  now:()=>Date.now(),AutoDomainParam,
  async readResinSnapshot(){
    const r=await dispatcher.ReadResinSnapshot();
    return {originalResin:r.originalResin,condensedResin:r.condensedResin,originalVerified:r.originalVerified===true,
      condensedVerified:r.condensedVerified===true,mainUiRestored:r.mainUiRestored===true,observedAt:r.observedAt};
  },
  async runDomain(param,milliseconds){
    const result=await withTimeout(milliseconds,token=>dispatcher.RunAutoDomainTask(param,token));
    const rewards={};
    if(result)for(const pair of result)rewards[String(pair.Key)]=Number(pair.Value);
    return rewards;
  },
  async runCraft(country,count,budget,reserve,milliseconds){
    const r=await withTimeout(milliseconds,token=>dispatcher.RunCondensedResinCraftTask(country,count,budget,reserve,token));
    return {Status:r.Status,OriginalResinBefore:r.OriginalResinBefore,OriginalResinAfter:r.OriginalResinAfter,
      CondensedResinBefore:r.CondensedResinBefore,CondensedResinAfter:r.CondensedResinAfter,
      CondensedResinCreated:r.CondensedResinCreated,OriginalResinSpent:r.OriginalResinSpent,MainUiRestored:r.MainUiRestored===true,
      RecipeOriginalResinCost:r.RecipeOriginalResinCost,RecipeCostVerified:r.RecipeCostVerified===true,
      SafeCondensedCapacity:r.SafeCondensedCapacity,CondensedCapacityObserved:r.CondensedCapacityObserved===true};
  },
  writeText:(path,text)=>file.CreateDirectory('record')?file.WriteText(path,text,false):Promise.resolve(false),
  readText:path=>file.ReadTextSync(path),
  emit:event=>log.Info('[AUTO_GAME_EVENT] {payload}',JSON.stringify(event))
});
