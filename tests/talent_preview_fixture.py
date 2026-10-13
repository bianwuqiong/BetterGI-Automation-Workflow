"""Synthetic native-shaped UI scalars, never a real inventory or gameplay acceptance."""
from copy import deepcopy
from datetime import datetime,timezone
BASE=1791734400000  # 2026-10-11T16:00:00Z, entirely synthetic.
START=datetime.fromtimestamp(BASE/1000,timezone.utc).isoformat();FINISH=datetime.fromtimestamp((BASE+4000)/1000,timezone.utc).isoformat()
def rect(x,y,width,height):return dict(x=x,y=y,width=width,height=height)
def row(text,x,y,w,h):return {'text':text,'bounds':rect(x,y,w,h)}
def quantity(at,box,owned,required,prefix=''):
    raw=f'{owned}/{required}'
    return {'observedAt':BASE+at,'width':1920,'height':1080,'bounds':box,'raw':raw,'detectorRaw':raw,
        'owned':owned,'required':required,'complete':True,'prefix':prefix,'slashPixelVerified':False,
        'ocrRows':[row(prefix+raw,box['x']+8,box['y']+7,box['width']-16,box['height']-14)]}
def observation(character='梦见月瑞希',talent_type='元素战技',bonus=False):
    def common(at):return {'observedAt':BASE+at,'width':1920,'height':1080}
    names=[{**common(at),'overview':True,'name':character,'nameRegion':rect(1466,131,244,38),
        'nameRows':[row(character,1475,137,220,25)]} for at in (100,300,500)]
    display=4 if bonus else 1
    details=[{**common(at),'page':True,'type':talent_type,'title':'合成测试天赋','displayLevel':display,'baseLevel':1,
        'typeRegion':rect(242,13,98,36),'typeRows':[row(talent_type,250,20,80,22)],
        'titleRegion':rect(20,120,540,52),'titleRows':[row('合成测试天赋',30,130,220,30)],
        'levelRegion':rect(240,160,100,52),'levelRaw':f'等级{display}','levelRows':[row(f'等级{display}',250,175,60,20)],
        'colorSampleRegion':rect(230,150,120,72),'glyphRegion':rect(250,175,60,20),
        'glyphColor':'Cyan' if bonus else 'Neutral','brightPixels':120,'neutralPixels':0 if bonus else 120,
        'cyanPixels':120 if bonus else 0,'darkConflicts':0,'bonusRegion':rect(35,285,146,30),
        'bonusRaw':'天赋等级+3' if bonus else '','hasFixedPlusThree':bonus} for at in (800,1100)]
    def preview(at):
        return {**common(at),'page':True,'current':1,'next':2,
            'markerRegion':rect(420,235,1100,750),'rows':[row(t,x,y,100,30) for t,x,y in
                [('属性变更',500,250),('所需材料',500,580),('取消',650,940),('确认',1100,940)]],
            'currentLevelRegion':rect(760,245,160,65),'nextLevelRegion':rect(1000,245,170,65),
            'currentLevelRaw':'等级1','nextLevelRaw':'等级2','currentLevelRows':[row('等级1',780,255,100,30)],
            'nextLevelRows':[row('等级2',1020,255,100,30)],
            'materials':[{'name':'「自由」的教导','iconScore':.93,'card':rect(740,600,116,146),
                'iconRegion':rect(740,600,116,112),'quantity':quantity(at,rect(754,710,90,35),32,3)}],
            'coinRegion':rect(853,799,37,37),'coinName':'摩拉','coinScore':.91,
            'mora':quantity(at,rect(903,797,275,55),123456,12500)}
    previews=[preview(at) for at in (1400,1700,2700,3000)]
    tips=[{**common(at),'page':True,'name':'「自由」的教导','kind':'角色天赋素材','rawName':'[自由]的教导',
        'alternateRawName':'','alternateNameScale':4,'alternateNameRows':[],'alternateNamePreprocessing':'gray_threshold_210_inverse_cubic_4x',
        'nameRegion':rect(730,168,440,67),'nameRows':[row('[自由]的教导',740,180,250,35)],
        'kindRegion':rect(730,230,440,65),'kindRows':[row('角色天赋素材',740,240,260,30)],
        'sourceRegion':rect(730,690,460,65),'sourceRows':[row('来源',740,700,90,30)],
        'footerLabelRegion':rect(725,890,470,65),'footerLabelRows':[row('培养需求32/99',893,897,279,51)],
        'quantity':quantity(at,rect(885,890,295,65),32,99,'培养需求')} for at in (2100,2400)]
    worlds=[{**common(at),'phase':'world_restore','focused':True,'worldVerified':True} for at in (3400,3700)]
    evidence={'characterIdentity':names,'detailIdentityCarryover':details[-1],'preview':previews[-1],
        'materialTooltips':[tips],'rawFrames':names+details+previews[:2]+tips+previews[2:]+worlds,
        'characterSelectionAfterIdentity':False,'tooltipRequirementUsedAsUpgradeCost':False}
    return {'schemaVersion':1,'task':'talent-upgrade-inspection','status':'success','readOnly':True,'characterName':character,
        'talentType':talent_type,'talentName':'合成测试天赋','currentBaseLevel':1,'nextBaseLevel':2,
        'materials':[{'name':'「自由」的教导','owned':32,'required':3}],'mora':{'owned':123456,'required':12500},
        'evidenceVerified':True,'mainUiRestored':True,'confirmationSubmitted':False,'reason':'synthetic-fixture-only',
        'observedAt':datetime.fromtimestamp((BASE+3000)/1000,timezone.utc).isoformat(),'evidence':evidence}
def packet(character='梦见月瑞希',talent_type='元素战技',bonus=False):
    raw=observation(character,talent_type,bonus)
    return {'readOnly':True,'targetReached':False,'completedUpgrades':0,'selectedTalentType':talent_type,
        'nativeObservation':raw,'evidenceVerified':True,'costs':{'talentName':raw['talentName'],'currentBaseLevel':1,'nextBaseLevel':2,
            'materials':deepcopy(raw['materials']),'mora':deepcopy(raw['mora'])}}
