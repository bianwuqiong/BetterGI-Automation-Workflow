"""Independent selected-backpack-stack OCR validation; never derive stock from drops."""
from datetime import datetime
import math
import re
import unicodedata

SOURCE = 'backpack_selected_stack'


def _number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError('backpack evidence numeric field invalid')
    return value


def _rect(value):
    if not isinstance(value, dict):
        raise ValueError('backpack evidence rectangle missing')
    r = tuple(_number(value.get(k)) for k in ('x', 'y', 'width', 'height'))
    if r[0] < 0 or r[1] < 0 or r[2] <= 0 or r[3] <= 0:
        raise ValueError('backpack evidence rectangle invalid')
    return r


def _inside(a, b):
    return a[0] >= b[0] and a[1] >= b[1] and a[0] + a[2] <= b[0] + b[2] and a[1] + a[3] <= b[1] + b[3]


def _text(value):
    if not isinstance(value, str):
        raise ValueError('backpack evidence text invalid')
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value))


def _time(value):
    if not isinstance(value, str):
        raise ValueError('backpack evidence report interval missing')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('backpack evidence report timezone missing')
    return parsed.timestamp() * 1000


def verify_backpack_inventory(rows, *, materials, started_at, finished_at, category='weaponAscension'):
    """Recompute each exact named stack from its independent raw captures."""
    for identifier, row in rows.items():
        if not isinstance(row, dict) or row.get('source') != SOURCE:
            continue
        if row.get('status') == 'unknown' and row.get('count') is None:
            continue
        experience = {'104011': '精锻用杂矿', '104012': '精锻用良矿', '104013': '精锻用魔矿'}
        identity_valid = (identifier in experience and row.get('name') == experience[identifier]) if category == 'weaponExperience' else (
            category == 'weaponAscension' and re.fullmatch(r'114\d+', identifier))
        if (not identity_valid or row.get('status') != 'exact' or row.get('verified') is not True
                or row.get('name') != materials.get(identifier, {}).get('name')):
            raise ValueError('backpack evidence material/source/status mismatch')
        evidence = row.get('evidence', {})
        if not isinstance(evidence, dict):
            raise ValueError('backpack evidence object missing')
        if evidence.get('materialId') != identifier:
            raise ValueError('backpack evidence material identity mismatch')
        selection = evidence.get('selection', {})
        item = _rect(selection.get('itemRect'))
        x, y, clicked = (_number(selection.get(k)) for k in ('x', 'y', 'clickedAt'))
        if not item[0] <= x <= item[0] + item[2] or not item[1] <= y <= item[1] + item[3]:
            raise ValueError('backpack evidence click outside selected item')
        start, finish = _time(started_at), _time(finished_at)
        counts, times, regions = [], [], []
        for name in ('first', 'second'):
            frame = evidence.get(name, {})
            at = _number(frame.get('observedAt'))
            title, count = _rect(frame.get('nameRegion')), _rect(frame.get('countRegion'))
            if (frame.get('selectedItemVerified') is not True or _rect(frame.get('selectedItemRect')) != item
                    or not _inside(count, item) or not start <= clicked <= at <= finish):
                raise ValueError('backpack evidence selection/region/report-time mismatch')
            title_rows, count_rows = frame.get('nameRows'), frame.get('countRows')
            if (not isinstance(title_rows, list) or not isinstance(count_rows, list) or len(count_rows) != 1
                    or any(not _inside(_rect(r), title) for r in title_rows)
                    or any(not _inside(_rect(r), count) for r in count_rows)
                    or sum(_text(r.get('text')) == _text(row['name']) for r in title_rows) != 1):
                raise ValueError('backpack evidence full name/count rows missing or ambiguous')
            text = _text(count_rows[0].get('text'))
            if (frame.get('countMethod') != 'raw_ocr_without_detector'
                    or _text(frame.get('rawCountText')) != text or not re.fullmatch(r'[0-9]{1,9}', text)):
                raise ValueError('backpack evidence raw stack quantity unverified')
            counts.append(int(text)); times.append(at); regions.append((title, count))
        if (not 100 <= times[0] - clicked <= 5000 or not 100 <= times[1] - times[0] <= 5000
                or regions[0] != regions[1] or counts[0] != counts[1] or type(row.get('count')) is not int
                or row['count'] != counts[0]):
            raise ValueError('backpack evidence independent frames/count disagree')
