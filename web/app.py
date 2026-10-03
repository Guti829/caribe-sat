"""API + sitio web. Ejecutar: uvicorn web.app:app --reload"""
import datetime as dt
import time

import ee
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from caribesat import imagery
from caribesat.config import ROOT, get_region, load_config
from caribesat.ee_init import bbox_geom, init_ee

CFG = load_config()
STATIC = ROOT / "web" / "static"
_cache: dict[tuple, tuple[float, str]] = {}
TTL = 6 * 3600
EE_OK = {"ok": False, "error": ""}


@asynccontextmanager
async def lifespan(_app):
    try:
        init_ee()
        EE_OK["ok"] = True
    except Exception as e:  # la web sigue sirviendo las series aunque falle Earth Engine
        EE_OK["error"] = str(e)
    yield


app = FastAPI(title="CaribeSat", lifespan=lifespan)


@app.get("/api/regiones")
def regiones():
    return CFG["regiones"]


@app.get("/api/capas/{region_id}")
def capa(region_id: str,
         capa: str = Query("rgb", pattern="^(rgb|ndvi|agua|inundacion)$"),
         anio: int = Query(dt.date.today().year)):
    if not EE_OK["ok"]:
        raise HTTPException(503, f"Earth Engine no está disponible: {EE_OK['error']}")
    try:
        r = get_region(CFG, region_id)
    except KeyError:
        raise HTTPException(404, "Región no encontrada")
    key = (region_id, capa, anio)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return {"url": hit[1]}

    geom = bbox_geom(r["bbox"])
    if capa == "inundacion":
        end = dt.date.today()
        img = imagery.s1_water(geom, (end - dt.timedelta(days=60)).isoformat(), end.isoformat())
        vis = imagery.VIS["inundacion"]
    else:
        # Sentinel-2 da más detalle desde 2019; antes se usa Landsat
        sensor = "sentinel2" if anio >= 2019 else "landsat"
        comp, _ = imagery.annual_composite(geom, anio, sensor)
        img = imagery.layer_image(comp, capa)
        vis = imagery.VIS[capa]
    try:
        url = img.getMapId(vis)["tile_fetcher"].url_format
    except ee.EEException as e:
        raise HTTPException(502, f"Earth Engine rechazó la solicitud: {e}")
    _cache[key] = (time.time(), url)
    return {"url": url}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
