import os, time, threading, datetime as dt, traceback
from pathlib import Path
from store import *
import core, notify, story, autoviral


def _remix_file(msg):
    media = msg.get("video") or msg.get("document") or {}
    file_id = media.get("file_id")
    if not file_id:
        return
    try:
        d = Path("data/remix")
        d.mkdir(parents=True, exist_ok=True)
        src = d / f"src_{int(time.time())}.mp4"
        notify.download_file(file_id, src)
        topic = (msg.get("caption") or "").strip()
        if not topic:
            notify.send("Detectando el tema del video...")
            try:
                topic = autoviral.describe_video(src)
                notify.send(f"Tema detectado: {topic}")
            except Exception as ex:
                notify.send(f"No pude analizar el video ({str(ex)[:120]}), uso tema genérico.")
                topic = ""
        if os.getenv("GH_ACTIONS"):
            import ghremix, yt
            notify.send("Editando en la nube (unos minutos)...")
            out = ghremix.edit_video(src, topic=topic)
            notify.send_video(out, "Video editado: voz nueva, subtítulos, música y anti-copyright.")
            try:
                vid = yt.upload(out, {
                    "title": (topic or "Short editado")[:90],
                    "description": "Video editado con ayuda de IA.\n#Shorts",
                    "tags": [],
                }, cfg().get("upload_privacy", "private"))
                notify.send(f"Subido a YouTube: https://youtu.be/{vid}")
            except Exception as e2:
                notify.send(f"Editado, pero falló la subida a YouTube: {str(e2)[:200]}")
        else:
            out = autoviral.remix_video(src, topic=topic)
            notify.send_video(out, "Listo: marca de agua eliminada, voz nueva, subtítulos y música.")
    except Exception as ex:
        traceback.print_exc()
        notify.send(f"Error editando el video: {str(ex)[:300]}")


def slots_tick():
    s, c = state(), cfg()
    if s["paused"]:
        print("[slots_tick] Bot en pausa.", flush=True)
        return
    now = dt.datetime.now()
    done = s["slots"].setdefault(today(), [])
    print(f"[slots_tick] hora={now.strftime('%H:%M')} slots_hoy={done} generate_times={c['generate_times']}", flush=True)
    for slot in c["generate_times"]:
        h, m = map(int, slot.split(":"))
        diff = (now - now.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds() / 60
        if diff >= 0 and slot not in done:
            print(f"[slots_tick] Activando slot={slot} diff={diff:.1f}m", flush=True)
            done.append(slot)
            if s.get("trends_day") != today():
                s["trends_day"] = today()
            save_state(s)
            if diff <= 120:
                print("[slots_tick] Refrescando tendencias...", flush=True)
                story.refresh_trends()
                print("[slots_tick] Llamando a core.generate()...", flush=True)
                core.generate()
                print("[slots_tick] core.generate() terminado.", flush=True)
            else:
                print(f"[slots_tick] Slot {slot} fuera de ventana (diff={diff:.1f}m > 120m).", flush=True)
            return


def handle_commands():
    s = state()
    for u in notify.updates(s["offset"]):
        s = state()
        s["offset"] = u["update_id"] + 1
        save_state(s)
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != os.getenv("TELEGRAM_CHAT_ID"):
            continue
        if msg.get("video") or msg.get("document"):
            threading.Thread(target=_remix_file, args=(msg,), daemon=True).start()
            continue
        parts = (msg.get("text") or "").split()
        if not parts:
            continue
        cmd, arg = parts[0].lower(), (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None)
        print(f"[cmd] Recibido comando: {cmd} arg={arg}", flush=True)
        if cmd == "/ok" and arg:
            core.approve(arg)
        elif cmd == "/no" and arg:
            core.reject(arg)
            notify.send(f"Episodio {arg} descartado.")
        elif cmd == "/nuevo":
            core.generate()
        elif cmd == "/pausa":
            s = state(); s["paused"] = True; save_state(s); notify.send("Bot en pausa.")
        elif cmd == "/seguir":
            s = state(); s["paused"] = False; save_state(s); notify.send("Bot activo.")
        elif cmd == "/status":
            eps = ep_list()
            notify.send(f"Episodios: {len(eps)}. Subidos hoy: {state()['uploads'].get(today(), 0)}/{cfg()['daily_upload_cap']}. "
                        f"Pausa: {state()['paused']}.")


def main():
    if not os.getenv("GH_ACTIONS"):
        notify.send("Bot de Frutas Novelas encendido.")
    print("[main] Bot de Frutas Novelas iniciado.", flush=True)
    while True:
        print(f"[loop] hora={dt.datetime.now().strftime('%H:%M:%S')} hoy={today()}", flush=True)
        for step in (slots_tick, core.check_clips, core.check_uploads, handle_commands):
            print(f"[paso] Iniciando {step.__name__}", flush=True)
            try:
                step()
                print(f"[paso] Finalizado {step.__name__}", flush=True)
            except Exception as ex:
                traceback.print_exc()
                notify.send(f"Error en {step.__name__}: {str(ex)[:300]}")
        print("[loop] Durmiendo 20s...", flush=True)
        time.sleep(20)


if __name__ == "__main__":
    main()
