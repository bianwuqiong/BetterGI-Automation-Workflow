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


def frame_count(frame, target, selection, start, finish):
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
    header_name = '贵重道具' if target['category'] == 'preciousItems' else '角色培养道具'
    if header != expected_header or rows(frame.get('headerRows'), header, s).count(header_name) != 1:
        raise ValueError('weekly full category header unverified')
    x, y, width, height = item
    title, amount, icon = rect(stack.get('nameRegion')), rect(stack.get('countRegion')), rect(frame.get('iconRegion'))
    expected_title = (math.trunc(w*.682), math.trunc(w*.0625), math.trunc(w*.256), math.trunc(w*.03125))
    expected_amount = (x+math.trunc(width*5/125), y+math.trunc(height*128/153),
                       math.trunc(width*120/125)-math.trunc(width*5/125), math.trunc(height*150/153)-math.trunc(height*128/153))
    if (title != expected_title or amount != expected_amount or not _inside(title, (0, 0, w, h)) or not _inside(amount, item)
            or icon != (x, y, width, round(height*125/153)) or frame.get('iconMethod') != 'cell_resize_125x153_top_125x125'
            or stack.get('selectedItemVerified') is not True or rect(stack.get('selectedItemRect')) != item
            or rows(stack.get('nameRows'), title, s) != [target['materialName']]
            or stack.get('countMethod') != 'raw_ocr_without_detector' or len(stack.get('countRows', [])) != 1):
        raise ValueError('weekly full named selected-stack geometry unverified')
    detected = rows(stack['countRows'], amount, s)[0]
    raw = clean(stack.get('rawCountText'))
    if raw != detected or not re.fullmatch(r'(0|[1-9][0-9]{0,8})', raw):
        raise ValueError('weekly complete raw quantity/detector mismatch')
    border(stack.get('selectionEvidence'), item, w, h)
    return integer(int(raw))


def _verified_observation(raw, started_at, finished_at):
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
        first, second = frame_count(a, target, selection, start, finish), frame_count(b, target, selection, start, finish)
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


def verified_observation(raw, started_at, finished_at):
    try:
        return _verified_observation(raw, started_at, finished_at)
    except (AttributeError, TypeError, KeyError, IndexError, OverflowError) as error:
        raise ValueError('weekly malformed native raw evidence') from error


def verify_weekly_inventory(packet, started_at, finished_at):
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
        actual = verified_observation(packet.get('nativeObservation'), packet['readStartedAt'], packet['readFinishedAt'])
        if packet['inventory'] != actual:
            raise ValueError('weekly exact inventory differs from independently parsed raw native evidence')
        return True
    for material in MATERIALS:
        row = packet['inventory'][material['materialId']]
        if not isinstance(row, dict) or row.get('name') != material['materialName'] or row.get('status') != 'unknown' or row.get('count') is not None:
            raise ValueError('weekly unknown cannot contain guessed/partial exact inventory')
    return False
