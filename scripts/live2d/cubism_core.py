# -*- coding: utf-8 -*-
"""Cubism Core（Unity SDK に入っている Live2DCubismCore.dll）を、Python から呼ぶ。

書き出したモデル（.moc3）にパラメーターを与えて、Cubism と同じ計算で、各メッシュの頂点・不透明度・描画順を得る。
描画は render-moc.py。

使い方（Pythonから）
    import cubism_core as cc
    m = cc.Model('unity/Assets/Characters/Ciel/Ciel.model3.json')
    m.set({'ParamAngleX': 30})
    m.update()
    d = m.drawables()          # メッシュごとの dict（id, 頂点(px), uv, 三角形, 不透明度, 描画順 など）
"""
import ctypes as C
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, '..', '..', 'unity', 'Assets', 'Live2D', 'Cubism', 'Plugins', 'Windows', 'x86_64', 'Live2DCubismCore.dll')

_lib = None


def lib():
    global _lib
    if _lib is None:
        _lib = C.CDLL(os.path.abspath(DLL))
        P = C.c_void_p
        sig = {
            'csmGetVersion': (C.c_uint, []),
            'csmReviveMocInPlace': (P, [P, C.c_uint]),
            'csmGetSizeofModel': (C.c_uint, [P]),
            'csmInitializeModelInPlace': (P, [P, P, C.c_uint]),
            'csmUpdateModel': (None, [P]),
            'csmReadCanvasInfo': (None, [P, P, P, P]),
            'csmGetParameterCount': (C.c_int, [P]),
            'csmGetParameterIds': (C.POINTER(C.c_char_p), [P]),
            'csmGetParameterMinimumValues': (C.POINTER(C.c_float), [P]),
            'csmGetParameterMaximumValues': (C.POINTER(C.c_float), [P]),
            'csmGetParameterDefaultValues': (C.POINTER(C.c_float), [P]),
            'csmGetParameterValues': (C.POINTER(C.c_float), [P]),
            'csmGetPartCount': (C.c_int, [P]),
            'csmGetPartIds': (C.POINTER(C.c_char_p), [P]),
            'csmGetPartOpacities': (C.POINTER(C.c_float), [P]),
            'csmGetDrawableCount': (C.c_int, [P]),
            'csmGetDrawableIds': (C.POINTER(C.c_char_p), [P]),
            'csmGetDrawableConstantFlags': (C.POINTER(C.c_ubyte), [P]),
            'csmGetDrawableDynamicFlags': (C.POINTER(C.c_ubyte), [P]),
            'csmGetDrawableTextureIndices': (C.POINTER(C.c_int), [P]),
            'csmGetDrawableDrawOrders': (C.POINTER(C.c_int), [P]),
            'csmGetRenderOrders': (C.POINTER(C.c_int), [P]),
            'csmGetDrawableOpacities': (C.POINTER(C.c_float), [P]),
            'csmGetDrawableMaskCounts': (C.POINTER(C.c_int), [P]),
            'csmGetDrawableMasks': (C.POINTER(C.POINTER(C.c_int)), [P]),
            'csmGetDrawableVertexCounts': (C.POINTER(C.c_int), [P]),
            'csmGetDrawableVertexPositions': (C.POINTER(C.POINTER(C.c_float)), [P]),
            'csmGetDrawableVertexUvs': (C.POINTER(C.POINTER(C.c_float)), [P]),
            'csmGetDrawableIndexCounts': (C.POINTER(C.c_int), [P]),
            'csmGetDrawableIndices': (C.POINTER(C.POINTER(C.c_ushort)), [P]),
            'csmGetDrawableMultiplyColors': (C.POINTER(C.c_float), [P]),
            'csmGetDrawableScreenColors': (C.POINTER(C.c_float), [P]),
            'csmGetDrawableParentPartIndices': (C.POINTER(C.c_int), [P]),
        }
        for name, (res, args) in sig.items():
            f = getattr(_lib, name)
            f.restype, f.argtypes = res, args
    return _lib


def _aligned(size, align):
    raw = C.create_string_buffer(size + align)
    addr = (C.addressof(raw) + align - 1) // align * align
    return raw, addr


class Model:
    def __init__(self, model3_json):
        L = lib()
        self.dir = os.path.dirname(os.path.abspath(model3_json))
        self.settings = json.load(open(model3_json, encoding='utf-8'))
        refs = self.settings['FileReferences']
        moc = open(os.path.join(self.dir, refs['Moc']), 'rb').read()
        self._moc_buf, moc_addr = _aligned(len(moc), 64)
        C.memmove(moc_addr, moc, len(moc))
        self._moc = L.csmReviveMocInPlace(moc_addr, len(moc))
        if not self._moc:
            raise RuntimeError('moc3 を読めなかった（Core の版が古い可能性）')
        size = L.csmGetSizeofModel(self._moc)
        self._model_buf, model_addr = _aligned(size, 16)
        self.m = L.csmInitializeModelInPlace(self._moc, model_addr, size)
        self.textures = [os.path.join(self.dir, p) for p in refs['Textures']]
        sz = (C.c_float * 2)()
        org = (C.c_float * 2)()
        ppu = C.c_float()
        L.csmReadCanvasInfo(self.m, C.byref(sz), C.byref(org), C.byref(ppu))
        self.canvas = (sz[0], sz[1])
        self.origin = (org[0], org[1])
        self.ppu = ppu.value
        n = L.csmGetParameterCount(self.m)
        ids = L.csmGetParameterIds(self.m)
        self.param_ids = [ids[i].decode() for i in range(n)]
        mn, mx, df = L.csmGetParameterMinimumValues(self.m), L.csmGetParameterMaximumValues(self.m), L.csmGetParameterDefaultValues(self.m)
        self.param_range = {self.param_ids[i]: (mn[i], df[i], mx[i]) for i in range(n)}
        self.reset()

    def reset(self):
        v = lib().csmGetParameterValues(self.m)
        for i, pid in enumerate(self.param_ids):
            v[i] = self.param_range[pid][1]

    def set(self, values):
        """{パラメーターID: 値}。範囲の外は範囲へ収める。無い ID は無視して、その名前を返す。"""
        v = lib().csmGetParameterValues(self.m)
        missing = []
        for pid, val in values.items():
            if pid not in self.param_range:
                missing.append(pid)
                continue
            lo, _, hi = self.param_range[pid]
            v[self.param_ids.index(pid)] = min(hi, max(lo, float(val)))
        return missing

    def update(self):
        lib().csmUpdateModel(self.m)

    def drawables(self):
        L = lib()
        m = self.m
        n = L.csmGetDrawableCount(m)
        ids = L.csmGetDrawableIds(m)
        cflags = L.csmGetDrawableConstantFlags(m)
        tex = L.csmGetDrawableTextureIndices(m)
        dord = L.csmGetDrawableDrawOrders(m)
        rord = L.csmGetRenderOrders(m)
        op = L.csmGetDrawableOpacities(m)
        mc = L.csmGetDrawableMaskCounts(m)
        masks = L.csmGetDrawableMasks(m)
        vc = L.csmGetDrawableVertexCounts(m)
        vp = L.csmGetDrawableVertexPositions(m)
        uv = L.csmGetDrawableVertexUvs(m)
        ic = L.csmGetDrawableIndexCounts(m)
        ix = L.csmGetDrawableIndices(m)
        mul = L.csmGetDrawableMultiplyColors(m)
        scr = L.csmGetDrawableScreenColors(m)
        dflags = L.csmGetDrawableDynamicFlags(m)
        ox, oy = self.origin
        out = []
        for i in range(n):
            k = vc[i]
            pos = np.ctypeslib.as_array(vp[i], shape=(k * 2,)).reshape(-1, 2).astype(np.float64)
            px = np.stack([ox + pos[:, 0] * self.ppu, oy - pos[:, 1] * self.ppu], 1)
            uvs = np.ctypeslib.as_array(uv[i], shape=(k * 2,)).reshape(-1, 2).copy()
            tri = np.ctypeslib.as_array(ix[i], shape=(ic[i],)).reshape(-1, 3).astype(np.int64) if ic[i] else np.zeros((0, 3), np.int64)
            out.append(dict(
                id=ids[i].decode(), index=i, pos=px, uv=uvs, tri=tri,
                opacity=op[i], draw_order=dord[i], render_order=rord[i], texture=tex[i],
                blend=('add' if cflags[i] & 1 else 'mul' if cflags[i] & 2 else 'normal'),
                double_sided=bool(cflags[i] & 4), inverted_mask=bool(cflags[i] & 8),
                visible=bool(dflags[i] & 1),
                masks=[masks[i][j] for j in range(mc[i])],
                multiply=tuple(mul[i * 4 + j] for j in range(3)) if mul else (1, 1, 1),
                screen=tuple(scr[i * 4 + j] for j in range(3)) if scr else (0, 0, 0),
            ))
        return out
