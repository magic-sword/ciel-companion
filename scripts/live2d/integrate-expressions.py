"""Integrate imported v23 meshes and v24 replacement images into an expression rig.

Run after importing ciel-expression-additions.psd as new meshes in Cubism.
Usage: python -B scripts/live2d/integrate-expressions.py input.cmo3 output.cmo3
Always use a working copy. Open, rebuild the texture atlas and export in Cubism
before promoting the result to assets/ciel/rig/ciel.cmo3.
"""
import copy
import io
import re
import sys
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmo3_tool as t
import mesh_ops

ROOT = Path(__file__).resolve().parents[2]
PLAN = {
    'Cheek_Blush': ('Face_Skin', 'ParamCheek', 265),
    'Eye_L_Happy': ('Eye_L_Closed', 'ParamEyeLSmile', 512),
    'Eye_R_Happy': ('Eye_R_Closed', 'ParamEyeRSmile', 422),
    'Tear_L': ('Eye_L_Sclera', 'ParamTear', 515),
    'Tear_R': ('Eye_R_Sclera', 'ParamTear', 425),
    'Sweat': ('Face_Skin', 'ParamSweat', 640),
    'Eye_L_Sparkle': ('Eye_L_Iris', 'ParamSparkle', 455),
    'Eye_R_Sparkle': ('Eye_R_Iris', 'ParamSparkle', 365),
}


def named(node, tag, name):
    return node.find('.//%s[@xs.n="%s"]' % (tag, name))


def array(values):
    return ' '.join(t._fmt(float(v)) for v in np.asarray(values).ravel())


class Editor:
    def __init__(self, doc):
        self.doc = doc
        self.preamble = doc.xml[:doc.xml.index('<root')]
        self.root = ET.fromstring(doc.xml)
        self.shared = self.root.find('shared')
        self.ids = {n.get('xs.id'): n for n in self.root.iter() if n.get('xs.id')}
        self.next_id, self.next_idx = doc._next_ids()
        self.meshes = {named(n, 's', 'localName').text: n
                       for n in self.root.iter('CArtMeshSource') if n.get('xs.id')}
        self.params = {}
        for p in self.root.iter('CParameterSource'):
            ident = named(p, 'CParameterId', 'id')
            ident = self.ids[ident.get('xs.ref')] if ident.get('xs.ref') else ident
            self.params[ident.get('idstr')] = named(p, 'CParameterGuid', 'guid').get('xs.ref')

    def define(self, tag, **attrs):
        ref = '#%d' % self.next_id
        attrs.update({'xs.id': ref, 'xs.idx': str(self.next_idx)})
        self.next_id += 1
        self.next_idx += 1
        n = ET.SubElement(self.shared, tag, attrs)
        self.ids[ref] = n
        return n

    def add_param(self, ident, label):
        if ident in self.params:
            return
        guid = self.define('CParameterGuid', uuid=str(uuid.uuid4()), note=ident)
        pid = self.define('CParameterId', idstr=ident)
        sources = self.root.find('.//CParameterSourceSet/carray_list[@xs.n="_sources"]')
        p = copy.deepcopy(next(self.root.iter('CParameterSource')))
        named(p, 'CParameterGuid', 'guid').set('xs.ref', guid.get('xs.id'))
        named(p, 'CParameterId', 'id').set('xs.ref', pid.get('xs.id'))
        for key, value in [('minValue', '0.0'), ('maxValue', '1.0'), ('defaultValue', '0.0')]:
            named(p, 'f', key).text = value
        named(p, 's', 'name').text = label
        named(p, 's', 'description').text = label
        sources.append(p)
        sources.set('count', str(len(sources)))
        rootgroup = self.ids[self.root.find('.//CModelSource/CParameterGroup[@xs.n="rootParameterGroup"]').get('xs.ref')]
        children = named(rootgroup, 'carray_list', '_childGuids')
        ET.SubElement(children, 'CParameterGuid', {'xs.ref': guid.get('xs.id')})
        children.set('count', str(len(children)))
        self.params[ident] = guid.get('xs.id')

    def opacity_binding(self, name, param, visible_when_one):
        mesh = self.meshes[name]
        gridref = named(mesh, 'KeyformGridSource', 'keyformGridSource')
        if gridref.get('xs.ref'):
            grid = self.ids[gridref.get('xs.ref')]
        else:
            # Unbound imported meshes have an inline empty grid.
            grid = self.define('KeyformGridSource')
            mesh_parent = next(n for n in mesh.iter() if gridref in list(n))
            index = list(mesh_parent).index(gridref)
            mesh_parent.remove(gridref)
            mesh_parent.insert(index, ET.Element('KeyformGridSource', {'xs.n': 'keyformGridSource', 'xs.ref': grid.get('xs.id')}))
            ET.SubElement(grid, 'array_list', {'xs.n': 'keyformsOnGrid', 'count': '0'})
            ET.SubElement(grid, 'array_list', {'xs.n': 'keyformBindings', 'count': '0'})
        binding = self.define('KeyformBindingSource')
        ET.SubElement(binding, 'KeyformGridSource', {'xs.n': '_gridSource', 'xs.ref': grid.get('xs.id')})
        ET.SubElement(binding, 'CParameterGuid', {'xs.n': 'parameterGuid', 'xs.ref': self.params[param]})
        vals = ET.SubElement(binding, 'array_list', {'xs.n': 'keys', 'count': '2'})
        for v in ('0.0', '1.0'): ET.SubElement(vals, 'f').text = v
        for tag in ('InterpolationType', 'ExtendedInterpolationType'):
            ET.SubElement(binding, tag, {'xs.n': tag[0].lower() + tag[1:], 'v': 'LINEAR'})
        ET.SubElement(binding, 'i', {'xs.n': 'insertPointCount'}).text = '1'
        ET.SubElement(binding, 'f', {'xs.n': 'extendedInterpolationScale'}).text = '1.0'
        ET.SubElement(binding, 's', {'xs.n': 'description'})
        forms = named(mesh, 'carray_list', 'keyforms')
        ongrid = named(grid, 'array_list', 'keyformsOnGrid')
        byform = {named(n, 'CFormGuid', 'keyformGuid').get('xs.ref'): n for n in ongrid}
        oldforms = list(forms)
        forms.clear(); forms.set('xs.n', 'keyforms')
        ongrid.clear(); ongrid.set('xs.n', 'keyformsOnGrid')
        for value in (0, 1):
            for oldform in oldforms:
                form = copy.deepcopy(oldform)
                oldguid = named(form, 'CFormGuid', 'guid').get('xs.ref')
                guid = self.define('CFormGuid', uuid=str(uuid.uuid4()), note='Expression opacity')
                named(form, 'CFormGuid', 'guid').set('xs.ref', guid.get('xs.id'))
                opacity = named(form, 'f', 'opacity')
                opacity.text = str(float(opacity.text) * (value if visible_when_one else 1-value))
                forms.append(form)
                if oldguid in byform:
                    item = copy.deepcopy(byform[oldguid])
                    keys = named(item, 'array_list', '_keyOnParameterList')
                else:
                    item = ET.Element('KeyformOnGrid')
                    access = ET.SubElement(item, 'KeyformGridAccessKey', {'xs.n': 'accessKey'})
                    keys = ET.SubElement(access, 'array_list', {'xs.n': '_keyOnParameterList'})
                    ET.SubElement(item, 'CFormGuid', {'xs.n': 'keyformGuid'})
                key = ET.SubElement(keys, 'KeyOnParameter')
                ET.SubElement(key, 'KeyformBindingSource', {'xs.n': 'binding', 'xs.ref': binding.get('xs.id')})
                ET.SubElement(key, 'i', {'xs.n': 'keyIndex'}).text = str(value)
                keys.set('count', str(len(keys)))
                named(item, 'CFormGuid', 'keyformGuid').set('xs.ref', guid.get('xs.id'))
                ongrid.append(item)
        forms.set('count', str(len(forms))); ongrid.set('count', str(len(ongrid)))
        binds = named(grid, 'array_list', 'keyformBindings')
        ET.SubElement(binds, 'KeyformBindingSource', {'xs.ref': binding.get('xs.id')})
        binds.set('count', str(len(binds)))

    def replace_image(self, name, path):
        mesh = self.meshes[name]
        texture = self.ids[mesh.find('GTexture2D').get('xs.ref')]
        ext = self.ids[mesh.find('.//CTextureInputExtension').get('xs.ref')]
        inp = ext.find('.//CTextureInput_ModelImage')
        if inp.get('xs.ref'):
            inp = self.ids[inp.get('xs.ref')]
        mg = named(inp, 'CModelImageGuid', '_modelImageGuid').get('xs.ref')
        modelimg = next(n for n in self.root.iter('CModelImage')
                        if named(n, 'CModelImageGuid', 'guid').get('xs.ref') == mg)
        refs = {n.get('xs.ref') for n in modelimg.iter('CImageResource') if n.get('xs.ref')}
        # Once packed, srcImageResource is the shared atlas, not this mesh's
        # original image. Updating it would replace the entire model texture.
        current = ext.find('*[@xs.n="currentTextureInputData"]')
        if current is None or current.tag != 'CTextureInput_TextureAtlasRegion':
            refs.add(named(texture, 'CImageResource', 'srcImageResource').get('xs.ref'))
        # Update the original PSD layer image too, so regeneration retains v24.
        for layerref in modelimg.iter('CLayer'):
            layer = self.ids[layerref.get('xs.ref')]
            refs.update(n.get('xs.ref') for n in layer.iter('CImageResource') if n.get('xs.ref'))
        entries = {e.name: e for e in self.doc.caff.entries}
        image = Image.open(path).convert('RGBA')
        for ref in refs:
            resource = self.ids[ref]
            file = resource.find('file[@xs.n="imageFileBuf"]')
            if file is None: raise ValueError('Unexpected image resource: '+ref)
            w,h = int(resource.get('width')),int(resource.get('height'))
            ratio = 2 if w < image.width else 1
            logical = image.resize((image.width//ratio,image.height//ratio), Image.Resampling.LANCZOS)
            if logical.width>w or logical.height>h: raise ValueError('Unexpected image extent')
            padded = Image.new('RGBA',(w,h)); padded.paste(logical,(0,0))
            buf=io.BytesIO(); padded.save(buf,format='PNG'); data=buf.getvalue()
            entries[file.get('path')].data=data
            resource.set('imageFileBuf_size',str(len(data)))

    def flush(self):
        ET.indent(self.root)
        # Cubism's version processing instructions select the deserializers.
        self.doc.xml = self.preamble + ET.tostring(self.root, encoding='unicode')


def main():
    src,dst=sys.argv[1:3]
    doc=t.Cmo3(src)
    editor=Editor(doc)
    if 'ParamEar' not in editor.params: raise ValueError('Use the latest expr2 rig with ParamEar')
    for pid,label in [('ParamTear','涙'),('ParamSweat','汗'),('ParamSparkle','キラキラ')]: editor.add_param(pid,label)
    for path in sorted((ROOT/'assets/ciel/generated/v24/layers').glob('*.png')):
        editor.replace_image(path.stem,path)
    # New meshes must be editor-visible; opacity, rather than editor visibility, controls export.
    for name in PLAN: named(editor.meshes[name],'b','isVisible').text='true'
    editor.flush()
    for name,(reference,param,order) in PLAN.items():
        image=Image.open(ROOT/'assets/ciel/generated/v23/layers'/ (name+'.png'))
        bounds=image.getbbox(); bbox=(max(0,bounds[0]-6),max(0,bounds[1]-6),min(image.width,bounds[2]+6),min(image.height,bounds[3]+6))
        mesh_ops.remesh_quad(doc,name,bbox,max(2,round((bbox[2]-bbox[0])/45)),max(2,round((bbox[3]-bbox[1])/45)))
        e=Editor(doc); mesh,ref=e.meshes[name],e.meshes[reference]
        points=np.array(named(ref,'float-array','point').text.split(),float).reshape(-1,2)
        refpos=np.array(named(ref,'carray_list','keyforms').find('.//float-array[@xs.n="positions"]').text.split(),float).reshape(-1,2)
        coef=np.linalg.lstsq(np.c_[points,np.ones(len(points))],refpos,rcond=None)[0]
        target=named(mesh,'CDeformerGuid','targetDeformerGuid')
        target.attrib.clear(); target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
        pts=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
        for form in named(mesh,'carray_list','keyforms'):
            pos=named(form,'float-array','positions'); pos.text=array(np.c_[pts,np.ones(len(pts))]@coef)
            coord=named(form,'CoordType','coordType'); coord.attrib.clear();coord.attrib.update(named(named(ref,'carray_list','keyforms')[0],'CoordType','coordType').attrib)
            named(form,'i','drawOrder').text=str(order)
        if name.endswith('Sparkle'):
            clip=named(mesh,'carray_list','clipGuidList'); clip.clear();clip.attrib.update(named(ref,'carray_list','clipGuidList').attrib)
            clip.extend(copy.deepcopy(list(named(ref,'carray_list','clipGuidList'))))
        e.opacity_binding(name,param,True);e.flush()
    # Extend ear and iris geometry to include the newly drawn roots/top edges.
    for name in ('Ear_L_Base','Ear_R_Base','Ear_L_Inner','Ear_R_Inner','Ear_L_Outer','Ear_R_Outer','Eye_L_Iris','Eye_R_Iris'):
        image=Image.open(ROOT/'assets/ciel/generated/v24/layers'/(name+'.png'))
        a,b,c,d=image.getbbox();bbox=(max(0,a-6),max(0,b-6),min(image.width,c+6),min(image.height,d+6))
        mesh_ops.remesh_rect(doc,name,bbox,max(2,round((c-a)/45)),max(2,round((d-b)/45)))
    e=Editor(doc)
    for name in list(e.meshes):
        if name.startswith(('Eye_L_','Eye_R_')) and name not in PLAN:
            e.opacity_binding(name,'ParamEyeLSmile' if name.startswith('Eye_L_') else 'ParamEyeRSmile',False)
    e.flush()
    # Structural guards catch dangling references and malformed vertex arrays before Cubism opens it.
    root=ET.fromstring(doc.xml);ids={n.get('xs.id') for n in root.iter() if n.get('xs.id')}
    assert all(n.get('xs.ref') in ids for n in root.iter() if n.get('xs.ref'))
    for n in root.iter():
        if n.tag in ('float-array','short-array','int-array','byte-array') and n.text:
            assert int(n.get('count'))==len(n.text.split()),(n.tag,n.attrib)
    doc.save(dst)
    print('EXPRESSION_INTEGRATION_DONE',dst)


if __name__=='__main__': main()
