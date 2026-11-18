import os, time, datetime as dt, traceback
from store import *
import core, notify, story


def slots_tick():
    s, c = state(), cfg()
    if s["paused"]:
        return
    now = dt.datetime.now()
    done = s["slots"].setdefault(today(), [])
    for slot in c["generate_times"]:
        h, m = map(int, slot.split(":"))
        diff = (now - now.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds() / 60
        if diff >= 0 and slot not in done:
            done.append(slot)
            if s.get("trends_day") != today():
                s["trends_day"] = today()
            save_state(s)
            if diff <= 120:
                story.refresh_trends()
                core.generate()
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
        parts = (msg.get("text") or "").split()
        if not parts:
            continue
        cmd, arg = parts[0].lower(), (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None)
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
    while True:
        for step in (slots_tick, core.check_clips, core.check_uploads, handle_commands):
            try:
                step()
            except Exception as ex:
                traceback.print_exc()
                notify.send(f"Error en {step.__name__}: {str(ex)[:300]}")
        time.sleep(20)


if __name__ == "__main__":
    main()
