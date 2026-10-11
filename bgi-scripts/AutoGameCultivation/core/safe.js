// Copyright 2026 BetterGI Automation Workflow contributors. GPL-3.0-only.
import { expandTargets } from '../upstream/core/requirements.js';
import { mergeRequirements, calculateShortages } from '../upstream/core/calculator.js';
import { collectCraftingMaterialIds, buildCraftingPlan } from '../upstream/core/crafting.js';

const integer = (n, min, max) => Number.isInteger(n) && n >= min && n <= max;
const LIMITS = [20, 40, 50, 60, 70, 80, 90];
export function parseInputs(settings) {
  const runId = settings.runId;
  if (typeof runId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(runId)) throw new Error('runId必须为1-80位字母数字下划线或连字符');
  const mode = settings.mode || 'scan';
  if (!['scan', 'execute'].includes(mode)) throw new Error('mode必须为scan或execute');
  const target = JSON.parse(settings.targetConfigJson || '{}');
  const policy = JSON.parse(settings.policyJson || '{}');
  if (!target || Array.isArray(target) || typeof target !== 'object' || !policy || Array.isArray(policy) || typeof policy !== 'object') throw new Error('目标和策略必须为JSON对象');
  if (typeof target.characterName !== 'string' || !target.characterName.trim() || !integer(target.targetLevel, 1, 90)) throw new Error('角色名称或目标等级无效');
  for (const kind of ['normal', 'skill', 'burst']) if (!integer(target.talentTargets?.[kind], 1, 10)) throw new Error('必须指定三项1-10天赋目标');
  if (typeof target.includeEquippedWeapon !== 'boolean' || (target.includeEquippedWeapon && !integer(target.weaponTargetLevel, 1, 90))) throw new Error('装备武器目标无效');
  // Whitelist target fields: never persist arbitrary user fields such as UID or cookies.
  const cleanTarget = {characterName: target.characterName.trim(), targetLevel: target.targetLevel,
    talentTargets: {normal: target.talentTargets.normal, skill: target.talentTargets.skill, burst: target.talentTargets.burst},
    includeEquippedWeapon: target.includeEquippedWeapon, weaponTargetLevel: target.includeEquippedWeapon ? target.weaponTargetLevel : null};
  const flags = ['allowDomain', 'domainValidated', 'domainSingleAttemptVerified', 'allowBoss', 'bossValidated', 'allowCrafting', 'craftingValidated', 'validationMode', 'allowRoutes', 'allowWeekly', 'requireZhongliShieldCast', 'dailyMode', 'dailyDomainReady'];
  for (const key of flags) if (policy[key] !== undefined && typeof policy[key] !== 'boolean') throw new Error(`${key}必须为布尔值`);
  const cleanPolicy = Object.fromEntries(flags.map(k => [k, policy[k] === true]));
  cleanPolicy.validationScopeId=policy.validationScopeId ?? '';
  if(typeof cleanPolicy.validationScopeId!=='string' || (cleanPolicy.validationScopeId!=='' && !/^[A-Za-z0-9_-]{1,80}$/.test(cleanPolicy.validationScopeId))) throw new Error('初验scopeId必须为空或1-80位字母数字下划线连字符');
  cleanPolicy.validationAttemptedSources=policy.validationAttemptedSources ?? [];
  if(!Array.isArray(cleanPolicy.validationAttemptedSources) || cleanPolicy.validationAttemptedSources.some(kind=>!['boss','domain'].includes(kind)) || new Set(cleanPolicy.validationAttemptedSources).size!==cleanPolicy.validationAttemptedSources.length) throw new Error('初验已尝试来源必须为唯一boss/domain数组');
  cleanPolicy.validationAttemptedSources=[...cleanPolicy.validationAttemptedSources];
  if(!cleanPolicy.validationMode && !cleanPolicy.dailyMode && (cleanPolicy.validationScopeId!=='' || cleanPolicy.validationAttemptedSources.length)) throw new Error('仅初验或每日授权模式可指定scopeId');
  cleanPolicy.maxSteps = policy.maxSteps ?? 1;
  cleanPolicy.maxMinutes = policy.maxMinutes ?? 15;
  cleanPolicy.reserveOriginalResin = policy.reserveOriginalResin ?? 0;
  if (!integer(cleanPolicy.maxSteps, 1, 20) || !integer(cleanPolicy.maxMinutes, 1, 15) || !integer(cleanPolicy.reserveOriginalResin, 0, 10000)) throw new Error('执行步数/时间/原粹保留量无效');
  for (const k of ['originalResinBudget', 'condensedResinBudget', 'actualOriginalResin']) {
    if (policy[k] !== undefined && policy[k] !== null && !integer(policy[k], 0, 10000)) throw new Error(`${k}必须为非负整数或null`);
    cleanPolicy[k] = policy[k] ?? null;
  }
  cleanPolicy.domainResin = policy.domainResin ?? 'original';
  cleanPolicy.craftingCountry=policy.craftingCountry ?? '蒙德';
  if(!['蒙德','璃月'].includes(cleanPolicy.craftingCountry)) throw new Error('合成台国家只允许蒙德或璃月');
  cleanPolicy.resinObservedAt = typeof policy.resinObservedAt==='string' ? policy.resinObservedAt : null;
  cleanPolicy.bossTimeoutSeconds=policy.bossTimeoutSeconds ?? 180;
  if (!integer(cleanPolicy.bossTimeoutSeconds,120,180)) throw new Error('boss战斗超时必须为120-180秒');
  if (!['original', 'condensed'].includes(cleanPolicy.domainResin)) throw new Error('只允许原粹或浓缩树脂');
  for (const k of ['domainPartyName', 'bossPartyName', 'strategyName']) {
    if (policy[k] !== undefined && (typeof policy[k] !== 'string' || policy[k].length > 100)) throw new Error(`${k}无效`);
    cleanPolicy[k] = policy[k] || '';
  }
  if (policy.bossTeamName!==undefined) {
    if (typeof policy.bossTeamName!=='string' || policy.bossTeamName.length>100 || (cleanPolicy.bossPartyName && cleanPolicy.bossPartyName!==policy.bossTeamName)) throw new Error('boss队伍名称无效或相互冲突');
    cleanPolicy.bossPartyName=policy.bossTeamName;
  }
  if(cleanPolicy.validationMode && (cleanPolicy.originalResinBudget===null || cleanPolicy.originalResinBudget>60 || cleanPolicy.condensedResinBudget!==0 || cleanPolicy.domainResin!=='original' || cleanPolicy.maxSteps>2 || cleanPolicy.allowCrafting)) throw new Error('初验仅允许最多60原粹、0浓缩、最多2步且禁止材料合成');
  if(cleanPolicy.dailyMode && (cleanPolicy.validationMode || !cleanPolicy.validationScopeId || cleanPolicy.validationAttemptedSources.length || !integer(cleanPolicy.originalResinBudget,0,200) || cleanPolicy.condensedResinBudget!==0 || cleanPolicy.domainResin!=='original' || cleanPolicy.allowBoss || cleanPolicy.allowCrafting || !cleanPolicy.requireZhongliShieldCast)) throw new Error('每日授权只允许本scope单20原粹秘境，禁止boss或合成');
  if(mode==='execute' && cleanPolicy.dailyMode && !cleanPolicy.dailyDomainReady && (cleanPolicy.maxSteps!==1 || cleanPolicy.originalResinBudget>20)) throw new Error('每日授权首次领奖须限制为单步20原粹');
  if(!cleanPolicy.dailyMode && cleanPolicy.dailyDomainReady) throw new Error('dailyDomainReady仅用于每日授权');
  return {runId, mode, target: cleanTarget, policy: cleanPolicy};
}

function progress(level, limit, label) {
  if (!integer(level, 1, 90) || !LIMITS.includes(limit) || level > limit || level < (LIMITS[LIMITS.indexOf(limit)-1] ?? 0)) throw new Error(`${label}等级/突破上限缺失或不一致`);
  return {level, limit};
}
export function readProfile(raw, target, rulebook) {
  if (!raw || raw.CharacterName !== target.characterName) throw new Error('角色档案名称不匹配');
  if (!rulebook.characters?.[target.characterName]) throw new Error('规则库没有目标角色');
  const char = progress(raw.Level, raw.LevelLimit, '角色');
  const talent = {};
  for (const [key, field, bonus] of [['normal','AttackLevel','AttackHasBonus'], ['skill','SkillLevel','SkillHasBonus'], ['burst','BurstLevel','BurstHasBonus']]) {
    if (typeof raw[bonus] !== 'boolean' || !integer(raw[field], 1, 13)) throw new Error(`${key}天赋或命座标记缺失`);
    const base = raw[field] - (raw[bonus] ? 3 : 0);
    if (!integer(base, 1, 10)) throw new Error(`${key}天赋命座还原无效`);
    talent[key] = {display: raw[field], hasBonus: raw[bonus], base};
  }
  let weapon = null;
  if (target.includeEquippedWeapon) {
    if (typeof raw.WeaponName !== 'string' || !raw.WeaponName || !rulebook.weapons?.[raw.WeaponName]) throw new Error('装备武器缺失或规则库未收录，禁止猜测');
    weapon = {name: raw.WeaponName, ...progress(raw.WeaponLevel, raw.WeaponLevelLimit, '武器')};
  }
  return {characterName: target.characterName, character: char, talents: talent, weapon};
}
export function makeRequirements(profile, target, rulebook) {
  const goals = [{kind: 'character', name: target.characterName,
    level: {current: profile.character.level, currentLimit: profile.character.limit, target: Math.max(profile.character.level, target.targetLevel), targetLimit: LIMITS.find(n=>n>=Math.max(profile.character.level,target.targetLevel))},
    talents: Object.fromEntries(Object.entries(profile.talents).map(([k,v]) => [k, {current:v.base, target:Math.max(v.base, target.talentTargets[k])}]))}];
  if (profile.weapon) goals.push({kind:'weapon', name:profile.weapon.name, level:{current:profile.weapon.level,currentLimit:profile.weapon.limit,target:Math.max(profile.weapon.level,target.weaponTargetLevel),targetLimit:LIMITS.find(n=>n>=Math.max(profile.weapon.level,target.weaponTargetLevel))}});
  return mergeRequirements(expandTargets(goals, rulebook));
}
export function scanGroups(ids, materials) {
  const groups = {CharacterDevelopmentItems: [], Materials: []};
  for (const id of ids) {
    const material = materials[id];
    if (!material || material.status === 'excluded') continue;
    groups[/^(100|101)/.test(id) ? 'Materials' : 'CharacterDevelopmentItems'].push({id, name:material.name});
  }
  return Object.entries(groups).filter(([,v]) => v.length);
}
export function normalizeCounts(items, counts) {
  return Object.fromEntries(items.map(item => {
    const value = getCount(counts,item.name);
    return [item.id, integer(value, 0, 999999999) ? {name:item.name,count:value,status:'exact'} :
      {name:item.name,count:null,status:'unknown',reason:value === -2 ? '数量OCR失败' : '未找到或没有返回；不能推断为0'}];
  }));
}
function getCount(counts,name) {
  if (!counts) return undefined;
  if (typeof counts.get_Item==='function' && typeof counts.ContainsKey==='function') return counts.ContainsKey(name)?counts.get_Item(name):undefined;
  return counts[name];
}
export function exactCounts(inventory) {
  return Object.fromEntries(Object.entries(inventory).filter(([,v]) => v.status === 'exact' && integer(v.count,0,999999999)).map(([id,v]) => [id,v.count]));
}
// Plan connected recipe chains separately: an unread weapon material must not
// suppress suggestions for fully observed talent books. Only linear 3:1 chains
// are supported; neither probabilistic output nor arbitrary recipes are assumed.
function chainCraftingPlan(requirements, counts, recipes) {
  const ids=collectCraftingMaterialIds(requirements,recipes);
  const neighbors=new Map(ids.map(id=>[id,new Set()]));
  for (const id of ids) for (const input of recipes[id]?.inputs ?? []) {
    neighbors.get(id).add(String(input.id));neighbors.get(String(input.id)).add(id);
  }
  const visited=new Set(),chains=[],suggestions=[],unknownMaterialIds=[],invalidRecipeMaterialIds=[];
  const farmRequirements=new Map(),farmShortages={};
  for (const first of ids) {
    if (visited.has(first)) continue;
    const component=[],pending=[first];
    while (pending.length) {
      const id=pending.pop();if(visited.has(id))continue;
      visited.add(id);component.push(id);pending.push(...neighbors.get(id));
    }
    const chainReq=new Map(component.filter(id=>requirements.has(id)).map(id=>[id,requirements.get(id)]));
    const unknown=component.filter(id=>counts[id]===undefined);
    const outputs=new Map();let invalid=false;
    for (const id of component) if(recipes[id]) {
      const r=recipes[id];
      if(r.resultCount!==1 || r.inputs?.length!==1 || r.inputs[0].count!==3 || String(r.inputs[0].id)===id) {invalid=true;continue;}
      const low=String(r.inputs[0].id);outputs.set(low,(outputs.get(low)??0)+1);
    }
    // A finite linear chain has one recipe-free base and no branching output.
    if(component.filter(id=>!recipes[id]).length!==1 || [...outputs.values()].some(n=>n>1)) invalid=true;
    const chain={materialIds:component,unknownMaterialIds:unknown,validRecipeChain:!invalid,
      suggestions:[],farmRequirements:{},farmShortages:{},afterCraftingShortages:{}};
    unknownMaterialIds.push(...unknown);
    if(invalid) invalidRecipeMaterialIds.push(...component);
    if(unknown.length || invalid) {
      // Do not publish a guessed numeric farm deficit for an uncertain chain.
      for(const [id,required] of chainReq) {farmRequirements.set(id,required);chain.farmRequirements[id]=required;farmShortages[id]=null;chain.farmShortages[id]=null;chain.afterCraftingShortages[id]=null;}
    } else {
      const expanded=buildCraftingPlan(chainReq,counts,recipes);
      const simulated={...counts};
      // Expansion describes all crafts needed, which may exceed owned inputs.
      // Suggest only feasible crafts in dependency order, reserving each tier's
      // direct requirements and never altering the real inventory.
      for(const craft of [...expanded.craftPlan].reverse()) {
        const low=String(craft.inputs[0].id);
        const craftCount=Math.min(craft.craftCount,Math.floor(Math.max(0,simulated[low]-(chainReq.get(low)??0))/3));
        if(craftCount<=0) continue;
        simulated[low]-=3*craftCount;simulated[craft.materialId]+=craftCount;
        chain.suggestions.push({...craft,craftCount,produced:craftCount});
      }
      suggestions.push(...chain.suggestions);
      for(const [id,n] of expanded.farmRequirements) {
        farmRequirements.set(id,n);chain.farmRequirements[id]=n;
        farmShortages[id]=Math.max(0,n-counts[id]);chain.farmShortages[id]=farmShortages[id];
      }
      for(const [id,n] of chainReq) chain.afterCraftingShortages[id]=Math.max(0,n-simulated[id]);
    }
    chains.push(chain);
  }
  return {unknownMaterialIds,invalidRecipeMaterialIds,suggestions,farmRequirements,farmShortages,chains};
}
export function buildPlan(requirements, inventory, materials, recipes) {
  const counts = exactCounts(inventory);
  // Excluded resources cannot silently poison the supported crafting chain.
  const supported = new Map([...requirements].filter(([id]) => materials[id]?.status !== 'excluded'));
  const crafting = chainCraftingPlan(supported, counts, recipes);
  const shortages=calculateShortages(requirements,counts,materials).map(row=>{
    const inventoryKnown=counts[row.materialId]!==undefined;
    return inventoryKnown ? {...row,inventoryKnown:true} : {...row,owned:null,shortage:null,inventoryKnown:false,
      status:row.status==='excluded'?'excluded':'unknown',reason:'库存待核实，不能推断缺口数量'};
  });
  return {requirements: Object.fromEntries(requirements), shortages,
    crafting: {suggestionsOnly:true,executed:false,unknownMaterialIds:crafting.unknownMaterialIds,suggestions:crafting.suggestions,
      farmRequirements:Object.fromEntries(crafting.farmRequirements),farmShortages:crafting.farmShortages,
      invalidRecipeMaterialIds:crafting.invalidRecipeMaterialIds,chains:crafting.chains,
      shortageMeaning:'farmShortages仅为完整精确库存链的3:1基础材料等值缺口；afterCraftingShortages为未执行建议后的假设缺口，原始shortages仍是实际库存缺口'},
    manualResources:[{kind:'characterLevelExperience',status:'manual',reason:'上游规则未计算角色升级经验'},{kind:'weaponLevelExperience',status:'manual',reason:'上游规则未计算武器升级经验'},
      {kind:'levelUpMora',status:'manual',reason:'摩拉仅含突破和天赋；等级升级摩拉未计算，也未读取摩拉余额'}]};
}
export function candidateDomains(requirements, inventory, materials, recipes, policy, weekday) {
  const counts=exactCounts(inventory);
  const families = new Map();
  for (const [id, required] of requirements) {
    const m = materials[id];
    if (m?.executionType !== 'domain' || !m.domainName || required <= 0) continue;
    const key = `${m.domainName}:${m.sundaySelectedValue || ''}`;
    if (!families.has(key)) families.set(key,{kind:'domain',domainName:m.domainName,sundaySelectedValue:m.sundaySelectedValue || '',materialIds:[],openDays:m.openDays || []});
    families.get(key).materialIds.push(id);
  }
  return [...families.values()].map(task => {
    task.scanIds = collectCraftingMaterialIds(new Map(task.materialIds.map(id => [id,requirements.get(id)])), recipes);
    const known = task.scanIds.every(id => counts[id]!==undefined);
    const familyReq = new Map(task.materialIds.map(id => [id, requirements.get(id)]));
    const crafting = chainCraftingPlan(familyReq,counts,recipes);
    task.farmShortages=crafting.farmShortages;
    task.actualRequiredStockSatisfied=known && task.materialIds.every(id=>inventory[id].count>=requirements.get(id));
    task.needed = !known || crafting.invalidRecipeMaterialIds.length>0 || Object.values(crafting.farmShortages).some(n=>n>0);
    task.blockers = [];
    if (!known) task.blockers.push('本材料系列库存存在unknown/lower_bound');
    if (crafting.invalidRecipeMaterialIds.length) task.blockers.push('合成配方不是已支持的独立3:1材料链');
    if (!task.openDays.includes(weekday)) task.blockers.push('本游戏日不开放');
    if (weekday === 0 && !/^[1-9]\d*$/.test(task.sundaySelectedValue)) task.blockers.push('周日奖励序号未核实');
    task.validationAttempt=policy.validationMode===true;
    if(policy.validationMode && policy.validationAttemptedSources?.includes('domain')) task.blockers.push('同一初验scope已经尝试秘境，禁止重放');
    if (!policy.allowDomain || (!policy.domainValidated && !policy.validationMode && !policy.dailyMode) || !policy.domainSingleAttemptVerified) task.blockers.push('秘境未显式允许、未实机验收/有界初验或未确认全局复活重试上限=1');
    if (!policy.domainPartyName) task.blockers.push('未明确秘境队伍');
    task.executable = task.needed && !task.blockers.length;
    return task;
  });
}
export function candidateBosses(requirements,inventory,materials,policy,allowedBosses=[]) {
  const grouped=new Map();
  for (const [id,required] of requirements) {
    const material=materials[id];
    if (material?.executionType!=='boss' || !material.bossName || required<=0) continue;
    if (!grouped.has(material.bossName)) grouped.set(material.bossName,{kind:'boss',bossName:material.bossName,materialIds:[],scanIds:[],needed:false,blockers:[]});
    const task=grouped.get(material.bossName);task.materialIds.push(id);task.scanIds.push(id);
    if (inventory[id]?.status!=='exact' || inventory[id].count<required) task.needed=true;
  }
  return [...grouped.values()].map(task=>{
    if (!allowedBosses.includes(task.bossName)) task.blockers.push('静态首领名称不在固定BGI支持白名单');
    task.validationAttempt=policy.validationMode===true;
    if(policy.validationMode && policy.validationAttemptedSources?.includes('boss')) task.blockers.push('同一初验scope已经尝试首领，禁止重放');
    if (!policy.allowBoss || (!policy.bossValidated && !policy.validationMode)) task.blockers.push('普通boss尚未显式允许或本机实机验收/有界初验');
    if (!policy.bossPartyName.trim()) task.blockers.push('未明确boss队伍');
    if (!task.scanIds.every(id=>inventory[id]?.status==='exact')) task.blockers.push('boss材料库存存在unknown/lower_bound');
    task.executable=task.needed && !task.blockers.length;
    return task;
  });
}
export function candidateCrafting(requirements,inventory,materials,recipes,policy) {
  const plan=buildPlan(requirements,inventory,materials,recipes);
  return plan.crafting.chains.flatMap(chain=>chain.suggestions.slice(0,1).map(craft=>({
    kind:'crafting',materialId:craft.materialId,materialName:materials[craft.materialId]?.name,
    craftCount:craft.craftCount,materialType:null,craftingCountry:policy.craftingCountry,
    recipeEvidence:{resultCount:1,inputs:craft.inputs.map(i=>({id:String(i.id),count:3}))},
    scanIds:chain.materialIds,materialIds:chain.materialIds,needed:true,
    executable:policy.allowCrafting===true && policy.craftingValidated===true && Boolean(materials[craft.materialId]?.name),
    blockers:policy.allowCrafting===true && policy.craftingValidated===true?[]:['材料合成尚未显式允许或本机实机验收'],
  })));
}
export function verifiedCraft(before,after,task,result) {
  const ids=task.scanIds;
  if(!ids.every(id=>exactCounts(before)[id]!==undefined && exactCounts(after)[id]!==undefined)) return {verified:false,reason:'合成前后材料链库存不完整'};
  const delta=Object.fromEntries(ids.map(id=>[id,after[id].count-before[id].count]));
  const input=task.recipeEvidence.inputs[0].id,q=task.craftCount;
  const resultOk=result?.Success===true && result.MainUiRestored===true && result.MaterialName===task.materialName && result.TargetQuantity===q && result.ActualQuantity===q;
  const deltaOk=delta[input]===-3*q && delta[task.materialId]>=q && delta[task.materialId]<=2*q && ids.filter(id=>id!==input && id!==task.materialId).every(id=>delta[id]===0);
  return {verified:resultOk && deltaOk,delta,reason:resultOk&&deltaOk?null:'合成实际3:1消耗/产出或批次数不匹配；含返还等未知结果均停止，禁止重放'};
}
export function createDomainParam(Param, task, policy) {
  const p = new Param(1);
  p.DomainRoundNum=1;
  p.DomainName=task.domainName;
  p.PartyName=policy.domainPartyName;
  p.SundaySelectedValue=task.sundaySelectedValue;
  p.AutoArtifactSalvage=false;
  p.SpecifyResinUse=true;
  for (const name of ['OriginalResinUseCount','OriginalResin20UseCount','OriginalResin40UseCount','CondensedResinUseCount','TransientResinUseCount','FragileResinUseCount']) p[name]=0;
  // AutoDomainParam.SetDefault aliases the global List<string>. GetRange creates a
  // new native List before any Clear/Add, avoiding mutation of production settings.
  p.ResinPriorityList=p.ResinPriorityList.GetRange(0,0);
  p.ResinPriorityList.Clear();
  if (policy.domainResin==='original') {p.OriginalResin20UseCount=1;p.ResinPriorityList.Add('原粹树脂');}
  else {p.CondensedResinUseCount=1;p.ResinPriorityList.Add('浓缩树脂');}
  p.RewardRecognitionEnabled=true;
  if(policy.requireZhongliShieldCast) {p.RequireZhongliShieldCast=true;p.CombatOnly=false;}
  if (policy.strategyName) p.CombatStrategyPath=p.SetCombatStrategyPath(policy.strategyName);
  return p;
}
export function createBossParam(Param, bossName, policy) {
  const p=new Param();
  p.BossName=bossName;p.TeamName=policy.bossPartyName;p.SpecifyRunCount=true;p.RunCount=1;
  p.UseTransientResin=false;p.UseFragileResin=false;p.ReviveRetryCount=0;p.ReturnToStatueAfterEachRound=false;p.RewardRecognitionEnabled=true;
  p.Timeout=policy.bossTimeoutSeconds ?? 180;
  if (policy.strategyName) p.StrategyName=policy.strategyName;
  return p;
}
export function verifiedGain(before, after, ids) {
  if (!ids.every(id => before[id]?.status==='exact' && after[id]?.status==='exact')) return {verified:false,reason:'领奖前后库存不完整'};
  const delta=Object.fromEntries(ids.map(id => [id,after[id].count-before[id].count]));
  if (Object.values(delta).some(n => n<0)) return {verified:false,reason:'库存减少且本插件未执行材料消耗',delta};
  return {verified:Object.values(delta).some(n=>n>0),reason:Object.values(delta).some(n=>n>0)?null:'未确认材料增长',delta};
}
export function gameWeekday(now) { return new Date(now+8*3600000-4*3600000).getUTCDay(); }
export function normalizeResinSnapshot(raw,now) {
  const observed=Date.parse(raw?.observedAt || '');
  if(raw?.mainUiRestored!==true || !Number.isFinite(observed) || now-observed<0 || now-observed>120000) return null;
  const originalVerified=raw.originalVerified ?? raw.verified;
  const condensedVerified=raw.condensedVerified ?? raw.verified;
  const original=originalVerified===true && integer(raw.originalResin,0,200)?raw.originalResin:null;
  const condensed=condensedVerified===true && integer(raw.condensedResin,0,5)?raw.condensedResin:null;
  if(original===null && condensed===null) return null;
  return {originalResin:original,condensedResin:condensed,observedAt:raw.observedAt,verified:original!==null&&condensed!==null,
    originalVerified:original!==null,condensedVerified:condensed!==null,mainUiRestored:true};
}
export function observedBudgetBlocker(policy,spent,now,kind,snapshot) {
  // Budgets count prior confirmed claims; a freshly observed balance already
  // includes them, so never subtract earlier spending from the balance twice.
  const budget=budgetBlocker({...policy,reserveOriginalResin:0},spent,now,kind);
  if(budget) return budget;
  const observation=normalizeResinSnapshot(snapshot,now);
  if(!observation) return '树脂库存观测缺失、过期或未恢复主界面';
  if(kind==='domain' && policy.domainResin==='condensed') return observation.condensedResin===null || observation.condensedResin<1?'实际浓缩树脂不足或未核实':null;
  const cost=kind==='boss'?40:20;
  if(observation.originalResin===null) return '实际原粹树脂未核实';
  return observation.originalResin-cost<policy.reserveOriginalResin?'实际原粹不足或本轮会侵占预留原粹':null;
}
export function budgetBlocker(policy,spent,now,kind='domain') {
  if (kind==='domain' && policy.domainResin==='condensed') return policy.condensedResinBudget===null || spent.condensed+1>policy.condensedResinBudget ? '浓缩树脂预算缺失或耗尽' : null;
  const cost=kind==='boss'?40:20;
  if (policy.originalResinBudget===null || spent.original+cost>policy.originalResinBudget) return '原粹树脂预算缺失或耗尽';
  if (policy.reserveOriginalResin>0) {
    const observed=Date.parse(policy.resinObservedAt || '');
    if (policy.actualOriginalResin===null || !Number.isFinite(observed) || now-observed<0 || now-observed>120000) return '保留原粹需120秒内的实际树脂观测，花销预算不能替代库存';
    if (policy.actualOriginalResin-spent.original-cost<policy.reserveOriginalResin) return '本轮会侵占预留原粹树脂';
  }
  return null;
}
