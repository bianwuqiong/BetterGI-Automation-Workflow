"""Recompute one read-only next-talent cost from the native raw UI evidence.

Legacy fixtures remain diagnostic compatibility only. Neither legacy nor model-
pinned costs authorize consumption or replace the unintegrated native final gate.
"""
import math
from pathlib import Path
import re
import unicodedata
try:
    from .backpack_inventory_evidence import _number,_rect,_inside,_time
    from .named_count_model_assets import COUNT_MODEL_ASSETS
    from .named_inventory import RAW_DETECTOR,strict_models
    from .named_inventory_capture import original_png
except ImportError:
    from backpack_inventory_evidence import _number,_rect,_inside,_time
    from named_count_model_assets import COUNT_MODEL_ASSETS
    from named_inventory import RAW_DETECTOR,strict_models
    from named_inventory_capture import original_png

TYPES=('普通攻击','元素战技','元素爆发')
PINNED_SPLIT_METHOD='pinned_v6_v4_slash_integer_split'
SPLIT_METADATA=('splitRawModel','splitDetectorModel','splitModelEvidence','splitRawPaddleReadback')
PREVIEW_TIMING_METHOD='capture_read_evaluate_then_private_png_v1'
READ_TIMING_FIELDS={'captureCallStartedAt','captureReturnedAt','readerStartedAt','readerCompletedAt',
    'pairEvaluatedAt','diagnosticPngCompletedAt','pairAccepted'}
PRIVATE_CAPTURE_FIELDS={'observedAt','width','height','pixelType','path','pngSha256','nativePixelsSha256','source'}

def preview_timing(raw,previews,start,finish,*,trusted_runtime_root=None):
    """Authenticate retained PNG bytes and the reported evaluation sequence, not BitBlt ownership."""
    active=raw.get('previewTimingMethod') is not None or any(p.get('readTiming') is not None for p in previews)
    if not active:return
    if raw.get('previewTimingMethod')!=PREVIEW_TIMING_METHOD:
        raise ValueError('modern preview timing requires the exact capture/read/evaluate/PNG method')
    if cost_method(raw)!=PINNED_SPLIT_METHOD or any(cost_method(p)!=PINNED_SPLIT_METHOD for p in previews):
        raise ValueError('modern preview timing cannot authenticate legacy quantity costs')
    if trusted_runtime_root is None:raise ValueError('modern preview PNG requires trusted BetterGI runtime root')
    paths=set();file_ids=set()
    for offset in range(0,len(previews),2):
        first,second=previews[offset:offset+2];times=[]
        for index,p in enumerate((first,second)):
            timing=p.get('readTiming');pixels=p.get('privateCapture')
            if (not isinstance(timing,dict) or set(timing)!=READ_TIMING_FIELDS
                    or not isinstance(pixels,dict) or set(pixels)!=PRIVATE_CAPTURE_FIELDS):
                raise ValueError('modern preview requires both complete readTiming and original PNG metadata')
            for key in READ_TIMING_FIELDS-{'pairEvaluatedAt','pairAccepted'}:
                value=integer(timing[key],0,9007199254740991)
                if not start<=value<=finish:raise ValueError('preview timing clock outside actual run')
            at=integer(p.get('observedAt'),0,9007199254740991)
            if not timing['captureCallStartedAt']<=timing['captureReturnedAt']==at<=timing['readerStartedAt']<=timing['readerCompletedAt']:
                raise ValueError('preview actual capture/reader clock order mismatch')
            if index==0:
                if timing['pairEvaluatedAt'] is not None or timing['pairAccepted'] is not None:
                    raise ValueError('first preview frame cannot claim pair evaluation or acceptance')
            else:
                evaluated=integer(timing['pairEvaluatedAt'],0,9007199254740991)
                if not start<=evaluated<=finish or timing['pairAccepted'] is not True:
                    raise ValueError('second preview frame needs actual accepted pair evaluation')
            if ((p['width'],p['height'])!=(1920,1080) or type(pixels.get('observedAt')) is not int
                    or pixels['observedAt']!=at or not isinstance(pixels.get('path'),str)
                    or len(pixels['path'])>4096 or re.search(r'[\x00-\x1f\x7f]',pixels['path'])
                    or any(part in ('.','..') for part in re.split(r'[\\/]',pixels['path']))
                    or not Path(pixels['path']).is_absolute()):
                raise ValueError('preview original PNG origin/time/native geometry mismatch')
            try:
                runtime=Path(trusted_runtime_root).resolve(strict=True)
                path=Path(pixels['path']).resolve(strict=True)
                if not path.is_relative_to(runtime/'log'):
                    raise ValueError('preview original PNG must stay inside trusted runtime log')
                identity=path.stat();file_id=(identity.st_dev,identity.st_ino)
                if path in paths or identity.st_ino and file_id in file_ids:
                    raise ValueError('preview original PNG reused for another capture')
                paths.add(path);file_ids.add(file_id)
                # No workflow/state fallback: modern originals must be in this trusted runtime's log.
                with original_png(pixels,trusted_runtime_root):pass
            except (OSError,SyntaxError) as error:
                raise ValueError('modern preview original PNG unavailable or unverified') from error
            times.append(timing)
        a,b=times
        if (not a['readerCompletedAt']<b['captureCallStartedAt']
                or not b['readerCompletedAt']<=b['pairEvaluatedAt']<=a['diagnosticPngCompletedAt']<=b['diagnosticPngCompletedAt']
                or not 0<second['observedAt']-first['observedAt']<=5000
                or not 0<=b['pairEvaluatedAt']-second['observedAt']<=1500):
            raise ValueError('preview original pair freshness/evaluation-before-PNG sequence invalid')
        following=next((f for f in raw['evidence']['rawFrames'] if f['observedAt']>second['observedAt']),None)
        if following is not None:
            next_capture=following['observedAt']
            if 'materials' in following and 'current' in following:
                timing=following.get('readTiming')
                if not isinstance(timing,dict):raise ValueError('next modern preview capture timing missing')
                next_capture=integer(timing.get('captureCallStartedAt'),0,9007199254740991)
            if b['diagnosticPngCompletedAt']>min(next_capture,following['observedAt']):
                raise ValueError('preview PNG completion cannot follow the next original capture')

def modern_split(q):
    if not isinstance(q,dict):raise ValueError('talent quantity must be a native JSON object')
    return any(q.get(key) is not None for key in SPLIT_METADATA)

def split_model_shape(q):
    """Check native model provenance shape; it does not prove any local file bytes."""
    if not modern_split(q):return False
    if (q.get('splitRawModel')!='V6' or q.get('splitDetectorModel')!='V4'
            or type(q.get('splitRawPaddleReadback')) is not int or q['splitRawPaddleReadback']!=8
            or q.get('slashPixelVerified') is not True or q.get('splitRegionMethod')!='slash_vertical_band'
            or type(q.get('splitOcrScale')) is not int or q['splitOcrScale']!=4
            or type(q.get('splitVerticalPaddingReference')) is not int or q['splitVerticalPaddingReference']!=6
            or q.get('prefix','')!=''):
        raise ValueError('modern quantity requires complete pinned V6/V4 slash-band metadata')
    proof=q.get('splitModelEvidence')
    if (not isinstance(proof,dict) or set(proof)!={'loadMethod','provider','rawModel','detectorModel','countModels','rawDetectorAsset'}
            or proof['loadMethod']!='new_cpu_uncached_original_onnx_and_labels_under_read_pins'
            or proof['provider']!='Cpu' or proof['rawModel']!='V6' or proof['detectorModel']!='V4'):
        raise ValueError('modern quantity strict model evidence incomplete')
    models=proof['countModels']
    expected={'rawPaddleConfig':8,'rawPaddleName':'V6','fixedDetectorConfig':7,'fixedDetectorName':'V4',
        'pinMethod':'actual_bundled_open_read_sha256_hold_session'}
    if (not isinstance(models,dict) or set(models)!={*expected,'assets'}
            or any(type(models.get(key)) is not type(value) or models[key]!=value for key,value in expected.items())
            or not isinstance(models['assets'],list) or len(models['assets'])!=5):
        raise ValueError('modern quantity original count model pins incomplete')
    for asset,(name,path) in zip([*models['assets'],proof['rawDetectorAsset']],
            [*COUNT_MODEL_ASSETS,('PpOcrDetV6',RAW_DETECTOR)]):
        if (not isinstance(asset,dict) or set(asset)!={'modelName','relativePath','sha256','length'}
                or asset['modelName']!=name or asset['relativePath']!=path
                or not isinstance(asset['sha256'],str) or not re.fullmatch('[0-9a-fA-F]{64}',asset['sha256'])
                or type(asset['length']) is not int or not 0<asset['length']<=1024*1024*1024):
            raise ValueError('modern quantity fixed six-model asset proof invalid')
    return True

def split_models(q,trusted_runtime_root):
    if split_model_shape(q):
        if trusted_runtime_root is None:raise ValueError('modern quantity requires trusted BetterGI runtime root')
        # Fixed relative asset paths are independently hashed by the Host, never trusted from JSON.
        strict_models(q['splitModelEvidence'],trusted_runtime_root)

def cost_method(value):
    marker=value.get('costQuantityMethod')
    if marker not in (None,'legacy_observed_ratio',PINNED_SPLIT_METHOD):
        raise ValueError('talent cost quantity method is not reviewed')
    return marker or 'legacy_observed_ratio'

def quantity_chain_modern(q):
    return modern_split(q) or isinstance(q.get('initialReading'),dict) and modern_split(q['initialReading'])

def preview_materials(p):
    values=p.get('materials')
    if (not isinstance(values,list) or not 1<=len(values)<=4
            or any(not isinstance(item,dict) or not isinstance(item.get('quantity'),dict) for item in values)):
        raise ValueError('preview bounded native material quantity objects missing')
    return values
def clean(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',value)) if isinstance(value,str) else ''
def material_name(value): return clean(value).replace('[','「').replace(']','」')
def integer(value,minimum=0,maximum=2147483647):
    if type(value) is not int or not minimum<=value<=maximum: raise ValueError('talent preview integer invalid')
    return value
def digits(raw):
    if not re.fullmatch(r'(0|[1-9][0-9]{0,9})',clean(raw)): raise ValueError('complete integer text required')
    return integer(int(clean(raw)))
def frame(value,start,finish):
    if not isinstance(value,dict): raise ValueError('talent raw frame missing')
    w,h=integer(value.get('width'),800,4096),integer(value.get('height'),450,2160)
    if w*9!=h*16 or not start<=_number(value.get('observedAt'))<=finish: raise ValueError('talent frame dimensions/time invalid')
    return w/1920
def region(value,key,reference):
    box=_rect(value.get(key));s=value['width']/1920
    if any(abs(a-b*s)>1 for a,b in zip(box,reference)): raise ValueError('talent UI evidence region differs from actual page geometry')
    return box
def character_region(value):
    for reference in ((1466,131,244,38),(1460,124,264,52),(1420,110,360,68)):
        try:return region(value,'nameRegion',reference)
        except ValueError:pass
    raise ValueError('character name ROI outside reviewed inspection14/15/16 whitelist')
def rows_text(rows,box,s,full=True,projected=False):
    if not isinstance(rows,list) or not rows: raise ValueError('complete raw OCR rows missing')
    for row in rows:
        rect=_rect(row.get('bounds'))
        if not _inside(rect,box) or full and min(rect[0]-box[0],box[0]+box[2]-rect[0]-rect[2])<2*s-(1 if projected else 0):
            raise ValueError('talent integer/name OCR touches crop edge')
    return ''.join(clean(row.get('text')) for row in rows)
def pair(a,b):
    if (a.get('width'),a.get('height'))!=(b.get('width'),b.get('height')) or not 0<_number(b.get('observedAt'))-_number(a.get('observedAt'))<=5000:
        raise ValueError('talent independent fresh frames required')
def quantity(q,start,finish,prefix='',*,trusted_runtime_root=None):
    s=frame(q,start,finish);box=_rect(q.get('bounds'))
    split_models(q,trusted_runtime_root)
    if not _inside(box,(0,0,q['width'],q['height'])) or q.get('complete') is not True or q.get('prefix','')!=prefix:
        raise ValueError('complete quantity crop/prefix proof missing')
    owned,required=integer(q.get('owned')),integer(q.get('required'),0 if prefix else 1)
    if q.get('slashPixelVerified') is True:
        slash=_rect(q.get('slashBounds'));left=_rect(q.get('numeratorRegion'));right=_rect(q.get('denominatorRegion'))
        method=q.get('splitRegionMethod')
        if method is None:
            top,bottom=box[1],box[1]+box[3]
        elif method=='slash_vertical_band' and type(q.get('splitVerticalPaddingReference')) is int and q['splitVerticalPaddingReference']==6:
            pad=max(3,round(6*s));top=max(box[1],slash[1]-pad);bottom=min(box[1]+box[3],slash[1]+slash[3]+pad)
        else:raise ValueError('split method/padding is not the reviewed legacy or slash glyph band')
        if (prefix or q.get('splitOcrScale')!=4 or box[2]>=200*s or not _inside(slash,box)
                or slash[2]<2 or slash[3]<6 or not 1.5<=slash[3]/slash[2]<=5 or integer(q.get('slashInkPixels'))<6
                or not -1<=_number(q.get('slashCorrelation'))<=-.75 or slash[0]-box[0]<=8
                or box[0]+box[2]-slash[0]-slash[2]<=8 or slash[0]-box[0]<box[2]*.2 or slash[0]+slash[2]>box[0]+box[2]*.85
                or left!=(box[0],top,slash[0]-box[0]-1,bottom-top)
                or right!=(slash[0]+slash[2]+1,top,box[0]+box[2]-slash[0]-slash[2]-1,bottom-top)
                or len(q.get('numeratorRows',[]))!=1 or len(q.get('denominatorRows',[]))!=1):
            raise ValueError('actual slash/split integer geometry unverified')
        numerator=rows_text(q['numeratorRows'],left,s,projected=method is None)
        denominator=rows_text(q['denominatorRows'],right,s,projected=method is None)
        if method is not None:
            for values,bounds in ((q['numeratorRows'],left),(q['denominatorRows'],right)):
                if any(min(_rect(row['bounds'])[1]-bounds[1],bounds[1]+bounds[3]-_rect(row['bounds'])[1]-_rect(row['bounds'])[3])<2*s for row in values):
                    raise ValueError('slash-band complete integer must clear all four actual crop edges')
        if numerator!=clean(q.get('numeratorRaw')) or denominator!=clean(q.get('denominatorRaw')) or (digits(numerator),digits(denominator))!=(owned,required):
            raise ValueError('split raw integers differ from parsed quantity')
    else:
        raw=clean(q.get('raw'));detected=rows_text(q.get('ocrRows'),box,s)
        if prefix:
            if not detected.startswith(prefix): raise ValueError('actual tooltip prefix missing')
            detected=detected[len(prefix):]
        if raw!=clean(q.get('detectorRaw')) or raw!=detected or not re.fullmatch(r'(0|[1-9][0-9]{0,9})/(0|[1-9][0-9]{0,9})',raw):
            raise ValueError('whole complete raw quantity ambiguity')
        if tuple(digits(part) for part in raw.split('/'))!=(owned,required): raise ValueError('raw quantity differs from declared integers')
    return owned,required

def retained_initial(q,parent,start,finish,*,trusted_runtime_root=None):
    initial=q.get('initialReading')
    frame(initial,start,finish)
    split_models(initial,trusted_runtime_root)
    if (initial.get('observedAt')!=parent['observedAt'] or (initial['width'],initial['height'])!=(parent['width'],parent['height'])
            or type(initial.get('complete')) is not bool or not isinstance(initial.get('raw'),str)
            or not isinstance(initial.get('detectorRaw'),str) or not isinstance(initial.get('ocrRows'),list)
            or initial.get('initialReading') is not None or initial.get('prefix','')!=''):
        raise ValueError('initial quantity raw/frame provenance missing')
    box=_rect(initial.get('bounds'))
    for row in initial['ocrRows']:
        if not isinstance(row.get('text'),str) or not _inside(_rect(row.get('bounds')),box):
            raise ValueError('initial detector rows changed or outside their real crop')
    if not initial['complete'] and (initial.get('owned') is not None or initial.get('required') is not None):
        raise ValueError('failed initial reading must retain nullable quantities')
    return initial

def material_crop(item,parent,start,finish,*,trusted_runtime_root=None):
    q=item['quantity'];s=parent['width']/1920
    if q.get('initialReading') is None:
        if q.get('cropMethod','fixed_or_initial')!='fixed_or_initial' or q.get('sourceCountRow') is not None:
            raise ValueError('derived material crop has no actual initial reading')
        return
    if q.get('cropMethod')!='source_count_row_pad20x5_intersect_card':raise ValueError('unrecognized derived material crop method')
    initial=retained_initial(q,parent,start,finish,trusted_runtime_root=trusted_runtime_root);source=q.get('sourceCountRow',{})
    box=_rect(source.get('bounds'));band=(440*s,690*s,1040*s,100*s)
    if not re.fullmatch(r'[0-9/]{2,20}',clean(source.get('text'))) or not _inside(box,band) or min(box[0]-band[0],band[0]+band[2]-box[0]-box[2])<2*s:
        raise ValueError('actual material source count row outside complete count band')
    x,y,w,h=box
    expected_initial=(x-round(8*s),y-round(5*s),w+round(16*s),h+round(10*s))
    center=x+w//2;expected_card=(center-round(58*s),y+h-round(138*s),round(116*s),round(146*s))
    card=_rect(item['card'])
    if _rect(initial['bounds'])!=expected_initial or card!=expected_card:
        raise ValueError('material initial pad8/card are not derived from actual source row')
    left=max(card[0],x-round(20*s));right=min(card[0]+card[2],x+w+round(20*s))
    top=max(card[1],y-round(5*s));bottom=min(card[1]+card[3],y+h+round(5*s))
    if _rect(q['bounds'])!=(left,top,right-left,bottom-top):raise ValueError('material padded crop is not exactly intersected with actual card')
    if initial['complete'] and quantity(initial,start,finish,trusted_runtime_root=trusted_runtime_root)!=quantity(q,start,finish,trusted_runtime_root=trusted_runtime_root):raise ValueError('high-confidence initial material quantity conflicts with final actual crop')

def mora_crop(q,parent,start,finish,*,trusted_runtime_root=None):
    if q.get('initialReading') is None:
        if q.get('cropMethod','fixed_or_initial')!='fixed_or_initial' or q.get('sourceCountRow') is not None:
            raise ValueError('derived Mora crop has no actual initial reading')
        region(q,'bounds',(903,797,275,55));return
    if q.get('cropMethod')!='unique_initial_detector_row_pad12':raise ValueError('unrecognized derived Mora crop method')
    initial=retained_initial(q,parent,start,finish,trusted_runtime_root=trusted_runtime_root);region(initial,'bounds',(903,797,275,55))
    numeric=[row for row in initial['ocrRows'] if re.fullmatch(r'(0|[1-9][0-9]{0,9})/(0|[1-9][0-9]{0,9})',clean(row['text']))]
    if len(numeric)!=1 or q.get('sourceCountRow')!=numeric[0]:raise ValueError('Mora source is not the unique real initial complete ratio row')
    s=parent['width']/1920;row_box=_rect(numeric[0]['bounds'])
    rows_text(numeric,_rect(initial['bounds']),s)
    x,y,w,h=row_box;pad=round(12*s);expected=(x-pad,y-pad,w+2*pad,h+2*pad)
    if (_rect(q['bounds'])!=expected or expected[0]<parent['width']*.44 or expected[0]+expected[2]>parent['width']*.65
            or expected[1]<parent['height']*.7 or expected[1]+expected[3]>parent['height']*.81):
        raise ValueError('Mora derived box is not actual detector row plus bounded pad12')
    if initial['complete'] and quantity(initial,start,finish,trusted_runtime_root=trusted_runtime_root)!=quantity(q,start,finish,trusted_runtime_root=trusted_runtime_root):raise ValueError('high-confidence initial Mora quantity conflicts with final actual crop')

def coin_identity(p):
    variant=p.get('coinVariant','tight_37')
    if variant=='tight_37':region(p,'coinRegion',(853,799,37,37))
    elif variant=='real_background_padding_8_reference_53':
        region(p,'coinRegion',(845,791,53,53));region(p,'initialCoinRegion',(853,799,37,37))
        score=_number(p.get('initialCoinScore'))
        if not 0<=score<=1 or not isinstance(p.get('initialCoinName'),str) or score>=.75 and p['initialCoinName']!='摩拉':
            raise ValueError('initial high-confidence currency conflicts with selected real-background variant')
    else:raise ValueError('currency variant is not an explicitly selected reviewed crop')
    if p.get('coinName')!='摩拉' or not .75<=_number(p.get('coinScore'))<=1:
        raise ValueError('actual primary Mora identity model missing; diagnostic image is not proof')

def entry_global_header(value,name,character,s):
    if name.get('nameSource')!='talent_global_header' or name.get('nameBoxMethod')!='whole_header_ocr_box_contains_name':
        raise ValueError('talent entry identity must use the current global header raw box')
    box=_rect(name.get('nameRegion'));menu=_rect(value.get('menuRegion'))
    if box!=tuple(round(v*s) for v in (130,20,320,85)) or menu!=tuple(round(v*s) for v in (40,390,320,100)):
        raise ValueError('talent global header/menu outside reviewed exact geometry')
    values=name.get('nameRows');menu_rows=value.get('menuRows')
    if not isinstance(values,list) or len(values)!=1 or not isinstance(menu_rows,list) or len(menu_rows)!=1:
        raise ValueError('talent global header/menu must have one complete original row')
    header=rows_text(values,box,s);label=rows_text(menu_rows,menu,s)
    for row,bounds in ((values[0],box),(menu_rows[0],menu)):
        r=_rect(row['bounds'])
        if min(r[1]-bounds[1],bounds[1]+bounds[3]-r[1]-r[3])<2*s:raise ValueError('talent global header/menu full row clipped')
    match=re.fullmatch(r'(火|水|风|雷|草|冰|岩)元素/([^/]+)',header)
    if (name.get('headerRaw')!=''.join(row['text'] for row in values) or not match or match[2]!=clean(character)
            or name.get('name')!=match[2] or name.get('headerElement')!=match[1] or label!='天赋'):
        raise ValueError('talent current complete element/name must derive from the original global header')


def entry_observation(value,character,start,finish,global_header=False):
    s=frame(value,start,finish)
    if (value.get('phase')!='talent_entry_observation' or value.get('focused') is not True or value.get('overview') is not True
            or value.get('promptVisible') is not False or value.get('reviveVisible') is not False):
        raise ValueError('talent entry current focused known page required')
    name=value.get('character');frame(name,start,finish)
    if (name.get('observedAt')!=value['observedAt'] or (name['width'],name['height'])!=(value['width'],value['height'])
            or name.get('overview') is not True):
        raise ValueError('talent entry full current character identity unverified')
    if global_header:entry_global_header(value,name,character,s)
    else:
        name_box=character_region(name)
        if (name.get('nameSource','attribute_right_full_name')!='attribute_right_full_name' or clean(name.get('name'))!=clean(character)
                or len(name.get('nameRows',[]))!=1 or rows_text(name['nameRows'],name_box,s)!=clean(character)):
            raise ValueError('legacy talent entry full current character identity unverified')
        r=_rect(name['nameRows'][0]['bounds'])
        if min(r[1]-name_box[1],name_box[1]+name_box[3]-r[1]-r[3])<2*s:raise ValueError('talent entry character cropped')
    box=region(value,'region',(1536,0,384,900));raw_rows=value.get('rows')
    if not isinstance(raw_rows,list):raise ValueError('talent entry complete original rows missing')
    candidates=[]
    for row in raw_rows:
        if not isinstance(row.get('text'),str) or not _inside(_rect(row.get('bounds')),box):raise ValueError('talent list raw row outside fixed ROI')
        text=clean(row['text']);match=re.fullmatch(r'(?:Lv\.?|等级)?([0-9]{1,2})',text,re.IGNORECASE)
        if match and 1<=int(match[1])<=15:candidates.append(row)
    candidates.sort(key=lambda row:row['bounds']['y'])
    if len(candidates)!=3 or value.get('candidates')!=candidates:raise ValueError('talent candidates are not exactly the three raw-derived ordered level rows')
    for row in candidates:
        b=_rect(row['bounds'])
        if min(b[0]-box[0],b[1]-box[1],box[0]+box[2]-b[0]-b[2],box[1]+box[3]-b[1]-b[3])<2*s:raise ValueError('talent candidate needs complete four-edge bounds')
    if any(_rect(candidates[i]['bounds'])[1]+_rect(candidates[i]['bounds'])[3]>=_rect(candidates[i+1]['bounds'])[1] for i in range(2)):
        raise ValueError('talent candidate boxes overlap or lose row order')
    return candidates

def rolling_identity(evidence,frames,names,character,start,finish):
    if (evidence.get('characterIdentityMethod')!='bounded_rolling_exact_triple'
            or type(evidence.get('characterIdentityObservationLimitMs')) is not int or evidence['characterIdentityObservationLimitMs']!=12000
            or type(evidence.get('characterIdentityPollMs')) is not int or evidence['characterIdentityPollMs']!=300):
        raise ValueError('unreviewed character rolling observation method/limits')
    trials=evidence.get('characterIdentityTrials')
    originals=[f for f in frames if f.get('phase')=='character_identity_observation']
    if (not isinstance(trials,list) or not 3<=len(trials)<=41 or trials!=originals or names!=trials[-3:]
            or frames[:len(trials)]!=trials or trials[-1]['observedAt']-trials[0]['observedAt']>=12000):
        raise ValueError('rolling character trials must retain the complete raw prefix and final accepted triple')
    valid=[]
    for index,n in enumerate(trials):
        s=frame(n,start,finish);box=_rect(n.get('nameRegion'));raw_rows=n.get('nameRows')
        if (box!=tuple(round(v*s) for v in (1420,110,360,68)) or type(n.get('overview')) is not bool
                or not isinstance(n.get('name'),str) or not isinstance(raw_rows,list)
                or any(not isinstance(r.get('text'),str) or not _inside(_rect(r.get('bounds')),box) for r in raw_rows)
                or clean(n['name'])!=''.join(clean(r['text']) for r in raw_rows)
                or index and n['observedAt']-trials[index-1]['observedAt']<300):
            raise ValueError('rolling trial original name rows/geometry/poll timing invalid')
        exact=n['overview'] and len(raw_rows)==1 and clean(n['name'])==clean(character)
        if exact:
            r=_rect(raw_rows[0]['bounds'])
            exact=min(r[0]-box[0],r[1]-box[1],box[0]+box[2]-r[0]-r[2],box[1]+box[3]-r[1]-r[3])>=2*s
        valid.append(exact)
        if index>=2 and all(valid[-3:]) and n['observedAt']-trials[index-2]['observedAt']<=5000 and all(trials[j]['observedAt']-trials[j-1]['observedAt']<=5000 for j in (index-1,index)):
            if index!=len(trials)-1:raise ValueError('rolling observation continued after the first verified exact triple')
            break
    else:raise ValueError('rolling final triple lacks independent full-name proof')

def entry_triple(values,character,start,finish,global_header,completed_at=None):
    result=[entry_observation(f,character,start,finish,global_header) for f in values]
    pair(values[0],values[1]);pair(values[1],values[2])
    if completed_at is not None and (completed_at<values[2]['observedAt'] or completed_at-values[1]['observedAt']>1500
            or completed_at-values[2]['observedAt']>1500):raise ValueError('entry triple is not fresh at the actual third-frame read completion')
    for a,b in ((values[0]['character'],values[1]['character']),(values[1]['character'],values[2]['character'])):
        if a.get('nameSource')!=b.get('nameSource') or clean(a.get('headerRaw',''))!=clean(b.get('headerRaw','')):
            raise ValueError('talent current global header/source changed between picked and click frames')
    for index in range(3):
        a,b,c=(_rect(v[index]['bounds']) for v in result)
        center_y=lambda r:r[1]+int(r[3])//2
        center_x=lambda r:r[0]+int(r[2])//2
        if abs(center_y(a)-center_y(b))>6 or abs(center_y(b)-center_y(c))>6 or abs(center_x(b)-center_x(c))>6:
            raise ValueError('talent entry pair/click geometry not stably bound')
        if len({clean(v[index]['text']) for v in result})!=1:raise ValueError('talent entry raw level text changed')
    return result


def entry_binding(evidence,frames,character,talent_type,start,finish,names,details):
    selected=evidence.get('twoPickedEntryFrames');click=evidence.get('entryClickFrame')
    if not isinstance(selected,list) or len(selected)!=2 or not isinstance(click,dict):raise ValueError('explicit two picked entry frames and fresh click frame required')
    all_entries=[f for f in frames if f.get('phase')=='talent_entry_observation']
    global_header=('talentEntryIdentitySource' in evidence or any('menuRegion' in f or 'menuRows' in f
        or isinstance(f.get('character'),dict) and (f['character'].get('nameSource')=='talent_global_header'
        or f['character'].get('nameBoxMethod')=='whole_header_ocr_box_contains_name' or f['character'].get('headerRaw')
        or f['character'].get('headerElement')) for f in all_entries))
    if global_header:
        if evidence.get('talentEntryIdentitySource')!='talent_global_header':raise ValueError('talent global header source cannot downgrade to legacy entry identity')
        for n in evidence.get('characterIdentityTrials',names):
            if (n.get('nameSource')!='attribute_right_full_name' or n.get('nameBoxMethod')!='actual_name_ocr_box'
                    or n.get('headerRaw','')!='' or n.get('headerElement','')!=''):
                raise ValueError('initial attribute identity cannot be replaced by a talent header')
    if any(f not in all_entries for f in [*selected,click]) or selected[0]==selected[1] or click in selected:
        raise ValueError('explicit entry references are not independent actual raw frames')
    positions=[all_entries.index(f) for f in [*selected,click]]
    if positions[1]!=positions[0]+1 or positions[2]!=positions[1]+1:raise ValueError('picked entry pair/click must be consecutive original observations')
    if selected[0]['observedAt']<=names[-1]['observedAt'] or click['observedAt']>=details[0]['observedAt']:
        raise ValueError('entry click out of this character-to-detail sequence')
    if not all_entries or click['observedAt']-all_entries[0]['observedAt']>12000:raise ValueError('talent entry bounded observation deadline exceeded')
    if any(f['observedAt']<names[-1]['observedAt'] or f['observedAt']>click['observedAt'] for f in all_entries):
        raise ValueError('extra entry observations outside original pre-click sequence')
    rolling_keys=('talentEntryObservationMethod','talentEntryObservationLimitMs','talentEntryObservationPollMs')
    rolling=any(key in evidence for key in rolling_keys)
    if rolling:
        if (evidence.get('talentEntryObservationMethod')!='bounded_contiguous_entry_triple'
                or type(evidence.get('talentEntryObservationLimitMs')) is not int or evidence['talentEntryObservationLimitMs']!=12000
                or type(evidence.get('talentEntryObservationPollMs')) is not int or evidence['talentEntryObservationPollMs']!=300
                or not global_header or not 3<=len(all_entries)<=41 or [*selected,click]!=all_entries[-3:]
                or click['observedAt']-all_entries[0]['observedAt']>=12000):
            raise ValueError('bounded entry rolling method/limits/final contiguous triple invalid')
        for index,f in enumerate(all_entries):
            completed=integer(f.get('readCompletedAt'),0,9223372036854775807)
            if (f.get('focused') is not True or f.get('promptVisible') is not False or f.get('reviveVisible') is not False
                    or not f['observedAt']<=completed<=finish or index and f['observedAt']-all_entries[index-1]['readCompletedAt']<300):
                raise ValueError('entry observation cannot continue after focus/prompt/revive abort or shorten polling')
        if click['readCompletedAt']-all_entries[0]['observedAt']>=12000:raise ValueError('entry completion cannot extend the original observation deadline')
        for index in range(len(all_entries)-3):
            try:entry_triple(all_entries[index:index+3],character,start,finish,global_header,all_entries[index+2]['readCompletedAt'])
            except ValueError:continue
            raise ValueError('entry rolling observation continued after the first legal contiguous triple')
    result=entry_triple([*selected,click],character,start,finish,global_header,click['readCompletedAt'] if rolling else None)
    picked=result[-1][TYPES.index(talent_type)]
    level=int(re.fullmatch(r'(?:Lv\.?|等级)?([0-9]{1,2})',clean(picked['text']),re.IGNORECASE)[1])
    if level!=integer(details[0].get('displayLevel'),1,13):raise ValueError('requested talent index does not bind to the actual clicked detail level')
def detail(d,talent_type,start,finish):
    s=frame(d,start,finish)
    if d.get('page') is not True or d.get('type')!=talent_type: raise ValueError('talent detail type/page mismatch')
    title=rows_text(d.get('titleRows'),region(d,'titleRegion',(20,120,540,52)),s)
    actual_type=rows_text(d.get('typeRows'),region(d,'typeRegion',(242,13,98,36)),s,full=False)
    raw=rows_text(d.get('levelRows'),region(d,'levelRegion',(240,160,100,52)),s,full=False)
    match=re.fullmatch(r'(?:等级|Lv\.?)?([1-9]|1[0-3])',raw,re.IGNORECASE)
    if title!=clean(d.get('title')) or not title or actual_type!=talent_type or clean(d.get('levelRaw'))!=raw or not match:
        raise ValueError('talent full title/type/level raw mismatch')
    display=integer(d.get('displayLevel'),1,13);base=integer(d.get('baseLevel'),1,9)
    if int(match[1])!=display: raise ValueError('detail display level differs from raw OCR')
    glyph=_rect(d.get('glyphRegion'));sample=_rect(d.get('colorSampleRegion'))
    level=_rect(d.get('levelRegion'))
    if not _inside(glyph,sample) or not _inside(level,sample) or glyph!=_rect(d['levelRows'][0]['bounds']) or len(d['levelRows'])!=1:
        raise ValueError('color sample is not the complete actual level glyph')
    minimum=max(20,math.ceil(glyph[2]*glyph[3]*.08));bright=integer(d.get('brightPixels'));neutral=integer(d.get('neutralPixels'));cyan=integer(d.get('cyanPixels'));dark=integer(d.get('darkConflicts'))
    bonus=clean(d.get('bonusRaw'));region(d,'bonusRegion',(35,285,146,30))
    explicit=re.fullmatch(r'天赋等级\+3',bonus) is not None
    if d.get('glyphColor')=='Neutral' and bright>=minimum and neutral<=bright and neutral/bright>=.95 and cyan==0 and dark<minimum:
        plus=False
        if explicit or any(part in bonus for part in ('+','天赋','等级')): raise ValueError('neutral level conflicts with bonus marker')
    elif d.get('glyphColor')=='Cyan' and bright>=minimum and cyan<=bright and cyan/bright>=.95 and neutral/bright<=.01 and explicit and display>=4:
        plus=True
    else: raise ValueError('talent glyph color/+3 evidence unverified')
    if d.get('hasFixedPlusThree') is not plus or base!=display-(3 if plus else 0): raise ValueError('base talent level/+3 mismatch')
    return title,base,display,plus
def preview(p,current,start,finish,*,trusted_runtime_root=None):
    s=frame(p,start,finish)
    if p.get('page') is not True or p.get('current')!=current or p.get('next')!=current+1: raise ValueError('preview next basic level mismatch')
    for key,value,ref in (('currentLevelRows',current,(760,245,160,65)),('nextLevelRows',current+1,(1000,245,170,65))):
        region_key='currentLevelRegion' if key=='currentLevelRows' else 'nextLevelRegion'
        raw_key='currentLevelRaw' if key=='currentLevelRows' else 'nextLevelRaw'
        if rows_text(p.get(key),region(p,region_key,ref),s,full=False)!=f'等级{value}' or clean(p.get(raw_key))!=f'等级{value}': raise ValueError('preview raw next-level label mismatch')
    names=[clean(row.get('text')) for row in p.get('rows',[])]
    marker=region(p,'markerRegion',(420,235,1100,750))
    rows_text(p.get('rows'),marker,s,full=False)
    if any(names.count(name)!=1 for name in ('属性变更','所需材料','取消','确认')): raise ValueError('full upgrade popup markers missing')
    materials=preview_materials(p)
    marker=cost_method(p)
    if (marker==PINNED_SPLIT_METHOD and any(not modern_split(item.get('quantity',{})) for item in materials)
            or marker!=PINNED_SPLIT_METHOD and any(quantity_chain_modern(item.get('quantity',{})) for item in materials)):
        raise ValueError('talent popup method and every material split proof must agree')
    result=[]
    for item in materials:
        name=material_name(item.get('name'));card=_rect(item.get('card'));icon=_rect(item.get('iconRegion'))
        if not name or not .75<=_number(item.get('iconScore'))<=1 or not _inside(card,(p['width']*.2,p['height']*.5,p['width']*.6,p['height']*.25)) or not _inside(icon,card):
            raise ValueError('actual material card identity/geometry unverified')
        if not _inside(_rect(item['quantity']['bounds']),card) or item['quantity']['observedAt']!=p['observedAt']: raise ValueError('material quantity outside actual card/frame')
        material_crop(item,p,start,finish,trusted_runtime_root=trusted_runtime_root)
        owned,required=quantity(item['quantity'],start,finish,trusted_runtime_root=trusted_runtime_root)
        result.append({'name':name,'owned':owned,'required':required})
    if len({item['name'] for item in result})!=len(result): raise ValueError('duplicate material identity')
    if quantity_chain_modern(p['mora']):raise ValueError('pinned material split metadata cannot authenticate Mora ratio')
    coin_identity(p);mora_crop(p['mora'],p,start,finish,trusted_runtime_root=trusted_runtime_root)
    if p['mora']['observedAt']!=p['observedAt']: raise ValueError('Mora cost not from the same actual popup')
    owned,required=quantity(p['mora'],start,finish)
    return result,{'owned':owned,'required':required}


def verified_observation(raw,character,talent_type,started_at,finished_at,*,trusted_runtime_root=None):
    start,finish=_time(started_at),_time(finished_at)
    if (not isinstance(raw,dict) or raw.get('schemaVersion')!=1 or raw.get('task')!='talent-upgrade-inspection'
            or raw.get('status')!='success' or raw.get('readOnly') is not True or raw.get('evidenceVerified') is not True
            or raw.get('mainUiRestored') is not True or raw.get('confirmationSubmitted') is not False
            or raw.get('characterName')!=character or raw.get('talentType')!=talent_type or talent_type not in TYPES):
        raise ValueError('single-talent readonly observation scope/cleanup mismatch')
    evidence=raw.get('evidence',{});frames=evidence.get('rawFrames',[]);names=evidence.get('characterIdentity',[])
    if (evidence.get('characterSelectionAfterIdentity') is not False or evidence.get('tooltipRequirementUsedAsUpgradeCost') is not False
            or not isinstance(frames,list) or not isinstance(names,list) or len(names)!=3): raise ValueError('raw character/identity carryover evidence missing')
    for index,f in enumerate(frames):
        frame(f,start,finish)
        if index and (f['observedAt']<=frames[index-1]['observedAt'] or (f['width'],f['height'])!=(frames[0]['width'],frames[0]['height'])):
            raise ValueError('raw frame timeline is duplicated, unordered or changes game client')
    if (any(key in evidence for key in ('characterIdentityMethod','characterIdentityTrials','characterIdentityObservationLimitMs','characterIdentityPollMs'))
            or any(f.get('phase')=='character_identity_observation' for f in frames)):
        rolling_identity(evidence,frames,names,character,start,finish)
    for n in names:
        s=frame(n,start,finish)
        box=character_region(n)
        if n not in frames or n.get('overview') is not True or clean(n.get('name'))!=clean(character) or rows_text(n.get('nameRows'),box,s)!=clean(character):
            raise ValueError('actual full character name not independently observed')
        if any(min(_rect(row['bounds'])[1]-box[1],box[1]+box[3]-_rect(row['bounds'])[1]-_rect(row['bounds'])[3])<2*s for row in n['nameRows']):
            raise ValueError('complete character name must clear all four ROI edges')
    pair(names[0],names[1]);pair(names[1],names[2])
    if names[2]['observedAt']-names[0]['observedAt']>5000: raise ValueError('character triple stale')
    details=[f for f in frames if 'displayLevel' in f]
    if len(details)!=2 or details[0]['observedAt']<=names[2]['observedAt']: raise ValueError('selected talent details not after actual character identity')
    pair(*details);a=detail(details[0],talent_type,start,finish);b=detail(details[1],talent_type,start,finish)
    if a!=b or evidence.get('detailIdentityCarryover')!=details[1] or raw.get('talentName')!=b[0]: raise ValueError('talent detail pair/carryover title mismatch')
    if (any(key in evidence for key in ('talentEntryObservationMethod','talentEntryObservationLimitMs','talentEntryObservationPollMs'))
            or 'talentEntryIdentitySource' in evidence or 'characterIdentityMethod' in evidence or 'twoPickedEntryFrames' in evidence
            or 'entryClickFrame' in evidence or any(f.get('phase')=='talent_entry_observation' for f in frames)):
        entry_binding(evidence,frames,character,talent_type,start,finish,names,details)
    previews=[f for f in frames if 'materials' in f and 'current' in f]
    if len(previews)<2 or len(previews)%2 or previews[0]['observedAt']<=details[1]['observedAt'] or evidence.get('preview')!=previews[-1]: raise ValueError('independent full next-cost popup pair missing')
    preview_timing(raw,previews,start,finish,trusted_runtime_root=trusted_runtime_root)
    method=cost_method(raw)
    if any(cost_method(p)!=method for p in previews):raise ValueError('payload and every popup quantity method must agree')
    pinned_proof=None
    for p in previews:
        for item in preview_materials(p):
            q=item['quantity']
            for reading in (q,q.get('initialReading')):
                if reading is not None and modern_split(reading):
                    split_model_shape(reading)
                    if pinned_proof is not None and reading['splitModelEvidence']!=pinned_proof:
                        raise ValueError('all material and popup split model proofs must be identical')
                    pinned_proof=reading['splitModelEvidence']
    costs=None
    for index in range(0,len(previews),2):
        pair(previews[index],previews[index+1])
        for p in previews[index:index+2]:
            actual=preview(p,b[1],start,finish,trusted_runtime_root=trusted_runtime_root)
            if costs is not None and costs!=actual: raise ValueError('costs changed across actual popup observations')
            costs=actual
    tooltips=evidence.get('materialTooltips',[])
    if len(tooltips)!=len(costs[0]): raise ValueError('not every actual material has full tooltip identity')
    for item,two in zip(costs[0],tooltips):
        if not isinstance(two,list) or len(two)!=2: raise ValueError('material tooltip pair missing')
        pair(*two)
        for tip in two:
            s=frame(tip,start,finish)
            if tip not in frames or tip.get('page') is not True or material_name(tip.get('name'))!=item['name']: raise ValueError('tooltip identity not tied to actual material card')
            box=region(tip,'nameRegion',(730,168,440,67));candidates=[]
            for rows_key,raw_key,projected in (('nameRows','rawName',False),('alternateNameRows','alternateRawName',True)):
                try:
                    actual_name=rows_text(tip.get(rows_key),box,s,projected=projected)
                    if actual_name==clean(tip.get(raw_key)) and (not projected or tip.get('alternateNameScale')==4
                            and tip.get('alternateNamePreprocessing')=='gray_threshold_210_inverse_cubic_4x'): candidates.append(material_name(actual_name))
                except ValueError: pass
            kind=rows_text(tip.get('kindRows'),region(tip,'kindRegion',(730,230,440,65)),s)
            sources=[clean(row.get('text')) for row in tip.get('sourceRows',[])]
            rows_text(tip.get('sourceRows'),region(tip,'sourceRegion',(730,690,460,65)),s,full=False)
            if item['name'] not in candidates or kind!=tip.get('kind') or kind not in ('角色天赋素材','角色与武器培养素材') or sources.count('来源')!=1:
                raise ValueError('fullnamed actual material tooltip unverified')
            footer=rows_text(tip.get('footerLabelRows'),region(tip,'footerLabelRegion',(725,890,470,65)),s,full=False)
            if not footer.startswith('培养需求'): raise ValueError('actual cultivation footer label missing')
            region(tip['quantity'],'bounds',(885,890,295,65))
            if quantity(tip['quantity'],start,finish,'培养需求',trusted_runtime_root=trusted_runtime_root)[0]!=item['owned']: raise ValueError('tooltip actual owned differs from popup owned')
        if two[0]['observedAt']<=previews[1]['observedAt'] or two[1]['observedAt']>=previews[-1]['observedAt']: raise ValueError('tooltip read out of this cost-preview sequence')
    worlds=[f for f in frames if f.get('phase')=='world_restore']
    if len(worlds)<2: raise ValueError('world cleanup independent frames missing')
    pair(worlds[-2],worlds[-1])
    for world in worlds[-2:]:
        frame(world,start,finish)
        if world.get('focused') is not True or world.get('worldVerified') is not True or world['observedAt']<=previews[-1]['observedAt']: raise ValueError('world cleanup raw proof missing')
    integer(raw.get('currentBaseLevel'),1,9);integer(raw.get('nextBaseLevel'),2,10)
    for item in [*raw.get('materials',[]),raw.get('mora',{})]:
        integer(item.get('owned'));integer(item.get('required'),1)
    if raw.get('materials')!=costs[0] or raw.get('mora')!=costs[1] or raw.get('currentBaseLevel')!=b[1] or raw.get('nextBaseLevel')!=b[1]+1 or abs(_time(raw.get('observedAt'))-previews[-1]['observedAt'])>1:
        raise ValueError('declared next talent costs differ from independently parsed raw UI')
    return {'talentName':b[0],'currentBaseLevel':b[1],'nextBaseLevel':b[1]+1,'materials':costs[0],'mora':costs[1]}


def verify_talent_preview(packet,character,talent_type,started_at,finished_at,*,trusted_runtime_root=None):
    if (not isinstance(packet,dict) or packet.get('readOnly') is not True or packet.get('targetReached') is not False
            or type(packet.get('completedUpgrades')) is not int or packet.get('completedUpgrades')!=0 or packet.get('selectedTalentType')!=talent_type): raise ValueError('talent preview read-only summary scope invalid')
    if packet.get('evidenceVerified') is not True:
        if packet.get('costs') is not None: raise ValueError('unknown talent preview costs must remain null')
        return False
    actual=verified_observation(packet.get('nativeObservation'),character,talent_type,started_at,finished_at,trusted_runtime_root=trusted_runtime_root)
    if packet.get('costs')!=actual: raise ValueError('talent preview summary differs from raw evidence')
    return True
