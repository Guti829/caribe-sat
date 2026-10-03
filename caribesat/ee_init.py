"""Autenticación con Google Earth Engine.

- Local: ejecuta `earthengine authenticate` una vez y define GEE_PROJECT.
- Servidor / CI: define GEE_SERVICE_ACCOUNT_JSON con el JSON de la cuenta de servicio.
"""
import json
import os

import ee

_initialized = False


def init_ee() -> None:
    global _initialized
    if _initialized:
        return
    project = os.environ.get("GEE_PROJECT")
    sa_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        creds = ee.ServiceAccountCredentials(info["client_email"], key_data=sa_json)
        ee.Initialize(creds, project=project or info.get("project_id"))
    else:
        ee.Initialize(project=project)
    _initialized = True


def bbox_geom(bbox: list[float]) -> ee.Geometry:
    return ee.Geometry.Rectangle(bbox, proj="EPSG:4326", geodesic=False)
