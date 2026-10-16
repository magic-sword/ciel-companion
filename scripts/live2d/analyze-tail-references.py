"""Read official local sample rigs and summarize evidence for Ciel's tail design.

Never writes to the reference files. Output contains structural metadata only.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import xml.etree.ElementTree as ET

import cmo3_tool
import cubism_core

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT/'.local/reference-rigs'
OUT = ROOT/'.local/reference-rig-analysis'
MODELS = {
    'natori': ('natori_ja/natori_pro_t06.cmo3', 'natori_ja/runtime/natori_pro_t06.model3.json'),
    'miara': ('miara_ja/miara_pro_t05.cmo3', 'miara_ja/runtime/miara_pro_t04.model3.json'),
    'hiyori': ('hiyori_ja/hiyori_pro/hiyori_pro_t11.cmo3',
               'hiyori_ja/hiyori_pro/runtime/hiyori_pro_t11.model3.json'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def named(node, tag, name):
    return node.find(f'.//{tag}[@xs.n="{name}"]')


def segments_summary(curve):
    s = curve['Segments']
    points = [[s[0], s[1]]]
    types = []
    i = 2
    while i < len(s):
        typ = int(s[i])
        types.append(typ)
        count = 7 if typ == 1 else 3
        assert typ in (0, 1, 2, 3) and i+count <= len(s)
        points.append(s[i+count-2:i+count])
        i += count
    return {'target': curve['Target'], 'id': curve['Id'], 'points': points,
            'segment_types': dict(Counter(types)),
            'value_range_at_keys': [min(p[1] for p in points), max(p[1] for p in points)]}


def native(path):
    root = ET.fromstring(cmo3_tool.Cmo3(path).xml)
    refs = {n.get('xs.id'): n for n in root.iter() if n.get('xs.id')}

    def resolve(node):
        return refs.get(node.get('xs.ref'), node) if node is not None else None

    def text(node, tag, name):
        n = named(node, tag, name)
        return n.text if n is not None else None

    params = {}
    for p in root.iter('CParameterSource'):
        guid = named(p, 'CParameterGuid', 'guid')
        ident = resolve(named(p, 'CParameterId', 'id'))
        if guid is not None and ident is not None:
            key = guid.get('xs.ref') or guid.get('xs.id')
            params[key] = ident.get('idstr')

    def bindings(node):
        grid = resolve(named(node, 'KeyformGridSource', 'keyformGridSource'))
        result = []
        if grid is None:
            return result
        container = named(grid, 'array_list', 'keyformBindings')
        if container is None:
            return result
        for item in container:
            b = resolve(item)
            pg = named(b, 'CParameterGuid', 'parameterGuid')
            keys = named(b, 'array_list', 'keys')
            result.append({'id': params.get(pg.get('xs.ref') or pg.get('xs.id')) if pg is not None else None,
                           'keys': [float(f.text) for f in keys] if keys is not None else []})
        return result

    nodes, by_guid = [], {}
    for tag, idtag, guidtag in [('CPartSource', 'CPartId', 'CPartGuid'),
                               ('CWarpDeformerSource', 'CDeformerId', 'CDeformerGuid'),
                               ('CRotationDeformerSource', 'CDeformerId', 'CDeformerGuid'),
                               ('CArtMeshSource', 'CDrawableId', 'CDrawableGuid')]:
        for n in root.iter(tag):
            if not n.get('xs.id'):
                continue
            ident = resolve(named(n, idtag, 'id'))
            if ident is None and tag == 'CArtMeshSource':
                ident = resolve(named(n, 'CArtMeshId', 'id'))
            guid = named(n, guidtag, 'guid')
            target = named(n, 'CDeformerGuid', 'targetDeformerGuid')
            parent = named(n, 'CPartGuid', 'parentGuid')
            forms = named(n, 'carray_list', 'keyforms')
            orders, opacities = [], []
            if forms is not None:
                orders = [int(f.text) for f in forms.iter('i') if f.get('xs.n') == 'drawOrder']
                opacities = [float(f.text) for f in forms.iter('f') if f.get('xs.n') == 'opacity']
            row = {'kind': tag, 'id': ident.get('idstr') if ident is not None else None,
                   'name': text(n, 's', 'localName'), 'ref': n.get('xs.id'),
                   'guid': guid.get('xs.ref') or guid.get('xs.id') if guid is not None else None,
                   'deformer_ref': target.get('xs.ref') if target is not None else None,
                   'part_ref': parent.get('xs.ref') if parent is not None else None,
                   'parameters': bindings(n),
                   'draw_order_range': [min(orders), max(orders)] if orders else None,
                   'opacity_range': [min(opacities), max(opacities)] if opacities else None,
                   'draw_order_group': text(n, 'b', 'enableDrawOrderGroup') == 'true',
                   'form_count': len(forms) if forms is not None else 0}
            nodes.append(row)
            if row['guid']:
                by_guid[row['guid']] = row
    for row in nodes:
        row['parent_deformer_id'] = by_guid.get(row.pop('deformer_ref'), {}).get('id')
        row['parent_part_id'] = by_guid.get(row.pop('part_ref'), {}).get('id')
    glue = [n for n in root.iter('CGlueSource') if n.get('xs.id')]
    grouped = [n for n in nodes if n['draw_order_group']]
    varying = [n for n in nodes if n['draw_order_range'] and n['draw_order_range'][0] != n['draw_order_range'][1]]
    skinned = [n for n in nodes if 'Skinning' in (n['id'] or '')]
    skin_rot = [n for n in nodes if n['kind'] == 'CRotationDeformerSource' and
                any((p['id'] or '').startswith('Param_Angle_Rotation_') for p in n['parameters'])]
    return {'counts': dict(Counter(n['kind'] for n in nodes)), 'glue_count': len(glue),
            'draw_order_groups': grouped, 'varying_draw_order_nodes': varying,
            'skinning_parts': skinned, 'skinning_rotations': skin_rot, 'nodes': nodes}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_hashes = {p: sha(p) for p in REF.rglob('*') if p.is_file()}
    result = {}
    for key, (native_rel, runtime_rel) in MODELS.items():
        path, settings_path = REF/native_rel, REF/runtime_rel
        settings = read_json(settings_path)
        files = settings['FileReferences']
        base = settings_path.parent
        cdi = read_json(base/files['DisplayInfo'])
        physics = read_json(base/files['Physics'])
        motions = []
        for motion in sorted(base.rglob('*.motion3.json')):
            data = read_json(motion)
            curves = [segments_summary(c) for c in data.get('Curves', [])]
            motions.append({'file': motion.relative_to(ROOT).as_posix(),
                            'duration': data['Meta']['Duration'],
                            'parts': [c for c in curves if c['target'] == 'PartOpacity'],
                            'parameter_ids': [c['id'] for c in curves if c['target'] == 'Parameter']})
        n = native(path)
        core = cubism_core.Model(settings_path)
        core.update()
        runtime_check = {
            'parameter_count': len(core.param_ids), 'drawable_count': len(core.drawables()),
            'physics_output_ids_missing_in_core': sorted({o['Destination']['Id']
                for s in physics['PhysicsSettings'] for o in s['Output']} - set(core.param_ids)),
        }
        assert not runtime_check['physics_output_ids_missing_in_core']
        if key == 'miara':
            observations = []
            for value in (-1, 0, 1):
                core.reset()
                assert not core.set({'ParamFairyDO': value})
                core.update()
                selected = {d['id']: d for d in core.drawables()}
                observations.append({'ParamFairyDO': value,
                                     'fairy_ArtMesh187_render_order': selected['ArtMesh187']['render_order'],
                                     'body_ArtMesh100_render_order': selected['ArtMesh100']['render_order']})
            assert observations[0]['fairy_ArtMesh187_render_order'] < observations[0]['body_ArtMesh100_render_order']
            assert observations[-1]['fairy_ArtMesh187_render_order'] > observations[-1]['body_ArtMesh100_render_order']
            runtime_check['draw_order_group_probe'] = observations
        controlled_order_ids = {p['id'] for row in n['varying_draw_order_nodes'] for p in row['parameters']}
        # Keep only the relevant curves, rather than copying sample animations.
        order_curves = []
        for motion in sorted(base.rglob('*.motion3.json')):
            data = read_json(motion)
            order_curves.append({'file': motion.name, 'curves': [segments_summary(c) for c in data.get('Curves', [])
                                  if c['Target'] == 'Parameter' and c['Id'] in controlled_order_ids]})
        animation_files = []
        for animation in sorted(path.parent.glob('*.can3')):
            doc = ET.fromstring(cmo3_tool.Cmo3(animation).xml)
            tags = Counter(n.tag for n in doc.iter())
            animation_files.append({'file': animation.relative_to(ROOT).as_posix(),
                                    'sha256': sha(animation),
                                    'scene_and_track_tags': {t: c for t, c in tags.items() if any(s in t.lower() for s in ['scene', 'track', 'motionclip'])}})
        result[key] = {'cmo3': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
                       'model3': settings_path.relative_to(ROOT).as_posix(),
                       'pose': read_json(base/files['Pose']) if 'Pose' in files else None,
                       'runtime_parameters': cdi.get('Parameters', []),
                       'physics': [{'id': s['Id'], 'particle_count_including_root': len(s['Vertices']),
                                    'inputs': s['Input'], 'outputs': s['Output'], 'vertices': s['Vertices']}
                                   for s in physics['PhysicsSettings']],
                       'motions': motions, 'draw_order_motion_curves': order_curves,
                       'animations': animation_files, 'native': n,
                       'runtime_core_verification': runtime_check}
        print(key, 'native', n['counts'], 'order groups', len(n['draw_order_groups']),
              'varying orders', len(n['varying_draw_order_nodes']), 'skin rotations', len(n['skinning_rotations']), flush=True)
    assert all(sha(p) == digest for p, digest in source_hashes.items())
    result['verification'] = {'reference_files_unchanged': len(source_hashes),
                              'method': 'Read-only parsing of CMO3/CAN3 and exported runtime JSON. Core load and Miara draw-order parameter probe. No Editor playback or physics simulation.'}
    (OUT/'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('REFERENCE_ANALYSIS_READY', OUT.relative_to(ROOT), flush=True)


if __name__ == '__main__':
    main()
