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


def build_frames(region: dict, out_dir: Path, end_year: int, width: int = 1080):
    """Descarga un PNG por año y calcula la métrica. Devuelve [{anio, png, valor, escenas}]."""
    geom = bbox_geom(region["bbox"])
    scale = 10 if region["sensor"] == "sentinel2" else 30
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in range(region["anio_inicio"], end_year + 1, region.get("paso_anios", 1)):
        comp, n_scenes = imagery.annual_composite(geom, year, region["sensor"])
        n = n_scenes.getInfo()
        if n == 0:
            print(f"  {year}: sin escenas, se omite")
            continue
        url = imagery.visualized(comp, region["capa_video"]).getThumbURL(
            {"region": geom, "dimensions": width, "format": "png"})
        r = requests.get(url, timeout=180)
        r.raise_for_status()
        png = out_dir / f"{year}.png"
        Image.open(io.BytesIO(r.content)).save(png)
        valor = _metric(comp, geom, region["metrica"], scale).getInfo()
        frames.append({"anio": year, "png": str(png), "escenas": n,
                       "valor": round(valor, 3) if valor is not None else None})
        print(f"  {year}: {n} escenas, {region['metrica']}={frames[-1]['valor']}")
    return frames
