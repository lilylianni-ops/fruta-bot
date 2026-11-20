import os, re, time, threading, datetime as dt, traceback
from pathlib import Path
from store import *
import core, notify, story, autoviral

os.environ.setdefault("GH_ACTIONS", os.environ.get("GITHUB_ACTIONS", ""))

_YT_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/\S+")


def _card(title, sub="", pct=0):
    notify.card(title, sub, pct)


def _process_src(src, topic):
    try:
        if os.getenv("GH_ACTIONS"):
            import ghremix, yt
            _card("EDITANDO VIDEO", topic or "en la nube", 2)

            def _prog(msg, pct):
                _card(msg.upper()[:38], topic or "", pct)

            out = ghremix.edit_video(src, topic=topic, progress=_prog)
            _card("VIDEO LISTO", "enviando resultado", 97)
            notify.send_video(out, "Video editado: voz nueva, subtítulos, música y anti-copyright.")
            _card("SUBIENDO A YOUTUBE", "", 98)
            try:
                vid = yt.upload(out, {
                    "title": (topic or "Short editado")[:90],
                    "description": "Video editado con ayuda de IA.\n#Shorts",
                    "tags": [],
                }, cfg().get("upload_privacy", "private"))
                notify.send(f"Subido a YouTube: https://youtu.be/{vid}")
                _card("COMPLETADO", f"youtu.be/{vid}", 100)
            except Exception as e2:
                notify.send(f"Editado, pero falló la subida a YouTube: {str(e2)[:200]}")
                _card("EDICION LISTA", "fallo la subida a YouTube", 100)
        else:
            _card("EDITANDO VIDEO", "servidor local", 2)
            out = autoviral.remix_video(src, topic=topic)
            notify.send_video(out, "Listo: marca de agua eliminada, voz nueva, subtítulos y música.")
            _card("COMPLETADO", "video entregado", 100)
    except Exception as ex:
        traceback.print_exc()
        notify.send(f"Error editando el video: {str(ex)[:300]}")
        _card("ERROR", str(ex)[:50], 0)


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
        _process_src(src, topic)
    except Exception as ex:
        traceback.print_exc()
        notify.send(f"Error editando el video: {str(ex)[:300]}")


def _remix_url(text):
    m = _YT_RE.search(text)
    if not m:
        return
    url = m.group(0)
    try:
        import yt_dlp
        d = Path("data/remix")
        d.mkdir(parents=True, exist_ok=True)
        base = d / f"yt_{int(time.time())}"
        _card("DESCARGANDO VIDEO", "desde YouTube", 1)
        opts = {
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": str(base) + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {}},
        }
        ck = os.environ.get("YT_COOKIES", "cookies.txt")
        if Path(ck).exists():
            opts["cookiefile"] = ck
            notify.send("Usando sesion de YouTube para descargar...")
        last_err = None
        for attempt in range(2):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                last_err = None
                break
            except Exception as ex:
                last_err = ex
                if attempt == 0:
                    notify.send("Reintentando descarga (YouTube desafió el bot-check)...")
                    time.sleep(15)
        if last_err:
            raise last_err
        src = None
        for f in sorted(d.glob(f"{base.name}.*")):
            if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
                src = f
        if not src or not src.exists():
            cands = sorted(d.glob("yt_*.mp4"), key=lambda p: p.stat().st_mtime)
            src = cands[-1] if cands else None
        if not src:
            raise RuntimeError("yt-dlp no produjo archivo")
        topic = ((info or {}).get("title") or "").strip() or msg_caption(text)
        notify.send(f"Descargado: {src.name} — editando...")
        _process_src(src, topic)
    except Exception as ex:
        traceback.print_exc()
        msg = str(ex)[:300]
        if "not a bot" in msg.lower():
            msg += " — YouTube está bloqueando la sesión; hay que re-exportar cookies.txt y actualizar el secret YT_COOKIES."
        notify.send(f"Error con el video de YouTube: {msg}")


def msg_caption(text):
    """Texto que no es la URL se usa como tema/caption opcional."""
    return _YT_RE.sub("", text).strip()


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
        gh = bool(os.getenv("GH_ACTIONS"))
        if msg.get("video") or msg.get("document"):
            if gh:
                _remix_file(msg)
            else:
                threading.Thread(target=_remix_file, args=(msg,), daemon=True).start()
            continue
        parts = (msg.get("text") or "").split()
        if not parts:
            continue
        if _YT_RE.search(msg["text"]):
            if gh:
                _remix_url(msg["text"])
            else:
                threading.Thread(target=_remix_url, args=(msg["text"],), daemon=True).start()
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
    if os.getenv("GH_ACTIONS"):
        # En GitHub: una pasada y salir. Comandos de Telegram primero
        # (el cron externo nos despierta cada pocos min).
        for step in (handle_commands, core.check_uploads, slots_tick, core.check_clips):
            try:
                step()
            except Exception as ex:
                traceback.print_exc()
                notify.send(f"Error en {step.__name__}: {str(ex)[:300]}")
        return
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
