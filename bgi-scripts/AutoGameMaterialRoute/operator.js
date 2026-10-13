// GPL-3.0-only. One pinned, zero-resin route; no blind replay or inventory inference.
export const MATERIALS={'112044':'破旧的刀镡','112045':'影打刀镡','112046':'名刀镡'};
const ids=Object.keys(MATERIALS),integer=n=>Number.isSafeInteger(n)&&n>=0&&n<=999999999;
const flag=v=>v===true||v==='true'||v==='True';
export function parseRouteSettings(settings) {
  const route=JSON.parse(String(settings.routeJson));
  const input={runId:String(settings.runId),gameDate:String(settings.gameDate),mode:String(settings.mode),route,
    partyName:String(settings.partyName),strategyName:String(settings.strategyName),requireZhongliShield:flag(settings.requireZhongliShield),maxMinutes:Number(settings.maxMinutes)};
  input.timeoutSeconds=settings.timeoutSeconds===undefined?input.maxMinutes*60:Number(settings.timeoutSeconds);
  if(settings.sessionId!==undefined||settings.segmentId!==undefined) {
    input.sessionId=String(settings.sessionId);input.segmentId=String(settings.segmentId);
    if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,76}$/.test(input.sessionId)||!/^s[12]$/.test(input.segmentId)
       ||input.runId!==`${input.sessionId}-${input.segmentId}`)throw new Error('Material segment association differs');
  }
  if(settings.expectedTeamJson!==undefined) {
    input.expectedTeam=JSON.parse(String(settings.expectedTeamJson));
    if(!Array.isArray(input.expectedTeam)||input.expectedTeam.length!==4||new Set(input.expectedTeam).size!==4
      ||input.expectedTeam.some(name=>typeof name!=='string'||!name))throw new Error('Expected full party must contain four distinct slot names');
  }
  if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(input.runId)||!/^\d{4}-\d{2}-\d{2}$/.test(input.gameDate)
     ||input.mode!=='material-route'||input.strategyName!=='木偶星超导'||!input.requireZhongliShield
     ||!input.partyName||!Number.isInteger(input.timeoutSeconds)||input.timeoutSeconds<1||input.timeoutSeconds>480)
    throw new Error('Invalid bounded material route settings');
  if(!route||typeof route!=='object'||!/^auto_game_handguard\/[a-f0-9]{40}\/.+\.json$/.test(route.relativePath)
     ||route.relativePath.includes('..')||route.relativePath.includes('\\')||route.relativePath.includes(':')
     ||!(/^[a-f0-9]{64}$/).test(route.sha256)||!Array.isArray(route.fightPoints)||!route.fightPoints.length)
    throw new Error('Pinned route scope or identity missing');
  for(const key of ['originalResinBudget','condensedResinBudget','fragileResinBudget','transientResinBudget'])
    if(typeof settings[key]==='boolean'||Number(settings[key])!==0)throw new Error('Material route resource budgets must be zero');
  if(flag(settings.allowCrafting)||flag(settings.allowUpgrade))throw new Error('Crafting and upgrading are disabled');
  return input;
}
export function normalizeHandguards(raw) {
  const read=name=>{
    if(raw==null)return undefined;
    if(typeof raw.ContainsKey==='function'&&typeof raw.get_Item==='function')return raw.ContainsKey(name)?raw.get_Item(name):undefined;
    if(raw instanceof Map)return raw.get(name);
    return raw[name];
  };
  return Object.fromEntries(ids.map(id=>{
    const value=read(MATERIALS[id]);
    return [id,{name:MATERIALS[id],count:integer(value)?value:null,status:integer(value)?'exact':'unknown'}];
  }));
}
function gameDate(now) {return new Date(now+4*3600000).toISOString().slice(0,10);}
function exactInventory(value) {return ids.every(id=>value[id]?.status==='exact'&&integer(value[id].count));}
async function readStableInventory(api,phase,input,diagnostics) {
  const observations=[];
  for(let n=0;n<2;n++) {
    if(api.clearTriggers)api.clearTriggers();
    const inventory=normalizeHandguards(await api.countItems(Object.values(MATERIALS)));
    if(api.clearTriggers)api.clearTriggers();
    observations.push({observedAt:new Date(api.now()).toISOString(),inventory});
    if(n===0)await api.sleep(180);
  }
  diagnostics[phase]=observations;
  if(!observations.every(o=>exactInventory(o.inventory))||ids.some(id=>observations[0].inventory[id].count!==observations[1].inventory[id].count))
    return null;
  const inventory=observations[1].inventory;
  api.emit({task:'material-route-inventory',runId:input.runId,gameDate:input.gameDate,phase,status:'exact',
    counts:Object.fromEntries(ids.map(id=>[id,inventory[id].count])),observationCount:2});
  return inventory;
}
export async function runMaterialRoute(settings,api) {
  const input=parseRouteSettings(settings),started=api.now();
  if(gameDate(started)!==input.gameDate)throw new Error('Material route game-day mismatch');
  const request={runId:input.runId,routePath:input.route.relativePath,sha256:input.route.sha256,
    partyName:input.partyName,strategyName:input.strategyName,requireZhongliShield:true,timeoutSeconds:input.timeoutSeconds};
  if(input.expectedTeam)request.expectedTeam=input.expectedTeam;
  const report={schemaVersion:1,...input,status:'unknown',noResinSpend:true,noCrafting:true,noUpgrade:true,
    targetReached:false,rewards:{},resinEvents:[],startedAt:new Date(started).toISOString(),finishedAt:null,
    wallSeconds:null,beforeInventory:null,afterInventory:null,materialGains:{},materialGainsVerified:false,
    nativeReturnCompleted:false,parameterEvidence:request,nativeResult:null,inventoryObservations:{}};
  const path=`record/${input.runId}.json`;
  async function persist() {const text=JSON.stringify(report,null,2);if(await api.writeText(path,text)!==true||api.readText(path)!==text)throw new Error('Material route checkpoint write/readback failed');}
  await persist();
  try {
    report.beforeInventory=await readStableInventory(api,'before',input,report.inventoryObservations);
    if(!report.beforeInventory)throw new Error('Actual pre-route inventory is unknown or unstable');
    if(gameDate(api.now())!==input.gameDate)throw new Error('Route crossed game-day boundary before combat');
    await persist();
    report.nativeResult=await api.runRoute(request);
    if(!report.nativeResult||typeof report.nativeResult!=='object')throw new Error('Native route result missing');
    report.parameterEvidence=report.nativeResult.parameterEvidence;
    if(Object.keys(request).some(key=>Array.isArray(request[key])
      ? !Array.isArray(report.parameterEvidence?.[key])||request[key].length!==report.parameterEvidence[key].length||request[key].some((v,i)=>v!==report.parameterEvidence[key][i])
      : report.parameterEvidence?.[key]!==request[key]))throw new Error('Actual native route parameters differ');
    report.nativeReturnCompleted=report.nativeResult.status==='completed';
    await persist();
    report.afterInventory=await readStableInventory(api,'after',input,report.inventoryObservations);
    if(report.afterInventory) {
      const gains=Object.fromEntries(ids.map(id=>[id,report.afterInventory[id].count-report.beforeInventory[id].count]));
      if(Object.values(gains).every(n=>n>=0)){report.materialGains=gains;report.materialGainsVerified=true;}
    }
    if(gameDate(api.now())!==input.gameDate)throw new Error('Route crossed game-day boundary');
    if(report.nativeReturnCompleted&&report.nativeResult.cleanupCompleted===true&&report.nativeResult.mainUiRestored===true
       &&report.materialGainsVerified)report.status='success';
    else report.status=report.nativeReturnCompleted?'unknown':(['failed','cancelled','timeout'].includes(report.nativeResult.status)?report.nativeResult.status:'unknown');
  } catch(error) {report.reason=String(error?.message||error).slice(0,400);report.status='unknown';}
  report.finishedAt=new Date(api.now()).toISOString();report.wallSeconds=(api.now()-started)/1000;
  await persist();
  api.emit({task:'刀镡路线',runId:input.runId,gameDate:input.gameDate,mode:input.mode,status:report.status,
    reportRelativePath:path,evidenceVerified:true,targetReached:false});
  return report;
}
