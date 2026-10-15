"""CLI del proyecto.

  python -m caribesat.pipeline series                  # series de clima + métricas para la web
  python -m caribesat.pipeline video --region la_mojana [--upload]
  python -m caribesat.pipeline semanal [--upload]      # lo que corre el cron cada semana
"""
import argparse
import datetime as dt
import json

from . import climate, timelapse, video
from .config import DATA_DIR, OUT_DIR, get_region, load_config
from .ee_init import bbox_geom, init_ee


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def cmd_series(cfg, only=None):
    c = cfg["clima"]
    ref = tuple(c["climatologia"])
    for r in cfg["regiones"]:
        if only and r["id"] != only:
            continue
        print(f"Series: {r['nombre']}")
        geom = bbox_geom(r["bbox"])
        path = DATA_DIR / f"{r['id']}.json"
        data = _read_json(path, {})
        data.update({
            "region": r,
            "actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "lluvia": climate.precipitation(geom, c["anio_inicio"], ref),
            "sst": (climate.sea_surface_temperature(geom, c["anio_inicio"], ref)
                    if r.get("mar", True) else None),
        })
        _write_json(path, data)


def cmd_video(cfg, region_id, upload=False):
    r = get_region(cfg, region_id)
    year = dt.date.today().year - 1   # último año completo
    print(f"Timelapse: {r['nombre']} ({r['anio_inicio']}-{year})")
    frames = timelapse.build_frames(r, OUT_DIR / r["id"] / "frames", year)
    if len(frames) < 2:
        raise SystemExit("No hay suficientes años con imágenes para el video.")

    # la métrica anual también alimenta la web
    path = DATA_DIR / f"{r['id']}.json"
    data = _read_json(path, {"region": r})
    data["metrica_anual"] = [{"anio": f["anio"], "valor": f["valor"]} for f in frames]
    _write_json(path, data)

    mp4 = video.build_video(r, frames, OUT_DIR / r["id"] / f"{r['id']}_{year}.mp4", cfg["video"])
    texto = video.texto_publicacion(r, frames)
    mp4.with_suffix(".txt").write_text(texto, encoding="utf-8")   # texto listo para Instagram
    print(f"  Video: {mp4}")
    if not upload:
        return
    from .youtube import upload_short
    a, b = frames[0]["anio"], frames[-1]["anio"]
    title = f"{r['nombre']} desde el espacio: {a}–{b} | {r['tema']} #Shorts"
    desc = texto + "\n#Shorts"
    try:
        vid = upload_short(mp4, title, desc, ["satélite", "Caribe", "Colombia", r["tema"]],
                           cfg["video"].get("privacidad", "public"))
    except Exception as e:  # el video queda en los artefactos del flujo aunque falle la subida
        msg = str(e).replace("\n", " ")[:400]
        if "invalid_grant" in msg:
            msg = ("El permiso de YouTube venció o fue revocado (invalid_grant). Saca un refresh token "
                   "nuevo en el OAuth Playground y actualiza el secreto YT_REFRESH_TOKEN. " + msg)
        print(f"::error title=Subida a YouTube::{msg}")
        raise SystemExit(1)
    print(f"  Publicado: https://youtube.com/shorts/{vid}")
    vids = _read_json(DATA_DIR / "videos.json", [])
    vids.insert(0, {"id": vid, "region": r["id"], "titulo": title,
                    "fecha": dt.date.today().isoformat()})
    _write_json(DATA_DIR / "videos.json", vids[:200])


def cmd_reels(cfg, regiones: str):
    for rid in [x.strip() for x in regiones.split(",") if x.strip()]:
        cmd_video(cfg, rid, upload=False)


def cmd_semanal(cfg, upload=False):
    cmd_series(cfg)
    cmd_video(cfg, siguiente_region(cfg), upload)


def siguiente_region(cfg) -> str:
    """Elige la región que lleva más tiempo sin reel (las que nunca han tenido van primero),
    así cada semana sale un lugar distinto y no se repite hasta recorrerlas todas."""
    ultimo = {}
    for v in _read_json(DATA_DIR / "videos.json", []):
        ultimo[v["region"]] = max(ultimo.get(v["region"], ""), v.get("fecha", ""))
    orden = {r["id"]: i for i, r in enumerate(cfg["regiones"])}
    elegida = min(cfg["regiones"], key=lambda r: (ultimo.get(r["id"], ""), orden[r["id"]]))
    print(f"Región de la semana: {elegida['nombre']} (último reel: {ultimo.get(elegida['id'], 'nunca')})")
    return elegida["id"]


def main():
    p = argparse.ArgumentParser(prog="caribesat")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("series")
    s.add_argument("--region")
    v = sub.add_parser("video")
    v.add_argument("--region", required=True)
    v.add_argument("--upload", action="store_true")
    rr = sub.add_parser("reels")
    rr.add_argument("--regiones", required=True, help="ids separados por coma")
    w = sub.add_parser("semanal")
    w.add_argument("--upload", action="store_true")
    args = p.parse_args()

    cfg = load_config()
    try:
        _run(args, cfg)
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        donde = traceback.extract_tb(e.__traceback__)[-1]
        print(f"::error title=Fallo en {args.cmd}::{type(e).__name__} en {donde.filename.split('/')[-1]}:{donde.lineno}: {str(e)[:400]}")
        raise


def _run(args, cfg):
    init_ee()
    if args.cmd == "series":
        cmd_series(cfg, args.region)
    elif args.cmd == "video":
        cmd_video(cfg, args.region, args.upload)
    elif args.cmd == "reels":
        cmd_reels(cfg, args.regiones)
    else:
        cmd_semanal(cfg, args.upload)


if __name__ == "__main__":
    main()
