"""Resolve bounded cultivation pairs from the runner's actual ItemV2 assets."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata

CSV_PATH='Assets/Model/ItemV2/item.csv'
MODEL_PATH='Assets/Model/ItemV2/item.onnx'
PARSER_VERSION='named-cultivation-catalog-1'
MATERIAL_ID=re.compile(r'(?:104|112|113|114)[0-9]{3}\Z')


def _file(root,relative,maximum):
    path=(root/relative).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('named inventory asset escaped trusted runtime')
    before=path.stat()
    if not 0<before.st_size<=maximum:raise ValueError('named inventory asset size invalid')
    with path.open('rb') as stream:content=stream.read(maximum+1)
    after=path.stat();identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if len(content)!=before.st_size or identity(before)!=identity(after):raise ValueError('named inventory asset changed during read')
    return content,{'relativePath':relative,'byteLength':len(content),'sha256':hashlib.sha256(content).hexdigest()},(path,identity(after))


def _controlled(text):return any(unicodedata.category(c)=='Cc' for c in text)


def load_runtime_catalog(trusted_runtime_root):
    if trusted_runtime_root is None:raise ValueError('named inventory requires trusted runtime root')
    root=Path(trusted_runtime_root).resolve(strict=True)
    if not root.is_dir():raise ValueError('named inventory runtime root is not a directory')
    content,csv_asset,csv_identity=_file(root,CSV_PATH,20_000_000)
    unused,model_asset,model_identity=_file(root,MODEL_PATH,100_000_000)
    reader=csv.reader(io.StringIO(content.decode('utf-8-sig'),newline=''),strict=True)
    headers=next(reader,None)
    if not headers:raise ValueError('named inventory CSV header missing')
    headers=[value.strip().lstrip('\ufeff') for value in headers]
    keys=('variant_id','item_class_id','item_name','material_type','quality_level','embedding')
    if any(headers.count(k)!=1 for k in keys):raise ValueError('named inventory required CSV columns missing or duplicated')
    indices={key:headers.index(key) for key in keys};rows=[]
    for fields in reader:
        if not fields:continue
        if len(rows)>=50000 or len(fields)!=len(headers):raise ValueError('named inventory CSV row shape/count invalid')
        item_class,name=fields[indices['item_class_id']].strip(),fields[indices['item_name']].strip()
        if not 1<=len(item_class)<=160 or not 1<=len(name)<=160 or _controlled(item_class) or _controlled(name):
            raise ValueError('named inventory CSV identity text invalid')
        embedding=re.sub(r'[ \t\r\n]','',fields[indices['embedding']])
        try:decoded=base64.b64decode(embedding,validate=True)
        except (ValueError,base64.binascii.Error) as error:raise ValueError('named inventory CSV embedding encoding invalid') from error
        if not 0<len(decoded)<=65536 or len(decoded)%4:raise ValueError('named inventory CSV embedding shape invalid')
        quality=fields[indices['quality_level']]
        quality=int(quality) if re.fullmatch(r'[0-9]+',quality) and len(quality)<=10 and int(quality)<=2147483647 else -1
        match=re.fullmatch(r'material:([1-9][0-9]{0,8})',item_class)
        rows.append({'csvRowNumber':len(rows)+2,'variantId':fields[indices['variant_id']].strip(),'itemClassId':item_class,
            'materialId':match[1] if match else '', 'fullName':name,'materialType':fields[indices['material_type']].strip(),
            'qualityLevel':quality,'rowSha256':hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest(),
            'embeddingByteLength':len(decoded)})
    if not rows:raise ValueError('named inventory CSV empty')
    for path,identity in (csv_identity,model_identity):
        final=path.stat()
        if (final.st_dev,final.st_ino,final.st_size,final.st_mtime_ns)!=identity:raise ValueError('named inventory asset set changed during read')
    return {'version':{'csv':csv_asset,'model':model_asset,'parserVersion':PARSER_VERSION},'rows':rows}


def resolve_material(catalog,material):
    if (not isinstance(material,dict) or set(material)!={'materialId','materialName'} or not isinstance(material.get('materialId'),str)
            or not MATERIAL_ID.fullmatch(material['materialId']) or not isinstance(material.get('materialName'),str)
            or not 1<=len(material['materialName'])<=80 or material['materialName']!=material['materialName'].strip() or _controlled(material['materialName'])):
        raise ValueError('named inventory accepts exact cultivation ID/fullname pairs only')
    identifier,name=material['materialId'],material['materialName'];item_class='material:'+identifier
    matches=[r for r in catalog['rows'] if r['itemClassId']==item_class]
    if (not matches or any(r['fullName']!=name for r in matches)
            or len({(r['fullName'],r['materialType'],r['qualityLevel']) for r in matches})!=1
            or any(r['fullName']==name and r['itemClassId']!=item_class for r in catalog['rows'])):
        raise ValueError('named inventory CSV pair missing/conflicting or name ambiguous globally')
    row=matches[0];kind=row['materialType']
    if row['embeddingByteLength']<=0 or not 1<=row['qualityLevel']<=5:raise ValueError('named inventory actual model prototype missing')
    if identifier.startswith('104') and kind=='角色天赋素材':purpose='talentBookOrCrown'
    elif identifier.startswith('112') and kind in ('角色与武器培养素材',''):purpose='developmentMaterialNamespace'
    elif identifier.startswith('114') and kind=='武器突破素材':purpose='weaponAscensionMaterial'
    elif identifier=='113021':purpose='fixedDreamSolventRoute'
    elif identifier.startswith('113') and kind in ('','角色突破素材'):purpose='developmentMaterialNamespace'
    else:raise ValueError('named inventory material namespace/type not supported')
    return {**material,'category':'preciousItems' if identifier=='113021' else 'characterDevelopmentItems','purpose':purpose,
        'csvRow':dict(row),'catalogVersion':catalog['version']}
