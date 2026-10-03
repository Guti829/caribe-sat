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
    print(f"  Video: {mp4}")
    if not upload:
        return
    from .youtube import upload_short
    a, b = frames[0]["anio"], frames[-1]["anio"]
    title = f"{r['nombre']} desde el espacio: {a}–{b} | {r['tema']} #Shorts"
    desc = (f"{r['tema']} en {r['nombre']} vista con satélites entre {a} y {b}.\n\n"
            f"Fuentes: {video.SOURCES[r['sensor']]}, procesado en Google Earth Engine.\n"
            + " ".join(cfg["video"]["hashtags"]))
    vid = upload_short(mp4, title, desc, ["satélite", "Caribe", "Colombia", r["tema"]],
                       cfg["video"].get("privacidad", "public"))
    print(f"  Publicado: https://youtube.com/shorts/{vid}")
    vids = _read_json(DATA_DIR / "videos.json", [])
    vids.insert(0, {"id": vid, "region": r["id"], "titulo": title,
                    "fecha": dt.date.today().isoformat()})
    _write_json(DATA_DIR / "videos.json", vids[:30])


def cmd_semanal(cfg, upload=False):
    cmd_series(cfg)
    regiones = cfg["regiones"]
    week = dt.date.today().isocalendar().week
    cmd_video(cfg, regiones[week % len(regiones)]["id"], upload)   # rota una región por semana


def main():
    p = argparse.ArgumentParser(prog="caribesat")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("series")
    s.add_argument("--region")
    v = sub.add_parser("video")
    v.add_argument("--region", required=True)
    v.add_argument("--upload", action="store_true")
    w = sub.add_parser("semanal")
    w.add_argument("--upload", action="store_true")
    args = p.parse_args()

    cfg = load_config()
    init_ee()
    if args.cmd == "series":
        cmd_series(cfg, args.region)
    elif args.cmd == "video":
        cmd_video(cfg, args.region, args.upload)
    else:
        cmd_semanal(cfg, args.upload)


if __name__ == "__main__":
    main()
