"""Independent raw-frame checks for a separate read-only resource diagnostic."""
from datetime import datetime
import re
import unicodedata

try:
    from .backpack_inventory_evidence import _number, _rect, _inside, _time, verify_backpack_inventory
except ImportError:
    from backpack_inventory_evidence import _number, _rect, _inside, _time, verify_backpack_inventory

EXPERIENCE = {'104011': '精锻用杂矿', '104012': '精锻用良矿', '104013': '精锻用魔矿'}


def _clean(value):
    return unicodedata.normalize('NFKC', value).strip() if isinstance(value, str) else ''


def _balance(value):
    text = _clean(value)
    if not re.fullmatch(r'(0|[1-9][0-9]{0,9})', text) or int(text) > 2147483647:
        return None
    return int(text)


def _mora_frame(frame, start, finish):
    width, height = frame.get('width'), frame.get('height')
    if type(width) is not int or type(height) is not int or width < 800 or width * 9 != height * 16:
        raise ValueError('mora frame dimensions invalid')
    scale = width / 1920
    at = _number(frame.get('observedAt'))
    icon, amount = _rect(frame.get('iconRegion')), _rect(frame.get('balanceRegion'))
    headers, rows = frame.get('headerRows'), frame.get('balanceRows')
    score = _number(frame.get('iconScore'))
    if (not start <= at <= finish or frame.get('backpackTabVerified') is not True or frame.get('promptVisible') is not False
            or not isinstance(headers, list) or sum(_clean(row.get('text')) == '贵重道具' for row in headers) != 1
            or any(not _inside(_rect(row), (100*scale, 0, 350*scale, 100*scale)) for row in headers)
            or frame.get('iconName') != '摩拉' or not .75 <= score <= 1
            or icon[0] < 330*scale-1 or icon[1] < 970*scale-1 or icon[0]+icon[2] > 420*scale+1 or icon[1]+icon[3] > 1070*scale+1
            or amount[0] < 390*scale-1 or amount[1] < 970*scale-1 or amount[0]+amount[2] > 750*scale+1 or amount[1]+amount[3] > 1070*scale+1
            or icon[0]+icon[2] > amount[0] or amount[0]-icon[0]-icon[2] > 25*scale+1
            or not isinstance(rows, list) or len(rows) != 1):
        raise ValueError('mora page/model/crop identity unverified')
    row = _rect(rows[0])
    if not _inside(row, amount) or row[0]-amount[0] < 2*scale or amount[0]+amount[2]-row[0]-row[2] < 2*scale:
        raise ValueError('mora integer touches crop boundary')
    balance = _balance(frame.get('rawBalanceText'))
    if balance is None or balance != _balance(rows[0].get('text')):
        raise ValueError('mora raw integer differs from full OCR row')
    return balance


def mora_count(raw, started_at, finished_at):
    if (not isinstance(raw, dict) or raw.get('source') != 'precious_items_bottom_mora' or raw.get('materialId') != '202'
            or raw.get('materialName') != '摩拉' or raw.get('readOnly') is not True or raw.get('verified') is not True
            or raw.get('status') != 'verified' or raw.get('mainUiRestored') is not True or raw.get('cleanupCompleted') is not True):
        raise ValueError('mora identity/cleanup unverified')
    start, finish = _time(started_at), _time(finished_at)
    first, second = raw.get('first'), raw.get('second')
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ValueError('mora independent frames missing')
    if (first.get('width') != second.get('width') or first.get('height') != second.get('height')
            or _rect(first.get('iconRegion')) != _rect(second.get('iconRegion'))
            or _rect(first.get('balanceRegion')) != _rect(second.get('balanceRegion'))
            or not 100 <= _number(second.get('observedAt'))-_number(first.get('observedAt')) <= 5000
            or abs(_time(raw.get('observedAt'))-_number(second.get('observedAt'))) > 1):
        raise ValueError('mora independent-frame identity/time mismatch')
    a, b = _mora_frame(first, start, finish), _mora_frame(second, start, finish)
    if a != b or type(raw.get('balance')) is not int or raw['balance'] != a:
        raise ValueError('mora reported balance differs from both raw frames')
    return a


def verify_resource_coverage(raw, started_at, finished_at):
    if (not isinstance(raw, dict) or raw.get('readOnly') is not True or raw.get('upgradeBudgetComplete') is not False
            or raw.get('levelExperienceObserved') is not False or not isinstance(raw.get('inventory'), dict)
            or set(raw['inventory']) != {'202', *EXPERIENCE}):
        raise ValueError('resource coverage read-only/schema/scope mismatch')
    rows = raw['inventory']
    mora = rows['202']
    if mora.get('status') == 'exact':
        count = mora_count(raw.get('moraObservation'), started_at, finished_at)
        if type(mora.get('count')) is not int or mora.get('count') != count or mora.get('verified') is not True or mora.get('name') != '摩拉' or mora.get('evidence') != raw.get('moraObservation'):
            raise ValueError('resource Mora inventory differs from independent raw frames')
    elif mora.get('name') != '摩拉' or mora.get('status') != 'unknown' or mora.get('count') is not None:
        raise ValueError('unknown Mora must remain unknown/null')
    minerals = {key: rows[key] for key in EXPERIENCE}
    packet = raw.get('weaponExperienceObservation')
    if any(row.get('status') == 'exact' for row in minerals.values()):
        if not isinstance(packet, dict) or packet.get('category') != 'weaponExperience' or packet.get('readOnly') is not True or packet.get('mainUiRestored') is not True or packet.get('cleanupCompleted') is not True:
            raise ValueError('weapon experience raw category/cleanup unverified')
        for identifier, row in minerals.items():
            if row.get('status') == 'exact':
                pair = packet.get('observations', {}).get(identifier, {})
                evidence = row.get('evidence', {})
                if any(evidence.get(key) != pair.get(key) for key in ('selection', 'first', 'second')):
                    raise ValueError('weapon experience raw observations differ from exact row')
        verify_backpack_inventory(minerals, materials={key: {'name': name} for key, name in EXPERIENCE.items()},
            started_at=started_at, finished_at=finished_at, category='weaponExperience')
    for identifier, row in minerals.items():
        if row.get('name') != EXPERIENCE[identifier] or row.get('status') not in ('exact', 'unknown') or row.get('status') == 'unknown' and row.get('count') is not None:
            raise ValueError('weapon experience unknown/identity mismatch')
    verified = all(row.get('status') == 'exact' for row in rows.values())
    if raw.get('allVerified') is not verified:
        raise ValueError('resource coverage summary contradicts raw item evidence')
    return verified
