// GPL-3.0-only. Local runner supplies pinned route data and zero resource budgets.
import {runMaterialRoute} from './operator.js';
import {runMaterialRouteSession} from './session.js';
import {runMaterialRecovery} from './recovery.js';
import {runPartyPreparation} from './preparation.js';
const api={
  now:()=>Date.now(),sleep,clearTriggers:()=>dispatcher.ClearAllTriggers(),
  async countItems(names) {
    const param=new CountInventoryItemParam();param.IconRecognitionMode=ItemIconRecognitionMode.Item;
    param.GridScreenName=GridScreenName.CharacterDevelopmentItems;
    for(const name of names)param.ItemNames.Add(name);
    return dispatcher.RunCountInventoryItemTask(param);
  },
  async runRoute(request) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {cts.CancelAfter(request.timeoutSeconds*1000+5000);return JSON.parse(await pathingScript.RunMaterialRoute(JSON.stringify(request),cts.Token));}
    finally {cts.Dispose();}
  },
  async runRecovery(request) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {cts.CancelAfter(request.timeoutSeconds*1000+5000);return JSON.parse(await pathingScript.RunMaterialRecovery(JSON.stringify(request),cts.Token));}
    finally {cts.Dispose();}
  },
  async runPreparation(request) {
    const cts=dispatcher.GetLinkedCancellationTokenSource();
    try {cts.CancelAfter(request.timeoutSeconds*1000+5000);return JSON.parse(await pathingScript.RunPartyPreparation(JSON.stringify(request),cts.Token));}
    finally {cts.Dispose();}
  },
  writeText:(path,text)=>file.CreateDirectory('record')?file.WriteText(path,text,false):Promise.resolve(false),
  readText:path=>file.ReadTextSync(path),emit:event=>log.Info('[AUTO_GAME_EVENT] {payload}',JSON.stringify(event))
};
const mode=String(settings.mode);
await (mode==='party-preparation'?runPartyPreparation(settings,api):mode==='material-recovery'?runMaterialRecovery(settings,api):mode==='material-route-session'?runMaterialRouteSession(settings,api):runMaterialRoute(settings,api));
