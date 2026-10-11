// GPL-3.0-only. Two independently evidenced routes in one login; no replay after uncertain progress.
import {parseRouteSettings,runMaterialRoute} from './operator.js';
const zeroBudgets={originalResinBudget:0,condensedResinBudget:0,fragileResinBudget:0,transientResinBudget:0,allowCrafting:false,allowUpgrade:false};
const gameDate=now=>new Date(now+4*3600000).toISOString().slice(0,10);
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
function segmentSettings(payload,row) {
  return {...zeroBudgets,runId:row.runId,sessionId:payload.sessionId,segmentId:row.segmentId,
    gameDate:payload.gameDate,mode:'material-route',routeJson:JSON.stringify(row.route),
    partyName:payload.partyName,strategyName:payload.strategyName,requireZhongliShield:payload.requireZhongliShield,
    expectedTeamJson:JSON.stringify(payload.expectedTeam),timeoutSeconds:row.timeoutSeconds,maxMinutes:row.timeoutSeconds/60};
}
export function parseSessionSettings(settings) {
  const p=JSON.parse(String(settings.sessionJson));
  if(!p||p.schemaVersion!==1||settings.mode!=='material-route-session'||String(settings.runId)!==p.sessionId
     ||String(settings.gameDate)!==p.gameDate||!p.sessionId||p.sessionId.length>77
     ||p.safeHub!=='mondstadt-city'||!Array.isArray(p.segments)||p.segments.length!==2
     ||p.requireZhongliShield!==true)throw new Error('Invalid bounded material session settings');
  const flag=v=>v===true||v==='true'||v==='True';
  for(const key of ['originalResinBudget','condensedResinBudget','fragileResinBudget','transientResinBudget'])
    if(typeof settings[key]==='boolean'||Number(settings[key])!==0)throw new Error('Session resource budgets must be zero');
  if(flag(settings.allowCrafting)||flag(settings.allowUpgrade))throw new Error('Session crafting and upgrading are disabled');
  for(let i=0;i<2;i++) {
    const row=p.segments[i],expectedId=`s${i+1}`;
    if(row.segmentId!==expectedId||row.runId!==`${p.sessionId}-${expectedId}`||row.timeoutSeconds<60)
      throw new Error('Segment scope or bounded timeout differs');
    parseRouteSettings(segmentSettings(p,row));
  }
  const [a,b]=p.segments.map(row=>row.route);
  if(a.relativePath===b.relativePath||a.sha256===b.sha256||a.fightPoints.some(x=>b.fightPoints.some(y=>
    !Number.isFinite(x.x)||!Number.isFinite(x.y)||!Number.isFinite(y.x)||!Number.isFinite(y.y)||Math.hypot(x.x-y.x,x.y-y.y)<=80)))
    throw new Error('Session routes overlap or lack finite fight coordinates');
  return p;
}
export function recoveryCompleted(result,request) {
  if(!result||result.task!=='material-route-recovery'||result.status!=='completed'
     ||result.runId!==request.runId||result.sessionId!==request.sessionId||result.stage!==request.stage
     ||Object.keys(request).some(key=>!same(result.parameterEvidence?.[key],request[key])))return false;
  for(const key of ['loadingObserved','mainUiRestored','grounded','positionVerified','noRevivePrompt',
    'teamVerified','evidenceVerified','scopeRecovered','cleanupCompleted','noResinSpend','noFood','noRevive','noCrafting','noUpgrade'])
    if(result[key]!==true)return false;
  const pos=result.actualPosition;
  return same(result.actualTeam,request.expectedTeam)&&Number.isFinite(result.elapsedMs)&&result.elapsedMs>=0
    &&result.elapsedMs<=request.timeoutSeconds*1000+5000&&Number.isFinite(pos?.x)&&Number.isFinite(pos?.y)
    &&Math.hypot(pos.x+867.7041015625,pos.y-2281.378173828125)<=20;
}
export async function runMaterialRouteSession(settings,api) {
  const payload=parseSessionSettings(settings),started=api.now();
  if(gameDate(started)!==payload.gameDate)throw new Error('Session game-day mismatch');
  const report={schemaVersion:1,runId:payload.sessionId,sessionId:payload.sessionId,gameDate:payload.gameDate,
    mode:'material-route-session',status:'unknown',noResinSpend:true,noCrafting:true,noUpgrade:true,
    targetReached:false,rewards:{},resinEvents:[],startedAt:new Date(started).toISOString(),finishedAt:null,
    wallSeconds:null,recoveries:[],segments:[]};
  const path=`record/${payload.sessionId}.json`;
  async function persist() {
    const text=JSON.stringify(report,null,2);
    if(await api.writeText(path,text)!==true||api.readText(path)!==text)throw new Error('Session checkpoint write/readback failed');
  }
  const boundary=(row,status,extra={})=>api.emit({task:'material-route-segment',sessionId:payload.sessionId,
    runId:row.runId,segmentId:row.segmentId,status,...extra});
  async function recover(runId,stage) {
    const request={runId,sessionId:payload.sessionId,stage,safeHub:payload.safeHub,partyName:payload.partyName,expectedTeam:payload.expectedTeam,timeoutSeconds:60};
    if(api.clearTriggers)api.clearTriggers();
    const result=await api.runRecovery(request);
    if(api.clearTriggers)api.clearTriggers();
    report.recoveries.push(result);await persist();
    return recoveryCompleted(result,request);
  }
  await persist();
  let mayContinue=false,failed=false;
  try {mayContinue=await recover(payload.sessionId,'startup');failed=!mayContinue;}
  catch(error){report.reason=String(error?.message||error).slice(0,400);failed=true;}
  for(const row of payload.segments) {
    if(!mayContinue||gameDate(api.now())!==payload.gameDate) {
      report.segments.push({runId:row.runId,segmentId:row.segmentId,status:'not-started'});
      boundary(row,'not-started',{evidenceVerified:true});await persist();continue;
    }
    boundary(row,'started');
    let segment,recoveryVerified=false;
    try {
      segment=await runMaterialRoute(segmentSettings(payload,row),api);
      recoveryVerified=await recover(row.runId,'after');
    } catch(error) {
      report.reason=String(error?.message||error).slice(0,400);
    }
    const status=segment?.status||'unknown';
    report.segments.push({runId:row.runId,segmentId:row.segmentId,status,
      reportRelativePath:`record/${row.runId}.json`,recoveryVerified});
    boundary(row,'finished',{routeStatus:status,recoveryVerified});await persist();
    mayContinue=status==='success'&&recoveryVerified&&gameDate(api.now())===payload.gameDate;
    failed||=!mayContinue;
  }
  report.status=!failed&&report.segments.every(row=>row.status==='success'&&row.recoveryVerified)?'success':'failed';
  report.finishedAt=new Date(api.now()).toISOString();report.wallSeconds=(api.now()-started)/1000;
  await persist();
  api.emit({task:'material-route-session',runId:payload.sessionId,sessionId:payload.sessionId,gameDate:payload.gameDate,
    reportRelativePath:path,status:report.status,evidenceVerified:true});
  return report;
}
