"""Complete synthetic protocol/images. Never an actual game or live acceptance."""
import base64,csv,hashlib,io,json
from datetime import datetime,timezone
from pathlib import Path
from copy import deepcopy
import cv2
import numpy as np
from PIL import Image
from scripts.named_inventory_catalog import CSV_PATH,MODEL_PATH,load_runtime_catalog,resolve_material
from scripts.named_count_model_assets import COUNT_MODEL_ASSETS,read_named_count_model_assets
from scripts.named_inventory_world import ANCHORS
from scripts.named_inventory import RAW_DETECTOR
from tests.weekly_inventory_fixture import border,rect

BASE=1791734400000
def digest(data):return hashlib.sha256(data).hexdigest()
def native_rect(x,y,w,h):return {**rect(x,y,w,h),'top':y,'bottom':y+h,'left':x,'right':x+w,
    'location':{'x':x,'y':y},'size':{'width':w,'height':h},'topLeft':{'x':x,'y':y},'bottomRight':{'x':x+w,'y':y+h}}
def write(root,relative,data):p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p
def png(image):return cv2.imencode('.png',image)[1].tobytes()
def setup(root):
    write(root,'User/Config.json',json.dumps({'otherConfig':{'ocrConfig':{'paddleOcrModelConfig':8}}}).encode())
    for name,path in COUNT_MODEL_ASSETS:write(root,path,('synthetic-'+name).encode())
    write(root,RAW_DETECTOR,b'synthetic-detector-v6')
    stream=io.StringIO(newline='');w=csv.writer(stream);w.writerow(['variant_id','item_class_id','item_name','material_type','quality_level','embedding'])
    w.writerow(['1','material:104301','合成教导','角色天赋素材','2',base64.b64encode(b'\0'*16).decode()]);w.writerow(['2','material:202','摩拉','','3',base64.b64encode(b'\0'*16).decode()])
    write(root,CSV_PATH,stream.getvalue().encode());write(root,MODEL_PATH,b'synthetic-item-model')
    models=read_named_count_model_assets(root);models['pinMethod']='actual_bundled_open_read_sha256_hold_session'
    strict={'loadMethod':'new_cpu_uncached_original_onnx_and_labels_under_read_pins','provider':'Cpu','rawModel':'V6','detectorModel':'V4','countModels':models,
        'rawDetectorAsset':{'modelName':'PpOcrDetV6','relativePath':RAW_DETECTOR,'sha256':digest(b'synthetic-detector-v6'),'length':len(b'synthetic-detector-v6')}}
    rng=np.random.default_rng(23);templates={};configs={}
    for task,name,file in ANCHORS:
        template=rng.integers(0,255,(8,8,3),dtype=np.uint8);templates[name]=template
        write(root,f'GameTask/{task}/Assets/1920x1080/{file}',png(template))
        configs.setdefault(task,{'version':1,'regions':{},'objects':{}})['objects'][name]={'type':'TemplateMatch','template':file,'roi':'rect(20,20,80,80)','threshold':.8}
    for task,c in configs.items():write(root,f'GameTask/{task}/Assets/Recognition.json',json.dumps(c).encode())
    return strict,templates
def world_image(templates):
    image=np.full((1080,1920,3),120,dtype=np.uint8);image[40:48,40:48]=templates['PaimonMenu'];return image
def world_proof(root,image,at):
    anchors=[]
    for task,name,file in ANCHORS:
        path=f'GameTask/{task}/Assets/1920x1080/{file}';definition=f'GameTask/{task}/Assets/Recognition.json';data=(root/path).read_bytes();mat=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        a={'task':task,'objectName':name,'relativeTemplatePath':path,'fileSha256':digest(data),'relativeDefinitionPath':definition,'definitionSha256':digest((root/definition).read_bytes()),
            'searchRegion':rect(20,20,80,80),'threshold':.8,'useThreeChannels':False,'matchMode':'CCoeffNormed','useMask':False,
            'templatePngBase64':base64.b64encode(data).decode(),'templatePngSha256':digest(data),'templatePixelsSha256':digest(mat.tobytes()),'match':rect(0,0,0,0)}
        search=cv2.cvtColor(image[20:100,20:100],cv2.COLOR_BGR2GRAY);template=cv2.cvtColor(mat,cv2.COLOR_BGR2GRAY);_,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED))
        if score>=.8:a['match']=rect(20+point[0],20+point[1],8,8)
        anchors.append(a)
    return {'observedAt':at,'width':1920,'height':1080,'anchors':anchors}
def selected(root,models,at):
    image=np.full((1080,1920,3),120,dtype=np.uint8);item=rect(110,300,125,153)
    cv2.rectangle(image,(110,300),(234,452),(240,240,240),1)
    image[420:458,115:230]=245;image[434:447,145:155]=30
    crop=image[420:458,115:230];mask=cv2.inRange(cv2.cvtColor(cv2.resize(crop,(345,114)),cv2.COLOR_BGR2HSV),np.array([0,0,0],np.uint8),np.array([180,140,210],np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);allc=[rect(*v) for v in sorted((cv2.boundingRect(c) for c in contours),key=lambda b:(b[0],b[1]))]
    chosen=[c for c in allc if c['width']>1 and c['height']>=12 and c['width']*c['height']>=20 and c['y']+c['height']>=114*.55 and c['width']/c['height']<=3]
    x=min(c['x'] for c in chosen);y=min(c['y'] for c in chosen);w=max(c['x']+c['width'] for c in chosen)-x;h=max(c['y']+c['height'] for c in chosen)-y;gw=round(w*48/h)
    normalized=np.full((96,gw+48),255,np.uint8);normalized[24:72,24:24+gw]=cv2.resize(cv2.bitwise_not(mask[y:y+h,x:x+w]),(gw,48),interpolation=cv2.INTER_NEAREST)
    detector={'text':'7',**rect(26,26,gw-4,44)};px=115+int(np.floor((x+2*w/gw)/3));py=420+int(np.floor((y+2*h/48)/3));right=115+int(np.ceil((x+(gw-2)*w/gw)/3));bottom=420+int(np.ceil((y+46*h/48)/3));source={'text':'7',**rect(px,py,right-px,bottom-py)}
    reading={'method':'grid_hsv_foreground_exact_dual_ocr','sourceScale':3,'maximumSaturation':140,'maximumValue':210,'minimumComponentArea':20,'minimumComponentHeight':12,'minimumComponentBottomRatio':.55,'maximumComponentAspectRatio':3,
        'glyphHeight':48,'horizontalPadding':24,'verticalPadding':24,'topPaddingReference':8,'bottomPaddingReference':8,'ocrScale':1,'detectorModel':'PaddleV4_fixed','rawModel':'configured_native_paddle_without_detector','sourceInterpolation':'linear','glyphInterpolation':'nearest','ocrInterpolation':'nearest',
        'sourceRegion':rect(115,420,115,38),'allComponents':allc,'components':chosen,'foregroundBounds':rect(x,y,w,h),'foregroundSourceBounds':rect(115+x//3,420+y//3,int(np.ceil((x+w)/3))-x//3,int(np.ceil((y+h)/3))-y//3),
        'glyphWidth':gw,'normalizedWidth':gw+48,'normalizedHeight':96,'ocrInputWidth':gw+48,'ocrInputHeight':96,'raw':'7','detectorRows':[detector],'sourceRows':[source],
        'sourcePixelsSha256':digest(crop.tobytes()),'maskPixelsSha256':digest(mask.tobytes()),'normalizedPixelsSha256':digest(normalized.tobytes()),'ocrInputPixelsSha256':digest(normalized.tobytes()),'modelEvidence':models,'rawPaddleReadback':8}
    outline=border(item)
    for index,side in enumerate(outline['sides']):
        vertical=index<2;edge=(110,234,300,452)[index];begin=330 if vertical else 125;end=414 if vertical else 178;best=None
        for coordinate in range(edge-8,edge+9):
            line=image[begin:end,coordinate] if vertical else image[coordinate,begin:end];neutral=int(np.count_nonzero((line.min(axis=1)>=225)&(line.max(axis=1).astype(int)-line.min(axis=1).astype(int)<=35)))
            if best is None or neutral>best[1]:best=(coordinate,neutral)
        side.update(coordinate=best[0],neutralCount=best[1]);side['samples']=[]
        for position in range(begin,end,max(1,int((end-begin)/12))):
            xx,yy=(best[0],position) if vertical else (position,best[0]);b,g,r=map(int,image[yy,xx]);side['samples'].append({'x':xx,'y':yy,'b':b,'g':g,'r':r})
    stack={'observedAt':at,'nameRegion':rect(1280,110,540,78),'nameRows':[{'text':'合成教导',**rect(1300,130,150,25)}],'countRegion':reading['sourceRegion'],'countRows':[source],'countMethod':reading['method'],'rawCountText':'7','selectedItemVerified':True,'selectedItemRect':item,'selectionEvidence':outline}
    initial={**deepcopy(stack),'nameRegion':rect(1309,120,491,60),'nameRows':[{'text':'合成教导',**rect(1320,130,150,25)}],'countRegion':rect(115,428,115,22),'countRows':[],'countMethod':'raw_ocr_without_detector','rawCountText':'~7'}
    frame={'stack':stack,'initialStack':initial,'countReading':reading,'width':1920,'height':1080,'category':'characterDevelopmentItems','gameActive':True,'promptVisible':False,'tabVerified':True,'headerRegion':rect(100,0,350,100),'headerRows':[{'text':'养成道具',**rect(120,24,180,30)}],'iconName':'合成教导','iconScore':.9,'iconRegion':rect(110,300,125,125),'iconMethod':'cell_resize_125x153_top_125x125'}
    return image,frame
def fixture(root):
    strict,templates=setup(root);catalog=load_runtime_catalog(root);pair={'materialId':'104301','materialName':'合成教导'};target=resolve_material(catalog,pair)
    binding={'processId':123,'windowHandle':456,'processStartedUtcTicks':'639012345678901234','executablePath':str(root/'GenshinImpact.exe'),'systemInfoGeneration':'a'*32,'backendGeneration':'1','backendAssemblyMvid':'b'*32,'captureRectangle':native_rect(0,30,1920,1080),'captureMethod':'actual_synchronous_BitBltCapture'}
    context={'source':'runner_windows_os_preflight',**{k:binding[k] for k in ('processId','windowHandle','processStartedUtcTicks','executablePath','captureRectangle')},'foregroundWindowHandle':456}
    context['captureRectangle']=rect(0,30,1920,1080)
    request={'runId':'synthetic-run','stepId':'synthetic-step','phase':'diagnostic','materials':[pair]};session='bitblt-inventory:'+'c'*64
    raw={'schemaVersion':1,'source':'named_cultivation_backpack_selected_stack','readOnly':True,'confirmationSubmitted':False,'targetReached':False,'completedUpgrades':0,**{k:request[k] for k in ('runId','stepId','phase')},'status':'verified','mainUiRestored':True,'cleanupCompleted':True,'startedAt':BASE,'finishedAt':BASE+3500,'observedAt':BASE+1900,'captureSession':session,'gameBinding':binding,'catalogVersion':catalog['version'],'strictModels':strict,'countModels':strict['countModels'],'requestedMaterials':[target],'inventory':{'104301':7},'observations':{},'rejectedObservations':{},'rawFrames':[],'entryWorldFrames':[],'worldFrames':[]}
    for i,(at,kind) in enumerate(((200,'world_entry'),(500,'world_entry'),(1500,'named_selected_stack'),(1900,'named_selected_stack'),(2700,'world_restore'),(3100,'world_restore'))):
        when=BASE+at
        if 'world' in kind:image=world_image(templates);recognized={'observedAt':when,'width':1920,'height':1080,'focused':True,'world':True,'prompt':False,'knownBag':False,'escapeRequested':False};raw['entryWorldFrames' if kind=='world_entry' else 'worldFrames'].append(recognized)
        else:image,recognized=selected(root,strict['countModels'],when)
        data=png(image);path=write(root,f'log/named-inventory-native-frames/{"d"*32}/{i}.png',data);pixels={'observedAt':when,'width':1920,'height':1080,'pixelType':'CV_8UC3','path':str(path),'pngSha256':digest(data),'nativePixelsSha256':digest(image.tobytes()),'source':'diagnostic_only_lossless_native_srcmat_no_resize'}
        if kind=='named_selected_stack':recognized['privateCapture']=pixels
        record={'phase':kind,'observedAt':when,'actualCapture':{'callStartedAt':when-20,'callReturnedAt':when,'nativeWidth':1920,'nativeHeight':1080,'pixelType':'CV_8UC3','binding':binding,'returnedRectangle':binding['captureRectangle'],'freshnessSource':'BitBltSession.GetImage_executes_BitBlt_GdiFlush_new_buffer_each_call'},'privateCapture':pixels,'recognized':recognized}
        if 'world' in kind:record['worldEvidence']=world_proof(root,image,when)
        raw['rawFrames'].append(record)
    material_frames=[f['recognized'] for f in raw['rawFrames'] if f['phase']=='named_selected_stack']
    raw['observations']['104301']={'material':target,'pair':{'selection':{'itemRect':rect(110,300,125,153),'x':172,'y':365,'clickedAt':BASE+1100},'first':material_frames[0],'second':material_frames[1]},'reason':'same_frame_model_header_full_title_raw_quantity_border_pair'}
    receipt={'schemaVersion':1,'source':'actual_synchronous_BitBlt_inventory_binding','readOnly':True,'confirmationSubmitted':False,'observedAt':BASE,'gameBinding':binding,'captureSession':session}
    packet={'readOnly':True,'request':request,'targetReached':False,'completedUpgrades':0,'sessionAfterVerified':False,
        'consumptionVerified':False,'liveVerified':False,'rawEvidenceVerified':False,
        'readStartedAt':datetime.fromtimestamp(BASE/1000,timezone.utc).isoformat(),
        'readFinishedAt':datetime.fromtimestamp((BASE+4000)/1000,timezone.utc).isoformat(),'bindingReceipt':receipt,'nativeObservation':raw}
    return packet,request,context

def mora_fixture(root):
    packet,unused,context=fixture(root);named=packet['nativeObservation'];readings=[];frames=[]
    for f in named['rawFrames']:
        if f['phase']=='named_selected_stack':
            at=f['observedAt'];read={'observedAt':at,'width':1920,'height':1080,'backpackTabVerified':True,'promptVisible':False,
                'headerRows':[{'text':'贵重道具',**rect(120,24,180,30)}],'iconName':'摩拉','iconScore':.9,'iconRegion':rect(354,1000,37,37),'balanceRegion':rect(392,1000,168,40),
                'balanceRows':[{'text':'123456',**rect(400,1005,100,25)}],'rawBalanceText':'123456'}
            f={**f,'phase':'actual_Mora_balance','recognized':read};readings.append(read)
        frames.append(f)
    raw={k:named[k] for k in ('schemaVersion','readOnly','confirmationSubmitted','targetReached','completedUpgrades','status','mainUiRestored','cleanupCompleted','startedAt','finishedAt','captureSession','gameBinding','catalogVersion','strictModels','entryWorldFrames','worldFrames')}
    raw.update(source='bound_precious_items_bottom_mora',materialId='202',materialName='摩拉',balance=123456,readings=readings,rawFrames=frames,
        request={'balanceRegion':rect(392,1000,168,40),'iconRegion':rect(354,1000,37,37)})
    return {**{key:packet[key] for key in ('readOnly','targetReached','completedUpgrades','sessionAfterVerified','consumptionVerified','liveVerified','rawEvidenceVerified','readStartedAt','readFinishedAt')},'bindingReceipt':packet['bindingReceipt'],'nativeObservation':raw},context
