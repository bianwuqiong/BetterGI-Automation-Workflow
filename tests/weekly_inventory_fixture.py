"""Anonymous synthetic native17 raw evidence; no screenshots or account inventory."""
from copy import deepcopy
from datetime import datetime, timezone
from scripts.weekly_inventory import MATERIALS, SOURCE, verified_observation

BASE = 1791734400000
START = '2026-10-11T16:00:00Z'
FINISH = '2026-10-11T16:00:04.200Z'


def rect(x, y, width, height):
    return dict(x=x, y=y, width=width, height=height)


def border(item):
    x, y, w, h = (item[k] for k in ('x', 'y', 'width', 'height'))
    sides = []
    for i, edge in enumerate((x, x+w-1, y, y+h-1)):
        vertical = i < 2
        begin, end = (y+int(h*.2), y+int(h*.75)) if vertical else (x+int(w*.12), x+int(w*.55))
        samples = [dict(x=edge if vertical else p, y=p if vertical else edge, b=240, g=240, r=240)
                   for p in range(begin, end, max(1, int((end-begin)/12)))]
        sides.append(dict(axis='x' if vertical else 'y', coordinate=edge, sampleCount=end-begin, neutralCount=end-begin, samples=samples))
    return dict(verified=True, method='four_side_neutral_outline', minimumChannel=225, maximumSpread=35, minimumFraction=.9, sides=sides)


def native_fixture():
    raw = dict(source=SOURCE, category='weeklyConversion', readOnly=True, status='verified', mainUiRestored=True,
               cleanupCompleted=True, inventory={}, observations={}, rejectedObservations={}, worldFrames=[])
    for i, material in enumerate(MATERIALS):
        identifier, name, category = (material[k] for k in ('materialId', 'materialName', 'category'))
        item = rect(110, 300, 125, 153)
        selection = dict(itemRect=item, x=172, y=365, clickedAt=BASE+100+i*1000)
        value = (7, 12, 19, 5)[i]
        def frame(at):
            stack = dict(observedAt=at, nameRegion=rect(1309, 120, 491, 60),
                nameRows=[dict(text=name, **rect(1320,126,150,20))], countRegion=rect(115,428,115,22),
                countRows=[dict(text=str(value), **rect(130,433,20,12))], countMethod='raw_ocr_without_detector',
                rawCountText=str(value), selectedItemVerified=True, selectedItemRect=deepcopy(item), selectionEvidence=border(item))
            return dict(stack=stack, width=1920, height=1080, category=category, gameActive=True, promptVisible=False,
                tabVerified=True, headerRegion=rect(100,0,350,100),
                headerRows=[dict(text='贵重道具' if category=='preciousItems' else '角色培养道具', **rect(120,24,180,30))],
                iconName=name, iconScore=.92, iconRegion=rect(110,300,125,125), iconMethod='cell_resize_125x153_top_125x125')
        raw['inventory'][identifier] = value
        raw['observations'][identifier] = dict(selection=selection, first=frame(selection['clickedAt']+300), second=frame(selection['clickedAt']+550))
    raw['observedAt'] = datetime.fromtimestamp((BASE+3650)/1000, timezone.utc).isoformat()
    raw['worldFrames'] = [dict(observedAt=BASE+t,width=1920,height=1080,focused=True,world=True,prompt=False,knownBag=False,escapeRequested=False) for t in (3800,4000)]
    return raw


def packet():
    raw = native_fixture()
    return dict(readOnly=True, targetReached=False, completedUpgrades=0, requestedMaterials=deepcopy(list(MATERIALS)),
                nativeObservation=raw, inventory=verified_observation(raw,START,FINISH), allVerified=True,
                readStartedAt=START, readFinishedAt=FINISH)


def make_unknown(value):
    value['allVerified'] = False
    value['inventory'] = {m['materialId']: dict(name=m['materialName'], count=None, status='unknown') for m in MATERIALS}
    return value
