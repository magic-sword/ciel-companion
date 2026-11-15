"""Bind exact spatial data to one request. No action/verb classification lives here."""
import copy
import re
import unicodedata


AXIS = re.compile(r'(?<![a-zA-Z])([xyzXYZ])(?![a-zA-Z])\s*(?:座標|軸)?\s*(?:=|:|は|が)?\s*')
AXIS_GROUP = re.compile(r'(?<![a-zA-Z])[xyzXYZ](?:\s*/\s*[xyzXYZ])+(?![a-zA-Z])')
VALUE = re.compile(r'([+-]?\d+)(?:\s*(?:〜|~|から|–|-)\s*([+-]?\d+))?(?![\d.])')
DIMENSION = re.compile(r'(?<![\d.])(\d{1,12})\s*[×xX]\s*(\d{1,12})(?:\s*[×xX]\s*(\d{1,12}))?(?![\d.])')


def dimension_mentions(text):
    normalized = unicodedata.normalize('NFKC', text)
    matches = list(DIMENSION.finditer(normalized))
    if any((m.start() and normalized[m.start()-1] in '+-−') or re.match(r'\s*[×xX]\s*\d', normalized[m.end():]) for m in matches):
        raise ValueError('Invalid dimensions')
    for start in re.finditer(r'(?<![\d.])\d[\d.]*\s*[×xX]', normalized):
        if not any(m.start() <= start.start() < m.end() for m in matches):
            raise ValueError('Invalid dimensions')
    return [{'id': f'D{i+1}', 'dimensions': [int(v) for v in m.groups() if v], 'span': [m.start(), m.end()]}
            for i, m in enumerate(matches)]


def coordinate_mentions(text):
    """Preserve each labelled value separately; never guess which Y to discard."""
    normalized = unicodedata.normalize('NFKC', text).replace('−', '-')
    dimensions = dimension_mentions(normalized)
    groups=list(AXIS_GROUP.finditer(normalized))
    out = []
    for match in AXIS.finditer(normalized):
        if any(g.start()<=match.start()<g.end()for g in groups):continue
        if any(d['span'][0] <= match.start() < d['span'][1] for d in dimensions):
            continue
        value = VALUE.match(normalized, match.end())
        if not value or len(value[1]) > 12 or len(value[2] or '') > 12:
            raise ValueError('Invalid coordinate')
        tail = normalized[value.end():]
        if tail[:1] in ('.', '〜', '~', '-', '–', '=', ':', '万', '億') or re.match(r'[a-zA-Z0-9]', tail) or tail.startswith('から'):
            raise ValueError('Invalid coordinate')
        lo, hi = int(value[1]), int(value[2] or value[1])
        out.append({'id': f'C{len(out)+1}', 'axis': match[1].lower(),
                    'range': [min(lo, hi), max(lo, hi)], 'span': [match.start(), value.end()]})
    if out and re.search(r'(?:いや|ではなく(?:て)?|じゃなく(?:て)?|訂正して)[、,\s:]*[+-]?\d',normalized):
        raise ValueError('Unlabelled coordinate correction requires clarification')
    return out


def explicit_axes(text):
    """Only unambiguous labelled integer axes; duplicates/partial numbers fail closed.

    A correction or a protected Y mentioned separately is deliberately not resolved
    by last-number-wins. Such utterances need a clarified target in this version.
    """
    text = unicodedata.normalize('NFKC', text).replace('−', '-')
    try:
        dimensions = dimension_mentions(text)
    except ValueError:
        return True, {}
    groups=list(AXIS_GROUP.finditer(text))
    matches = [m for m in AXIS.finditer(text) if not any(d['span'][0] <= m.start() < d['span'][1] for d in dimensions)
               and not any(g.start()<=m.start()<g.end()for g in groups)]
    axes = {}
    valid = True
    for match in matches:
        axis = match[1].lower()
        value = VALUE.match(text, match.end())
        if not value or axis in axes:
            valid = False
            continue
        end = value.end()
        if (text[end:end+1] in ('.', '〜', '~', '-', '–', '=', ':', '万', '億')
                or re.match(r'[a-zA-Z0-9]', text[end:]) or text[end:end+2] == 'から'):
            valid = False
        if len(value[1]) > 12 or len(value[2] or '') > 12:
            valid = False
            continue
        lo, hi = int(value[1]), int(value[2] or value[1])
        axes[axis] = [min(lo, hi), max(lo, hi)]
    return bool(matches), axes if valid else {}


class TargetCandidates:
    """Private bindings and model-facing schemas are distinct from MCP schemas.

    One utterance's target (coordinates in its words, or what the owner pointed at) is bound to the
    actions that declare a target binding; the model sees only the id T1, never the value."""
    def __init__(self, request_id, text, references, definitions):
        self.request_id = request_id
        self.bindings = {}
        self.definitions = copy.deepcopy(definitions)
        self.text = text
        try:
            coordinate_mentions(text)   # malformed or corrected coordinates bind nothing
            valid = True
        except ValueError:
            valid = False
        explicit, axes = explicit_axes(text)
        if not valid:
            axes = {}
        self.targets = []
        if explicit and axes:
            self.targets.append({'id': 'T1', 'source': 'explicit_coordinates', 'axes': axes})
        elif not explicit and references and references.get('selection_id'):
            self.targets.append({'id': 'T1', 'source': references.get('source', 'pointer'),
                                 'points': copy.deepcopy(references.get('points', []))})
        for key, definition in self.definitions.items():
            spec = definition.get('target_binding')
            if not spec:
                continue
            bound = {}
            if spec.get('kind') == 'reference' and not explicit and references and references.get('selection_id'):
                bound = {spec['argument']: references['selection_id']}
                fields = [spec['argument']]
            elif spec.get('kind') == 'axes':
                fields = list(spec['fields'])
                for field, axis_end in spec['fields'].items():
                    axis, end = axis_end
                    if axis in axes:
                        bound[field] = axes[axis][end]
                if len(bound) != len(fields):
                    bound = {}
                if spec.get('point') and any(a != b for a, b in axes.values()):
                    bound = {}
            else:
                fields = [spec.get('argument')]
            schema = definition['arguments']
            for field in fields:
                schema.get('properties', {}).pop(field, None)
            schema['required'] = [f for f in schema.get('required', []) if f not in fields] + ['target_id']
            schema['properties']['target_id'] = {'type': 'string', 'enum': ['T1'] if bound else []}
            definition['target_ids'] = ['T1'] if bound else []
            # Raw reference UUIDs and numeric parameter schemas never reach the model.
            definition.pop('reference_argument', None)
            definition.pop('target_binding', None)
            self.bindings[key] = bound

    def resolve(self, capability, arguments):
        if capability not in self.bindings:
            return arguments
        bound = self.bindings[capability]
        if not bound or arguments.get('target_id') != 'T1':
            raise ValueError('Target is not bound to this request and capability')
        return {**{k: v for k, v in arguments.items() if k != 'target_id'}, **bound}
