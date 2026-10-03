"""Series climáticas mensuales: lluvia (CHIRPS) y temperatura del mar (NOAA OISST)."""
import datetime as dt
from statistics import mean

import ee

NODATA = -9999


def _monthly(collection, geom, start: str, n_months: int, agg: str, band: str, scale: int):
    start_d = ee.Date(start)

    def per_month(i):
        d = start_d.advance(i, "month")
        sub = collection.filterDate(d, d.advance(1, "month"))
        img = sub.sum() if agg == "sum" else sub.mean()
        stats = ee.Dictionary(img.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=scale,
            maxPixels=1e10, bestEffort=True))
        return ee.Feature(None, {"fecha": d.format("YYYY-MM"), "valor": stats.get(band, NODATA)})

    fc = ee.FeatureCollection(ee.List.sequence(0, n_months - 1).map(per_month))
    out = []
    for f in fc.getInfo()["features"]:
        p = f["properties"]
        v = p.get("valor")
        if v is not None and v != NODATA:
            out.append((p["fecha"], float(v)))
    return out


def _months_between(start_year: int, lag_months: int) -> int:
    today = dt.date.today()
    total = (today.year - start_year) * 12 + today.month - 1
    return max(total - lag_months, 1)


def _with_anomalies(series, ref: tuple[int, int], decimals=2):
    clim = {}
    for fecha, v in series:
        y, m = int(fecha[:4]), int(fecha[5:])
        if ref[0] <= y <= ref[1]:
            clim.setdefault(m, []).append(v)
    clim = {m: mean(vs) for m, vs in clim.items()}
    return [{"fecha": f, "valor": round(v, decimals),
             "anomalia": round(v - clim[int(f[5:])], decimals) if int(f[5:]) in clim else None}
            for f, v in series]


def precipitation(geom, start_year: int, ref: tuple[int, int]):
    """Lluvia mensual (mm) y su anomalía frente a la climatología."""
    col = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    n = _months_between(start_year, lag_months=2)   # CHIRPS publica con ~1-2 meses de rezago
    s = _monthly(col, geom, f"{start_year}-01-01", n, "sum", "precipitation", 5566)
    return _with_anomalies(s, ref, 1)


def sea_surface_temperature(geom, start_year: int, ref: tuple[int, int]):
    """Temperatura superficial del mar mensual (°C) en un radio de 25 km."""
    col = (ee.ImageCollection("NOAA/CDR/OISST/V2_1").select("sst")
           .map(lambda i: i.multiply(0.01).copyProperties(i, ["system:time_start"])))
    n = _months_between(start_year, lag_months=1)
    s = _monthly(col, geom.buffer(25000), f"{start_year}-01-01", n, "mean", "sst", 27830)
    return _with_anomalies(s, ref, 2)
