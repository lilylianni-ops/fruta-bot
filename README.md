# Bot de Frutas Novelas (YouTube Shorts)

Escribe un episodio nuevo cada vez, te da los prompts de los clips, arma el video (voz, subtítulos, 9:16),
te lo manda a Telegram para aprobar y lo sube a YouTube marcado como contenido sintético.

## Instalar
1. Instala Python 3.10+ y ffmpeg (que `ffmpeg` y `ffprobe` funcionen en la terminal).
2. `pip install -r requirements.txt`
3. Copia `.env.example` a `.env` y llénalo:
   - GEMINI_API_KEY: gratis en aistudio.google.com/apikey (si da error de modelo, copia el nombre exacto del modelo Flash desde AI Studio a "model" en config.json)
   - TELEGRAM_TOKEN: crea un bot con @BotFather. TELEGRAM_CHAT_ID: tu id (escríbele a @userinfobot).
   - PANEL_PASSWORD: una clave larga para el panel.
4. YouTube: en Google Cloud crea un proyecto, activa "YouTube Data API v3", crea credenciales OAuth tipo
   "Aplicación de escritorio" y guarda el archivo como `client_secret.json` en esta carpeta.
   La primera vez que subas, se abre el navegador para autorizar. Si el bot va a vivir en un servidor sin pantalla,
   autoriza primero en tu PC y copia `token.json` al servidor.

## Usar
- Antes de encender, corre `python3 check.py`: te dice qué falta o qué falla.
- `./run.sh` deja el bot corriendo y lo reinicia si se cae. `python3 panel.py` abre el panel en http://127.0.0.1:5000
- Cada hora de `generate_times` (config.json) el bot escribe un episodio y te avisa por Telegram.
- Pega los prompts de `data/episodes/epNNN/prompts.txt` en tus herramientas de video, y suelta los clips en `data/episodes/epNNN/clips/` (en orden).
- Cuando estén todos, el bot arma el video y te lo manda. Responde `/ok N` para subir o `/no N` para descartar.
- Comandos: /status, /nuevo, /pausa, /seguir.

## Cosas que debes saber
- `upload_privacy` empieza en "private" a propósito. Los videos subidos por API desde proyectos sin verificar quedan privados hasta que Google audite el proyecto; mientras, publícalos tú desde YouTube Studio.
- `daily_upload_cap` limita las subidas por día (empieza en 2).
- La voz usa edge-tts, que es gratis pero no oficial: revisa sus términos antes de monetizar, o cambia a tu propia voz.
- Revisa los términos de uso comercial de cada herramienta de video que uses. Si el plan gratis no da derechos comerciales o deja marca de agua, no lo uses para el canal monetizado.
- Mira cada episodio antes de aprobarlo. Si dejas `auto_approve` en true, YouTube puede ver el canal como producción en masa.
- Edita `data/bible.json` (se crea al primer episodio) para cambiar personajes, estilo y mundo.
