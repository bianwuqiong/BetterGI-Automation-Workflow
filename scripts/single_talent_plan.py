"""Derive one readonly scope after the Host verifies actual preview evidence."""
KEYS = {'普通攻击': 'normal', '元素战技': 'skill', '元素爆发': 'burst'}
import re


def derive_single_talent_step(target, talent_type, costs, catalog):
    key = KEYS.get(talent_type)
    goal = target.get('talentTargets', {}).get(key)
    current = costs.get('currentBaseLevel')
    if (key is None or type(goal) is not int or not 1 <= goal <= 10
            or type(current) is not int or not 1 <= current <= 9
            or type(costs.get('nextBaseLevel')) is not int or costs['nextBaseLevel'] != current + 1
            or not isinstance(costs.get('talentName'), str) or not costs['talentName']):
        raise ValueError('single talent target or verified cost invalid')
    reached = current >= goal
    plan = dict(kind='single-talent-next-step', readOnly=True, executionEnabled=False, targetReached=False,
                characterName=target['characterName'], talentType=talent_type, talentName=costs['talentName'],
                currentBaseLevel=current, nextBaseLevel=None if reached else current + 1, targetBaseLevel=goal,
                status='selected-talent-at-target' if reached else 'awaiting-upgrade-verification',
                materials=[], mora=None, namedInventoryScope=None)
    if reached:
        return plan
    materials = costs.get('materials')
    if not isinstance(materials, list) or not 1 <= len(materials) <= 8 or not isinstance(catalog, dict):
        raise ValueError('single talent material scope missing')
    def quantity(value, minimum=0):
        if type(value) is not int or not minimum <= value <= 999999999:
            raise ValueError('single talent quantity invalid')
        return value
    for material in materials:
        matches = [identifier for identifier, row in catalog.items() if row.get('name') == material.get('name')]
        if len(matches) != 1 or re.fullmatch(r'(104|112|113|114)[0-9]{3}', matches[0]) is None:
            raise ValueError('single talent exact material mapping missing')
        owned, required = quantity(material.get('owned')), quantity(material.get('required'), 1)
        plan['materials'].append(dict(materialId=matches[0], materialName=material['name'], owned=owned,
                                      required=required, missing=max(0, required-owned)))
    mora = costs.get('mora', {})
    owned, required = quantity(mora.get('owned')), quantity(mora.get('required'), 1)
    if len({m['materialId'] for m in plan['materials']}) != len(materials):
        raise ValueError('single talent duplicate material')
    plan['mora'] = {**mora, 'missing': max(0, required-owned)}
    plan['namedInventoryScope'] = dict(executionEnabled=False,
        policy=dict(originalResinBudget=0, condensedResinBudget=0, maxMinutes=3),
        materials=[dict(materialId=m['materialId'], materialName=m['materialName']) for m in plan['materials']])
    return plan
