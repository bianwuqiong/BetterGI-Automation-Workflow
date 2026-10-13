// Copyright 2026 BetterGI Automation Workflow contributors. GPL-3.0-only.
const day=at=>new Date(at+4*3600000).toISOString().slice(0,10);
const integer=(value,low,high)=>Number.isInteger(value)&&value>=low&&value<=high;
const iso=at=>new Date(at).toISOString();
export function parseSettings(settings) {
  if(typeof settings.runId!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(settings.runId))throw Error('invalid artifact runId');
  const config=JSON.parse(settings.configJson),p=config.policy,t=config.target;
  const artifactRewardNames=JSON.parse(settings.artifactRewardNamesJson??'[]');
  if(config.executionEnabled!==true||settings.singleAttemptVerified!==true||p?.domainValidated!==true&&p?.validationOnly!==true||p.requireZhongliShieldCast!==true)throw Error('artifact execution not enabled/validated');
  for(const [key,low,high] of [['maxClaims',1,20],['maxMinutes',1,25],['originalResinBudget',0,200],['condensedResinBudget',0,100],['maxCrafts',0,20],['reserveOriginalResin',0,200]])if(!integer(p[key],low,high))throw Error(`invalid ${key}`);
  for(const key of ['fragileResinBudget','transientResinBudget','primogemBudget'])if(p[key]!==0)throw Error('forbidden resin refill');
  if(p.validationOnly===true&&(p.maxClaims!==1||p.originalResinBudget!==0||p.condensedResinBudget!==0||p.maxCrafts!==0))throw Error('validation needs one round and zero spend');
  if(p.maxCrafts>0&&(p.craftingValidated!==true||!integer(p.craftOriginalResinCost,1,200)||!integer(p.condensedCapacity,1,200)))throw Error('craft cost/capacity not verified');
  if(!['蒙德','璃月'].includes(p.craftingCountry)||typeof p.preferCondensed!=='boolean')throw Error('invalid craft country/preference');
  for(const key of ['characterName','artifactSet','domainName','partyName','strategyName'])if(typeof t?.[key]!=='string'||!t[key].trim()||t[key].length>100)throw Error('invalid artifact target');
  if(/[\\/:]/.test(t.strategyName)||t.strategyName.includes('..'))throw Error('invalid strategy basename');
  if(typeof settings.configSha256!=='string'||!/^[a-f0-9]{64}$/.test(settings.configSha256))throw Error('invalid artifact config identity');
  if(p.validationOnly!==true&&(!Array.isArray(artifactRewardNames)||artifactRewardNames.length===0
      ||artifactRewardNames.length>10000||artifactRewardNames.some(name=>typeof name!=='string'||!name)))throw Error('native artifact class names missing');
  config.artifactRewardNames=artifactRewardNames;
  return config;
}
export function snapshot(raw,now,gameDate,capacity) {
  const at=Date.parse(raw?.observedAt);
  if(!Number.isFinite(at)||now-at<0||now-at>120000||day(at)!==gameDate
    ||raw.mainUiRestored!==true||raw.originalVerified!==true||raw.condensedVerified!==true
    ||!integer(raw.originalResin,0,200)||!integer(raw.condensedResin,0,capacity??200))throw Error('fresh exact resin balances missing');
  return {originalResin:raw.originalResin,condensedResin:raw.condensedResin,
    originalVerified:true,condensedVerified:true,mainUiRestored:true,observedAt:raw.observedAt};
}
export function safeCraftRequest(policy,total,balance) {
  if(policy.preferCondensed!==true||total.condensedResinSpent>=policy.condensedResinBudget
      ||!integer(policy.craftOriginalResinCost,1,200)||!integer(policy.condensedCapacity,1,200))return 0;
  return Math.max(0,Math.min(policy.maxCrafts-total.crafts,policy.condensedCapacity-balance.condensedResin,
    Math.floor((balance.originalResin-policy.reserveOriginalResin)/policy.craftOriginalResinCost),
    Math.floor((policy.originalResinBudget-total.originalResinSpent)/policy.craftOriginalResinCost),5));
}
export function domainParam(Param,target,resin,runId,stepId) {
  const param=new Param(1);
  const evidence={DomainRoundNum:1,DomainName:target.domainName,PartyName:target.partyName,
    SpecifyResinUse:true,CombatOnly:resin==='none',RequireZhongliShieldCast:true,OriginalResinUseCount:0,
    OriginalResin20UseCount:resin==='original'?1:0,OriginalResin40UseCount:0,
    CondensedResinUseCount:resin==='condensed'?1:0,FragileResinUseCount:0,TransientResinUseCount:0,
    AutoArtifactSalvage:false,RewardRecognitionEnabled:resin!=='none'};
  for(const [key,value] of Object.entries(evidence))param[key]=value;
  // GetRange allocates a new .NET list: never Clear the global aliased list.
  param.ResinPriorityList=param.ResinPriorityList.GetRange(0,0);
  if(resin!=='none')param.ResinPriorityList.Add(resin==='original'?'原粹树脂':'浓缩树脂');
  param.CombatStrategyPath=param.SetCombatStrategyPath(target.strategyName);
  if(typeof param.CombatStrategyPath!=='string'||!param.CombatStrategyPath.endsWith(`${target.strategyName}.txt`))throw Error('strategy path not verified');
  for(const [key,value] of Object.entries(evidence))if(param[key]!==value)throw Error(`native parameter ${key} not verified`);
  if(param.ResinPriorityList.Count!==(resin==='none'?0:1))throw Error('native resin list mismatch');
  evidence.ResinPriorityList=resin==='none'?[]:[resin==='original'?'原粹树脂':'浓缩树脂'];
  evidence.CombatStrategyPath=param.CombatStrategyPath;
  // Native optional scope fields are supplied only by the artifact engine overlay.
  if(resin!=='none'){
    param.ArtifactRunId=runId;param.ArtifactStepId=stepId;
    if(param.ArtifactRunId!==runId||param.ArtifactStepId!==stepId)throw Error('native artifact scope fields not verified');
    evidence.ArtifactRunId=runId;evidence.ArtifactStepId=stepId;
  }
  return {param,evidence};
}
export async function runArtifacts(settings,api) {
  const config=parseSettings(settings),p=config.policy,t=config.target;
  const runId=settings.runId,started=api.now(),gameDate=settings.gameDate;
  const authorizationEnd=settings.validUntilUTC==null?Infinity:Date.parse(settings.validUntilUTC);
  if(!(authorizationEnd>=started))throw Error('artifact authorization window expired/invalid');
  if(day(started)!==gameDate)throw Error('artifact authorization day expired');
  const path=`record/${runId}.json`;
  let prior=null;try{prior=api.readText(path);}catch{}
  if(prior)throw Error('artifact checkpoint already exists; unknown must never replay');
  const report={schemaVersion:1,runId,mode:'artifact-farming',gameDate,configSha256:settings.configSha256,
    target:t,policy:p,startedAt:iso(started),finishedAt:null,status:'unknown',targetReached:false,
    mainStatsVerified:false,steps:[],totals:{originalResinSpent:0,condensedResinSpent:0,crafts:0,claims:0},reason:null};
  const write=async()=>{const text=JSON.stringify(report,null,2);if(await api.writeText(path,text)!==true||api.readText(path)!==text)throw Error('artifact durable checkpoint write/readback failed');};
  await write(); // Pre-operation unknown, including before the first read-only snapshot.
  const remaining=()=>Math.min(300000,started+p.maxMinutes*60000-api.now(),authorizationEnd-api.now());
  const guard=()=>{if(day(api.now())!==gameDate)throw Error('artifact game day changed');if(remaining()<=0)throw Error('artifact time budget reached');};
  const read=async()=>{guard();return snapshot(await api.readResinSnapshot(),api.now(),gameDate,p.condensedCapacity);};
  try {
    let balance=await read();report.initialResinObservation=balance;await write();
    if(p.validationOnly===true) {
      report.recipeInspection=await api.runCraft(p.craftingCountry,1,0,200,remaining());
      const recipe=report.recipeInspection;
      if(recipe?.Status!=='skipped'||recipe.MainUiRestored!==true||recipe.OriginalResinSpent!==0
          ||recipe.CondensedResinCreated!==0||recipe.RecipeCostVerified!==true
          ||!integer(recipe.RecipeOriginalResinCost,1,200)||!integer(recipe.SafeCondensedCapacity,1,200)
          ||recipe.CondensedCapacityObserved!==false)throw Error('zero-budget recipe inspection not verified');
      balance=await read();await write();
      const step={stepId:`${runId}:step-1`,type:'validation',status:'unknown',startedAt:iso(api.now()),before:balance};
      const {param,evidence}=domainParam(api.AutoDomainParam,t,'none',runId,step.stepId);
      step.parameterEvidence=evidence;report.steps.push(step);await write();
      step.rewards=await api.runDomain(param,remaining());step.after=await read();step.finishedAt=iso(api.now());
      if(Object.keys(step.rewards??{}).length!==0||step.after.condensedResin!==step.before.condensedResin
          ||![0,1].includes(step.after.originalResin-step.before.originalResin))throw Error('no-claim validation returned rewards or spent resin');
      step.status='success';report.status='success';report.finishedAt=iso(api.now());await write();
      api.emit({task:'圣遗物刷取',runId,mode:report.mode,status:report.status,evidenceVerified:true,reportRelativePath:path,targetReached:false,completedClaims:0});
      return report;
    }
    while(report.totals.claims<p.maxClaims) {
      guard();balance=snapshot(balance,api.now(),gameDate,p.condensedCapacity);
      const total=report.totals;
      const canUseCondensed=total.condensedResinSpent<p.condensedResinBudget;
      const requested=safeCraftRequest(p,total,balance);
      // One native commit, bounded by real balance, policy, capacity and native max5.
      if(requested>0) {
        const budget=requested*p.craftOriginalResinCost;
        const step={stepId:`${runId}:step-${report.steps.length+1}`,type:'craft',status:'unknown',startedAt:iso(api.now()),before:balance,
          requestedCount:requested,craftBudget:budget};
        report.steps.push(step);await write();
        const result=await api.runCraft(p.craftingCountry,requested,budget,p.reserveOriginalResin,remaining());
        step.nativeResult=result;step.after=await read();step.finishedAt=iso(api.now());
        const created=result?.CondensedResinCreated,spent=created*p.craftOriginalResinCost;
        if(result?.Status!=='success'||result.MainUiRestored!==true||!integer(created,1,requested)
          ||result.OriginalResinSpent!==spent
          ||step.after.originalResin-step.before.originalResin!==-spent
          ||step.after.condensedResin-step.before.condensedResin!==created
          ||result.OriginalResinBefore!==step.before.originalResin||result.OriginalResinAfter!==step.after.originalResin
          ||result.CondensedResinBefore!==step.before.condensedResin||result.CondensedResinAfter!==step.after.condensedResin)throw Error('craft result and fresh balances disagree; stop without replay');
        step.actualCreated=created;step.partialQuantity=created<requested;
        total.originalResinSpent+=spent;total.crafts+=created;step.status='success';balance=step.after;await write();continue;
      }
      const resin=canUseCondensed&&balance.condensedResin>0?'condensed':
        total.originalResinSpent+20<=p.originalResinBudget&&balance.originalResin-20>=p.reserveOriginalResin?'original':null;
      if(!resin){report.reason='verified available resin/budget exhausted';break;}
      const step={stepId:`${runId}:step-${report.steps.length+1}`,type:'claim',resin,status:'unknown',startedAt:iso(api.now()),before:balance};
      const {param,evidence}=domainParam(api.AutoDomainParam,t,resin,runId,step.stepId);
      step.parameterEvidence=evidence;report.steps.push(step);await write();
      const rewards=await api.runDomain(param,remaining());step.rewards=rewards;
      step.after=await read();step.finishedAt=iso(api.now());
      const deltaOriginal=step.after.originalResin-step.before.originalResin;
      const deltaCondensed=step.after.condensedResin-step.before.condensedResin;
      const paid=resin==='condensed'?deltaCondensed===-1&&[0,1].includes(deltaOriginal):
        deltaCondensed===0&&[-20,-19].includes(deltaOriginal);
      if(!paid||!rewards||Object.keys(rewards).length===0||Object.entries(rewards).some(([key,value])=>!key||!integer(value,1,999999999)))throw Error('fresh resin spend and actual reward receipt not both verified; stop without replay');
      if(!Object.keys(rewards).some(name=>config.artifactRewardNames.includes(name)))throw Error('actual artifact-class reward missing; Mora alone cannot prove artifacts');
      total[resin==='condensed'?'condensedResinSpent':'originalResinSpent']+=resin==='condensed'?1:20;
      total.claims++;step.status='success';balance=step.after;await write();
    }
    report.status='success';
  } catch(error) {report.status='unknown';report.reason=String(error?.message||error).slice(0,350);}
  report.finishedAt=iso(api.now());await write();
  api.emit({task:'圣遗物刷取',runId,mode:report.mode,status:report.status,evidenceVerified:true,
    reportRelativePath:path,targetReached:false,completedClaims:report.totals.claims});
  return report;
}
