"""Check actual synchronous capture records and original PNGs under trusted roots."""
import hashlib
import io
import os
from pathlib import Path
import re
from PIL import Image

FRESHNESS_SOURCE='BitBltSession.GetImage_executes_BitBlt_GdiFlush_new_buffer_each_call'
CAPTURE_METHOD='actual_synchronous_BitBltCapture'
PIXEL_SOURCE='diagnostic_only_lossless_native_srcmat_no_resize'


def integer(value,low=0,high=9007199254740991):
    if type(value) is not int or not low<=value<=high:raise ValueError('named inventory capture integer invalid')
    return value


def sha(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',value):raise ValueError('named inventory original fingerprint missing')
    return value.lower()


def rectangle_core(value,*,allow_derived=True,require_derived=False):
    """Read actual OpenCvSharp Rect JSON without discarding inconsistent metadata."""
    core_keys={'x','y','width','height'}
    derived_keys={'top','bottom','left','right','location','size','topLeft','bottomRight'}
    if not isinstance(value,dict) or set(value) not in (core_keys,core_keys|derived_keys):
        raise ValueError('named inventory rectangle fields not from reviewed serializer')
    if require_derived and set(value)!=core_keys|derived_keys:
        raise ValueError('named inventory actual native Rect requires complete twelve fields')
    core={k:integer(value[k],-2147483648 if k in ('x','y') else 0,2147483647) for k in core_keys}
    if set(value)!=core_keys:
        if not allow_derived:raise ValueError('named inventory BackpackRect contains unreviewed derived fields')
        x,y,w,h=(core[k] for k in ('x','y','width','height'))
        expected={'top':y,'bottom':y+h,'left':x,'right':x+w,'location':{'x':x,'y':y},'size':{'width':w,'height':h},
            'topLeft':{'x':x,'y':y},'bottomRight':{'x':x+w,'y':y+h}}
        for k,e in expected.items():
            v=value[k]
            if isinstance(e,dict):
                if not isinstance(v,dict) or set(v)!=set(e) or any(type(v[n]) is not int or v[n]!=e[n] for n in e):
                    raise ValueError('named inventory rectangle derived coordinates inconsistent')
            elif type(v) is not int or v!=e:raise ValueError('named inventory rectangle derived edge inconsistent')
    return core


def capture_binding(binding,expected):
    if not isinstance(binding,dict) or not isinstance(expected,dict) or binding!=expected:
        raise ValueError('named inventory capture binding differs from trusted runner identity')
    if binding.get('captureMethod')!=CAPTURE_METHOD:raise ValueError('named inventory requires actual synchronous BitBlt')
    for key in ('processId','windowHandle'):integer(binding.get(key),1)
    ticks=binding.get('processStartedUtcTicks')
    if not isinstance(ticks,str) or not re.fullmatch(r'[1-9][0-9]{0,18}',ticks) or int(ticks)>9223372036854775807:
        raise ValueError('named inventory process start ticks require exact decimal text')
    rectangle=rectangle_core(binding.get('captureRectangle'),require_derived=True)
    integer(rectangle['x'],-100000,100000);integer(rectangle['y'],-100000,100000)
    if type(rectangle['width']) is not int or type(rectangle['height']) is not int or (rectangle['width'],rectangle['height'])!=(1920,1080):
        raise ValueError('named inventory actual physical client must be 1920x1080')


def original_png(metadata,trusted_runtime_root,trusted_workflow_root=None):
    if (not isinstance(metadata,dict) or metadata.get('source')!=PIXEL_SOURCE or metadata.get('pixelType')!='CV_8UC3'
            or type(metadata.get('width')) is not int or type(metadata.get('height')) is not int
            or (metadata['width'],metadata['height'])!=(1920,1080) or not isinstance(metadata.get('path'),str)):
        raise ValueError('named inventory original native pixels missing')
    root=Path(trusted_runtime_root).resolve(strict=True);allowed=[(root/'log').resolve()]
    if trusted_workflow_root is not None:allowed.append((Path(trusted_workflow_root).resolve(strict=True)/'state').resolve())
    path=Path(metadata['path']).resolve(strict=True)
    if path.suffix.lower()!='.png' or not path.is_file() or not any(path.is_relative_to(p) for p in allowed):
        raise ValueError('named inventory PNG must stay inside the trusted private evidence directory')
    before=path.stat()
    if not 0<before.st_size<=10*1024*1024:raise ValueError('named inventory PNG byte length invalid')
    content=path.read_bytes();after=path.stat()
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if identity(before)!=identity(after) or len(content)!=before.st_size or hashlib.sha256(content).hexdigest()!=sha(metadata.get('pngSha256')):
        raise ValueError('named inventory original PNG changed or hash differs')
    if not content.startswith(b'\x89PNG\r\n\x1a\n') or not content.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82'):
        raise ValueError('named inventory PNG signature/complete stream invalid')
    with Image.open(io.BytesIO(content)) as check:
        if check.format!='PNG' or check.mode!='RGB' or check.size!=(1920,1080):raise ValueError('named inventory PNG geometry/type differs from native capture')
        check.verify()
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        if hashlib.sha256(image.tobytes('raw','BGR')).hexdigest()!=sha(metadata.get('nativePixelsSha256')):
            raise ValueError('named inventory original BGR pixels differ from native source')
        return image.copy()


def capture_timeline(frames,binding,expected_binding,start,finish,*,trusted_runtime_root,trusted_workflow_root=None):
    capture_binding(binding,expected_binding)
    if not isinstance(frames,list) or not 1<=len(frames)<=2048:raise ValueError('named inventory actual capture timeline missing')
    previous=-1;paths=set();file_ids=set();images={}
    for f in frames:
        if not isinstance(f,dict) or not isinstance(f.get('actualCapture'),dict) or not isinstance(f.get('recognized'),dict):
            raise ValueError('named inventory original recognized/raw capture record missing')
        proof=f['actualCapture'];pixels=f.get('privateCapture')
        rectangle_core(proof.get('returnedRectangle'),require_derived=True)
        capture_binding(proof.get('binding'),binding)
        began=integer(proof.get('callStartedAt'));returned=integer(proof.get('callReturnedAt'))
        if (not start<=began<=returned<=finish or returned-began>5000 or returned<=previous or began<previous
                or f.get('observedAt')!=returned or proof.get('binding')!=binding or proof.get('returnedRectangle')!=binding['captureRectangle']
                or proof.get('freshnessSource')!=FRESHNESS_SOURCE or proof.get('pixelType')!='CV_8UC3'
                or type(proof.get('nativeWidth')) is not int or type(proof.get('nativeHeight')) is not int
                or (proof['nativeWidth'],proof['nativeHeight'])!=(1920,1080)
                or not isinstance(pixels,dict) or pixels.get('observedAt')!=returned):
            raise ValueError('named inventory actual call interval/binding/returned pixels inconsistent')
        if not isinstance(pixels.get('path'),str):raise ValueError('named inventory original PNG path missing')
        path=Path(pixels['path']).resolve(strict=True);identity=path.stat();key=os.path.normcase(str(path))
        file_id=(identity.st_dev,identity.st_ino)
        if key in paths or identity.st_ino and file_id in file_ids:raise ValueError('named inventory original PNG file reused for another acquisition')
        paths.add(key);file_ids.add(file_id)
        image=original_png(pixels,trusted_runtime_root,trusted_workflow_root)
        image.close()
        images[returned]=f
        previous=returned
    return images
