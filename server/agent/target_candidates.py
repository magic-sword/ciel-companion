"""Bind exact spatial data to one request. No action/verb classification lives here."""
import copy
import re
import unicodedata


AXIS = re.compile(r'(?<![a-zA-Z])([xyzXYZ])(?![a-zA-Z])\s*(?:座標|軸)?\s*(?:=|:|は|が)?\s*')
AXIS_GROUP = re.compile(r'(?<![a-zA-Z])[xyzXYZ](?:\s*/\s*[xyzXYZ])+(?![a-zA-Z])')
VALUE = re.compile(r'([+-]?\d+)(?:\s*(?:〜|~|から|–|-)\s*([+-]?\d+))?(?![\d.])')
DIMENSION = re.compile(r'(?<![\d.])(\d{1,12})\s*[×xX]\s*(\d{1,12})(?:\s*[×xX]\s*(\d{1,12}))?(?![\d.])')
QUOTED = re.compile(r'```([\s\S]*?)```|「([^」]*)」|『([^』]*)』|“([^”]*)”|‘([^’]*)’|"([^"]*)"|(?<!\w)\x27([^\x27\n]+)\x27(?!\w)|`([^`]*)`')


def quoted_contents(text):
    normalized=unicodedata.normalize('NFKC',text)
    return [next(v for v in match.groups()if v is not None).strip()for match in QUOTED.finditer(normalized)]


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
    """Private bindings and model-facing schemas are distinct from MCP schemas."""
    def __init__(self, request_id, text, references, definitions):
        self.request_id = request_id
        self.bindings = {}
        self.definitions = copy.deepcopy(definitions)
        self.roles = {}
        self.role_candidates = {}
        self.text = text
        try:
            self.mentions = coordinate_mentions(text)
            self.dimensions = dimension_mentions(text)
            self.valid_mentions = True
        except ValueError:
            self.mentions, self.dimensions, self.valid_mentions = [], [], False
        explicit, axes = explicit_axes(text)
        if not self.valid_mentions:axes={}
        self.targets = []
        if explicit and axes:
            self.targets.append({'id': 'T1', 'source': 'explicit_coordinates', 'axes': axes})
        elif not explicit and references and references.get('selection_id'):
            self.targets.append({'id': 'T1', 'source': references.get('source', 'pointer'),
                                 'points': copy.deepcopy(references.get('points', []))})
        for key, definition in self.definitions.items():
            preparation = definition.get('preparation')
            if preparation:
                self._prepare_roles(key, definition, preparation, references)
                continue
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
        if capability in self.roles:
            return self._resolve_roles(capability, arguments)
        if capability not in self.bindings:
            return arguments
        bound = self.bindings[capability]
        if not bound or arguments.get('target_id') != 'T1':
            raise ValueError('Target is not bound to this request and capability')
        return {**{k: v for k, v in arguments.items() if k != 'target_id'}, **bound}

    def _prepare_roles(self, capability, definition, preparation, references):
        if preparation.get('version') != 1 or preparation.get('target_binding', {}).get('kind') != 'region_roles':
            definition['target_ids'] = []
            return
        self.roles[capability] = copy.deepcopy(references)
        role_targets = copy.deepcopy(self.mentions + self.dimensions)
        previous = references.get('confirmed_spec') if references and preparation.get('allow_repeat') else None
        if previous:
            role_targets.append({'id':'R1','source':'previous_work','operation':previous['operation'],
                                 **{k:copy.deepcopy(previous[k])for k in ('block','clear_blocks')if k in previous},
                                 'summary':references.get('summary','')})
        elif references and references.get('selection_id'):
            role_targets.append({'id': 'P1', 'source': references.get('source', 'pointer'),
                                 'points': copy.deepcopy(references.get('points', []))})
        self.targets.extend(t for t in role_targets if not any(v['id'] == t['id'] for v in self.targets))
        axes = {a: {'type': 'string', 'enum': [m['id'] for m in self.mentions if m['axis'] == a]} for a in 'xyz'}
        role = {'type': 'object', 'additionalProperties': False, 'properties': axes}
        schema = copy.deepcopy(preparation['intent_schema'])
        missing=[]
        if not previous:
            for field,choices in preparation.get('source_values',{}).items():
                if field not in schema.get('properties',{}):continue
                spans=[];values=set()
                aliases=sorted(((alias,value)for value,names in choices.items()for alias in names),key=lambda v:-len(v[0]))
                for alias,value in aliases:
                    for match in re.finditer(re.escape(alias),self.text,re.I):
                        if not any(match.start()<end and match.end()>start for start,end in spans):
                            spans.append(match.span());values.add(value)
                entry=schema['properties'][field]
                (entry['items']if entry.get('type')=='array'else entry)['enum']=sorted(values)
                if field in schema.get('required',[]) and not values:missing.append(field)
            axes_present={m['axis']for m in self.mentions}
            if not references or self.mentions:
                reference_axes=preparation.get('reference_axes',[])if references and axes_present<={'y'}else []
                missing.extend(a for a in preparation.get('required_axes',[])if a not in axes_present and a not in reference_axes)
            if sum(m['axis']=='y'for m in self.mentions)<preparation.get('required_height_mentions',0):missing.append('ground/top')
        if missing:definition['missing_fields']=missing
        edit_role=copy.deepcopy(role)
        required_axes=preparation.get('required_axes')
        if required_axes is not None:
            edit_role['properties']={a:v for a,v in edit_role['properties'].items()if a in required_axes and v['enum']}
            if all(a in edit_role['properties']for a in required_axes):edit_role['required']=list(required_axes)
        schema['properties']['target_roles'] = {'type': 'object', 'additionalProperties': False,
            'properties': {'edit': edit_role, 'preserve': {'type': 'array', 'maxItems': 4, 'items': role},
                           'reference': {'type': 'string', 'enum': ['P1'] if references and references.get('selection_id') else []},
                           'ground': axes['y'], 'top': axes['y'],
                           'dimensions': {'type': 'string', 'enum': [d['id'] for d in self.dimensions]}}}
        if required_axes and all(a in edit_role.get('required',[])for a in required_axes):
            # A sole explicit value for a required edit axis belongs to edit.
            # Preserved regions inherit it; emitting that ID again is invalid.
            saved_role=schema['properties']['target_roles']['properties']['preserve']['items']
            saved_role['properties']={a:v for a,v in saved_role['properties'].items()
                if a not in required_axes or len(v.get('enum',[]))!=1}
        permitted = preparation.get('roles')
        role_properties = schema['properties']['target_roles']['properties']
        # Service-declared labels constrain source roles independently of the LLM.
        normalized=unicodedata.normalize('NFKC',self.text)
        labelled={}
        for name,prefixes in preparation.get('role_prefixes',{}).items():
            if name not in role_properties:continue
            matches=[m['id']for m in self.mentions if any(
                re.search(re.escape(prefix)+r'\s*$',normalized[:m['span'][0]],re.I)for prefix in prefixes)]
            if matches:
                role_properties[name]={**role_properties[name],'enum':matches}
                labelled[name]=matches
        self.role_candidates[capability]=labelled
        for name,aliases in preparation.get('source_roles',{}).items():
            if not any(alias.casefold()in self.text.casefold()for alias in aliases):
                role_properties.pop(name,None)
                if name=='preserve'and required_axes is not None and len(self.mentions)>len(required_axes)+preparation.get('required_height_mentions',0):
                    definition['missing_fields']=[*definition.get('missing_fields',[]),'coordinate_roles']
        if previous:
            role_properties.clear()
            role_properties['previous']={'const':'R1'}
            permitted=['previous']
        if permitted is not None:
            for name in list(role_properties):
                if name not in permitted:
                    del role_properties[name]
        if len({m['axis'] for m in self.mentions}) == len(self.mentions):
            role_properties.pop('preserve', None)
        if required_axes is not None and len(self.mentions)<=len(required_axes)+preparation.get('required_height_mentions',0):
            role_properties.pop('preserve',None)
        if not self.dimensions:
            role_properties.pop('dimensions', None)
        for name,entry in list(role_properties.items()):
            if entry.get('enum')==[]:del role_properties[name]
        for axis in list(axes):
            if not axes[axis]['enum']:del axes[axis]
        required_roles=['previous']if previous else []
        if not previous:
            if self.dimensions:required_roles.append('dimensions')
            if required_axes and all(a in {m['axis']for m in self.mentions}for a in required_axes):required_roles.append('edit')
            elif references and references.get('selection_id'):required_roles.append('reference')
            if preparation.get('required_height_mentions'):required_roles+=['ground','top']
        schema['properties']['target_roles']['required']=required_roles
        schema['required'] = [*schema.get('required', []), 'target_roles']
        definition['arguments'] = schema
        definition['preparation'] = {k: v for k, v in preparation.items() if k not in ('intent_schema', 'target_binding', 'variants', 'roles', 'source_values', 'source_roles','role_prefixes', 'required_axes', 'required_height_mentions', 'reference_axes','continuation_patterns','negative_request_patterns')}
        definition['target_ids'] = [m['id'] for m in role_targets]
        # Still expose incomplete intentions so the model can ask for missing fields.
        definition['target_ids'] = definition['target_ids'] or ['needs_target']

    def _resolve_roles(self, capability, arguments):
        if not self.valid_mentions:
            raise ValueError('Malformed coordinates require clarification')
        by_id = {m['id']: m for m in self.mentions}
        roles = arguments.get('target_roles', {})
        for name,allowed in self.role_candidates.get(capability,{}).items():
            if name in roles and roles[name]not in allowed:
                raise ValueError('Coordinate role conflicts with its source label')
        reference = self.roles[capability]
        if roles.get('previous'):
            if roles!={'previous':'R1'} or not reference or not reference.get('confirmed_spec') or self.mentions or self.dimensions:
                raise ValueError('Previous work cannot replace newly specified coordinates')
            original=reference['confirmed_spec']
            for name,value in arguments.items():
                if name=='target_roles':continue
                before=original.get(name)
                if (sorted(value)!=sorted(before) if isinstance(value,list) and isinstance(before,list) else value!=before):
                    raise ValueError('Continuing cannot silently change the confirmed specification')
            return copy.deepcopy(original)
        used = set()

        def axes(values, inherited=None):
            result = dict(inherited or {})
            for axis, ref in values.items():
                if ref not in by_id or by_id[ref]['axis'] != axis or ref in used:
                    raise ValueError('Invalid or reused coordinate role')
                used.add(ref)
                result[axis] = list(by_id[ref]['range'])
            return result

        edit = axes(roles.get('edit', {}))
        spec = {k: copy.deepcopy(v) for k, v in arguments.items() if k != 'target_roles'}
        if self.dimensions:
            if len(self.dimensions) != 1 or roles.get('dimensions') != self.dimensions[0]['id']:
                raise ValueError('Dimensions need one explicit role')
            spec['expected_dimensions'] = self.dimensions[0]['dimensions']
        if roles.get('reference'):
            if roles['reference'] != 'P1' or not reference or edit:
                raise ValueError('Conflicting pointer and explicit target')
            spec['selection_id'] = reference['selection_id']
        else:
            if set(edit) != set('xyz') and not (spec['operation'] == 'level' and set(edit) == set('xz')):
                raise ValueError('Missing coordinate axes')
            spec['region'] = {axis+str(end+1): values[end] for axis, values in edit.items() for end in range(2)}
        preserve = []
        for saved in roles.get('preserve', []):
            protected = axes(saved, edit)
            if set(protected) != set('xyz'):
                raise ValueError('Missing preserve axes')
            preserve.append({axis+str(end+1): values[end] for axis, values in protected.items() for end in range(2)})
        if 'ground' in roles or 'top' in roles:
            if not all(k in roles for k in ('ground','top')) or spec['operation'] != 'level':
                raise ValueError('Ground and top are required for level')
            heights = axes({'y': roles['ground']})['y'], axes({'y': roles['top']})['y']
            if any(lo != hi for lo, hi in heights):
                raise ValueError('Ground and top must be single heights')
            spec.pop('region', None)
            spec['level'] = {axis+str(end+1): bounds[end] for axis, bounds in edit.items() if axis in 'xz' for end in range(2)}
            spec['level'].update(ground_y=heights[0][0], top_y=heights[1][0])
        if preserve:
            spec['preserve_regions'] = preserve
        if used != set(by_id):
            raise ValueError('Every mentioned coordinate needs an explicit role')
        return spec
