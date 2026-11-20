import traceback
from store import *
import story, video, yt, notify, aiclips, autoviral


def generate():
    e = story.new_episode()
    if cfg().get("auto_clips"):
        notify.send(f"Episodio {e['n']} creado: {e['title']} — generando clips y armando solo.")
    else:
        notify.send(f"Episodio {e['n']} listo: {e['title']}\n\nGancho: {e['hook']}\n\n"
                    f"Pega los {len(e['clips'])} prompts de data/episodes/ep{e['n']:03d}/prompts.txt en tus herramientas de video "
                    f"y suelta los clips en data/episodes/ep{e['n']:03d}/clips/")
    return e


def build(n):
    e = ep_load(n)
    e["status"] = "assembling"
    ep_save(e)
    try:
        if cfg().get("use_autoviral") and autoviral.available():
            path, secs = autoviral.produce(n)
        else:
            path, secs = video.assemble(n)
    except Exception as ex:
        e["status"], e["error"] = "error", str(ex)[:400]
        ep_save(e)
        notify.send(f"Error armando el episodio {n}: {e['error']}")
        return
    e["status"] = "waiting_approval"
    ep_save(e)
    notify.send_video(path, f"Episodio {n}: {e['title']} ({int(secs)} s)\nResponde /ok {n} para subir o /no {n} para descartar.")
    notify.send(f"Episodio {n} armado. Falta tu aprobación (/ok {n} o /no {n}).")
    if cfg().get("auto_approve"):
        approve(n)


def check_clips():
    auto = cfg().get("auto_clips")
    for e in ep_list():
        if e["status"] != "waiting_clips":
            continue
        need = len(e["narration"])
        if auto and len(video.find_clips(e["n"])) < need:
            try:
                aiclips.ensure_clips(e["n"])
            except Exception as ex:
                notify.send(f"Error generando clips del episodio {e['n']}: {str(ex)[:300]}")
                traceback.print_exc()
                continue
        if len(video.find_clips(e["n"])) >= need:
            build(e["n"])


def approve(n):
    e = ep_load(n)
    if e and e["status"] in ("waiting_approval", "error"):
        e["status"] = "approved"
        ep_save(e)
    check_uploads()


def reject(n):
    e = ep_load(n)
    if e:
        e["status"] = "rejected"
        ep_save(e)


def check_uploads():
    c = cfg()
    for e in ep_list():
        if e["status"] != "approved":
            continue
        if state()["uploads"].get(today(), 0) >= c["daily_upload_cap"]:
            return
        try:
            vid = yt.upload(ep_dir(e["n"]) / "final.mp4", e, c["upload_privacy"])
            e["status"], e["youtube_id"] = "uploaded", vid
            ep_save(e)
            s = state()
            s["uploads"][today()] = s["uploads"].get(today(), 0) + 1
            save_state(s)
            notify.send(f"Subido el episodio {e['n']} ({c['upload_privacy']}): https://youtu.be/{vid}")
        except Exception as ex:
            e["status"], e["error"] = "error", str(ex)[:400]
            ep_save(e)
            notify.send(f"Error subiendo el episodio {e['n']}: {e['error']}")
            traceback.print_exc()
