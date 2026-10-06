"""Expression study invoked by build_face_registration.py inside GIMP.

Source-resolution motion study, not final Cubism artwork. Shared globals are the
verified reference, partitions, gaze_frames and the GIMP export helpers.
"""
EXPR = ROOT / 'assets/private/ciel/live2d/gimp/face-expressions-v1'
EXPR.mkdir(parents=True, exist_ok=True)
eye_masks = {}
skin = bytearray(reference)
blink_polygons = {
    'R': [(37,78),(46,64),(62,52),(85,49),(104,58),(114,76),(109,95),(101,108),(73,110),(52,103),(42,91)],
    'L': [(164,78),(172,61),(188,49),(214,47),(232,60),(243,77),(235,96),(218,109),(183,110),(170,97)],
}
for side in ['R', 'L']:
    mask = {4 * (y * W + x) for y in range(H) for x in range(W)
            if inside(x + .5, y + .5, blink_polygons[side])}
    eye_masks[side] = mask
    samples = []
    for i in range(0, len(reference), 4):
        rgb = reference[i:i + 3]
        sx, sy = (i // 4) % W, (i // 4) // W
        xlo, xhi = (55, 110) if side == 'R' else (175, 226)
        if xlo <= sx <= xhi and 111 <= sy <= 126 and min(rgb) > 230 and max(rgb) - min(rgb) < 22:
            samples.append(((i // 4) % W, (i // 4) // W, rgb))
    assert samples
    for i in mask:
        x, y = (i // 4) % W, (i // 4) // W
        skin[i:i + 4] = interpolate(samples, x, y)
eye_domain = eye_masks['R'] | eye_masks['L']


def blinking(source, closure):
    if closure == 0:
        return bytes(source)
    result = bytearray(source)
    openness = 1 - closure
    for side, mask in eye_masks.items():
        for i in mask:
            x, y = (i // 4) % W, (i // 4) // W
            start, end = (44, 111) if side == 'R' else (168, 239)
            t = max(0, min(1, (x - start) / (end - start)))
            center = 81 + 13 * math.sin(math.pi * t)
            # Lids occlude the original iris instead of squashing its texture.
            arc = math.sin(math.pi * t)
            upper = (81 - 25 * arc) * openness + center * closure
            lower = (81 + 25 * arc) * openness + center * closure
            alpha = max(0.0, min(1.0, y - upper + .5, lower - y + .5)) if openness else 0.0
            values = [source[i + c] * alpha for c in range(3)]
            taper = math.sin(math.pi * t) ** .4
            thickness = (2.1 - .7 * closure) * taper
            lash = max(0.0, min(1, (thickness + .6 - abs(y - upper)))) * min(1, closure * 4)
            rgb = [values[c] + skin[i + c] * (1 - alpha) for c in range(3)]
            # Preserve the original pale boundary pixels to avoid a polygon seam.
            edge = min((sum(4 * ((y + oy) * W + x + ox) in mask
                            for ox, oy in [(-d,0),(d,0),(0,-d),(0,d)]) / 4)
                       for d in [1, 2])
            result[i:i + 4] = bytes([round((rgb[c] * (1 - lash) + (55, 60, 73)[c] * lash) * edge
                                          + source[i + c] * (1 - edge)) for c in range(3)] + [255])
    return bytes(result)


mouth_domain = {4 * (y * W + x) for y in range(133, 157) for x in range(116, 166)}
mouth_skin = bytearray(reference)
for i in mouth_domain:
    x, y = (i // 4) % W, (i // 4) // W
    # Interpolate clean porcelain skin above and below the existing mouth line.
    a, b = 4 * (130 * W + x), 4 * (159 * W + x)
    t = (y - 130) / 29
    mouth_skin[i:i + 4] = bytes([round(reference[a + c] * (1 - t) + reference[b + c] * t)
                                for c in range(3)] + [255])


def speaking(amount):
    if amount == 0:
        return reference
    result = bytearray(reference)
    cx, cy = 140.0, 141.2 + amount * 1.4
    rx, ry = 12 + amount * 2, .6 + amount * 6
    for i in mouth_domain:
        x, y = (i // 4) % W, (i // 4) // W
        # Gradually remove the source closed line, retaining it exactly at zero.
        fade = min(1, amount * 4)
        base = [reference[i + c] * (1 - fade) + mouth_skin[i + c] * fade for c in range(3)]
        color = [0.0] * 3
        for sx in [.125, .375, .625, .875]:
            for sy in [.125, .375, .625, .875]:
                u, v = (x + sx - cx) / rx, (y + sy - cy) / ry
                if u * u + v * v <= 1:
                    # Quiet cool mouth interior; no strong human-skin blush.
                    inside_color = (66, 52, 67)
                    if amount >= .5 and v > .45 and u * u + ((v - .72) / .5) ** 2 < .8:
                        inside_color = (153, 115, 135)
                    for c in range(3): color[c] += inside_color[c]
                else:
                    for c in range(3): color[c] += base[c]
        result[i:i + 4] = bytes([round(c / 16) for c in color] + [255])
    return bytes(result)


def verify_expression(rgba, domain):
    outside = sum(rgba[i:i + 4] != reference[i:i + 4]
                  for i in range(0, len(reference), 4) if i not in domain)
    holes = sum(rgba[i + 3] != 255 for i in range(0, len(reference), 4))
    assert outside == 0 and holes == 0
    return dict(changed_pixels_outside_domain=outside, nonopaque_pixels=holes,
                changed_pixels=compare(rgba)['changed_pixels'])


blink_atlas = Gimp.Image.new(W * 17, H * 5, Gimp.ImageBaseType.RGB)
mouth_atlas = Gimp.Image.new(W * 5, H, Gimp.ImageBaseType.RGB)
comparison_doc = Gimp.Image.new(W * 5, H * 2, Gimp.ImageBaseType.RGB)
states_doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
expression_checks = {'blink': {}, 'mouth': {}}
for level in range(5):
    amount = level / 4
    for frame, source in gaze_frames.items():
        rgba = blinking(source, amount)
        expression_checks['blink'][f'{frame}:{level}'] = verify_expression(rgba, eye_domain)
        new_layer(blink_atlas, f'Gaze_{frame}_Blink_{level}', rgba, frame * W).set_offsets(frame * W, level * H)
        if frame == 8:
            new_layer(comparison_doc, f'Blink_{level}', rgba, level * W)
            new_layer(states_doc, f'Blink_{level}', rgba).set_visible(False)
        if level == 0:
            assert rgba == source
    mouth = speaking(amount)
    expression_checks['mouth'][str(level)] = verify_expression(mouth, mouth_domain)
    new_layer(mouth_atlas, f'Mouth_{level}', mouth, level * W)
    new_layer(comparison_doc, f'Mouth_{level}', mouth, level * W).set_offsets(level * W, H)
    new_layer(states_doc, f'Mouth_{level}', mouth).set_visible(False)
new_layer(states_doc, 'Normal_Approved', reference)
for name, doc in [('blink-atlas', blink_atlas), ('mouth-atlas', mouth_atlas), ('comparison', comparison_doc)]:
    run_proc('file-png-export', image=doc, file=Gio.File.new_for_path(str(EXPR / (name + '.png'))))
    doc.delete()
expression_checks['normal'] = compare(composite(states_doc))
assert expression_checks['normal']['equal']
expected_states = {layer.get_name(): pixels(layer) for layer in states_doc.get_layers()}
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    path = EXPR / ('expression-states.' + suffix)
    run_proc(proc, image=states_doc, file=Gio.File.new_for_path(str(path)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    expression_checks[suffix] = compare(composite(loaded))
    expression_checks[suffix]['all_state_pixels_match'] = all(
        pixels(layer) == expected_states[layer.get_name()] for layer in loaded.get_layers())
    assert expression_checks[suffix]['equal'] and len(loaded.get_layers()) == 11
    assert expression_checks[suffix]['all_state_pixels_match']
    loaded.delete()
states_doc.delete()
(EXPR / 'verification.json').write_text(json.dumps(dict(
    source='docs/assets/ciel/ciel-approved-appearance-v1.png', crop=list(CROP),
    stage='Expression motion study, not rig-ready art', checks=expression_checks,
    blink_polygons=blink_polygons, levels=[0, .25, .5, .75, 1],
    skin_sampling='Clean cheek pixels, y111..126, min RGB >230, channel spread <22',
    limitations=['Closed lids occlude the reference iris using provisional animated lid curves',
                 'Open mouth is newly drawn procedural artwork, awaiting appearance review',
                 'Full-frame state layers are preview frames, not Cubism parts',
                 'No final-resolution artwork or Cubism deformation tests']), indent=2), encoding='utf-8')
print('CIEL_EXPRESSIONS_OK', flush=True)
