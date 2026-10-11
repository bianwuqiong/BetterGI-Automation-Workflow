// GPL-3.0-only. Free fixed-statue healing/revival; no item, route or inventory API.
const flags=['noItemConsumption','noRevivalItemConsumption','noResinSpend','noFood','noCrafting','noUpgrade'];
const gameDate=now=>new Date(now+4*3600000).toISOString().slice(0,10);
const statue={id:'4',country:'蒙德',area:'风起地',x:-1265.917,y:1928.381,arrivalX:-1266.3422,arrivalY:1934.3658};
function equal(a,b) {
  if(typeof a!==typeof b)return false;
  if(a===null||b===null||typeof a!=='object')return a===b;
  return Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>k in b&&equal(a[k],b[k]));
}
export function parsePreparationSettings(settings) {
  const request=JSON.parse(String(settings.preparationJson)),runId=String(settings.runId),date=String(settings.gameDate);
  const fields=['runId','expectedTeam','allowStatueRevival','timeoutSeconds'];
  if(!request||typeof request!=='object'||Object.keys(request).length!==fields.length||fields.some(k=>!(k in request))
    ||String(settings.mode)!=='party-preparation'||!/^\d{4}-\d{2}-\d{2}$/.test(date)
    ||!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(runId)||request.runId!==runId
    ||request.allowStatueRevival!==true||request.timeoutSeconds!==120
    ||!Array.isArray(request.expectedTeam)||request.expectedTeam.length!==4||new Set(request.expectedTeam).size!==4
    ||!request.expectedTeam.includes('钟离')||request.expectedTeam.some(n=>typeof n!=='string'||!n||n!==n.trim()))
    throw new Error('Invalid zero-item fixed-statue preparation settings');
  for(const key of ['originalResinBudget','condensedResinBudget','fragileResinBudget','transientResinBudget'])
    if(typeof settings[key]==='boolean'||![0,'0'].includes(settings[key]))throw new Error('Preparation budgets must be zero');
  for(const key of ['allowCrafting','allowUpgrade'])if(![false,'false','False'].includes(settings[key]))
    throw new Error('Preparation crafting and upgrading are disabled');
  return {request,runId,gameDate:date};
}
export function preparationCompleted(result,request) {
  if(!result||result.task!=='party-preparation'||result.status!=='completed'||result.runId!==request.runId
    ||!equal(result.parameterEvidence,request)||!equal(result.statue,statue)||!equal(result.actualTeam,request.expectedTeam)
    ||result.teamObservationCount!==2||result.activeSlotRestored!==4||'noRevive' in result
    ||result.statueProximityObservationCount!==2||result.statueProximityVerified!==true
    ||('statueApproachPerformed' in result&&typeof result.statueApproachPerformed!=='boolean')
    ||!['evidenceVerified','loadingObserved','positionVerified','mainUiRestored','grounded','noRevivePrompt',
      'teamVerified','cleanupCompleted','revivalMayHaveOccurred',...flags].every(k=>result[k]===true)
    ||!Number.isFinite(result.elapsedMs)||result.elapsedMs<0||result.elapsedMs>125000
    ||!Number.isFinite(result.actualPosition?.x)||!Number.isFinite(result.actualPosition?.y)
    ||Math.hypot(result.actualPosition.x-statue.arrivalX,result.actualPosition.y-statue.arrivalY)>20
    ||Math.hypot(result.actualPosition.x-statue.x,result.actualPosition.y-statue.y)>5
    ||!Array.isArray(result.slotHealthEvidence)||result.slotHealthEvidence.length!==4)return false;
  return result.slotHealthEvidence.every((row,index)=>row?.slot===index+1&&row.name===request.expectedTeam[index]
    &&row.observations===2&&row.identityVerified===true&&row.identityObservations===2&&row.ocrMatchingObservations===2
    &&[row.hp,row.maxHp,row.ratio].every(Number.isFinite)&&row.hp>0&&row.hp<=row.maxHp&&row.hp/row.maxHp>=.8
    &&Math.abs(row.ratio-row.hp/row.maxHp)<=1e-9);
}
export async function runPartyPreparation(settings,api) {
  const input=parsePreparationSettings(settings),started=api.now();
  if(gameDate(started)!==input.gameDate)throw new Error('Preparation game-day mismatch');
  const report={schemaVersion:1,runId:input.runId,gameDate:input.gameDate,mode:'party-preparation',status:'unknown',
    allowStatueRevival:true,...Object.fromEntries(flags.map(k=>[k,true])),targetReached:false,rewards:{},resinEvents:[],
    parameterEvidence:input.request,nativeResult:null,startedAt:new Date(started).toISOString(),finishedAt:null,wallSeconds:null};
  const path=`record/${input.runId}.json`;
  async function persist(){const text=JSON.stringify(report,null,2);
    if(await api.writeText(path,text)!==true||api.readText(path)!==text)throw new Error('Preparation checkpoint write/readback failed');}
  await persist();
  try {
    if(api.clearTriggers)api.clearTriggers();
    report.nativeResult=await api.runPreparation(input.request);
    if(api.clearTriggers)api.clearTriggers();
    if(gameDate(api.now())!==input.gameDate||api.now()-started>300000)throw new Error('Preparation crossed its game-day or five-minute bound');
    if(preparationCompleted(report.nativeResult,input.request))report.status='success';
    else if(['failed','cancelled','timeout'].includes(report.nativeResult?.status))report.status=report.nativeResult.status;
  }catch(error){report.reason=String(error?.message||error).slice(0,400);}
  report.finishedAt=new Date(api.now()).toISOString();report.wallSeconds=(api.now()-started)/1000;
  await persist();api.emit({task:'队伍免费恢复',runId:input.runId,gameDate:input.gameDate,mode:'party-preparation',
    status:report.status,reportRelativePath:path,evidenceVerified:true});
  return report;
}
