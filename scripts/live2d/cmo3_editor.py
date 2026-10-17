"""Cubism Editor の .cmo3 を、XML の木（ElementTree）として書き換える道具。

cmo3_tool.Cmo3 で開いた文書から Editor を作り、部品・パラメーター・キーを足してから flush() で文書へ戻す。
- define：新しい共有オブジェクト（xs.id 付き）を作る
- add_param：パラメーターを足す（範囲 0〜1、初期値 0。必要なら呼び出し側で書き換える）
- opacity_binding：メッシュの不透明度を、パラメーターのキーで切り替える
- replace_image：メッシュの絵（PSD の層の画像も）を差し替える
もとは表情の取り込み（v23）のスクリプトの一部だったものを、共通の道具として切り出した。
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

    def opacity_binding(self, name, param, visible_when_one, key_values=(0, 1)):
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
        vals.set('count',str(len(key_values)))
        for v in key_values: ET.SubElement(vals, 'f').text = str(float(v))
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
        for value_index,value in enumerate(key_values):
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
                ET.SubElement(key, 'i', {'xs.n': 'keyIndex'}).text = str(value_index)
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
