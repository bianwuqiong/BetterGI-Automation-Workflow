// Copyright 2026 BetterGI Automation Workflow contributors. GPL-3.0-only.
import {runRehearsal} from './probe.js';
await runRehearsal(settings,{
  now:()=>Date.now(),AutoDomainParam,
  async runDomain(param,timeoutMs) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {cts.CancelAfter(timeoutMs);const result=await dispatcher.RunAutoDomainTask(param,cts.Token);return {rewardCount:result?.Count};}
    finally {cts.Dispose();}
  },
  writeText:(path,text)=>file.CreateDirectory('record')?file.WriteText(path,text,false):Promise.resolve(false),
  readText:path=>file.ReadTextSync(path),
  emit:event=>log.Info('[AUTO_GAME_EVENT] {payload}',JSON.stringify(event))
});
