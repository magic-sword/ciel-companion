"""Mouth material keys and combined expression atlases, in the GIMP remake scope.

These are source-resolution appearance studies, not Cubism keyforms.
"""
BLINK_LEVELS=33
MOUTH_LEVELS=33
mouth_domain={4*(y*W+x) for y in range(133,157) for x in range(116,166)}
mouth_skin=bytearray(reference)
for y in range(139,145):
    for x in range(125,157):
        i=4*(y*W+x);a=4*(137*W+x);b=4*(148*W+x);t=(y-137)/11
        mouth_skin[i:i+4]=bytes([round(reference[a+c]*(1-t)+reference[b+c]*t) for c in range(3)]+[255])

def mouth_materials(amount):
    materials={name:bytearray(W*H*4) for name in ['Interior','Tongue','UpperLip','LowerLip']}
    if not amount:return materials
    for i in mouth_domain:
        x,y=(i//4)%W,(i//4)//W
        coverage={name:0.0 for name in materials}
        for sx in [.125,.375,.625,.875]:
            for sy in [.125,.375,.625,.875]:
                t=(x+sx-126.5)/28
                if not 0<t<1:continue
                arc=math.sin(math.pi*t)
                center=140.6+.55*arc
                top=center-amount*2.0*arc
                bottom=center+amount*7.5*arc
                yy=y+sy
                if top<=yy<=bottom:
                    coverage['Interior']+=1/16
                    if yy>top+(bottom-top)*.74 and .2<t<.8:
                        coverage['Tongue']+=max(0,(amount-.4)/.6)/16
                taper=arc**.5
                if abs(yy-top)<.32*taper:coverage['UpperLip']+=1/16
                if abs(yy-bottom)<.28*taper:coverage['LowerLip']+=1/16
        colors={'Interior':(67,58,78),'Tongue':(127,102,128),
                'UpperLip':(94,94,111),'LowerLip':(134,128,146)}
        for name,cov in coverage.items():
            if cov:materials[name][i:i+4]=bytes([*colors[name],round(cov*255)])
    return materials

def speaking(amount,materials):
    if not amount:return reference
    result=bytearray(reference)
    fade=min(1,amount*8)
    for i in mouth_domain:
        rgb=[reference[i+c]*(1-fade)+mouth_skin[i+c]*fade for c in range(3)]
        for buf in materials.values():
            alpha=buf[i+3]/255
            rgb=[rgb[c]*(1-alpha)+buf[i+c]*alpha for c in range(3)]
        result[i:i+4]=bytes([round(v) for v in rgb]+[255])
    return bytes(result)

eye_frames={}
mouth_frames={}
eye_doc=Gimp.Image.new(W*17,H*BLINK_LEVELS,Gimp.ImageBaseType.RGB)
mouth_doc=Gimp.Image.new(W*MOUTH_LEVELS,H,Gimp.ImageBaseType.RGB)
mouth_keys=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(mouth_keys,'Face_Reference',reference)
underpaint=bytearray(W*H*4)
for i in mouth_domain:
    if mouth_skin[i:i+4]!=reference[i:i+4]:underpaint[i:i+4]=mouth_skin[i:i+4]
layer(mouth_keys,'Skin_Underpaint',underpaint).set_visible(False)
for level in range(BLINK_LEVELS):
    closure=level/(BLINK_LEVELS-1)
    for frame in range(17):
        rgba=render((frame-8)/2,closure)
        assert all(rgba[i:i+4]==reference[i:i+4] for i in opaque_hair_indices)
        if closure==1:assert rgba==closed
        eye_frames[(frame,level)]=rgba
        layer(eye_doc,f'Gaze_{frame}_Closure_{level}',rgba,frame*W,level*H)
    print('REMAKE_BLINK_LEVEL',level,flush=True)
for level in range(MOUTH_LEVELS):
    amount=level/(MOUTH_LEVELS-1)
    materials=mouth_materials(amount)
    rgba=speaking(amount,materials)
    mouth_frames[level]=rgba
    layer(mouth_doc,f'Mouth_{level}',rgba,level*W)
    if level in [(MOUTH_LEVELS-1)//4,(MOUTH_LEVELS-1)//2,MOUTH_LEVELS-1]:
        for name,buf in materials.items():
            layer(mouth_keys,f'Mouth_{level}_{name}',buf).set_visible(False)
    print('REMAKE_EXPRESSION_LEVEL',level,flush=True)
assert eye_frames[(8,0)]==mouth_frames[0]==reference
for name,doc in [('blink-atlas',eye_doc),('mouth-atlas',mouth_doc)]:
    run_proc('file-png-export',image=doc,file=Gio.File.new_for_path(str(OUT/(name+'.png'))))
    doc.delete()
for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    path=OUT/('mouth-material-keys.'+suffix)
    expected={item.get_name():pixels(item) for item in mouth_keys.get_layers()}
    run_proc(proc,image=mouth_keys,file=Gio.File.new_for_path(str(path)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    assert composite(loaded)==reference
    assert {item.get_name():pixels(item) for item in loaded.get_layers()}==expected
    loaded.delete()
mouth_keys.delete()

# Combine the same regions used by the browser, including the reported failure case.
combined=Gimp.Image.new(W*3,H*3,Gimp.ImageBaseType.RGB)
for row,blink in enumerate([0,(BLINK_LEVELS-1)//2,BLINK_LEVELS-1]):
    for col,frame in enumerate([0,8,16]):
        rgba=bytearray(eye_frames[(frame,blink)])
        for i in mouth_domain:rgba[i:i+4]=mouth_frames[MOUTH_LEVELS-1][i:i+4]
        layer(combined,f'{frame}_{blink}',rgba,col*W,row*H)
run_proc('file-png-export',image=combined,file=Gio.File.new_for_path(str(OUT/'combined-comparison.png')))
combined.delete()
tracking=[]
for side,x,y in [('R',87,68),('L',192,66)]:
    i=4*(y*W+x)
    assert data[side]['buffers']['Highlight'][i+3]==255
    for dx in [-4,0,4]:
        rgba=eye_frames[(8+dx*2,0)];j=4*(y*W+x+dx)
        assert rgba[j:j+4]==reference[i:i+4], 'Primary highlight failed to follow iris'
        tracking.append(dict(side=side,gaze_px=dx,source=[x,y],destination=[x+dx,y],equal=True))
for level,rgba in mouth_frames.items():
    assert all(rgba[i:i+4]==reference[i:i+4] for i in range(0,len(reference),4) if i not in mouth_domain)
report['primary_highlight_tracking']=tracking
report['browser_masks']=dict(hair_pixels=sorted(i//4 for i in opaque_hair_indices),
    source_hair_pixels=sorted(i//4 for i in hair_indices),
    eye_pixels=sorted(i//4 for i in eye_indices),mouth_rect=[116,133,50,24])
report['hair_alpha_compositing']=dict(
    pixels=[dict(pixel=i//4,rgba=list(hair_matte[i:i+4])) for i in translucent_hair_indices],
    underlays=[hair_underlay_samples[((frame-8)/2,level/(BLINK_LEVELS-1))]
               for level in range(BLINK_LEVELS) for frame in range(17)],
    order='blink level first, then gaze frame; colors match pixels array order',
    method='straight alpha in encoded RGB, rounded to 8 bit; estimated material')
report['expression_atlas']=dict(gaze_frames=17,blink_levels=BLINK_LEVELS,mouth_levels=MOUTH_LEVELS,
    neutral_equal=True,hair_holdouts_equal=True,closed_independent_of_gaze=True,
    mouth_material_roundtrip_equal=True,
    mouth_design='Curved upper/lower lip, separate interior and subtle tongue; awaiting visual review')
(OUT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('REMAKE_EXPRESSIONS_READY',flush=True)
