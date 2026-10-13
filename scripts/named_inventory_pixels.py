"""Recompute same-frame selected border and exact count preprocessing pixels."""
import hashlib
try:from .named_inventory_capture import sha
except ImportError:from named_inventory_capture import sha


def verify_selected_pixels(frame,image):
    try:
        import cv2
        import numpy as np
    except ImportError as error:raise ValueError('headless exact-count verification dependency unavailable') from error
    source=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR);stack=frame['stack'];item=stack['selectedItemRect'];proof=stack['selectionEvidence'];r=frame['countReading']
    x,y,w,h=(item[k] for k in ('x','y','width','height'));radius=max(3,round(w*8/125))
    for index,side in enumerate(proof['sides']):
        vertical=index<2;edge=(x,x+w-1,y,y+h-1)[index];begin=y+int(h*.2) if vertical else x+int(w*.12);end=y+int(h*.75) if vertical else x+int(w*.55)
        best=None
        for coordinate in range(edge-radius,edge+radius+1):
            if coordinate<0 or coordinate>=(1920 if vertical else 1080):raise ValueError('selected border search outside original PNG')
            line=source[begin:end,coordinate] if vertical else source[coordinate,begin:end]
            neutral=int(np.count_nonzero((line.min(axis=1)>=225)&(line.max(axis=1).astype(int)-line.min(axis=1).astype(int)<=35)))
            if best is None or neutral>best[1]:best=(coordinate,neutral)
        if side['coordinate']!=best[0] or side['neutralCount']!=best[1] or side['sampleCount']!=end-begin:raise ValueError('selected border derived counts/coordinate differ from original pixels')
        for p in side['samples']:
            if list(map(int,source[p['y'],p['x']]))!=[p['b'],p['g'],p['r']]:raise ValueError('selected border recorded pixels differ from original PNG')
    box=r['sourceRegion'];sx,sy,sw,sh=(box[k] for k in ('x','y','width','height'));crop=source[sy:sy+sh,sx:sx+sw]
    enlarged=cv2.resize(crop,(sw*3,sh*3),interpolation=cv2.INTER_LINEAR);hsv=cv2.cvtColor(enlarged,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,np.array([0,0,0],np.uint8),np.array([180,140,210],np.uint8))
    contours,unused=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    components=[{'x':x,'y':y,'width':w,'height':h} for x,y,w,h in sorted((cv2.boundingRect(c) for c in contours),key=lambda b:(b[0],b[1]))]
    if components!=r['allComponents']:raise ValueError('exact count contours do not derive from actual source pixels')
    f=r['foregroundBounds'];fx,fy,fw,fh=(f[k] for k in ('x','y','width','height'));foreground=cv2.bitwise_not(mask[fy:fy+fh,fx:fx+fw])
    glyph=cv2.resize(foreground,(r['glyphWidth'],48),interpolation=cv2.INTER_NEAREST);normalized=np.full((96,r['glyphWidth']+48),255,dtype=np.uint8)
    normalized[24:72,24:24+r['glyphWidth']]=glyph
    for key,actual in (('sourcePixelsSha256',crop),('maskPixelsSha256',mask),('normalizedPixelsSha256',normalized),('ocrInputPixelsSha256',normalized)):
        if hashlib.sha256(actual.tobytes()).hexdigest()!=sha(r.get(key)):raise ValueError('exact count preprocessing fingerprint not derived from original PNG')
