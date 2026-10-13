"""Recompute six fixed world anchors from original PNGs and runtime definitions."""
import ast
import base64
import hashlib
import json
from pathlib import Path
try:
    from .named_inventory_capture import sha,rectangle_core
    from .named_inventory_catalog import _file
except ImportError:
    from named_inventory_capture import sha,rectangle_core
    from named_inventory_catalog import _file

ANCHORS=(('Common/Element','PaimonMenu','paimon_menu.png'),('Common/Element','InDomain','in_domain.png'),
    ('Common/Element','PromptDialogLeftBottomStar','prompt_dialog_left_bottom_star.png'),('Common/Element','BtnBlackConfirm','btn_black_confirm.png'),
    ('AutoFight','Confirm','confirm.png'),('QuickTeleport','MapCloseButton','MapCloseButton.png'))


def _roi(expression,regions):
    if expression is None:return (0,0,0,0)
    if not isinstance(expression,str):raise ValueError('named inventory world ROI definition invalid')
    if expression.startswith('@'):
        expression=regions.get(expression[1:])
        if not isinstance(expression,str) or expression.startswith('@'):raise ValueError('named inventory world ROI alias unsupported')
    node=ast.parse(expression,mode='eval').body
    def number(n):
        if isinstance(n,ast.Constant) and type(n.value) in (int,float):return n.value
        if isinstance(n,ast.Name) and n.id in ('cw','ch','s'):return {'cw':1920,'ch':1080,'s':1}[n.id]
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.USub):return -number(n.operand)
        if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div):
            a,b=number(n.left),number(n.right)
            return {ast.Add:lambda:a+b,ast.Sub:lambda:a-b,ast.Mult:lambda:a*b,ast.Div:lambda:a/b}[type(n.op)]()
        raise ValueError('named inventory world ROI expression not reviewed')
    if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.func.id!='rect' or len(node.args)!=4 or node.keywords:
        raise ValueError('named inventory world ROI must be bounded rect arithmetic')
    values=tuple(number(n) for n in node.args)
    if any(v!=int(v) for v in values):raise ValueError('named inventory world ROI fractional coordinates unsupported')
    return tuple(int(v) for v in values)


def verify_world_pixels(frame,image,trusted_runtime_root):
    try:
        import cv2
        import numpy as np
    except ImportError as error:raise ValueError('headless OpenCV world verification dependency unavailable') from error
    proof=frame.get('worldEvidence')
    if (not isinstance(proof,dict) or proof.get('observedAt')!=frame['observedAt'] or proof.get('width')!=1920 or proof.get('height')!=1080
            or not isinstance(proof.get('anchors'),list) or len(proof['anchors'])!=6):raise ValueError('named inventory original world anchor descriptors missing')
    root=Path(trusted_runtime_root).resolve(strict=True);source=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
    result=[]
    for index,(a,(task,name,file)) in enumerate(zip(proof['anchors'],ANCHORS)):
        relative=f'GameTask/{task}/Assets/1920x1080/{file}';definition=f'GameTask/{task}/Assets/Recognition.json'
        if (a.get('task')!=task or a.get('objectName')!=name or a.get('relativeTemplatePath')!=relative
                or a.get('relativeDefinitionPath')!=definition):raise ValueError('named inventory world descriptor chose an unreviewed asset')
        asset,unused,identity=_file(root,relative,2*1024*1024)
        definition_bytes,unused,identity=_file(root,definition,1024*1024)
        if hashlib.sha256(asset).hexdigest()!=sha(a.get('fileSha256')) or hashlib.sha256(definition_bytes).hexdigest()!=sha(a.get('definitionSha256')):
            raise ValueError('named inventory world asset/definition fingerprint differs')
        config=json.loads(definition_bytes.decode('utf-8-sig'));obj=config.get('objects',{}).get(name)
        if not isinstance(obj,dict) or obj.get('type')!='TemplateMatch' or obj.get('template')!=file:raise ValueError('named inventory world template definition identity differs')
        box=_roi(obj.get('roi'),config.get('regions',{}));declared=rectangle_core(a.get('searchRegion'),allow_derived=False)
        if tuple(declared.get(k) for k in ('x','y','width','height'))!=box or a.get('useMask') is not False or obj.get('useMask',False) is not False:
            raise ValueError('named inventory world ROI/mask lacks reviewed semantics')
        threshold=obj.get('threshold',.8);channels=obj.get('use3Channels',False);mode=obj.get('templateMatchMode','CCoeffNormed')
        if a.get('threshold')!=threshold or type(threshold) not in (int,float) or not 0<threshold<=1 or a.get('useThreeChannels') is not channels or a.get('matchMode')!=mode or mode!='CCoeffNormed':
            raise ValueError('named inventory world matcher definition differs')
        loaded=cv2.imdecode(np.frombuffer(asset,dtype=np.uint8),cv2.IMREAD_COLOR)
        try:encoded=base64.b64decode(a.get('templatePngBase64',''),validate=True)
        except ValueError as error:raise ValueError('named inventory actual template PNG encoding invalid') from error
        template=cv2.imdecode(np.frombuffer(encoded,dtype=np.uint8),cv2.IMREAD_COLOR)
        if (loaded is None or template is None or not np.array_equal(loaded,template) or hashlib.sha256(encoded).hexdigest()!=sha(a.get('templatePngSha256'))
                or hashlib.sha256(template.tobytes()).hexdigest()!=sha(a.get('templatePixelsSha256'))):raise ValueError('named inventory actual loaded template pixels differ from original asset')
        x,y,w,h=box if box!=(0,0,0,0) else (0,0,1920,1080)
        if x<0 or y<0 or w<=0 or h<=0 or x+w>1920 or y+h>1080 or template.shape[0]>h or template.shape[1]>w:raise ValueError('named inventory world search geometry invalid')
        region=source[y:y+h,x:x+w]
        if not channels:region=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY);template=cv2.cvtColor(template,cv2.COLOR_BGR2GRAY)
        response=cv2.matchTemplate(region,template,cv2.TM_CCOEFF_NORMED);unused,score,unused_point,point=cv2.minMaxLoc(response)
        expected={'x':x+point[0],'y':y+point[1],'width':template.shape[1],'height':template.shape[0]} if score>=threshold else {'x':0,'y':0,'width':0,'height':0}
        if rectangle_core(a.get('match'),allow_derived=False)!=expected:raise ValueError('named inventory original world pixels contradict declared template match')
        if index==0 and not expected['width'] or index>0 and expected['width']:raise ValueError('named inventory original PNG does not prove unobstructed outside world')
        result.append({'objectName':name,'score':float(score),'match':expected})
    return result
