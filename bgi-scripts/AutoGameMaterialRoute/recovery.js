// GPL-3.0-only. Fixed city recovery only; no inventory, route, attack or farming lease.
import {recoveryCompleted} from './session.js';
const gameDate=now=>new Date(now+4*3600000).toISOString().slice(0,10);
export function parseRecoverySettings(settings) {
  const request=JSON.parse(String(settings.recoveryJson)),runId=String(settings.runId),date=String(settings.gameDate);
  const fields=['runId','sessionId','partyName','expectedTeam','safeHub','stage','timeoutSeconds'];
  if(!request||typeof request!=='object'||Object.keys(request).length!==fields.length||fields.some(k=>!(k in request))
    ||String(settings.mode)!=='material-recovery'||!/^\d{4}-\d{2}-\d{2}$/.test(date)
    ||!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(runId)||request.runId!==runId||request.sessionId!==runId
    ||request.safeHub!=='mondstadt-city'||request.stage!=='startup'||typeof request.partyName!=='string'||!request.partyName.trim()
    ||!Number.isInteger(request.timeoutSeconds)||request.timeoutSeconds<1||request.timeoutSeconds>60
    ||!Array.isArray(request.expectedTeam)||request.expectedTeam.length!==4||new Set(request.expectedTeam).size!==4
    ||!request.expectedTeam.includes('钟离')||request.expectedTeam.some(n=>typeof n!=='string'||!n||n!==n.trim()))
    throw new Error('Invalid zero-resource fixed-hub recovery settings');
  for(const key of ['originalResinBudget','condensedResinBudget','fragileResinBudget','transientResinBudget'])
    if(typeof settings[key]==='boolean'||Number(settings[key])!==0)throw new Error('Recovery resource budgets must be zero');
  for(const key of ['allowCrafting','allowUpgrade'])if([true,'true','True'].includes(settings[key]))
    throw new Error('Recovery crafting and upgrading are disabled');
  return {request,runId,gameDate:date};
}
export async function runMaterialRecovery(settings,api) {
  const input=parseRecoverySettings(settings),started=api.now();
  if(gameDate(started)!==input.gameDate)throw new Error('Recovery game-day mismatch');
  const report={schemaVersion:1,runId:input.runId,sessionId:input.runId,gameDate:input.gameDate,mode:'material-recovery',
    status:'unknown',noResinSpend:true,noFood:true,noRevive:true,noCrafting:true,noUpgrade:true,targetReached:false,
    rewards:{},resinEvents:[],parameterEvidence:input.request,nativeResult:null,startedAt:new Date(started).toISOString(),
    finishedAt:null,wallSeconds:null};
  const path=`record/${input.runId}.json`;
  async function persist() {const text=JSON.stringify(report,null,2);
    if(await api.writeText(path,text)!==true||api.readText(path)!==text)throw new Error('Recovery checkpoint write/readback failed');}
  await persist();
  try {
    if(api.clearTriggers)api.clearTriggers();
    report.nativeResult=await api.runRecovery(input.request);
    if(api.clearTriggers)api.clearTriggers();
    if(gameDate(api.now())!==input.gameDate)throw new Error('Recovery crossed game-day boundary');
    if(recoveryCompleted(report.nativeResult,input.request))report.status='success';
    else if(['failed','cancelled','timeout'].includes(report.nativeResult?.status))report.status=report.nativeResult.status;
  } catch(error){report.reason=String(error?.message||error).slice(0,400);}
  report.finishedAt=new Date(api.now()).toISOString();report.wallSeconds=(api.now()-started)/1000;
  await persist();api.emit({task:'材料安全恢复',runId:input.runId,gameDate:input.gameDate,mode:'material-recovery',
    status:report.status,reportRelativePath:path,evidenceVerified:true});
  return report;
}
