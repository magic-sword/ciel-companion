"""Bind exact spatial data to one request. No action/verb classification lives here."""
import copy
import re
import unicodedata


AXIS = re.compile(r'(?<![a-zA-Z])([xyzXYZ])(?![a-zA-Z])\s*(?:座標|軸)?\s*(?:=|:|は|が)?\s*')
VALUE = re.compile(r'([+-]?\d+)(?:\s*(?:〜|~|から|–|-)\s*([+-]?\d+))?(?![\d.])')


def explicit_axes(text):
    """Only unambiguous labelled integer axes; duplicates/partial numbers fail closed.

    A correction or a protected Y mentioned separately is deliberately not resolved
    by last-number-wins. Such utterances need a clarified target in this version.
    """
    text = unicodedata.normalize('NFKC', text).replace('−', '-')
    matches = list(AXIS.finditer(text))
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
    """Private bindings and model-facing schemas are distinct from MCP schemas."""
    def __init__(self, request_id, text, references, definitions):
        self.request_id = request_id
        self.bindings = {}
        self.definitions = copy.deepcopy(definitions)
        explicit, axes = explicit_axes(text)
        self.targets = []
        if explicit and axes:
            self.targets.append({'id': 'T1', 'source': 'explicit_coordinates', 'axes': axes})
        elif not explicit and references:
            self.targets.append({'id': 'T1', 'source': references.get('source', 'pointer'),
                                 'points': copy.deepcopy(references.get('points', []))})
        for key, definition in self.definitions.items():
            spec = definition.get('target_binding')
            if not spec:
                continue
            bound = {}
            if spec.get('kind') == 'reference' and not explicit and references:
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
