"""Colecciones ópticas y de radar armonizadas, índices y visualización."""
import ee

BANDS = ["blue", "green", "red", "nir", "swir1", "swir2"]


# ---------- Landsat Colección 2, Nivel 2 (reflectancia de superficie) ----------
def _landsat_mask(img):
    qa = img.select("QA_PIXEL")
    # bit 1: nube dilatada, bit 3: nube, bit 4: sombra de nube
    ok = (qa.bitwiseAnd(1 << 1).eq(0)
          .And(qa.bitwiseAnd(1 << 3).eq(0))
          .And(qa.bitwiseAnd(1 << 4).eq(0)))
    return ok


def _prep_l57(img):
    sr = (img.select(["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"], BANDS)
          .multiply(0.0000275).add(-0.2))
    return ee.Image(sr.updateMask(_landsat_mask(img)).copyProperties(img, ["system:time_start"]))


def _prep_l89(img):
    sr = (img.select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"], BANDS)
          .multiply(0.0000275).add(-0.2))
    return ee.Image(sr.updateMask(_landsat_mask(img)).copyProperties(img, ["system:time_start"]))


def landsat(geom, start, end):
    def col(cid, prep):
        return ee.ImageCollection(cid).filterBounds(geom).filterDate(start, end).map(prep)
    return (col("LANDSAT/LT05/C02/T1_L2", _prep_l57)
            .merge(col("LANDSAT/LE07/C02/T1_L2", _prep_l57))
            .merge(col("LANDSAT/LC08/C02/T1_L2", _prep_l89))
            .merge(col("LANDSAT/LC09/C02/T1_L2", _prep_l89)))


# ---------- Sentinel-2 con Cloud Score+ ----------
def sentinel2(geom, start, end, cs_threshold=0.6):
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")

    def prep(img):
        sr = (img.select(["B2", "B3", "B4", "B8", "B11", "B12"], BANDS).divide(10000)
              .updateMask(img.select("cs").gte(cs_threshold)))
        return ee.Image(sr.copyProperties(img, ["system:time_start"]))

    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom).filterDate(start, end)
            .linkCollection(cs, ["cs"])
            .map(prep))


def annual_composite(geom, year: int, sensor: str):
    start, end = f"{year}-01-01", f"{year + 1}-01-01"
    col = sentinel2(geom, start, end) if sensor == "sentinel2" else landsat(geom, start, end)
    return col.median().clip(geom), col.size()


# ---------- Índices ----------
def ndvi(img):
    return img.normalizedDifference(["nir", "red"]).rename("ndvi")


def mndwi(img):
    return img.normalizedDifference(["green", "swir1"]).rename("mndwi")


def water_mask(img):
    return mndwi(img).gt(0).rename("agua")


def built_mask(img):
    """Área construida aproximada: NDBI > 0, poca vegetación y sin agua."""
    ndbi = img.normalizedDifference(["swir1", "nir"])
    return ndbi.gt(0).And(ndvi(img).lt(0.25)).And(mndwi(img).lt(0)).rename("urbano")


def s1_water(geom, start, end, threshold_db=-18):
    """Agua / inundación con radar Sentinel-1 (funciona con nubes)."""
    vv = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterBounds(geom).filterDate(start, end)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .select("VV").median())
    return vv.focalMedian(30, "circle", "meters").lt(threshold_db).selfMask().rename("agua").clip(geom)


# ---------- Visualización ----------
VIS = {
    "rgb": {"bands": ["red", "green", "blue"], "min": 0.0, "max": 0.3, "gamma": 1.3},
    "ndvi": {"min": 0.0, "max": 0.85,
             "palette": ["8c5a2b", "c9a15b", "e8dfa0", "8fbf6a", "3d8a4a", "114d2c"]},
    "agua": {"min": 0, "max": 1, "palette": ["d9d2bf", "1f6fa3"]},
    "inundacion": {"min": 0, "max": 1, "palette": ["1f6fa3"]},
    "urbano": {"min": 0, "max": 1, "palette": ["d9d2bf", "c4462f"]},
}


def layer_image(composite, layer: str):
    if layer == "ndvi":
        return ndvi(composite)
    if layer == "agua":
        return water_mask(composite)
    if layer == "urbano":
        return built_mask(composite)
    return composite


def visualized(composite, layer: str):
    return layer_image(composite, layer).visualize(**VIS[layer])
