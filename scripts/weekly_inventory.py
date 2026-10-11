"""Independent raw checks for four fixed read-only weekly material stacks."""
import math
import re
import unicodedata
try:
    from .backpack_inventory_evidence import _number, _rect, _inside, _time
except ImportError:
    from backpack_inventory_evidence import _number, _rect, _inside, _time

MATERIALS = (
    {'materialId': '113060', 'materialName': '残火灯烛', 'category': 'characterDevelopmentItems'},
    {'materialId': '113061', 'materialName': '丝织之羽', 'category': 'characterDevelopmentItems'},
    {'materialId': '113062', 'materialName': '否定裁断', 'category': 'characterDevelopmentItems'},
    {'materialId': '113021', 'materialName': '异梦溶媒', 'category': 'preciousItems'},
)
SOURCE = 'weekly_conversion_backpack_selected_stack'
HEADER_ALIASES={'characterDevelopmentItems':('角色培养道具','养成道具'),'preciousItems':('贵重道具',)}
MODEL_ASSETS=(
    ('PpOcrDetV4','Assets/Model/PaddleOCR/Det/V4/PP-OCRv4_mobile_det_infer/slim.onnx'),
    ('PpOcrRecV4','Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/slim.onnx'),
    ('PpOcrRecV6','Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/slim.onnx'),
    ('PpOcrRecV4-labels','Assets/Model/PaddleOCR/Rec/V4/PP-OCRv4_mobile_rec_infer/inference.yml'),
    ('PpOcrRecV6-labels','Assets/Model/PaddleOCR/Rec/V6/PP-OCRv6_small_rec_infer/inference.yml'),
)


def clean(value):
    if not isinstance(value, str):
        raise ValueError('weekly raw text missing')
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value))


def integer(value, minimum=0, maximum=999999999):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('weekly integer invalid')
    return value


def rect(value):
    box = _rect(value)
    if any(type(value[k]) is not int for k in ('x', 'y', 'width', 'height')):
        raise ValueError('weekly native rectangle must contain integers')
    return box


def rows(value, box, scale):
    if not isinstance(value, list) or not value:
        raise ValueError('weekly raw OCR rows missing')
    for row in value:
        r = rect(row)
        if not _inside(r, box) or min(r[0]-box[0], r[1]-box[1], box[0]+box[2]-r[0]-r[2], box[1]+box[3]-r[1]-r[3]) < 2*scale:
            raise ValueError('weekly raw OCR row clipped')
    return [clean(row.get('text')) for row in value]


def dimensions(frame, start, finish):
    w, h = integer(frame.get('width'), 800, 4096), integer(frame.get('height'), 450, 2160)
    at = _number(frame.get('stack', {}).get('observedAt', frame.get('observedAt')))
    if w*9 != h*16 or not start <= at <= finish:
        raise ValueError('weekly dimensions or current-run time invalid')
    return w/1920


def border(raw, item, w, h):
    if (not isinstance(raw, dict) or raw.get('verified') is not True or raw.get('method') != 'four_side_neutral_outline'
            or raw.get('minimumChannel') != 225 or raw.get('maximumSpread') != 35 or raw.get('minimumFraction') != .9
            or not isinstance(raw.get('sides'), list) or len(raw['sides']) != 4):
        raise ValueError('weekly raw selection border missing')
    x, y, width, height = item
    radius = max(3, round(width*8/125))
    for index, side in enumerate(raw['sides']):
        vertical = index < 2
        edge = (x, x+width-1, y, y+height-1)[index]
        begin = y+math.trunc(height*.2) if vertical else x+math.trunc(width*.12)
        end = y+math.trunc(height*.75) if vertical else x+math.trunc(width*.55)
        coordinate = integer(side.get('coordinate'), 0, w-1 if vertical else h-1)
        samples = integer(side.get('sampleCount'), 1)
        neutral = integer(side.get('neutralCount'))
        if side.get('axis') != ('x' if vertical else 'y') or abs(coordinate-edge) > radius or samples != end-begin or neutral > samples or neutral/samples < .9:
            raise ValueError('weekly raw border geometry or neutral fraction invalid')
        positions = list(range(begin, end, max(1, math.trunc((end-begin)/12))))
        pixels = side.get('samples')
        if not isinstance(pixels, list) or len(pixels) != len(positions):
            raise ValueError('weekly raw border pixel samples incomplete')
        actual_neutral = 0
        for pixel, p in zip(pixels, positions):
            px, py = integer(pixel.get('x'), 0, w-1), integer(pixel.get('y'), 0, h-1)
            if (px if vertical else py) != coordinate or (py if vertical else px) != p:
                raise ValueError('weekly raw border pixel positions invalid')
            channels = [integer(pixel.get(k), 0, 255) for k in ('b', 'g', 'r')]
            actual_neutral += min(channels) >= 225 and max(channels)-min(channels) <= 35
        if actual_neutral/len(positions) < .9 or actual_neutral > neutral or neutral-actual_neutral > samples-len(positions):
            raise ValueError('weekly border raw pixels contradict selection')


def _trusted_model_assets(root):
    try:
        if __package__:
            from .named_count_model_assets import read_named_count_model_assets
        else:
            from named_count_model_assets import read_named_count_model_assets
        actual=read_named_count_model_assets(root)
    except (OSError,RuntimeError) as error:
        raise ValueError('weekly independent fixed model assets unavailable') from error
    expected={'rawPaddleConfig':8,'rawPaddleName':'V6','fixedDetectorConfig':7,'fixedDetectorName':'V4'}
    if not isinstance(actual,dict) or any(type(actual.get(k)) is not type(v) or actual[k]!=v for k,v in expected.items()):
        raise ValueError('weekly independent configured/fixed model identity differs')
    return actual.get('assets')


def model_identity(reading,actual_assets):
    m=reading.get('modelEvidence');fixed={'rawPaddleConfig':8,'rawPaddleName':'V6','fixedDetectorConfig':7,'fixedDetectorName':'V4',
        'pinMethod':'actual_bundled_open_read_sha256_hold_session'}
    if (not isinstance(m,dict) or type(reading.get('rawPaddleReadback')) is not int or reading['rawPaddleReadback']!=8
            or any(type(m.get(k)) is not type(v) or m[k]!=v for k,v in fixed.items())
            or not isinstance(m.get('assets'),list) or len(m['assets'])!=5):raise ValueError('weekly count fixed models/config readback missing')
    for asset,(name,path) in zip(m['assets'],MODEL_ASSETS):
        if (not isinstance(asset,dict) or asset.get('modelName')!=name or asset.get('relativePath')!=path
                or not isinstance(asset.get('sha256'),str) or not re.fullmatch(r'[0-9a-fA-F]{64}',asset['sha256'])):
            raise ValueError('weekly model asset identity/path/fingerprint invalid')
        integer(asset.get('length'),1,2147483647)
    normalized=[{**a,'sha256':a['sha256'].lower()} for a in m['assets']]
    if actual_assets is None or normalized!=actual_assets:raise ValueError('weekly model assets must match the independently read trusted runtime')


def named_count(reading,item,scale,actual_assets):
    fixed={'method':'grid_hsv_foreground_exact_dual_ocr','sourceScale':3,'maximumSaturation':140,'maximumValue':210,
        'minimumComponentArea':20,'minimumComponentHeight':12,'minimumComponentBottomRatio':.55,
        'maximumComponentAspectRatio':3.0,'glyphHeight':48,'horizontalPadding':24,'verticalPadding':24,'topPaddingReference':8,'bottomPaddingReference':8,
        'ocrScale':1,'detectorModel':'PaddleV4_fixed','rawModel':'configured_native_paddle_without_detector',
        'sourceInterpolation':'linear','glyphInterpolation':'nearest','ocrInterpolation':'nearest'}
    if not isinstance(reading,dict) or any((type(reading.get(k)) not in (int,float) if type(v) is float else type(reading.get(k)) is not type(v)) or reading[k]!=v for k,v in fixed.items()):
        raise ValueError('weekly named-count fixed preprocessing method missing')
    model_identity(reading,actual_assets)
    x,y,w,h=item;pad=max(1,round(8*w/125));source=(x+math.trunc(w*5/125),y+math.trunc(h*128/153)-pad,math.trunc(w*120/125)-math.trunc(w*5/125),
        math.trunc(h*150/153)-math.trunc(h*128/153)+2*pad)
    if rect(reading.get('sourceRegion'))!=source:raise ValueError('weekly count source must use the exact grid crop and bounded vertical padding')
    all_components=reading.get('allComponents');components=reading.get('components')
    if not isinstance(all_components,list) or not 1<=len(all_components)<=1000 or not isinstance(components,list):raise ValueError('weekly original mask contours missing')
    boxes=[rect(c) for c in all_components];mask=(0,0,source[2]*3,source[3]*3)
    if any(not _inside(b,mask) for b in boxes) or boxes!=sorted(boxes,key=lambda b:(b[0],b[1])):raise ValueError('weekly mask component bounds/order invalid')
    selected=[c for c,b in zip(all_components,boxes) if b[2]>1 and b[3]>=12 and b[2]*b[3]>=20 and b[1]+b[3]>=mask[3]*.55 and b[2]/b[3]<=3]
    if not selected or components!=selected:raise ValueError('weekly foreground components not exactly derived from all original contours')
    boxes=[rect(c) for c in selected];left=min(b[0] for b in boxes);top=min(b[1] for b in boxes)
    f=(left,top,max(b[0]+b[2] for b in boxes)-left,max(b[1]+b[3] for b in boxes)-top)
    glyph=max(1,round(f[2]*48/f[3]));canvas=(0,0,glyph+48,96)
    expected_fg=(source[0]+math.floor(f[0]/3),source[1]+math.floor(f[1]/3),
        math.ceil((f[0]+f[2])/3)-math.floor(f[0]/3),math.ceil((f[1]+f[3])/3)-math.floor(f[1]/3))
    if (rect(reading.get('foregroundBounds'))!=f or rect(reading.get('foregroundSourceBounds'))!=expected_fg
            or integer(reading.get('glyphWidth'),1)!=glyph or integer(reading.get('normalizedWidth'),1)!=canvas[2]
            or integer(reading.get('normalizedHeight'),1)!=96 or integer(reading.get('ocrInputWidth'),1)!=canvas[2]
            or integer(reading.get('ocrInputHeight'),1)!=96):raise ValueError('weekly foreground union/normalization geometry differs from raw contours')
    for key in ('sourcePixelsSha256','maskPixelsSha256','normalizedPixelsSha256','ocrInputPixelsSha256'):
        if not isinstance(reading.get(key),str) or not re.fullmatch(r'[0-9a-fA-F]{64}',reading[key]):raise ValueError('weekly original preprocessing pixel fingerprints missing')
    if reading['ocrInputPixelsSha256']!=reading['normalizedPixelsSha256']:raise ValueError('weekly fixed detector/raw OCR must use the same original canvas')
    detector=reading.get('detectorRows');projected=reading.get('sourceRows')
    if not isinstance(detector,list) or len(detector)!=1 or not isinstance(projected,list) or len(projected)!=1:raise ValueError('weekly independent exact OCR rows missing')
    row=detector[0];b=rect(row);input_box=canvas;margin=max(2,2*scale*48*3/f[3])
    if not _inside(b,input_box) or min(b[0],b[1],input_box[2]-b[0]-b[2],input_box[3]-b[1]-b[3])<margin:raise ValueError('weekly normalized full integer clipped')
    px=source[0]+math.floor((f[0]+(b[0]-24)*f[2]/glyph)/3);py=source[1]+math.floor((f[1]+(b[1]-24)*f[3]/48)/3)
    right=source[0]+math.ceil((f[0]+(b[0]+b[2]-24)*f[2]/glyph)/3);bottom=source[1]+math.ceil((f[1]+(b[1]+b[3]-24)*f[3]/48)/3)
    if rect(projected[0])!=(px,py,right-px,bottom-py) or row.get('text')!=projected[0].get('text'):raise ValueError('weekly source OCR row is not the actual inverse-projected detector row')
    rows(projected,source,scale);rows([dict(zip(('x','y','width','height'),expected_fg),text='')],source,scale)
    raw_value=reading.get('raw');detected=row.get('text')
    if not isinstance(raw_value,str) or not isinstance(detected,str):raise ValueError('weekly original integer OCR text missing')
    raw=re.sub(r'\s+','',raw_value)
    if raw!=re.sub(r'\s+','',detected) or not re.fullmatch(r'(0|[1-9][0-9]{0,8})',raw):raise ValueError('weekly two complete integer OCR methods disagree')
    return integer(int(raw)),source


def initial_stack(frame,stack,item,start,finish):
    initial=frame.get('initialStack')
    if not isinstance(initial,dict) or initial.get('observedAt')!=stack['observedAt'] or initial.get('countMethod')!='raw_ocr_without_detector':
        raise ValueError('weekly initial rejected stack/frame missing')
    w=frame['width'];x,y,width,height=item
    title=(math.trunc(w*.682),math.trunc(w*.0625),math.trunc(w*.256),math.trunc(w*.03125))
    amount=(x+math.trunc(width*5/125),y+math.trunc(height*128/153),math.trunc(width*120/125)-math.trunc(width*5/125),math.trunc(height*150/153)-math.trunc(height*128/153))
    if (rect(initial.get('nameRegion'))!=title or rect(initial.get('countRegion'))!=amount or not isinstance(initial.get('rawCountText'),str)
            or any(initial.get(k)!=stack.get(k) for k in ('selectedItemVerified','selectedItemRect','selectionEvidence'))):raise ValueError('weekly initial grid geometry/selection scope changed')
    for key,box in (('nameRows',title),('countRows',amount)):
        values=initial.get(key)
        if not isinstance(values,list) or any(not isinstance(r.get('text'),str) or not _inside(rect(r),box) for r in values):raise ValueError('weekly initial raw OCR rows omitted or changed')
    return initial


def frame_count(frame, target, selection, start, finish,actual_assets=None):
    s = dimensions(frame, start, finish)
    w, h = frame['width'], frame['height']
    stack = frame.get('stack', {})
    item = rect(selection.get('itemRect'))
    score = _number(frame.get('iconScore'))
    if (frame.get('gameActive') is not True or frame.get('promptVisible') is not False or frame.get('tabVerified') is not True
            or frame.get('category') != target['category'] or frame.get('iconName') != target['materialName'] or not .75 <= score <= 1
            or not _inside(item, (0, 0, w, h))):
        raise ValueError('weekly focus/category/model unverified')
    header = rect(frame.get('headerRegion'))
    expected_header = (round(100*s), 0, round(350*s), round(100*s))
    aliases=HEADER_ALIASES[target['category']]
    if header != expected_header or sum(text in aliases for text in rows(frame.get('headerRows'), header, s)) != 1:
        raise ValueError('weekly full category header unverified')
    x, y, width, height = item
    title, amount, icon = rect(stack.get('nameRegion')), rect(stack.get('countRegion')), rect(frame.get('iconRegion'))
    modern='countReading' in frame or 'initialStack' in frame or stack.get('countMethod')=='grid_hsv_foreground_exact_dual_ocr'
    initial=None;number=None
    if modern:
        initial=initial_stack(frame,stack,item,start,finish)
        number,expected_amount=named_count(frame.get('countReading'),item,s,actual_assets)
        expected_title=tuple(round(v*s) for v in (1280,110,540,78))
    else:expected_title = (math.trunc(w*.682), math.trunc(w*.0625), math.trunc(w*.256), math.trunc(w*.03125))
    if not modern:expected_amount = (x+math.trunc(width*5/125), y+math.trunc(height*128/153),
                       math.trunc(width*120/125)-math.trunc(width*5/125), math.trunc(height*150/153)-math.trunc(height*128/153))
    if (title != expected_title or amount != expected_amount or not _inside(title, (0, 0, w, h)) or not _inside(amount, (0,0,w,h) if modern else item)
            or icon != (x, y, width, round(height*125/153)) or frame.get('iconMethod') != 'cell_resize_125x153_top_125x125'
            or stack.get('selectedItemVerified') is not True or rect(stack.get('selectedItemRect')) != item
            or rows(stack.get('nameRows'), title, s) != [target['materialName']]
            or stack.get('countMethod') != ('grid_hsv_foreground_exact_dual_ocr' if modern else 'raw_ocr_without_detector') or len(stack.get('countRows', [])) != 1):
        raise ValueError('weekly full named selected-stack geometry unverified')
    detected = rows(stack['countRows'], amount, s)[0]
    raw = clean(stack.get('rawCountText'))
    if raw != detected or not re.fullmatch(r'(0|[1-9][0-9]{0,8})', raw):
        raise ValueError('weekly complete raw quantity/detector mismatch')
    if modern:
        if stack['countRows']!=frame['countReading']['sourceRows'] or stack['rawCountText']!=frame['countReading']['raw'] or int(raw)!=number:
            raise ValueError('weekly stack summary not bound to original preprocessing reading')
        old_frame={k:v for k,v in frame.items() if k not in ('countReading','initialStack')};old_frame['stack']=initial
        try:old_count=frame_count(old_frame,target,selection,start,finish)
        except ValueError:old_count=None
        if old_count is not None and old_count!=number:raise ValueError('complete initial weekly count conflicts with final count')
    border(stack.get('selectionEvidence'), item, w, h)
    return integer(int(raw))


def _verified_observation(raw, started_at, finished_at, *, trusted_runtime_root=None):
    start, finish = _time(started_at), _time(finished_at)
    ids = {m['materialId'] for m in MATERIALS}
    if (not isinstance(raw, dict) or raw.get('source') != SOURCE or raw.get('category') != 'weeklyConversion'
            or raw.get('readOnly') is not True or raw.get('status') != 'verified' or raw.get('mainUiRestored') is not True
            or raw.get('cleanupCompleted') is not True or not isinstance(raw.get('inventory'), dict)
            or not isinstance(raw.get('observations'), dict) or set(raw['inventory']) != ids or set(raw['observations']) != ids):
        raise ValueError('weekly fixed four-ID readonly scope or cleanup invalid')
    if 'rejectedObservations' in raw and (not isinstance(raw['rejectedObservations'], dict) or not set(raw['rejectedObservations']) <= ids):
        raise ValueError('weekly rejected observations outside fixed four IDs')
    result, latest, client, segments = {}, start, None, []
    actual_assets=None
    if any(isinstance(f,dict) and ('countReading' in f or 'initialStack' in f or f.get('stack',{}).get('countMethod')=='grid_hsv_foreground_exact_dual_ocr')
            for observation in raw['observations'].values() if isinstance(observation,dict) for f in (observation.get('first'),observation.get('second'))):
        if trusted_runtime_root is None:raise ValueError('weekly fixed-model profile requires a trusted runtime root')
        actual_assets=_trusted_model_assets(trusted_runtime_root)
    for target in MATERIALS:
        identifier = target['materialId']
        pair = raw['observations'][identifier]
        selection, a, b = pair.get('selection', {}), pair.get('first', {}), pair.get('second', {})
        item = rect(selection.get('itemRect'))
        clicked, x, y = (_number(selection.get(k)) for k in ('clickedAt', 'x', 'y'))
        first_at, second_at = _number(a.get('stack', {}).get('observedAt')), _number(b.get('stack', {}).get('observedAt'))
        if (not item[0] <= x <= item[0]+item[2] or not item[1] <= y <= item[1]+item[3] or not start <= clicked <= finish
                or (a.get('width'), a.get('height')) != (b.get('width'), b.get('height'))
                or not 100 <= first_at-clicked <= 5000 or not 100 <= second_at-first_at <= 5000):
            raise ValueError('weekly independent selected frame pair/time invalid')
        shape = (a.get('width'), a.get('height'))
        if client is not None and shape != client:
            raise ValueError('weekly capture client changed')
        client = shape
        first, second = frame_count(a, target, selection, start, finish,actual_assets), frame_count(b, target, selection, start, finish,actual_assets)
        aliases=HEADER_ALIASES[target['category']]
        if [clean(row.get('text')) for row in a['headerRows'] if clean(row.get('text')) in aliases] != [clean(row.get('text')) for row in b['headerRows'] if clean(row.get('text')) in aliases]:
            raise ValueError('weekly actual reviewed header changed between independent frames')
        if first != second or integer(raw['inventory'][identifier]) != second:
            raise ValueError('weekly raw pair/declared count mismatch')
        segments.append((clicked, second_at))
        latest = max(latest, second_at)
        result[identifier] = {'name': target['materialName'], 'count': second, 'status': 'exact', 'verified': True,
                              'source': SOURCE, 'evidence': {'materialId': identifier, **pair}}
    segments.sort()
    if any(segments[index][0] <= segments[index-1][1] for index in range(1, len(segments))):
        raise ValueError('weekly selected capture intervals overlap or were reused')
    if abs(_time(raw.get('observedAt'))-latest) > 1:
        raise ValueError('weekly observedAt differs from last selected stack')
    worlds = raw.get('worldFrames')
    if not isinstance(worlds, list) or len(worlds) < 2:
        raise ValueError('weekly world raw pair missing')
    previous = latest
    for world in worlds:
        dimensions(world, start, finish)
        at = _number(world.get('observedAt'))
        if (world['width'], world['height']) != client or at <= previous:
            raise ValueError('weekly raw cleanup timeline changed or duplicated')
        previous = at
    a, b = worlds[-2:]
    if (not 0 < b['observedAt']-a['observedAt'] <= 5000 or finish-b['observedAt'] > 1500
            or any(world.get('focused') is not True or world.get('world') is not True or world.get('prompt') is not False
                   or world.get('knownBag') is not False or world.get('escapeRequested') is not False for world in (a, b))):
        raise ValueError('weekly focused fresh world restoration pair unverified')
    return result


def verified_observation(raw, started_at, finished_at, *, trusted_runtime_root=None):
    try:
        return _verified_observation(raw, started_at, finished_at,trusted_runtime_root=trusted_runtime_root)
    except (AttributeError, TypeError, KeyError, IndexError, OverflowError) as error:
        raise ValueError('weekly malformed native raw evidence') from error


def verify_weekly_inventory(packet, started_at, finished_at, *, trusted_runtime_root=None):
    if (not isinstance(packet, dict) or packet.get('readOnly') is not True or packet.get('targetReached') is not False
            or type(packet.get('completedUpgrades')) is not int or packet['completedUpgrades'] != 0
            or packet.get('requestedMaterials') != list(MATERIALS) or not isinstance(packet.get('inventory'), dict)
            or set(packet['inventory']) != {m['materialId'] for m in MATERIALS} or type(packet.get('allVerified')) is not bool):
        raise ValueError('weekly diagnostic requested four-ID/read-only scope invalid')
    start, finish = _time(started_at), _time(finished_at)
    read_start, read_finish = _time(packet.get('readStartedAt')), _time(packet.get('readFinishedAt'))
    if not start <= read_start <= read_finish <= finish or read_finish-read_start > 180000:
        raise ValueError('weekly diagnostic read interval outside this run')
    if packet['allVerified']:
        actual = verified_observation(packet.get('nativeObservation'), packet['readStartedAt'], packet['readFinishedAt'],trusted_runtime_root=trusted_runtime_root)
        if packet['inventory'] != actual:
            raise ValueError('weekly exact inventory differs from independently parsed raw native evidence')
        return True
    for material in MATERIALS:
        row = packet['inventory'][material['materialId']]
        if not isinstance(row, dict) or row.get('name') != material['materialName'] or row.get('status') != 'unknown' or row.get('count') is not None:
            raise ValueError('weekly unknown cannot contain guessed/partial exact inventory')
    return False
