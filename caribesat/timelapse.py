"""Compuestos anuales -> cuadros PNG + métrica por año (agua o NDVI)."""
import io
from pathlib import Path

import ee
import requests
from PIL import Image

from . import imagery
from .ee_init import bbox_geom


def _metric(composite, geom, metrica: str, scale: int):
    if metrica == "ndvi":
        v = imagery.ndvi(composite).reduceRegion(
            ee.Reducer.mean(), geom, scale, maxPixels=1e10, bestEffort=True).get("ndvi")
        return v
    mask = imagery.built_mask(composite) if metrica == "urbano" else imagery.water_mask(composite)
    band = "urbano" if metrica == "urbano" else "agua"
    area = (mask.selfMask().multiply(ee.Image.pixelArea())
            .reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e10, bestEffort=True)
            .get(band))
    return ee.Number(area).divide(1e6)


def ghsl_built_km2(geom) -> dict:
    """Superficie construida oficial (JRC GHSL P2023A, 100 m) por época: {1990: km², 1995: km², ...}.
    Mucho más fiable que el NDBI, que confunde suelo desnudo y vegetación seca con construcciones.
    Las épocas hasta 2020 son observadas; 2025 es una proyección del propio GHSL."""
    col = ee.ImageCollection("JRC/GHSL/P2023A/GHS_BUILT_S").select("built_surface")

    def por_epoca(img):
        km2 = ee.Number(img.reduceRegion(ee.Reducer.sum(), geom, 100, maxPixels=1e10, bestEffort=True)
                        .get("built_surface")).divide(1e6)
        return ee.Feature(None, {"anio": ee.Date(img.get("system:time_start")).get("year"), "km2": km2})

    fc = ee.FeatureCollection(col.map(por_epoca)).getInfo()
    return {int(f["properties"]["anio"]): f["properties"]["km2"] for f in fc["features"]}


def _interpola(serie: dict, anio: int):
    xs = sorted(k for k in serie if serie[k] is not None)
    if not xs:
        return None
    if anio <= xs[0]:
        return serie[xs[0]]
    if anio >= xs[-1]:
        return serie[xs[-1]]
    for a, b in zip(xs, xs[1:]):
        if a <= anio <= b:
            return serie[a] + (serie[b] - serie[a]) * (anio - a) / (b - a)


def build_frames(region: dict, out_dir: Path, end_year: int, width: int = 1080):
    """Descarga un PNG por año y calcula la métrica. Devuelve [{anio, png, valor, escenas}]."""
    geom = bbox_geom(region["bbox"])
    scale = 10 if region["sensor"] == "sentinel2" else 30
    out_dir.mkdir(parents=True, exist_ok=True)
    ghsl = None
    if region["metrica"] == "urbano":
        ghsl = ghsl_built_km2(geom)
        print(f"  GHSL construido (km²): { {k: round(v, 2) for k, v in sorted(ghsl.items())} }")
    frames = []
    for year in range(region["anio_inicio"], end_year + 1, region.get("paso_anios", 1)):
        try:
            frame = _frame(region, geom, year, scale, out_dir, width, ghsl)
        except Exception as e:  # un año con problemas no debe tumbar todo el video
            print(f"::warning title=Año {year} omitido ({region['id']})::{type(e).__name__}: {str(e)[:300]}")
            continue
        if frame:
            frames.append(frame)
    return frames


def _frame(region, geom, year, scale, out_dir, width, ghsl=None):
    comp, n_scenes = imagery.annual_composite(geom, year, region["sensor"])
    n = n_scenes.getInfo()
    if n == 0:
        print(f"  {year}: sin escenas, se omite")
        return None
    url = imagery.visualized(comp, region["capa_video"]).getThumbURL(
        {"region": geom, "dimensions": width, "format": "png"})
    r = requests.get(url, timeout=180)
    if not r.ok:
        raise RuntimeError(f"Earth Engine {r.status_code}: {r.text[:300]}")
    png = out_dir / f"{year}.png"
    Image.open(io.BytesIO(r.content)).save(png)
    if ghsl is not None:
        valor = _interpola(ghsl, year)
    else:
        valor = _metric(comp, geom, region["metrica"], scale).getInfo()
    f = {"anio": year, "png": str(png), "escenas": n, "valor": round(valor, 3) if valor is not None else None}
    print(f"  {year}: {n} escenas, {region['metrica']}={f['valor']}")
    return f
