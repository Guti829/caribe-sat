# CaribeSat

Monitoreo satelital de la región Caribe colombiana con datos públicos, publicado en una
web y como Shorts de YouTube.

| Qué mide | Fuente | Resolución |
|---|---|---|
| Línea de costa y agua (MNDWI) | Landsat 5/7/8/9, Sentinel-2 | 30 m / 10 m |
| Vegetación y manglar (NDVI) | Landsat, Sentinel-2 | 30 m / 10 m |
| Inundación reciente (radar, atraviesa nubes) | Sentinel-1 | 10 m |
| Lluvia mensual y anomalías | CHIRPS | ~5 km |
| Temperatura superficial del mar | NOAA OISST v2.1 | ~25 km |

## Estructura

```
config.yaml              regiones, parámetros de clima y video
caribesat/
  ee_init.py             autenticación Earth Engine
  imagery.py             Landsat/Sentinel armonizados, máscaras de nubes, índices
  climate.py             series mensuales de lluvia y SST con anomalías
  timelapse.py           compuestos anuales -> PNG + métrica
  video.py               Short vertical 1080x1920 con año, métrica y minigráfica
  youtube.py             subida con YouTube Data API v3
  pipeline.py            CLI: series | video | semanal
web/
  app.py                 FastAPI: /api/regiones, /api/capas/{region}
  static/index.html      mapa Leaflet + gráficas Plotly + videos
  static/data/*.json     datos generados por el pipeline
.github/workflows/semanal.yml   cron semanal que procesa, sube y hace commit
render.yaml              despliegue de la web en Render
```

## 1. Earth Engine

1. Crea un proyecto en Google Cloud y regístralo en https://code.earthengine.google.com/register.
2. Habilita la API de Earth Engine en el proyecto.
3. **Local:** `pip install -r requirements.txt`, luego `earthengine authenticate` y `export GEE_PROJECT=tu-proyecto`.
4. **Servidor/CI:** crea una cuenta de servicio con el rol *Earth Engine Resource Viewer* (y *Service Usage Consumer*),
   descarga su llave JSON y guárdala completa en la variable `GEE_SERVICE_ACCOUNT_JSON`.

> El nivel gratuito de Earth Engine es para uso no comercial. Si el canal se monetiza o el
> proyecto se usa comercialmente, revisa los planes de Earth Engine para uso comercial.

## 2. Probar local

```bash
python -m caribesat.pipeline series                     # genera web/static/data/*.json
python -m caribesat.pipeline video --region puerto_colombia   # video en out/
uvicorn web.app:app --reload                            # http://localhost:8000
```

## 3. YouTube

1. En Google Cloud habilita **YouTube Data API v3** y crea un cliente OAuth tipo *App de escritorio*.
2. Descarga `client_secret.json` en la raíz y ejecuta `python scripts/youtube_token.py`.
3. Guarda `YT_CLIENT_ID`, `YT_CLIENT_SECRET` y `YT_REFRESH_TOKEN`.
4. `python -m caribesat.pipeline video --region la_mojana --upload`

> **Importante:** los videos subidos por API desde proyectos no verificados quedan como
> **privados**, aunque pidas `public`. Para publicarlos automáticamente debes solicitar la
> auditoría de la API de YouTube (formulario de cumplimiento de YouTube API Services).
> Mientras tanto, los videos se suben privados y los publicas a mano desde YouTube Studio.
> Además, mientras la pantalla de consentimiento OAuth esté en modo *Testing*, el refresh
> token caduca a los 7 días: pásala a *In production*.

## 4. Automatizar y publicar

1. Sube el repo a GitHub y crea los secretos: `GEE_PROJECT`, `GEE_SERVICE_ACCOUNT_JSON`,
   `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
2. El workflow corre cada lunes: actualiza las series, genera el video de una región
   (rotación semanal), lo sube y hace commit de los JSON.
3. En Render crea un *Blueprint* desde el repo (usa `render.yaml`) y define `GEE_PROJECT`
   y `GEE_SERVICE_ACCOUNT_JSON`. Cada commit del workflow redespliega la web con datos nuevos.
4. Para lanzar un video a mano: Actions → *Proceso semanal* → *Run workflow* → región.

## Agregar una región

Añade un bloque en `config.yaml` con `id`, `nombre`, `tema`, `bbox`, `sensor`
(`landsat` para históricos desde 1985, `sentinel2` para detalle desde 2017),
`capa_video` (`rgb`, `ndvi`, `agua`), `metrica` (`agua`, `ndvi`), `anio_inicio` y `paso_anios`.
Dibuja el rectángulo en https://geojson.io para obtener el bbox. Mantén el video por
debajo de 60 s: con los tiempos por defecto caben unos 30 años.

## Limitaciones conocidas

- El Caribe es muy nuboso: los compuestos anuales usan la mediana de todas las escenas
  sin nubes, pero algunos años pueden verse incompletos. Para inundaciones usa la capa de radar.
- La métrica de agua cuenta solo píxeles despejados; compárala entre años con cautela.
- Landsat 7 (2003-2012) tiene franjas sin datos; la mediana las disimula en parte.
- Los bbox del `config.yaml` son aproximados; ajústalos a tu zona de interés.
