"""Genera un Short vertical 1080x1920 a partir de los cuadros anuales."""
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (12, 38, 48)          # azul petróleo profundo
INK = (236, 242, 236)
MUTED = (150, 178, 176)
ACCENT = (224, 170, 72)    # ocre sedimento
LINE = (62, 150, 170)

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "C:/Windows/Fonts"]
UNITS = {"agua": "km² de agua", "ndvi": "NDVI medio (vegetación)", "urbano": "km² urbanizados"}
LAYER_TXT = {"rgb": "Color natural", "ndvi": "Vigor de la vegetación (NDVI)",
             "agua": "Superficie de agua (MNDWI)", "urbano": "Zona construida (NDBI)"}
SOURCES = {"landsat": "Landsat 5/7/8/9 · USGS/NASA", "sentinel2": "Sentinel-2 · ESA Copernicus"}


def _font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"] if bold else \
            ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


F_TITLE, F_SUB, F_YEAR = _font(64, True), _font(38), _font(210, True)
F_STAT, F_SMALL = _font(46, True), _font(30)


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def _map_tile(png_path: str, box=(W - 80, 1000)):
    img = Image.open(png_path).convert("RGBA")
    img.thumbnail(box, Image.LANCZOS)
    bg = Image.new("RGBA", img.size, (20, 30, 34, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def _sparkline(draw, values, upto, rect):
    x0, y0, x1, y1 = rect
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(values)
    pts = [(x0 + i * (x1 - x0) / (n - 1), y1 - (v - lo) / span * (y1 - y0))
           for i, v in enumerate(values[:upto + 1]) if v is not None]
    draw.line([(x0, y1), (x1, y1)], fill=(40, 70, 80), width=2)
    if len(pts) > 1:
        draw.line(pts, fill=LINE, width=6, joint="curve")
    if pts:
        cx, cy = pts[-1]
        draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=ACCENT)


def render_frame(region, frame, idx, frames):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    y = 110
    for line in _wrap(d, region["nombre"], F_TITLE, W - 120):
        d.text((60, y), line, font=F_TITLE, fill=INK)
        y += 76
    d.text((60, y + 8), f"{region['tema']} · {LAYER_TXT[region['capa_video']]}", font=F_SUB, fill=MUTED)

    tile = _map_tile(frame["png"])
    ty = 360 + (1000 - tile.height) // 2
    im.paste(tile, ((W - tile.width) // 2, ty))

    d.text((60, 1370), str(frame["anio"]), font=F_YEAR, fill=INK)
    if frame["valor"] is not None:
        d.text((64, 1600), f"{frame['valor']:,.2f} {UNITS[region['metrica']]}", font=F_STAT, fill=ACCENT)
    _sparkline(d, [f["valor"] for f in frames], idx, (60, 1680, W - 60, 1790))
    d.text((60, 1830), f"Datos: {SOURCES[region['sensor']]} · Google Earth Engine",
           font=F_SMALL, fill=MUTED)
    return im


def render_end_card(region, frames):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    a, b = frames[0], frames[-1]
    y = 520
    for line in _wrap(d, f"{region['nombre']}: {a['anio']} → {b['anio']}", F_TITLE, W - 120):
        d.text((60, y), line, font=F_TITLE, fill=INK)
        y += 80
    if a["valor"] is not None and b["valor"] is not None:
        delta = b["valor"] - a["valor"]
        pct = (delta / a["valor"] * 100) if a["valor"] else 0
        d.text((60, y + 60), f"{delta:+,.2f}", font=_font(150, True), fill=ACCENT)
        d.text((60, y + 240), f"{UNITS[region['metrica']]} ({pct:+.1f} %)", font=F_SUB, fill=INK)
    _sparkline(d, [f["valor"] for f in frames], len(frames) - 1, (60, 1250, W - 60, 1500))
    for i, line in enumerate(["Monitoreo satelital del Caribe colombiano",
                              "Sigue el canal para ver la próxima región"]):
        d.text((60, 1640 + i * 50), line, font=F_SMALL, fill=MUTED)
    return im


def build_video(region, frames, out_path: Path, vcfg: dict):
    fps = vcfg.get("fps", 30)
    hold = int(vcfg.get("segundos_por_cuadro", 1.2) * fps)
    fade = int(vcfg.get("segundos_transicion", 0.4) * fps)
    end = int(vcfg.get("segundos_cierre", 3.5) * fps)
    rendered = [np.asarray(render_frame(region, f, i, frames)) for i, f in enumerate(frames)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    w = imageio.get_writer(out_path, fps=fps, codec="libx264", quality=8,
                           pixelformat="yuv420p", macro_block_size=8)
    for i, fr in enumerate(rendered):
        for _ in range(hold):
            w.append_data(fr)
        if i + 1 < len(rendered):
            nxt = rendered[i + 1].astype(np.float32)
            cur = fr.astype(np.float32)
            for k in range(1, fade + 1):
                t = k / (fade + 1)
                w.append_data((cur * (1 - t) + nxt * t).astype(np.uint8))
    endcard = np.asarray(render_end_card(region, frames))
    for _ in range(end):
        w.append_data(endcard)
    w.close()
    secs = (len(rendered) * hold + (len(rendered) - 1) * fade + end) / fps
    if secs > 60:
        print(f"  Aviso: el video dura {secs:.0f}s; sube paso_anios para mantenerlo < 60 s")
    return out_path
