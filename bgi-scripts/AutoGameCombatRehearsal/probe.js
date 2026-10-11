// Copyright 2026 BetterGI Automation Workflow contributors. GPL-3.0-only.
export async function runRehearsal(settings,api) {
  const runId=settings.runId;
  if(typeof runId!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(runId)) throw Error('无效运行编号');
  if(settings.domainName!=='逆悬的冰河'||settings.strategyName!=='木偶星超导') throw Error('未核实的演练场景或策略');
  const minutes=Number(settings.maxMinutes);
  if(!Number.isInteger(minutes)||minutes<1||minutes>5) throw Error('战斗演练上限必须为1–5分钟');
  if(typeof settings.partyName!=='string'||settings.partyName.length>100) throw Error('无效队伍名称');
  const report={schemaVersion:1,runId,mode:'combat-rehearsal',status:'unknown',
    startedAt:new Date(api.now()).toISOString(),finishedAt:null,parameterEvidence:{},
    noRewardClaim:true,rewards:{},targetReached:false,nativeReturnCompleted:false,reason:null};
  const path=`record/${runId}.json`;
  const write=async()=>{const text=JSON.stringify(report,null,2);if(await api.writeText(path,text)!==true||api.readText(path)!==text)throw Error('演练证据写入失败');};
  try {
    const param=new api.AutoDomainParam(1);
    param.DomainName=settings.domainName;param.PartyName=settings.partyName;
    param.CombatStrategyPath=param.SetCombatStrategyPath(settings.strategyName);
    const expected={DomainRoundNum:1,DomainName:settings.domainName,PartyName:settings.partyName,
      CombatOnly:true,RequireZhongliShieldCast:true,SpecifyResinUse:true,
      OriginalResinUseCount:0,OriginalResin20UseCount:0,OriginalResin40UseCount:0,
      CondensedResinUseCount:0,FragileResinUseCount:0,TransientResinUseCount:0,
      AutoArtifactSalvage:false,RewardRecognitionEnabled:false};
    for(const [key,value] of Object.entries(expected))param[key]=value;
    param.ResinPriorityList.Clear();
    for(const [key,value] of Object.entries(expected)) {
      if(param[key]!==value)throw Error(`原生参数${key}未匹配，未启动战斗`);
      report.parameterEvidence[key]=param[key];
    }
    const strategy=param.CombatStrategyPath;
    if(typeof strategy!=='string'||!/[\\/]User[\\/]AutoFight[\\/]木偶星超导\.txt$/.test(strategy))throw Error('未核实的原生策略路径');
    if(param.ResinPriorityList.Count!==0)throw Error('演练树脂优先列表必须为空');
    report.parameterEvidence.CombatStrategyPath=strategy;report.parameterEvidence.ResinPriorityList=[];
    await write(); // Exact parameter checkpoint exists before entering the domain.
    const result=await api.runDomain(param,minutes*60000);
    if(result?.rewardCount!==0)throw Error('演练原生返回未确认空奖励，不能记成功');
    report.nativeReturnCompleted=true;report.status='success';
  } catch(error) {report.reason=String(error?.message||error).slice(0,350);report.status='failed';}
  report.finishedAt=new Date(api.now()).toISOString();
  await write();
  api.emit({task:'战斗演练',runId,status:report.status,evidenceVerified:true,mode:report.mode,
    reportRelativePath:path,noRewardClaim:true,targetReached:false});
  return report; // Runner still requires the separate native challenge/exit event.
}
