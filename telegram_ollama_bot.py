"""
Bot de Telegram que responde usando Ollama local (llama3.2:1b).
Uso: python telegram_ollama_bot.py
Requiere TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en .env (los del bot de frutas).
"""
import os
import time
import requests
from pathlib import Path

BASE = Path(__file__).parent

# --- .env simple ---
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
API = f"https://api.telegram.org/bot{TOKEN}"

SYSTEM_PROMPT = """Actúa como "GTA-6 AutoEditor", un bot autónomo de IA.
Tu objetivo es transformar videos largos de GTA VI en Shorts monetizables.

Paso 1: Búsqueda Simulada.
Asume que has escaneado YouTube y TikTok en los últimos 24 horas. Selecciona el clip más viral disponible sobre "GTA 6 glitches" o "GTA 6 easter eggs".

Paso 2: Análisis de Copyright y Marca de Agua.
Describe visualmente cómo se debe recortar el video original (9:16) para eliminar logos de streamers o marcas de agua laterales. Usa términos técnicos como "crop-to-center" o "zoom-safe-area".

Paso 3: Narrativa Transformada (Fair Use).
Genera un guion de 15 segundos estilo "Sabías que...". El guion debe añadir valor educativo o humorístico para justificar el uso justo (fair use) y evitar reclamos de copyright automáticos.

Paso 4: Formato de Salida.
Devuelve la respuesta en JSON con estas claves:
{
  "video_title": "Título viral del clip",
  "youtube_url": "URL directa del video fuente",
  "edit_instructions": "Instrucciones precisas de recorte para eliminar marca de agua",
  "narration_script": "Texto exacto para la voz en off",
  "voice_tone": "Dinámico/Juvenil/Energetico"
}

No des explicaciones extra. Solo devuelve el JSON listo para ser procesado por mi editor automático."""


def ollama_chat(messages):
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL,
              "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
              "stream": False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def send(chat_id, text):
    # Telegram limita mensajes a 4096 chars
    for i in range(0, len(text), 4000):
        requests.post(f"{API}/sendMessage",
                      json={"chat_id": chat_id, "text": text[i:i + 4000]},
                      timeout=30)


def main():
    # Solo responde al chat configurado; offset para no repetir mensajes
    offset = None
    history = {}  # chat_id -> [messages]
    print(f"Bot corriendo con {MODEL}. Ctrl+C para salir.")
    while True:
        params = {"timeout": 30}
        if offset is not None:
            params["offset"] = offset
        try:
            r = requests.get(f"{API}/getUpdates", params=params, timeout=40)
            r.raise_for_status()
        except requests.RequestException as e:
            print("Error de red:", e)
            time.sleep(5)
            continue

        for upd in r.json().get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg or "text" not in msg:
                continue
            chat_id = str(msg["chat"]["id"])
            if ALLOWED_CHAT and chat_id != ALLOWED_CHAT:
                continue

            text = msg["text"].strip()
            if text.startswith("/start"):
                send(chat_id, f"Hola, soy un bot con {MODEL} corriendo en tu PC. Escribe lo que quieras.")
                continue
            if text.startswith("/clear"):
                history.pop(chat_id, None)
                send(chat_id, "Conversación limpiada.")
                continue

            msgs = history.setdefault(chat_id, [])
            msgs.append({"role": "user", "content": text})
            msgs[:] = msgs[-20:]  # últimas 20 interacciones
            try:
                reply = ollama_chat(msgs)
            except Exception as e:
                reply = f"Error con Ollama: {e}"
            msgs.append({"role": "assistant", "content": reply})
            send(chat_id, reply)


if __name__ == "__main__":
    main()
