"""Genera un reel vertical 1080x1920 (YouTube Shorts / Instagram Reels).

Estructura pensada para retener en los primeros segundos:
  1. Gancho (≈2,5 s): antes y después en pantalla dividida + pregunta.
  2. Timelapse año a año con acercamiento lento, cifra del año y línea que avanza.
  3. Cierre: cambio total + invitación a comentar y seguir la cuenta.
Lleva música ambiental original generada por código (sin derechos de terceros).
"""
import math
import subprocess
import wave
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (12, 38, 48)
INK = (236, 242, 236)
MUTED = (150, 178, 176)
ACCENT = (224, 170, 72)
LINE = (95, 179, 196)
CUENTA = "@caribe.sat"

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "C:/Windows/Fonts"]
UNITS = {"agua": "km² de agua", "ndvi": "NDVI medio (vegetación)", "urbano": "km² urbanizados"}
LAYER_TXT = {"rgb": "Color natural", "ndvi": "Vigor de la vegetación (NDVI)",
             "agua": "Superficie de agua (MNDWI)", "urbano": "Zona construida (NDBI)"}
SOURCES = {"landsat": "Landsat 5/7/8/9 · USGS/NASA", "sentinel2": "Sentinel-2 · ESA Copernicus"}
PREGUNTA = {"urbano": "¿Cuánto creció?", "agua": "¿Cuánto cambió el agua?", "ndvi": "¿Más verde o más seco?"}


def _font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"] if bold else \
            ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


F_HOOK, F_TITLE, F_SUB = _font(92, True), _font(62, True), _font(36)
F_YEAR, F_STAT, F_SMALL, F_TAG = _font(190, True), _font(46, True), _font(28), _font(54, True)
F_HOOK_YEAR = _font(130, True)


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


def _tile(png_path: str, size: int = 1000):
    """Mapa del año en un cuadro de size×size (relleno oscuro si no es cuadrado)."""
    img = Image.open(png_path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    base = Image.new("RGBA", (size, size), (20, 30, 34, 255))
    base.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
    return base.convert("RGB")


def _zoom(tile: Image.Image, z: float):
    if z <= 1.0001:
        return tile
    s = tile.width
    c = s / z
    o = (s - c) / 2
    return tile.crop((o, o, o + c, o + c)).resize((s, s), Image.BILINEAR)


def _sparkline(draw, values, upto, rect, width=6):
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
        draw.line(pts, fill=LINE, width=width, joint="curve")
    if pts:
        cx, cy = pts[-1]
        draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=ACCENT)


def _sombra(draw, xy, text, font, fill=INK, anchor=None):
    x, y = xy
    draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0), anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _cambio(frames):
    a, b = frames[0], frames[-1]
    if a["valor"] is None or b["valor"] is None:
        return None, None
    d = b["valor"] - a["valor"]
    return d, (d / a["valor"] * 100 if a["valor"] else 0)


# ---------------------------------------------------------------- escenas
def escena_gancho(region, frames, t_a, t_b):
    """Antes y después en pantalla dividida, con la pregunta encima."""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    half = (H - 40) // 2
    for i, (tile, f) in enumerate([(t_a, frames[0]), (t_b, frames[-1])]):
        y = i * (half + 40)
        recorte = tile.resize((W, W)).crop((0, (W - half) // 2, W, (W - half) // 2 + half))
        im.paste(recorte, (0, y))
        _sombra(d, (40, y + 30 if i == 0 else y + half - 160), str(f["anio"]), F_HOOK_YEAR)
    # banda central con el titular
    d.rectangle([0, half - 10, W, half + 50], fill=BG)
    titulo = f"Así cambió {region['nombre'].split(',')[0]}"
    box_h = 250
    y0 = half + 20 - box_h // 2
    d.rounded_rectangle([40, y0, W - 40, y0 + box_h], radius=28, fill=(12, 38, 48))
    d.text((W // 2, y0 + 82), titulo, font=_ajusta(d, titulo, F_HOOK, W - 140), fill=INK, anchor="mm")
    d.text((W // 2, y0 + 180), PREGUNTA.get(region["metrica"], "¿Qué cambió?"), font=F_TAG, fill=ACCENT, anchor="mm")
    return im


def _ajusta(d, texto, font, max_w):
    size = font.size
    f = font
    while d.textlength(texto, font=f) > max_w and size > 40:
        size -= 4
        f = _font(size, True)
    return f


def escena_anio(region, frames, idx, tile, z, progreso):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    # barra de progreso arriba
    d.rectangle([0, 0, W, 10], fill=(30, 60, 70))
    d.rectangle([0, 0, int(W * progreso), 10], fill=ACCENT)
    y = 70
    for line in _wrap(d, region["nombre"], F_TITLE, W - 120):
        d.text((60, y), line, font=F_TITLE, fill=INK)
        y += 72
    d.text((60, y + 6), f"{region['tema']} · {LAYER_TXT[region['capa_video']]}", font=F_SUB, fill=MUTED)
    mapa = _zoom(tile, z)
    im.paste(mapa, ((W - mapa.width) // 2, 300))
    f = frames[idx]
    d.text((52, 1290), str(f["anio"]), font=F_YEAR, fill=INK)
    if f["valor"] is not None:
        d.text((60, 1500), f"{f['valor']:,.2f} {UNITS[region['metrica']]}", font=F_STAT, fill=ACCENT)
    _sparkline(d, [fr["valor"] for fr in frames], idx, (60, 1590, W - 60, 1730))
    d.text((60, 1790), f"Datos: {SOURCES[region['sensor']]}", font=F_SMALL, fill=MUTED)
    d.text((60, 1832), "Procesado en Google Earth Engine", font=F_SMALL, fill=MUTED)
    d.text((W - 60, 1832), CUENTA, font=F_SMALL, fill=INK, anchor="ra")
    return im


def escena_cierre(region, frames):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    a, b = frames[0], frames[-1]
    y = 300
    for line in _wrap(d, f"{region['nombre']}: {a['anio']} → {b['anio']}", F_TITLE, W - 120):
        d.text((60, y), line, font=F_TITLE, fill=INK)
        y += 76
    delta, pct = _cambio(frames)
    if delta is not None:
        d.text((60, y + 50), f"{delta:+,.2f}", font=_font(160, True), fill=ACCENT)
        d.text((60, y + 240), f"{UNITS[region['metrica']]} ({pct:+.1f} %)", font=F_SUB, fill=INK)
    _sparkline(d, [f["valor"] for f in frames], len(frames) - 1, (60, 1020, W - 60, 1260), width=8)
    d.rounded_rectangle([60, 1380, W - 60, 1560], radius=26, outline=ACCENT, width=4)
    d.text((W // 2, 1440), "¿Reconoces tu barrio?", font=F_TAG, fill=INK, anchor="mm")
    d.text((W // 2, 1510), "Cuéntanos en los comentarios", font=F_SUB, fill=MUTED, anchor="mm")
    d.text((W // 2, 1680), f"Síguenos en {CUENTA}", font=F_TAG, fill=ACCENT, anchor="mm")
    d.text((W // 2, 1750), "Un lugar nuevo del Caribe cada semana", font=F_SUB, fill=MUTED, anchor="mm")
    return im


# ---------------------------------------------------------------- música
def musica(path: Path, segundos: float, sr: int = 44100):
    """Fondo ambiental original: acordes suaves La m – Fa – Do – Sol con un arpegio ligero."""
    n = int(segundos * sr)
    t = np.arange(n) / sr
    acordes = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [261.63, 329.63, 392.0], [196.0, 246.94, 293.66]]
    dur = 4.0
    out = np.zeros(n)
    for k in range(int(math.ceil(segundos / dur))):
        ini, fin = int(k * dur * sr), min(n, int((k + 1) * dur * sr + 0.5 * sr))
        if ini >= n:
            break
        tt = t[ini:fin] - k * dur
        env = np.minimum(1, tt / 0.8) * np.exp(-np.maximum(0, tt - dur) * 4)
        for f in acordes[k % 4]:
            out[ini:fin] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * 0.10
        # arpegio: 8 notas por acorde, una octava arriba
        for j in range(8):
            f = acordes[k % 4][j % 3] * 2
            a = ini + int(j * dur / 8 * sr)
            b = min(n, a + int(0.6 * sr))
            if a >= n:
                break
            ta = np.arange(b - a) / sr
            out[a:b] += np.sin(2 * np.pi * f * ta) * np.exp(-ta * 6) * 0.07
    fade = int(1.5 * sr)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    out = out / (np.abs(out).max() or 1) * 0.5
    pcm = (out * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- video
def build_video(region, frames, out_path: Path, vcfg: dict):
    fps = vcfg.get("fps", 30)
    hold = int(vcfg.get("segundos_por_cuadro", 0.9) * fps)
    fade = int(vcfg.get("segundos_transicion", 0.3) * fps)
    gancho = int(vcfg.get("segundos_gancho", 2.5) * fps)
    cierre = int(vcfg.get("segundos_cierre", 3.5) * fps)
    tiles = [_tile(f["png"]) for f in frames]
    n = len(frames)
    total_tl = n * hold + (n - 1) * fade
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mudo = out_path.with_suffix(".mudo.mp4")
    w = imageio.get_writer(mudo, fps=fps, codec="libx264", pixelformat="yuv420p", macro_block_size=8,
                           output_params=["-crf", "23", "-preset", "medium"])

    def put(img):
        w.append_data(np.asarray(img))

    def mezcla(a, b, steps):
        a, b = np.asarray(a).astype(np.float32), np.asarray(b).astype(np.float32)
        for k in range(1, steps + 1):
            t = k / (steps + 1)
            w.append_data((a * (1 - t) + b * t).astype(np.uint8))

    # 1. gancho
    g = escena_gancho(region, frames, tiles[0], tiles[-1])
    for _ in range(gancho):
        put(g)
    # 2. timelapse con acercamiento lento continuo
    k = 0
    primero = None
    previo = None
    for i in range(n):
        for h in range(hold):
            z = 1.0 + 0.10 * (k / max(total_tl, 1))
            img = escena_anio(region, frames, i, tiles[i], z, (k + 1) / total_tl)
            if primero is None:
                primero = img
                mezcla(g, img, 8)
            put(img)
            previo = img
            k += 1
        if i + 1 < n:
            z = 1.0 + 0.10 * (k / max(total_tl, 1))
            sig = escena_anio(region, frames, i + 1, tiles[i + 1], z, (k + 1) / total_tl)
            mezcla(previo, sig, fade)
            k += fade
    # 3. cierre
    c = escena_cierre(region, frames)
    mezcla(previo, c, 10)
    for _ in range(cierre):
        put(c)
    w.close()

    segundos = (gancho + 8 + total_tl + 10 + cierre) / fps
    wav = out_path.with_suffix(".wav")
    musica(wav, segundos)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(mudo), "-i", str(wav),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                    str(out_path)], check=True)
    mudo.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    if segundos > 90:
        print(f"  Aviso: el video dura {segundos:.0f}s; sube paso_anios para acortarlo")
    return out_path


def texto_publicacion(region, frames) -> str:
    """Texto para Instagram/YouTube con palabras clave y máximo 5 hashtags."""
    a, b = frames[0]["anio"], frames[-1]["anio"]
    lugar = region["nombre"].split(",")[0]
    delta, pct = _cambio(frames)
    cifra = f" El cambio: {delta:+,.2f} {UNITS[region['metrica']]} ({pct:+.1f} %)." if delta is not None else ""
    depto = {"barranquilla": "Atlántico", "puerto_colombia": "Atlántico", "cartagena": "Bolívar", "islas_rosario": "Bolívar",
             "santa_marta": "Magdalena", "cienaga_grande": "Magdalena", "riohacha": "LaGuajira", "alta_guajira": "LaGuajira",
             "valledupar": "Cesar", "monteria": "Córdoba", "sincelejo": "Sucre", "covenas": "Sucre",
             "san_andres": "SanAndrés", "la_mojana": "LaMojana"}.get(region["id"], "Caribe")
    tags = [f"#{lugar.replace(' ', '')}", f"#{depto}", "#ImágenesSatelitales",
            "#CambioClimático" if region["metrica"] != "urbano" else "#CrecimientoUrbano", "#CaribeColombiano"]
    return (f"{region['tema']} en {lugar} visto desde satélite, de {a} a {b}.{cifra}\n\n"
            f"¿Reconoces tu barrio? Cuéntanos en los comentarios y compártelo con alguien de {lugar}.\n\n"
            f"Mapa interactivo: caribesat.onrender.com\n"
            f"Datos: {SOURCES[region['sensor']]}, procesados en Google Earth Engine.\n\n"
            + " ".join(dict.fromkeys(tags)))
