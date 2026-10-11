// GPL-3.0-only. Safe orchestration; all BGI operations injected for offline tests.
import { collectCraftingMaterialIds } from '../upstream/core/crafting.js';
import { verifyWeaponGuideSession } from './weapon-guide.js';
import { verifyBackpackInventory } from './backpack-evidence.js';
import { readResourceCoverage } from './resource-coverage.js';
import { readTalentPreview } from './talent-preview.js';
import { readWeeklyInventory } from './weekly-inventory.js';
import {parseInputs,readProfile,makeRequirements,scanGroups,normalizeCounts,buildPlan,candidateDomains,candidateBosses,candidateCrafting,createDomainParam,createBossParam,verifiedGain,verifiedCraft,gameWeekday,normalizeResinSnapshot,observedBudgetBlocker} from './safe.js';

const cloneInventory=inventory=>JSON.parse(JSON.stringify(inventory));
const enabled=value=>value===true||value==='true'||value==='True';
const iso=at=>new Date(at).toISOString();
const gameDay=at=>Math.floor((at+4*3600000)/86400000); // UTC+8 04:00 reset.
const dailyOriginalReadPolicy=policy=>policy.dailyMode && policy.domainResin==='original'
  && !policy.allowBoss && !policy.allowCrafting && !policy.allowRoutes && !policy.allowWeekly;
const readWindowFresh=(read,now)=> {
  const start=Date.parse(read?.readStartedAt),finish=Date.parse(read?.readFinishedAt);
  return Number.isFinite(start) && Number.isFinite(finish) && start<=finish && finish<=now
    && now-start<=120000 && gameDay(start)===gameDay(now);
};
export function sameRunInventoryBefore(report,task,policy,usedAt) {
  if(!dailyOriginalReadPolicy(policy) || task.kind!=='domain') return null;
  const previous=report.steps.at(-1);
  const source=previous ? previous.afterInventoryRead : report.initialInventoryRead;
  const inventory=previous ? previous.after : source?.inventory;
  if(previous && (previous.status!=='success' || previous.type!=='domain' || previous.resin!=='original' || previous.maxClaims!==1
    || previous.stepId!==`${report.runId}:step-${report.steps.length}` || previous.domainName!==task.domainName
    || previous.sundaySelectedValue!==task.sundaySelectedValue
    || Object.keys(inventory??{}).length!==task.scanIds.length)) return null;
  const read={source:previous?'previous-step-after':'initial-current-run',runId:report.runId,
    ...(previous?{previousStepId:previous.stepId}:{}),readStartedAt:source?.startedAt,
    readFinishedAt:source?.finishedAt,usedAt:iso(usedAt)};
  if(source?.runId!==report.runId || !Number.isFinite(Date.parse(report.startedAt))
    || gameDay(Date.parse(report.startedAt))!==gameDay(usedAt) || Date.parse(source.startedAt)<Date.parse(report.startedAt)
    || !readWindowFresh(read,usedAt) || !task.scanIds.every(id=>inventory?.[id]?.status==='exact'
      && Number.isInteger(inventory[id].count) && inventory[id].count>=0 && inventory[id].count<=999999999)) return null;
  return {inventory:cloneInventory(Object.fromEntries(task.scanIds.map(id=>[id,inventory[id]]))),read};
}

export async function runCultivation(settings,api,data) {
  const input=parseInputs(settings);
  const started=api.now();
  const report={schemaVersion:1,runId:input.runId,mode:input.mode,target:input.target,
    startedAt:new Date(started).toISOString(),profile:null,inventory:{},plan:null,blockers:[],warnings:[],steps:[],
    requiredScanIds:[],manualInventoryIds:[],inventoryReadDiagnostics:[],
    status:'unknown',readOnly:input.mode==='scan',targetReached:false,
    metadata:{calculationScope:'角色/武器突破和天赋；不包括角色/武器等级升级经验与摩拉',
      sourceCommit:'3f1e938a6dcd5a34642dad03a91488db8d2da40c',inventoryZeroRequiresExplicitRecognition:true,
      capabilities:{profile:true,inventory:true,domain:'需要显式预算和本机验收/有界初验',boss:'需要显式预算和本机验收/有界初验；默认关闭',routes:'disabled:未安装/验收',weekly:'disabled:尚无安全适配',leyLine:'manual:未接入',upgrade:'manual:不自动升级',crafting:'需要显式允许和本机验收；计划仍仅是建议'}},
    policy:input.policy};
  let requirements=null;
  // A reader-stage crash is still an unknown result with no attempted resource
  // steps. Persist and verify this initial record before any game API is called.
  const entryCheckpointPath=`record/${input.runId}.json`;
  const entryCheckpoint=JSON.stringify(report,null,2);
  if(await api.writeText(entryCheckpointPath,entryCheckpoint)!==true || api.readText(entryCheckpointPath)!==entryCheckpoint)
    throw new Error('初始unknown记录写入失败，未调用角色/库存/树脂或资源接口');
  try {
    if([settings.weeklyInventoryOnly,settings.talentPreviewOnly,settings.resourceDiagnosticOnly,settings.resinDiagnosticOnly].filter(enabled).length>1)throw Error('只读诊断模式互斥，未调用游戏接口');
    if(enabled(settings.weeklyInventoryOnly)) {
      if(input.mode!=='scan'||input.policy.originalResinBudget!==0||input.policy.condensedResinBudget!==0||input.policy.maxMinutes>3
          ||['allowDomain','allowBoss','allowCrafting','allowRoutes','allowWeekly'].some(key=>input.policy[key]))throw Error('周本四库存仅允许独立scan、零预算、最多3分钟、禁止所有执行');
      report.metadata.diagnostic='weekly-conversion-inventory-only';
      report.metadata.calculationScope='只读三种周本材料与异梦溶媒具名库存；不计算转换配方、费用或执行升级';
      report.weeklyInventory=await readWeeklyInventory(api,started,started+input.policy.maxMinutes*60000);
      report.status=report.weeklyInventory.allVerified?'success':'unknown';
      report.blockers.push({code:'weekly_inventory_only',message:'只读取四项真实库存；不执行转换或消费，不宣称培养完成'});
    } else if(enabled(settings.talentPreviewOnly)) {
      if(input.mode!=='scan'||input.policy.originalResinBudget!==0||input.policy.condensedResinBudget!==0
          ||['allowDomain','allowBoss','allowCrafting','allowRoutes','allowWeekly'].some(key=>input.policy[key]))throw Error('天赋预览仅允许scan、零预算、禁止所有执行');
      report.metadata.diagnostic='talent-upgrade-preview-only';
      report.metadata.calculationScope='当前目标单项天赋的下一基础等级所需材料与摩拉，只读预览';
      report.talentPreview=await readTalentPreview(api,input.target.characterName,settings.talentPreviewType||'元素战技',started,started+input.policy.maxMinutes*60000);
      report.status=report.talentPreview.evidenceVerified?'success':'unknown';
      report.blockers.push({code:'talent_preview_only',message:'只核验下一等级预览，不确认升级、消费资源或宣称培养目标完成'});
    } else if(settings.resourceDiagnosticOnly===true || settings.resourceDiagnosticOnly==='true' || settings.resourceDiagnosticOnly==='True') {
      if(input.mode!=='scan'||settings.resinDiagnosticOnly===true||settings.resinDiagnosticOnly==='true'
          ||settings.resinDiagnosticOnly==='True'||input.policy.originalResinBudget!==0||input.policy.condensedResinBudget!==0
          ||input.policy.allowDomain||input.policy.allowBoss||input.policy.allowCrafting)throw Error('资源覆盖诊断仅允许单独scan、零预算、禁用所有资源执行');
      report.metadata.diagnostic='resource-coverage-only';
      report.resourceCoverage=await readResourceCoverage(api,started,started+input.policy.maxMinutes*60000);
      report.status=report.resourceCoverage.allVerified?'success':'unknown';
      report.blockers.push({code:'resource_coverage_only',message:'只核验摩拉与三种武器矿，不表示角色材料扫描、完整升级成本或实际升级完成'});
    } else if(settings.resinDiagnosticOnly===true || settings.resinDiagnosticOnly==='true' || settings.resinDiagnosticOnly==='True') {
      if(input.mode!=='scan') throw new Error('树脂只读探针不能以执行模式运行');
      report.metadata.diagnostic='resin-only';
      report.resinObservation=await api.readResinSnapshot();
      report.blockers.push({code:'diagnostic_only',message:'仅检查只读树脂接口，不代表角色材料扫描完成'});
    } else {
    const raw=await api.getCharacter(input.target.characterName,input.target.includeEquippedWeapon?'属性;武器;天赋':'属性;天赋');
    report.profile=readProfile(raw,input.target,data.rulebook);
    requirements=makeRequirements(report.profile,input.target,data.rulebook);
    const allIds=collectCraftingMaterialIds(requirements,data.recipes);
    const ids=initialScanIds(input,requirements,data,api.now(),allIds);
    if(ids.length!==allIds.length) report.metadata.deferredScanIds=allIds.filter(id=>!ids.includes(id));
    const initialReadStartedAt=api.now();
    report.inventory=await scan(ids,api,data.materials,guideContext(report,requirements));
    const initialReadFinishedAt=api.now();
    if(input.mode==='execute' && dailyOriginalReadPolicy(input.policy)) report.initialInventoryRead={runId:input.runId,
      startedAt:iso(initialReadStartedAt),finishedAt:iso(initialReadFinishedAt),inventory:cloneInventory(report.inventory)};
    addExcludedInventory(report,ids,data.materials);
    report.plan=buildPlan(requirements,report.inventory,data.materials,data.recipes);
    const requiredScanIds=scanGroups(ids,data.materials).flatMap(([,items])=>items.map(i=>i.id));
    report.requiredScanIds=requiredScanIds;
    report.manualInventoryIds=ids.filter(id=>data.materials[id]?.status==='excluded');
    const missing=requiredScanIds.filter(id=>report.inventory[id]?.status!=='exact');
    const undefinedRules=ids.filter(id=>!data.materials[id]);
    if (missing.length) report.blockers.push({code:'inventory_unknown',materialIds:missing,message:'扫描缺失或OCR不可靠，未当作0；执行相关类别前必须补充核实'});
    if (undefinedRules.length) report.blockers.push({code:'material_rule_missing',materialIds:undefinedRules,message:'材料静态规则缺失'});
    report.warnings.push({code:'manual_level_resources',message:report.metadata.calculationScope},
      {code:'no_upgrade',message:'缺口满足仅说明材料准备情况，不代表角色/武器已升级'},
      {code:'crafting_not_executed',message:'3:1建议未执行，也没有更改任何实际库存'});
    report.plan.domains=candidateDomains(requirements,report.inventory,data.materials,data.recipes,input.policy,gameWeekday(api.now()));
    report.plan.bosses=candidateBosses(requirements,report.inventory,data.materials,input.policy,data.allowedBosses);
    if (input.mode==='scan') {
      report.status=missing.length || undefinedRules.length?'unknown':'success';
      if(typeof api.readResinSnapshot==='function') {
        report.metadata.diagnostic='inventory-and-resin';
        report.resinObservation=normalizeResinSnapshot(await api.readResinSnapshot(),api.now());
        if(!report.resinObservation || !report.resinObservation.verified) {
          report.status='unknown';
          report.blockers.push({code:'resin_observation_unknown',message:'只读材料／余额联合检查未核实新鲜树脂或主界面恢复'});
        }
      }
    }
    else await execute(report,requirements,input,api,data,started);
    }
  } catch (error) {
    report.status='unknown';
    report.blockers.push({code:'read_or_execution_failed',message:String(error?.message || error).slice(0,300)});
  }
  report.finishedAt=new Date(api.now()).toISOString();
  const path=`record/${input.runId}.json`;
  // LimitedFile.WriteText returns false on failure; also verify the exact serialized result.
  const serialized=JSON.stringify(report,null,2);
  const wrote=await api.writeText(path,serialized);
  if (wrote!==true || api.readText(path)!==serialized) throw new Error('培养报告写入/回读失败；不得发出成功事件');
  const event={task:'培养材料',runId:input.runId,status:report.status,evidenceVerified:true,mode:input.mode,
    readOnly:input.mode==='scan',reportRelativePath:path,completedSteps:report.steps.filter(s=>s.status==='success').length,
    targetReached:false};
  api.emit(event);
  return report;
}
// Daily execution needs today's supported domain families, including every recipe
// input. A full read-only scan still measures all cultivation requirements.
export function initialScanIds(input,requirements,data,now,allIds=collectCraftingMaterialIds(requirements,data.recipes)) {
  const {policy}=input;
  if(input.mode!=='execute' || !policy.dailyMode) return allIds;
  if(!policy.allowDomain || !policy.domainSingleAttemptVerified || !policy.domainPartyName
    || !policy.requireZhongliShieldCast) return [];
  const weekday=gameWeekday(now);
  const eligible=new Map([...requirements].filter(([id,required])=> {
    const material=data.materials[id];
    return required>0 && material?.executionType==='domain' && material.domainName
      && material.openDays?.includes(weekday)
      && (weekday!==0 || /^[1-9]\d*$/.test(material.sundaySelectedValue||''));
  }));
  return collectCraftingMaterialIds(eligible,data.recipes);
}
function guideContext(report,requirements) {
  return report.profile?.weapon ? {characterName:report.profile.characterName,
    weaponName:report.profile.weapon.name,targetLevel:report.target.weaponTargetLevel,
    requirements,diagnostics:report.inventoryReadDiagnostics,
    // Same-run material identities only: every scan still reads new raw frames.
    backpackFirstIds:Object.entries(report.inventory).filter(([,row])=>row.source==='backpack_selected_stack'
      && row.verified===true && row.status==='exact' && row.count>0).map(([id])=>id),
    guideFirstIds:Object.entries(report.inventory).filter(([,row])=>row.source==='character_weapon_guide_tooltip'
      && row.verified===true && row.status==='exact').map(([id])=>id),
    readNamedStacks:report.mode==='scan' && report.policy.dailyMode===true} : null;
}
async function scan(ids,api,materials,context=null) {
  const result={};
  const backpackAttempts=new Map(),backpackRetryBlocked=new Set(),backpackAlternateGuideRead=new Set();
  async function readGuide(guideIds,routing) {
    if(!guideIds.length || !context || typeof api.readWeaponGuideInventory!=='function') return;
    const request={characterName:context.characterName,weaponName:context.weaponName,
      targetLevel:context.targetLevel,materials:guideIds.map(id=>({materialId:id,
        materialName:materials[id].name,required:context.requirements.get(id)}))};
    try {
      const observed=await api.readWeaponGuideInventory(request);
      if(observed?.mainUiRestored!==true) throw new Error('weapon_guide_main_ui_not_restored');
      const verified=verifyWeaponGuideSession(observed,request);
      for(const id of guideIds) if(verified[id]?.status==='exact') result[id]=verified[id];
      context.diagnostics.push({source:'character_weapon_guide_tooltip',requested:guideIds,routing,
        mainUiRestored:true,reason:observed.reason,evidence:observed.evidence});
    } catch(error) {
      context.diagnostics.push({source:'character_weapon_guide_tooltip',requested:guideIds,routing,
        reason:String(error?.message||error).slice(0,300)});
      if(error?.message==='weapon_guide_main_ui_not_restored') throw error;
    }
  }
  async function readBackpack(backpackIds,routing) {
    if(!backpackIds.length || typeof api.readBackpackInventory!=='function') return;
    let pending=backpackIds.filter(id=>(backpackAttempts.get(id)||0)<2 && !backpackRetryBlocked.has(id));
    while(pending.length) {
      const request={materials:pending.map(id=>({materialId:id,materialName:materials[id].name}))};
      for(const id of pending) backpackAttempts.set(id,(backpackAttempts.get(id)||0)+1);
      try {
        const observed=await api.readBackpackInventory(request);
        if(observed?.mainUiRestored!==true) throw new Error('backpack_main_ui_not_restored');
        const verified=verifyBackpackInventory(observed,request);
        for(const id of pending) if(verified[id]?.status==='exact') result[id]=verified[id];
        context.diagnostics.push({source:'backpack_selected_stack',requested:pending,routing,
          attempts:Object.fromEntries(pending.map(id=>[id,backpackAttempts.get(id)])),
          mainUiRestored:true,reason:observed.reason,evidence:observed});
        if(observed.source!=='backpack_selected_stack' || observed.readOnly!==true) {
          pending.forEach(id=>backpackRetryBlocked.add(id));break;
        }
        pending=pending.filter(id=>verified[id]?.status!=='exact' && backpackAttempts.get(id)<2);
      } catch(error) {
        pending.forEach(id=>backpackRetryBlocked.add(id));
        context.diagnostics.push({source:'backpack_selected_stack',requested:pending,routing,
          reason:String(error?.message||error).slice(0,300)});
        if(error?.message==='backpack_main_ui_not_restored') throw error;
        break; // No verified restoration state after an exception: do not retry in another route.
      }
    }
    // The scan diagnostic may use the independently verified guide after two clean
    // native misses. Hidden cards remain unknown; exceptions never open another UI.
    const alternate=context?.readNamedStacks ? backpackIds.filter(id=>backpackAttempts.get(id)===2
      && !backpackRetryBlocked.has(id) && !backpackAlternateGuideRead.has(id)
      && result[id]?.status==='unknown' && (context.requirements.get(id)??0)>0) : [];
    alternate.forEach(id=>backpackAlternateGuideRead.add(id));
    await readGuide(alternate,'native_pair_missing_named_guide_fallback');
  }
  // Identities are a routing hint only. Read new selected-name/count frames first,
  // before opening the generic icon grid that already failed for these stacks.
  const hintedBackpack=ids.filter(id=>/^114\d+$/.test(id) && materials[id]?.name
    && (context?.requirements.get(id)??0)>0 && context?.backpackFirstIds?.includes(id));
  for(const id of hintedBackpack) result[id]={name:materials[id].name,count:null,status:'unknown',
    reason:'backpack_named_stack_evidence_missing'};
  await readBackpack(hintedBackpack,'same_run_hint_first');
  // An exception/invalid native state cannot trigger another UI or downgrade the
  // previously required named-stack proof to a generic icon observation.
  if(hintedBackpack.some(id=>backpackRetryBlocked.has(id))) return result;
  await readGuide(ids.filter(id=>/^114\d+$/.test(id) && materials[id]?.name
    && (context?.requirements.get(id)??0)>0 && context?.guideFirstIds?.includes(id)), 'same_run_guide_hint_first');
  // Exclude only this call's freshly verified named rows, never old count fields.
  const genericIds=ids.filter(id=>result[id]?.status!=='exact');
  for (const [tab,items] of scanGroups(genericIds,materials)) {
    try {
      const observed=normalizeCounts(items,await api.countItems(tab,items.map(i=>i.name)));
      for(const id of hintedBackpack) if(result[id]?.status!=='exact') delete observed[id];
      Object.assign(result,observed);
    } catch {
      const observed=normalizeCounts(items,null);
      for(const id of hintedBackpack) delete observed[id];
      Object.assign(result,observed);
    }
  }
  const missing=ids.filter(id=>/^114\d+$/.test(id) && result[id]?.status==='unknown'
    && materials[id]?.name && (context?.requirements.get(id)??0)>0);
  const guideMissing=missing.filter(id=>result[id]?.status==='unknown');
  await readGuide(guideMissing,'missing_after_generic');
  // A satisfied material disappears from the guide's shortage cards. Read the actual
  // named backpack stack instead of deriving its stock from the target or rewards.
  const hidden=missing.filter(id=>result[id]?.status==='unknown');
  const named=context?.readNamedStacks ? ids.filter(id=>/^114\d+$/.test(id)
    && result[id]?.status==='exact' && result[id].count>0
    && !['character_weapon_guide_tooltip','backpack_selected_stack'].includes(result[id].source)) : [];
  const backpackIds=[...new Set([...hidden,...named])];
  // This diagnostic explicitly requires named stacks. A generic icon count
  // cannot make its result successful if the selected-name check is unavailable.
  for(const id of named) result[id]={name:materials[id].name,count:null,status:'unknown',
    reason:'backpack_named_stack_evidence_missing'};
  await readBackpack(backpackIds,'missing_or_named_fallback');
  return result;
}
function addExcludedInventory(report,ids,materials) {
  for (const id of ids) if (materials[id]?.status==='excluded') report.inventory[id]={name:materials[id].name,count:null,status:'unknown',reason:'manual:此资源不在可靠网格读取范围'};
}
async function execute(report,requirements,input,api,data,started) {
  const {policy}=input;
  const gameDayChanged=()=>policy.dailyMode && gameDay(api.now())!==gameDay(started);
  const gameDayBlocker=()=>report.blockers.push({code:'game_day_changed',message:'UTC+8 04:00游戏日已改变，停止新步骤；旧日授权不能跨日使用'});
  const insufficientTime=()=> {
    const remaining=policy.maxMinutes*60000-(api.now()-started);
    return remaining<=0 || (policy.dailyMode && remaining<240000);
  };
  const spent={original:0,condensed:0};
  const actualSpent={original:0,condensed:0};let actualComplete=true;
  const attemptedSources=new Set(policy.validationMode?policy.validationAttemptedSources:[]);
  const attemptKey=task=>policy.validationMode?task.kind:sourceKey(task);
  const uncertainSteps=[];
  if (policy.allowRoutes) report.blockers.push({code:'routes_disabled',message:'材料路线尚未安装并实机验收，保持不可执行'});
  if (policy.allowWeekly) report.blockers.push({code:'weekly_disabled',message:'周本无安全领奖与每周状态适配，保持不可执行'});
  if (report.blockers.some(b=>b.code==='material_rule_missing')) {report.status='unknown';return;}
  for (let index=0;index<policy.maxSteps;index++) {
    if(gameDayChanged()) {gameDayBlocker();break;}
    if (insufficientTime()) {report.blockers.push({code:'time_limit',message:'剩余时间不足以完成新步骤及库存／余额收尾，未开始下一步'});break;}
    const candidates=allCandidates(requirements,report.inventory,data,policy,api.now());
    report.plan.domains=candidates.filter(t=>t.kind==='domain');
    report.plan.bosses=candidates.filter(t=>t.kind==='boss');
    const executable=candidates.filter(t=>t.executable && (!policy.validationMode || !attemptedSources.has(attemptKey(t))));
    if(!executable.length) break;
    let resinBefore=executable.some(t=>t.kind!=='crafting')?await readResin(api,started+policy.maxMinutes*60000):null;
    const affordable=t=>t.kind==='crafting'?null:observedBudgetBlocker(policy,spent,api.now(),t.kind,resinBefore);
    const task=executable.find(t=>!affordable(t));
    if(!task) {report.blockers.push({code:'budget_blocked',message:executable.map(affordable).filter((v,i,a)=>a.indexOf(v)===i).join('；')});break;}
    const freshBefore=async()=> {
      const readStartedAt=api.now();
      const inventory=await scan(task.scanIds,api,data.materials,guideContext(report,requirements));
      const readFinishedAt=api.now();
      return {inventory:cloneInventory(inventory),read:{source:'fresh-current-run',runId:input.runId,
        readStartedAt:iso(readStartedAt),readFinishedAt:iso(readFinishedAt),usedAt:iso(readFinishedAt)}};
    };
    let beforePacket=sameRunInventoryBefore(report,task,policy,api.now()) ?? await freshBefore();
    let before=beforePacket.inventory;
    let checked=allCandidates(requirements,{...report.inventory,...before},data,policy,api.now()).find(t=>sourceKey(t)===sourceKey(task));
    if (!checked?.executable) {report.blockers.push({code:'pre_reward_unknown',materialIds:task.scanIds,message:'领奖前复核不完整或已达标，停止本次执行'});Object.assign(report.inventory,before);break;}
    if (insufficientTime()) {report.blockers.push({code:'time_limit',message:'复核后剩余时间不足以完成新步骤及收尾'});break;}
    // Inventory scans can take minutes; refresh the live resin balance after
    // scanning and again validate its age immediately before entering a claim.
    if(task.kind!=='crafting') resinBefore=await readResin(api,started+policy.maxMinutes*60000);
    if(beforePacket.read.source!=='fresh-current-run' && !readWindowFresh(beforePacket.read,api.now())) {
      beforePacket=await freshBefore();before=beforePacket.inventory;
      checked=allCandidates(requirements,{...report.inventory,...before},data,policy,api.now()).find(t=>sourceKey(t)===sourceKey(task));
      if(!checked?.executable) {report.blockers.push({code:'pre_reward_unknown',materialIds:task.scanIds,message:'过期库存重新读取后不完整或已达标'});Object.assign(report.inventory,before);break;}
      if(insufficientTime()) {report.blockers.push({code:'time_limit',message:'重新读取库存后剩余时间不足以完成新步骤及收尾'});break;}
      resinBefore=await readResin(api,started+policy.maxMinutes*60000);
    }
    const afterScanBudget=task.kind==='crafting'?null:observedBudgetBlocker(policy,spent,api.now(),task.kind,resinBefore);
    if(gameDayChanged()) {gameDayBlocker();break;}
    if (afterScanBudget) {report.blockers.push({code:'budget_blocked',message:afterScanBudget});break;}
    if (insufficientTime()) {report.blockers.push({code:'time_limit',message:'余额复核后剩余时间不足以完成新步骤及收尾'});break;}
    // Recompute after scanning so a batch cannot use an outdated larger amount.
    const chosen=checked;
    const resin=task.kind==='crafting'?'none':task.kind==='boss'?'original':policy.domainResin;
    const stepStartedAt=iso(api.now());beforePacket.read.usedAt=stepStartedAt;
    const step={stepId:`${input.runId}:step-${index+1}`,type:task.kind,
      ...(task.kind==='boss'?{bossName:task.bossName}:task.kind==='domain'?{domainName:task.domainName,sundaySelectedValue:task.sundaySelectedValue}:{materialId:chosen.materialId,materialName:chosen.materialName,craftCount:chosen.craftCount,
        craftingCountry:chosen.craftingCountry,materialType:null,recipeEvidence:chosen.recipeEvidence,moraCostStatus:'unverified:合成会消耗摩拉，未读取余额/成本'}),maxClaims:1,
      validationAttempt:policy.validationMode===true,resin,before,
      ...(dailyOriginalReadPolicy(policy) && task.kind==='domain'?{beforeInventoryRead:beforePacket.read}:{}),
      ...(task.kind!=='crafting'?{resinBefore}:{}),status:'unknown',startedAt:stepStartedAt};
    // Construct once, inspect the real object's fields, checkpoint the evidence,
    // and pass that exact instance to BGI. Never reconstruct from intent later.
    let taskParam=null;
    if (task.kind==='boss') {
      taskParam=createBossParam(api.AutoBossParam,task.bossName,policy);
      const expected={BossName:task.bossName,TeamName:policy.bossPartyName,SpecifyRunCount:true,RunCount:1,UseFragileResin:false,UseTransientResin:false,ReviveRetryCount:0,
        ReturnToStatueAfterEachRound:false,RewardRecognitionEnabled:true,Timeout:policy.bossTimeoutSeconds};
      step.parameterEvidence=readParameterEvidence(taskParam,expected);
      step.mappingEvidence={source:'upstream/data/materials.json',sourceCommit:report.metadata.sourceCommit,materialIds:[...task.materialIds],bossName:task.bossName};
    } else if(task.kind==='domain') {
      taskParam=createDomainParam(api.AutoDomainParam,task,policy);
      const expected={DomainRoundNum:1,DomainName:task.domainName,PartyName:policy.domainPartyName,SundaySelectedValue:task.sundaySelectedValue,
        AutoArtifactSalvage:false,SpecifyResinUse:true,OriginalResinUseCount:0,OriginalResin20UseCount:resin==='original'?1:0,OriginalResin40UseCount:0,
        CondensedResinUseCount:resin==='condensed'?1:0,TransientResinUseCount:0,FragileResinUseCount:0,RewardRecognitionEnabled:true};
      if(policy.requireZhongliShieldCast)Object.assign(expected,{RequireZhongliShieldCast:true,CombatOnly:false});
      step.parameterEvidence=readParameterEvidence(taskParam,expected);
      const priority=readNativeList(taskParam.ResinPriorityList),expectedPriority=resin==='original'?'原粹树脂':'浓缩树脂';
      if(priority.length!==1 || priority[0]!==expectedPriority) throw new Error('实际秘境树脂优先列表未匹配单种授权树脂');
      step.parameterEvidence.ResinPriorityList=priority;
      step.mappingEvidence={source:'upstream/data/materials.json',sourceCommit:report.metadata.sourceCommit,materialIds:[...task.materialIds],domainName:task.domainName,sundaySelectedValue:task.sundaySelectedValue};
    }
    if(gameDayChanged()) {gameDayBlocker();break;}
    if (insufficientTime()) {report.blockers.push({code:'time_limit',message:'记录新步骤前剩余时间不足以完成单轮及收尾'});break;}
    report.steps.push(step);
    // Persist a durable in-flight checkpoint before any resource operation. A crash is never replayable success.
    const checkpointPath=`record/${input.runId}.json`;
    const checkpoint=JSON.stringify(report,null,2);
    if (await api.writeText(checkpointPath,checkpoint)!==true || api.readText(checkpointPath)!==checkpoint) throw new Error('领奖前记录写入失败，未执行资源任务');
    if (gameDayChanged() || insufficientTime() || (beforePacket.read.source!=='fresh-current-run' && !readWindowFresh(beforePacket.read,api.now()))
      || (task.kind!=='crafting' && observedBudgetBlocker(policy,spent,api.now(),task.kind,resinBefore))) {
      if(gameDayChanged()) gameDayBlocker();
      step.reason='写入checkpoint后时间或树脂观测已过期，未执行资源任务';
      uncertainSteps.push(step.stepId);
      break;
    }
    try {
      attemptedSources.add(attemptKey(task));
      const remainingMilliseconds=policy.maxMinutes*60000-(api.now()-started);
      let craftingResult=null;
      if(task.kind==='crafting') {
        craftingResult=await api.runCrafting({materialId:chosen.materialId,materialName:chosen.materialName,craftCount:chosen.craftCount,materialType:null,craftingCountry:chosen.craftingCountry},remainingMilliseconds);
        step.resultEvidence={Success:craftingResult?.Success===true,MainUiRestored:craftingResult?.MainUiRestored===true,MaterialName:craftingResult?.MaterialName ?? null,TargetQuantity:craftingResult?.TargetQuantity ?? null,ActualQuantity:craftingResult?.ActualQuantity ?? null};
      }
      else if (task.kind==='boss') await api.runBoss(taskParam,remainingMilliseconds);
      else await api.runDomain(taskParam,remainingMilliseconds);
      // Never add task rewards to inventory: the exact before/after comparison is the sole gain ledger.
      const afterReadStartedAt=api.now();
      const after=cloneInventory(await scan(task.scanIds,api,data.materials,guideContext(report,requirements)));
      const afterReadFinishedAt=api.now();
      const gain=task.kind==='crafting'?verifiedCraft(before,after,chosen,craftingResult):verifiedGain(before,after,task.scanIds);
      const resinAfter=task.kind==='crafting'?null:await readResin(api,started+policy.maxMinutes*60000);
      const resinEvidence=task.kind==='crafting'?{verified:true,delta:null,reason:null}:verifyResinDelta(resinBefore,resinAfter,task.kind,resin);
      Object.assign(step,{after,...(dailyOriginalReadPolicy(policy) && task.kind==='domain'?{afterInventoryRead:{runId:input.runId,
        startedAt:iso(afterReadStartedAt),finishedAt:iso(afterReadFinishedAt)}}:{}),
        delta:gain.delta || {},...(task.kind!=='crafting'?{resinAfter,actualResinDelta:resinEvidence.delta}:{}),
        status:gain.verified&&resinEvidence.verified?'success':'unknown',reason:gain.reason || resinEvidence.reason});
      Object.assign(report.inventory,cloneInventory(after));
      if (!gain.verified || !resinEvidence.verified) {actualComplete=false;uncertainSteps.push(step.stepId);break;}
      if(task.kind==='crafting') {
        step.materialsSpent=Object.fromEntries(Object.entries(gain.delta).filter(([,n])=>n<0).map(([id,n])=>[id,-n]));
        continue;
      }
      const cost=task.kind==='boss'?40:resin==='original'?20:1;
      if (resin==='original') spent.original+=cost;else spent.condensed+=1;
      step.confirmedConfiguredResinCost=cost;
      for(const kind of ['original','condensed']) {
        if(resinEvidence.delta[kind]===null) actualSpent[kind]=null;
        else if(actualSpent[kind]!==null) actualSpent[kind]+=resinEvidence.delta[kind];
      }
      step.resinCostEvidence='单轮显式树脂参数 + 材料增长 + 新鲜实际树脂前后观测；actualResinDelta为前减后净减少，含自然恢复影响';
    } catch (error) {
      actualComplete=false;step.reason=String(error?.message || error).slice(0,300);
      // An exception can arrive after the commit. Capture observed inventory
      // without promoting it to success or automatically repeating the batch.
      if(task.kind==='crafting') {
        const after=await scan(task.scanIds,api,data.materials,guideContext(report,requirements));step.after=after;
        step.delta=Object.fromEntries(task.scanIds.filter(id=>before[id]?.status==='exact' && after[id]?.status==='exact').map(id=>[id,after[id].count-before[id].count]));
        Object.assign(report.inventory,after);
      }
      uncertainSteps.push(step.stepId);break;
    }
    finally {step.finishedAt=new Date(api.now()).toISOString();}
  }
  report.plan=buildPlan(requirements,report.inventory,data.materials,data.recipes);
  report.plan.domains=candidateDomains(requirements,report.inventory,data.materials,data.recipes,policy,gameWeekday(api.now()));
  report.plan.bosses=candidateBosses(requirements,report.inventory,data.materials,policy,data.allowedBosses);
  report.plan.craftingTasks=candidateCrafting(requirements,report.inventory,data.materials,data.recipes,policy);
  if(report.steps.some(s=>s.type==='crafting')) report.warnings=report.warnings.filter(w=>w.code!=='crafting_not_executed');
  report.spending={configuredConfirmedClaims:spent,actualResinDelta:actualComplete?actualSpent:null,reason:'actualResinDelta仅累加实际前减后观测的净减少，含自然恢复影响；配置花费单独记录'};
  for (const t of report.plan.domains.filter(t=>t.needed&&!t.executable)) report.blockers.push({code:'domain_disabled',domainName:t.domainName,message:t.blockers.join('；')});
  for (const t of report.plan.bosses.filter(t=>t.needed&&!t.executable)) report.blockers.push({code:'boss_disabled',bossName:t.bossName,message:t.blockers.join('；')});
  if (uncertainSteps.length) report.blockers.push({code:'reward_unknown',stepIds:uncertainSteps,message:'领奖结果未知，禁止自动重放'});
  const unserved=report.plan.shortages.filter(row=>row.shortage>0 && !['domain','boss'].includes(row.material?.executionType) && row.status!=='excluded');
  if (unserved.length) report.blockers.push({code:'manual_material_sources',materialIds:unserved.map(r=>r.materialId),message:'周本/特产/怪物材料暂不可执行'});
  report.status=report.steps.length>0&&report.steps.every(s=>s.status==='success')&&!uncertainSteps.length?'success':'unknown';
  report.successMeaning='仅确认本次有界领奖步骤的收益，未声称培养完成';
}
async function readResin(api,deadline) {
  if(typeof api.readResinSnapshot!=='function') return null;
  for(let attempt=0;attempt<3;attempt++) {
    if(deadline-api.now()<12000) return null;
    let raw;
    try {raw=await api.readResinSnapshot();}
    catch(error) {
      if(/cancel|取消/i.test(String(error?.name || '')+' '+String(error?.message || error))) throw error;
      return null;
    }
    const snapshot=normalizeResinSnapshot(raw,api.now());
    if(snapshot) return snapshot;
    // Only repeat a completed, read-only observation after verified main UI
    // restoration. Never reuse an old balance or navigate an unsupported UI.
    if(raw?.mainUiRestored!==true) return null;
  }
  return null;
}
function readParameterEvidence(param,expected) {
  const evidence={};
  for(const [key,value] of Object.entries(expected)) {
    evidence[key]=param[key];
    if(evidence[key]!==value) throw new Error(`实际资源参数${key}与单轮授权不符，未调用任务`);
  }
  return evidence;
}
export function readNativeList(list) {
  const count=list?.Count;
  if(!Number.isInteger(count)||count<0||count>10)throw new Error('无法读取实际秘境树脂优先列表，未调用任务');
  let values;
  // ClearScript exposes native IEnumerable as iterable, without CLR get_Item.
  // Read the actual task object's list; never substitute requested settings.
  if(typeof list[Symbol.iterator]==='function')values=Array.from(list);
  else if(typeof list.get_Item==='function')values=Array.from({length:count},(_,index)=>list.get_Item(index));
  // Offline injected fixture list has an independently checked actual Count.
  else if(Array.isArray(list.items))values=[...list.items];
  else throw new Error('无法读取实际秘境树脂优先列表，未调用任务');
  if(values.length!==count||values.some(value=>typeof value!=='string'))throw new Error('实际秘境树脂优先列表计数或项目类型不一致，未调用任务');
  return values;
}
function verifyResinDelta(before,after,kind,resin) {
  if(!before || !after || Date.parse(after.observedAt)<Date.parse(before.observedAt)) return {verified:false,delta:null,reason:'领奖后树脂观测缺失或时间顺序无效，禁止重放'};
  const delta={original:before.originalResin===null || after.originalResin===null?null:before.originalResin-after.originalResin,
    condensed:before.condensedResin===null || after.condensedResin===null?null:before.condensedResin-after.condensedResin};
  const expected=kind==='boss'?40:resin==='original'?20:1;
  const used=resin==='original'?delta.original:delta.condensed;
  const valid=resin==='original'?used!==null && used>=expected-2 && used<=expected && (delta.condensed===null || delta.condensed===0):used===1 && (delta.original===null || (delta.original>=-2 && delta.original<=0));
  return {verified:valid,delta,reason:valid?null:'树脂实际差值未匹配单轮树脂类型/上限，停止且禁止重放'};
}
function allCandidates(requirements,inventory,data,policy,now) {
  return [...candidateBosses(requirements,inventory,data.materials,policy,data.allowedBosses),
    ...candidateDomains(requirements,inventory,data.materials,data.recipes,policy,gameWeekday(now)),
    ...candidateCrafting(requirements,inventory,data.materials,data.recipes,policy)];
}
function sourceKey(t) {return `${t.kind}:${t.bossName ?? t.domainName ?? t.materialId}:${t.sundaySelectedValue ?? ''}`;}
