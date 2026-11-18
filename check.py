"""Prueba de arranque: corre `python check.py` antes de encender el bot."""
import os, shutil, requests
from store import *


def line(ok, msg):
    print(("OK     " if ok else "FALLA  ") + msg, flush=True)


def clean(e):
    t = str(e)
    for k in ("GEMINI_API_KEY", "TELEGRAM_TOKEN"):
        if os.getenv(k):
            t = t.replace(os.getenv(k), "***")
    return t[:250]


line(bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), "ffmpeg y ffprobe instalados")
for k in ("GEMINI_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    line(bool(os.getenv(k)), f"{k} está en el archivo .env")
line((ROOT / "client_secret.json").exists(), "client_secret.json está en la carpeta")

try:
    import story
    t = story._gen("Responde solo con la palabra: listo")
    line("listo" in t.lower(), f"Gemini responde (modelo: {cfg()['model']})")
except Exception as e:
    line(False, "Gemini: " + clean(e))

try:
    story.refresh_trends()
    line(bool(story.trends_text() and "sin tendencias" not in story.trends_text()), "Búsqueda de tendencias (si falla, el bot sigue sin ella)")
except Exception as e:
    line(False, "Tendencias: " + clean(e))

try:
    api = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}"
    me = requests.get(api + "/getMe", timeout=15).json()
    line(bool(me.get("ok")), "Token de Telegram válido")
    r = requests.post(api + "/sendMessage", data={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": "Prueba del bot de Frutas Novelas: todo bien."}, timeout=15).json()
    line(bool(r.get("ok")), "Te llegó el mensaje de prueba a Telegram" if r.get("ok") else "Telegram no pudo escribirte: mándale /start a tu bot primero")
except Exception as e:
    line(False, "Telegram: " + clean(e))

line((ROOT / "token.json").exists(), "YouTube ya autorizado" if (ROOT / "token.json").exists() else "YouTube se autoriza la primera vez que suba un video (es normal)")
