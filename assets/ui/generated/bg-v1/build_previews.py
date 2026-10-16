"""Normalize generated canvases and build only the requested review composites.

Run from the repository root. All output remains beside this script.
The artwork and time-of-day edits are produced by image_gen, not this script.
"""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
SIZE = (1080, 1920)
TIMES = ("day", "dusk", "night")
LABELS = {"day": "DAY / 昼", "dusk": "DUSK / 夕方", "night": "NIGHT / 夜"}
PREVIEW = ROOT / "previews"
PREVIEW.mkdir(exist_ok=True)
FONT = "C:/Windows/Fonts/YuGothM.ttc"


def font(size):
    return ImageFont.truetype(FONT, size)


def cover(im, size):
    return ImageOps.fit(im, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def strip(images, labels, dest, panel=(360, 640)):
    margin, header = 18, 52
    canvas = Image.new("RGB", (margin + len(images) * (panel[0] + margin), panel[1] + header + margin), "#14232b")
    draw = ImageDraw.Draw(canvas)
    for i, (im, label) in enumerate(zip(images, labels)):
        x = margin + i * (panel[0] + margin)
        draw.text((x, 13), label, font=font(19), fill="#e5f0f4")
        canvas.paste(im.resize(panel, Image.Resampling.LANCZOS).convert("RGB"), (x, header))
    canvas.save(dest)


def character_composite(bg, character, width):
    result = bg.convert("RGBA")
    w, h = result.size
    char_h = round(character.height * width / character.width)
    char = character.resize((width, char_h), Image.Resampling.LANCZOS)
    result.alpha_composite(char, ((w - width) // 2, h - char_h))
    return result


def app_ui(im):
    """Approximate screenshot UI, for review only; never baked into the assets."""
    im = im.convert("RGBA")
    w, h = im.size
    shade = Image.new("RGBA", im.size)
    d = ImageDraw.Draw(shade)
    for y in range(round(h * .57), h):
        a = round(175 * ((y / h - .57) / .43))
        d.line((0, y, w, y), fill=(11, 25, 35, a))
    im = Image.alpha_composite(im, shade)
    layer = Image.new("RGBA", im.size)
    d = ImageDraw.Draw(layer)
    cyan, white = (123, 218, 235, 180), (238, 248, 250, 240)
    d.text((32, 18), "C I E L", font=font(18), fill=white)
    d.text((32, 49), "● つながっていません（タップでつなぐ）", font=font(13), fill=(217, 238, 246, 180))
    d.rounded_rectangle((289, 9, 451, 58), 25, fill=(15, 46, 60, 150), outline=cyan, width=1)
    d.text((315, 23), "みんなで", font=font(17), fill=white)
    d.ellipse((463, 9, 511, 58), fill=(15, 46, 60, 150), outline=cyan)
    for sy, knob in ((26, 487), (34, 482), (42, 491)):
        d.line((477, sy, 498, sy), fill=white, width=1)
        d.ellipse((knob-2, sy-2, knob+2, sy+2), fill=white)
    d.text((w // 2, round(h * .798)), "接続していません", anchor="mt", font=font(24), fill=white, stroke_width=1, stroke_fill=(20, 35, 45, 130))
    cy = round(h * .91)
    d.ellipse((w//2-75, cy-75, w//2+75, cy+75), outline=(106, 212, 232, 115), width=2)
    # Simple microphone, file and volume symbols drawn without font-dependent glyphs.
    d.rounded_rectangle((w//2-6, cy-17, w//2+6, cy+8), 6, outline=white, width=3)
    d.arc((w//2-12, cy-9, w//2+12, cy+16), 0, 180, fill=white, width=3)
    d.line((w//2, cy+16, w//2, cy+24), fill=white, width=3)
    for cx, label in ((87, "議事録"), (453, "声の大きさ")):
        d.ellipse((cx-35, cy-62, cx+35, cy+8), outline=cyan, width=2)
        d.text((cx, cy+23), label, anchor="mt", font=font(14), fill=white)
    d.rectangle((81, cy-38, 94, cy-18), outline=white, width=2)
    d.line((84, cy-31, 91, cy-31), fill=white)
    d.polygon(((445,cy-30),(450,cy-30),(457,cy-36),(457,cy-20),(450,cy-26),(445,cy-26)), outline=white)
    d.arc((452,cy-38,466,cy-18), 290, 70, fill=white, width=2)
    return Image.alpha_composite(im, layer).convert("RGB")


def normalize(name):
    src = ROOT / "sources" / ("salon_" + name + "_generated.png")
    out = ROOT / ("salon_" + name + ".png")
    if src.exists():
        raw = Image.open(src).convert("RGB")
        cover(raw, SIZE).save(out)
        scale = max(SIZE[0] / raw.width, SIZE[1] / raw.height)
        return {"source_size": list(raw.size), "delivery_size": list(SIZE), "normalization": "center cover, Lanczos", "source_crop_width": round(SIZE[0]/scale, 3), "source_crop_height": round(SIZE[1]/scale, 3)}
    return None


def main():
    metadata = {}
    for name in TIMES:
        info = normalize(name)
        if info:
            metadata[name] = info
    day_path = ROOT / "salon_day.png"
    if not day_path.exists():
        raise SystemExit("salon_day.png or sources/salon_day_generated.png is required")
    screen = Image.open(ROOT / "inputs" / "app-screen-now.png").convert("RGB")
    day = Image.open(day_path).convert("RGB")
    day_screen = cover(day, screen.size)
    blend = Image.blend(screen, day_screen, .5)
    blend.save(PREVIEW / "day_overlay_50.png")
    strip([screen, day_screen, blend], ["CURRENT / 現画面", "DAY / 背景・同じ切り取り", "50% OVERLAY / 重ね合わせ"], PREVIEW / "day_composition_check.png", panel=(360, 780))
    # Safe regions marked only in this separate proof.
    regions = day.convert("RGBA")
    layer = Image.new("RGBA", regions.size)
    d = ImageDraw.Draw(layer)
    d.rectangle((324, 230, 724, 1248), fill=(80, 195, 223, 28), outline=(80, 195, 223, 200), width=3)
    d.rectangle((0, 1344, 1079, 1919), fill=(250, 183, 80, 25), outline=(250, 183, 80, 180), width=3)
    d.line((97, 0, 97, 1920), fill=(255, 100, 100, 180), width=3)
    d.line((983, 0, 983, 1920), fill=(255, 100, 100, 180), width=3)
    Image.alpha_composite(regions, layer).convert("RGB").save(PREVIEW / "day_safe_regions.png")
    character = Image.open(REPO / "assets" / "ciel" / "master" / "ciel-upper-body-2x.png").convert("RGBA")
    arts, full_comps, app_comps, labels = [], [], [], []
    for name in TIMES:
        path = ROOT / ("salon_" + name + ".png")
        if not path.exists():
            continue
        bg = Image.open(path).convert("RGB")
        assert bg.size == SIZE and bg.width * 16 == bg.height * 9
        # Exactly 14px at delivery resolution. Ciel stays sharp.
        blurred = bg.filter(ImageFilter.GaussianBlur(14))
        comp = character_composite(blurred, character, SIZE[0]).convert("RGB")
        comp.save(PREVIEW / ("salon_" + name + "_ciel.png"))
        # Actual screenshot aspect: background cover crop, 14px at 540x1170.
        # Sprite width=1.5x viewport approximates the large Live2D framing.
        phone_bg = cover(bg, screen.size).filter(ImageFilter.GaussianBlur(14))
        phone = app_ui(character_composite(phone_bg, character, round(screen.width * 1.5)))
        phone.save(PREVIEW / ("salon_" + name + "_app_approx.png"))
        arts.append(bg)
        full_comps.append(comp)
        app_comps.append(phone)
        labels.append(LABELS[name])
    strip(arts, labels, PREVIEW / "salon_triptych.png")
    strip(full_comps, labels, PREVIEW / "ciel_triptych.png")
    strip(app_comps, labels, PREVIEW / "app_triptych_approx.png", panel=(360, 780))
    (ROOT / "image_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print("Created review images for: " + ", ".join(labels))


if __name__ == "__main__":
    main()
