"""Rig natively imported tail meshes without changing the existing character.

Build on .local/tail-integration/imported.cmo3, then open the candidate in Cubism
and export SDK data. Material images are shared; left coordinates are mirrored.
"""
from pathlib import Path
import copy
import importlib.util
import io
import itertools
import json
import sys
import uuid
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
HERE = ROOT/'scripts/live2d'
sys.path.insert(0, str(HERE))
import cmo3_tool as t


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


lib = module('integration', HERE/'integrate-expressions.py')
preview = module('tail_skinning', HERE/'v63/tail-skinning.py')
named, array = lib.named, lib.array
WORK = ROOT/'.local/tail-integration'
DRAFT = WORK/'draft'
OUT = ROOT/'assets/ciel/rig/proofs/tail-v63'
ANCHOR = preview.ANCHOR
PARAMETERS = ['ParamCielTailWag', 'ParamCielTailFollow', 'ParamCielTailTip']


def world_positions(points, side, wag, follow, tip):
    posed = preview.skin(points, [0, follow*6, tip*3])
    local = posed-ANCHOR
    a = abs(wag) if (wag >= 0) == (side == 'Right') else 0.
    # Project the plume toward the pelvis at center. The part is also hidden
    # there, so switching does not create a stretched or semitransparent tail.
    local[:, 0] *= .18+.82*a
    local[:, 1] -= np.maximum(local[:, 1], 0)*(1-a)
    if side == 'Left': local[:, 0] *= -1
    return local+ANCHOR


def main():
    for folder in (DRAFT, OUT): folder.mkdir(parents=True, exist_ok=True)
    doc = t.Cmo3(WORK/'imported.cmo3')
    e = lib.Editor(doc)
    assert all('Tail_'+side in e.meshes for side in ('Left', 'Right'))
    breath = doc.warp_info('呼吸')
    origin = np.array([breath['x0'], breath['y0']])
    size = np.array([breath['x1']-breath['x0'], breath['y1']-breath['y0']])
    for pid, label in zip(PARAMETERS, ('尻尾 左右', '尻尾 中ほどの追従', '尻尾 毛先の追従')):
        e.add_param(pid, label)
        for p in e.root.iter('CParameterSource'):
            if named(p, 'CParameterGuid', 'guid').get('xs.ref') == e.params[pid]:
                for key, value in [('minValue', -1), ('maxValue', 1), ('defaultValue', 0)]:
                    named(p, 'f', key).text = str(float(value))
    im = Image.open(ROOT/'assets/ciel/current/layers/Tail_Right.png').convert('RGBA')
    w, h = im.size
    # Regular native mesh, with enough vertices for the large gentle curve.
    n = 21
    xx, yy = np.meshgrid(np.linspace(0, w, n), np.linspace(0, h, n))
    points = np.column_stack([xx.ravel(), yy.ravel()])
    tris, edges = [], {}
    for y in range(n-1):
        for x in range(n-1):
            a = y*n+x
            for tri in ([a, a+1, a+n+1], [a, a+n+1, a+n]):
                tris.append(tri)
                for i, j in zip(tri, np.roll(tri, -1)):
                    edge = tuple(sorted((int(i), int(j))))
                    edges[edge] = edges.get(edge, 0)+1
    tris = np.array(tris)

    def clone(old):
        new = e.define(old.tag)
        identity = {k: new.get(k) for k in ('xs.id', 'xs.idx')}
        new.attrib.update(old.attrib); new.attrib.update(identity)
        new.extend(copy.deepcopy(list(old))); new.text = old.text
        for node in new.iter():
            if node.get('xs.ref') == old.get('xs.id'): node.set('xs.ref', new.get('xs.id'))
            if node.get('uuid'): node.set('uuid', str(uuid.uuid4()))
        return new

    def set_array(node, tag, key, values):
        a = named(node, tag, key)
        values = np.asarray(values).ravel()
        a.set('count', str(len(values)))
        a.text = array(values) if tag == 'float-array' else ' '.join(str(int(v)) for v in values)

    def add_warp(side, label, parent, parent_box, pid):
        template = next(node for node in e.shared if node.tag == 'CWarpDeformerSource')
        warp = clone(template)
        name = 'Tail_'+side+'_'+label
        named(warp, 's', 'localName').text = name
        ident = named(warp, 'CDeformerId', 'id')
        ident.tag = 'CDeformerId';ident.attrib.clear();ident.attrib.update({'xs.n': 'id', 'idstr': name})
        guid = e.define('CDeformerGuid', uuid=str(uuid.uuid4()), note=name)
        named(warp, 'CDeformerGuid', 'guid').set('xs.ref', guid.get('xs.id'))
        named(warp, 'CDeformerGuid', 'targetDeformerGuid').set('xs.ref', parent)
        part_guid = named(e.meshes['Tail_'+side], 'CPartGuid', 'parentGuid').get('xs.ref')
        named(warp, 'CPartGuid', 'parentGuid').set('xs.ref', part_guid)
        ext = named(warp, 'carray_list', '_extensions');ext.clear();ext.attrib.update({'xs.n': '_extensions', 'count': '0'})
        bbox = np.array([650., 1250., 2750., 3350.] if side == 'Right' else [-550., 1250., 1550., 3350.])
        bx, by = np.meshgrid(np.linspace(bbox[0], bbox[2], 9), np.linspace(bbox[1], bbox[3], 9))
        world = np.column_stack([bx.ravel(), by.ravel()])
        named(warp, 'i', 'col').text = named(warp, 'i', 'row').text = '8'
        set_array(warp, 'float-array', 'positions', world)
        forms = named(warp, 'carray_list', 'keyforms');base_form = copy.deepcopy(forms[0])
        forms.clear();forms.attrib.update({'xs.n': 'keyforms', 'count': '1'});forms.append(base_form)
        named(base_form, warp.tag, '_source').set('xs.ref', warp.get('xs.id'))
        # Start from an unbound neutral form; opacity_binding also creates the
        # standard grid/access-key structure used for an ordinary parameter.
        grid = e.define('KeyformGridSource')
        ET.SubElement(grid, 'array_list', {'xs.n': 'keyformsOnGrid', 'count': '0'})
        ET.SubElement(grid, 'array_list', {'xs.n': 'keyformBindings', 'count': '0'})
        named(warp, 'KeyformGridSource', 'keyformGridSource').set('xs.ref', grid.get('xs.id'))
        form_guid = e.define('CFormGuid', uuid=str(uuid.uuid4()), note=name)
        named(base_form, 'CFormGuid', 'guid').set('xs.ref', form_guid.get('xs.id'))
        e.meshes[name] = warp;e.opacity_binding(name, pid, True, (-1, 0, 1));del e.meshes[name]
        source = world-ANCHOR
        if side == 'Left':source[:, 0] *= -1
        source = source/preview.SCALE+preview.PATH[0]
        for value, form in zip((-1, 0, 1), named(warp, 'carray_list', 'keyforms')):
            transformed = preview.skin(source, [0, value*6 if label == 'Follow' else 0,
                                                   value*3 if label == 'Tip' else 0])-ANCHOR
            if side == 'Left':transformed[:, 0] *= -1
            transformed += ANCHOR
            if parent_box is None:
                transformed = (transformed-origin)/size;coord = breath['coord']
            else:
                transformed = (transformed-parent_box[:2])/(parent_box[2:]-parent_box[:2]);coord = breath['coord']
            set_array(form, 'float-array', 'positions', transformed)
            named(form, 'f', 'opacity').text = '1.0'
            named(form, 'CoordType', 'coordType').set('xs.ref', coord)
        members = e.root.find('.//CDeformerSourceSet/carray_list[@xs.n="_sources"]')
        ET.SubElement(members, warp.tag, {'xs.ref': warp.get('xs.id')});members.set('count', str(len(members)))
        part = next(node for node in e.root.iter('CPartSource') if node.get('xs.id') and named(node, 'CPartGuid', 'guid').get('xs.ref') == part_guid)
        members = named(part, 'carray_list', '_childGuids')
        ET.SubElement(members, 'CDeformerGuid', {'xs.ref': guid.get('xs.id')});members.set('count', str(len(members)))
        return guid.get('xs.id'), bbox

    for side in ('Left', 'Right'):
        mesh = e.meshes['Tail_'+side]
        named(mesh, 'b', 'isVisible').text = 'true'
        follow_guid, box = add_warp(side, 'Follow', breath['guid'], None, PARAMETERS[1])
        tip_guid, _ = add_warp(side, 'Tip', follow_guid, box, PARAMETERS[2])
        named(mesh, 'CDeformerGuid', 'targetDeformerGuid').set('xs.ref', tip_guid)
        set_array(mesh, 'float-array', 'point', points)
        set_array(mesh, 'int-array', 'indices', tris)
        # The source vertex array determines the SDK vertex count, independently
        # of the editable mesh and its keyforms. Keep all three synchronized.
        rest_positions = mesh.find('float-array[@xs.n="positions"]')
        rest_positions.set('count', str(points.size));rest_positions.text = array(points.ravel())
        set_array(mesh, 'byte-array', 'pointPriority', [20]*len(points))
        set_array(mesh, 'int-array', 'pointUid', np.arange(len(points)))
        set_array(mesh, 'short-array', 'edge', list(edges))
        set_array(mesh, 'byte-array', 'edgePriority', [30 if v == 1 else 10 for v in edges.values()])
        editable = next(mesh.iter('GEditableMesh2'))
        editable.set('nextPointUid', str(len(points)))
        editable.set('useDelaunayTriangulation', 'false')
        template = copy.deepcopy(named(mesh, 'carray_list', 'keyforms')[0])
        forms = named(mesh, 'carray_list', 'keyforms')
        forms.clear(); forms.attrib.update({'xs.n': 'keyforms', 'count': '0'})
        grid = e.define('KeyformGridSource')
        named(mesh, 'KeyformGridSource', 'keyformGridSource').set('xs.ref', grid.get('xs.id'))
        ongrid = ET.SubElement(grid, 'array_list', {'xs.n': 'keyformsOnGrid', 'count': '0'})
        binds = ET.SubElement(grid, 'array_list', {'xs.n': 'keyformBindings', 'count': '1'})
        wag_keys = [-1, 0, .1, .25, .5, .75, 1] if side == 'Right' else [-1, -.75, -.5, -.25, -.1, 0, 1]
        keysets = [wag_keys]
        binding_nodes = []
        for pid, keys in zip(PARAMETERS, keysets):
            binding = e.define('KeyformBindingSource')
            ET.SubElement(binding, 'KeyformGridSource', {'xs.n': '_gridSource', 'xs.ref': grid.get('xs.id')})
            ET.SubElement(binding, 'CParameterGuid', {'xs.n': 'parameterGuid', 'xs.ref': e.params[pid]})
            vals = ET.SubElement(binding, 'array_list', {'xs.n': 'keys', 'count': str(len(keys))})
            for value in keys: ET.SubElement(vals, 'f').text = str(float(value))
            for tag in ('InterpolationType', 'ExtendedInterpolationType'):
                ET.SubElement(binding, tag, {'xs.n': tag[0].lower()+tag[1:], 'v': 'LINEAR'})
            for tag, key, value in [('i', 'insertPointCount', '1'), ('f', 'extendedInterpolationScale', '1.0'), ('s', 'description', '')]:
                ET.SubElement(binding, tag, {'xs.n': key}).text = value
            ET.SubElement(binds, 'KeyformBindingSource', {'xs.ref': binding.get('xs.id')})
            binding_nodes.append(binding)
        for indices in itertools.product(*(range(len(keys)) for keys in keysets)):
            wag = keysets[0][indices[0]]
            form = copy.deepcopy(template)
            guid = e.define('CFormGuid', uuid=str(uuid.uuid4()), note='Tail view and follow-through')
            named(form, 'CFormGuid', 'guid').set('xs.ref', guid.get('xs.id'))
            named(form, 'CArtMeshSource', '_source').set('xs.ref', mesh.get('xs.id'))
            set_array(form, 'float-array', 'positions', (world_positions(points, side, wag, 0, 0)-box[:2])/(box[2:]-box[:2]))
            named(form, 'CoordType', 'coordType').set('xs.ref', breath['coord'])
            visible = wag > 0 if side == 'Right' else wag < 0
            named(form, 'f', 'opacity').text = '1.0' if visible else '0.0'
            named(form, 'i', 'drawOrder').text = '10'
            forms.append(form)
            item = ET.SubElement(ongrid, 'KeyformOnGrid')
            access = ET.SubElement(item, 'KeyformGridAccessKey', {'xs.n': 'accessKey'})
            keys = ET.SubElement(access, 'array_list', {'xs.n': '_keyOnParameterList', 'count': '1'})
            for binding, index in zip(binding_nodes, indices):
                key = ET.SubElement(keys, 'KeyOnParameter')
                ET.SubElement(key, 'KeyformBindingSource', {'xs.n': 'binding', 'xs.ref': binding.get('xs.id')})
                ET.SubElement(key, 'i', {'xs.n': 'keyIndex'}).text = str(index)
            ET.SubElement(item, 'CFormGuid', {'xs.n': 'keyformGuid', 'xs.ref': guid.get('xs.id')})
        forms.set('count', str(len(forms))); ongrid.set('count', str(len(ongrid)))

    # One new atlas page shared by the two view meshes. Keep both existing
    # atlas pages and all old UV coordinates completely unchanged.
    oldatlas = next(node for node in e.shared if node.tag == 'CTextureAtlas')
    atlas = clone(oldatlas)
    named(atlas, 's', 'name').text = 'TailAtlas'
    atlas_guid = e.define('CTextureAtlasGuid', uuid=str(uuid.uuid4()), note='Tail atlas')
    named(atlas, 'CTextureAtlasGuid', 'guid').set('xs.ref', atlas_guid.get('xs.id'))
    oldresource = e.ids[named(oldatlas, 'CImageResource', 'cachedAtlasImage').get('xs.ref')]
    resource = clone(oldresource)
    atlas_size = 2048
    for key in ('width', 'height'):named(atlas, 'i', key).text = str(atlas_size)
    resource.set('width', str(atlas_size)); resource.set('height', str(atlas_size))
    atlas_pic = Image.new('RGBA', (atlas_size, atlas_size))
    atlas_pic.paste(im, (32, 32))
    buf = io.BytesIO(); atlas_pic.save(buf, format='PNG'); data = buf.getvalue()
    resource.set('imageFileBuf_size', str(len(data)))
    resource.find('file').set('path', 'tail_atlas_v63.png')
    for node in atlas.iter('CImageResource'): node.set('xs.ref', resource.get('xs.id'))
    named(atlas, 'b', 'lockCachedAtlasImage').text = 'true'
    page_entries = named(atlas, 'carray_list', 'modelImages')
    page_entries.clear(); page_entries.attrib.update({'xs.n': 'modelImages', 'count': '2'})
    entry_template = copy.deepcopy(named(oldatlas, 'carray_list', 'modelImages')[0])
    atlas_list = next(node for node in e.root.iter('carray_list') if node.get('xs.n') == '_textureAtlases')
    ET.SubElement(atlas_list, 'CTextureAtlas', {'xs.ref': atlas.get('xs.id')})
    atlas_list.set('count', str(len(atlas_list)))
    png_entry = copy.copy(next(entry for entry in doc.caff.entries if entry.name.endswith('.png')))
    png_entry.name = 'tail_atlas_v63.png'; png_entry.data = data; doc.caff.entries.append(png_entry)
    texture = clone(e.ids[e.meshes['Sweat'].find('GTexture2D').get('xs.ref')])
    named(texture, 's', 'name').text = 'TailAtlas'
    named(texture, 'CImageResource', 'srcImageResource').set('xs.ref', resource.get('xs.id'))
    region_template = next(node for node in e.shared if node.tag == 'CTextureInput_TextureAtlasRegion')
    for side in ('Left', 'Right'):
        mesh = e.meshes['Tail_'+side]
        ext = e.ids[mesh.find('.//CTextureInputExtension').get('xs.ref')]
        inputs = named(ext, 'carray_list', '_textureInputs')
        model_input = next(node for node in inputs if node.tag == 'CTextureInput_ModelImage')
        model_input = e.ids.get(model_input.get('xs.ref'), model_input)
        mg = named(model_input, 'CModelImageGuid', '_modelImageGuid').get('xs.ref')
        region = clone(region_template)
        named(region, 'CTextureInputExtension', '_owner').set('xs.ref', ext.get('xs.id'))
        named(region, 'CTextureAtlasGuid', 'textureAtlasGuid').set('xs.ref', atlas_guid.get('xs.id'))
        named(region, 'CAffine', 'inputImageLocalToCanvasTransform').attrib.update(m00='1.0', m01='0.0', m02='-32.0', m10='0.0', m11='1.0', m12='-32.0')
        ET.SubElement(inputs, 'CTextureInput_TextureAtlasRegion', {'xs.ref': region.get('xs.id')})
        inputs.set('count', str(len(inputs)))
        current = ext.find('*[@xs.n="currentTextureInputData"]')
        current.tag = 'CTextureInput_TextureAtlasRegion'; current.set('xs.ref', region.get('xs.id'))
        item = copy.deepcopy(entry_template)
        named(item, 'CTextureAtlas', 'atlas').set('xs.ref', atlas.get('xs.id'))
        named(item, 'CModelImageGuid', 'modelImageGuid').set('xs.ref', mg)
        named(item, 'CAffine', 'atlasLocalToCanvasTransform').attrib.update(m00='1.0', m01='0.0', m02='-32.0', m10='0.0', m11='1.0', m12='-32.0')
        transform = named(item, 'GTransform2', 'materialLocalToAtlasTransform')
        for key, value in [('position', 32), ('scale', 1)]:
            vector = named(transform, 'GVector2', key)
            for axis in ('x', 'y'): named(vector, 'f', axis).text = str(float(value))
        named(transform, 'f', 'eulerAngle').text = '0.0'
        page_entries.append(item)
        mesh.find('GTexture2D').set('xs.ref', texture.get('xs.id'))
        named(mesh, 'TextureState', 'textureState').set('v', 'TEXTURE_ATLAS')
        set_array(mesh, 'float-array', 'uvs', (points+32)/atlas_size)
        assert int(mesh.find('float-array[@xs.n="positions"]').get('count')) == points.size
        assert all(int(p.get('count')) == points.size for p in mesh.iter('float-array') if p.get('xs.n') in ('point', 'positions', 'uvs'))
    e.flush()
    missing = {node.get('xs.ref') for node in e.root.iter() if node.get('xs.ref') and node.get('xs.ref') not in e.ids}
    assert not missing, missing
    doc.save(DRAFT/'tail.cmo3')
    (DRAFT/'controls.json').write_text(json.dumps({'parameters': PARAMETERS, 'default': [0, 0, 0],
        'range': [-1, 1], 'root_model': ANCHOR.tolist(), 'parent': '呼吸',
        'left_source_is_shared_and_geometry_reflected': True, 'vertices_per_mesh': len(points),
        'keyforms_per_mesh': 7, 'follow_tip_warps': 4, 'additional_atlas_size': atlas_size}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('NATIVE_TAIL_RIG_READY', DRAFT/'tail.cmo3', flush=True)


if __name__ == '__main__': main()
