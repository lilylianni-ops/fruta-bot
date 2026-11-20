"""Puente con autoviral-studio-pro: le delega la producción/edición de videos."""
import os
import shutil
import time
from pathlib import Path

import requests

from store import cfg, ep_dir, ep_load
import video


def _url():
    return cfg().get("autoviral_url", "http://localhost:5000").rstrip("/")


def available():
    try:
        return requests.get(f"{_url()}/api/input-files", timeout=5).ok
    except Exception:
        return False


def _start(payload):
    r = requests.post(f"{_url()}/api/process", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["task_id"]


def _wait(task_id):
    deadline = time.time() + cfg().get("autoviral_timeout", 1800)
    while time.time() < deadline:
        time.sleep(10)
        st = requests.get(f"{_url()}/api/task-status/{task_id}", timeout=15).json()
        status = st.get("status")
        if status == "completed":
            return Path(st["output"])
        if status in ("error", "cancelled"):
            raise RuntimeError(st.get("error") or status)
    raise TimeoutError("autoviral no terminó a tiempo")


def _av_config(remix=False, **extra):
    c = cfg()
    base = {
        "target_duration": c.get("remix_duration", 60),
        "tts_voice": c.get("voice", "es-DO-RamonaNeural"),
        "tts_rate": c.get("voice_rate", "+0%"),
        "generate_subtitles": c.get("autoviral_subtitles", True),
        "whisper_model": c.get("autoviral_whisper", "base"),
        "subs_language": "es",
        "crop_9_16": True,
        "remove_watermark": True,
        "anti_copyright": True,
        "visual_dynamism": True,
        "music_volume": c.get("music_volume", 0.15),
        "original_audio_volume": c.get("original_audio_volume", 0.10),
    }
    if remix:
        base.update({
            "mirror": c.get("remix_mirror", False),
            "reorder_scenes": c.get("remix_reorder", True),
            "scene_duration": c.get("remix_scene_duration", 2.5),
            "zoom_range": c.get("remix_zoom_range", [1.15, 1.5]),
            "pitch_shift": c.get("remix_pitch", 1.5),
            "music_fx": c.get("remix_music_fx", {
                "tempo": 1.10,
                "pitch_semitones": 2,
                "bass": 3,
                "treble": -1,
                "extra_filters": [
                    "equalizer=f=3000:t=q:w=1:g=2",
                    "acompressor=threshold=-18dB:ratio=3:attack=10:release=100",
                ],
            }),
        })
    base.update(extra)
    return base


def produce(n):
    """Pide a autoviral que produzca el episodio. Devuelve (path_final.mp4, segundos)."""
    e, d = ep_load(n), ep_dir(n)
    clips = video.find_clips(n)[: len(e["narration"])]
    if not clips:
        raise RuntimeError("sin clips para autoviral")

    target = int(sum(video._dur(p) for p in clips))
    payload = _av_config(
        input_files=[str(p.resolve()) for p in clips],
        script_text=" ".join(e["narration"]),
        target_duration=target,
    )
    out = _wait(_start(payload))
    dest = d / "final.mp4"
    shutil.copy2(out, dest)
    return dest, target


def describe_video(path):
    """Analiza el video con Gemini y devuelve un tema corto para el guion."""
    from google import genai
    from store import cfg as _cfg
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    f = client.files.upload(file=str(path))
    for _ in range(60):
        state = getattr(f.state, "name", f.state)
        if state != "PROCESSING":
            break
        time.sleep(3)
        f = client.files.get(name=f.name)
    prompt = ("Resume en una frase corta (max 15 palabras), en español, de qué trata este video. "
              "Es el tema para un guion estilo 'Sabías que...'. Responde SOLO la frase, sin comillas.")
    last = None
    for model in [_cfg().get("model"), "gemini-2.5-flash"]:
        try:
            r = client.models.generate_content(model=model, contents=[f, prompt])
            txt = (r.text or "").strip().strip('"')
            if txt:
                return txt
        except Exception as e:
            last = e
    raise last


def remix_video(video_path, topic=""):
    """Edición completa de un video suelto: quita marcas, voz nueva 'Sabías que...',
    subtítulos, música, 9:16. Devuelve el Path del video final."""
    import random
    payload = _av_config(remix=True,
        input_files=[str(Path(video_path).resolve())],
        topic=topic or "video viral",
        script_mode="story",      # modo '¿Sabías que...?'
        script_tone="viral",
        llm_provider=cfg().get("remix_llm", "offline"),
        llm_config={"model": os.environ.get("OLLAMA_MODEL", "llama3.2:1b")},
    )
    if cfg().get("remix_randomize", True):
        fx = dict(payload.get("music_fx") or {})
        fx["tempo"] = round(random.uniform(1.05, 1.15), 3)
        fx["pitch_semitones"] = round(random.uniform(1, 3), 1)
        payload["music_fx"] = fx
        payload["pitch_shift"] = round(random.uniform(1.0, 2.5), 1)
        payload["scene_duration"] = round(random.uniform(1.0, 4.0), 1)
        z0 = round(random.uniform(1.10, 1.30), 2)
        z1 = round(random.uniform(1.40, 1.70), 2)
        payload["zoom_range"] = [min(z0, z1), max(z0, z1)]
    if topic:
        payload["watermark_text"] = topic[:40]
    return _wait(_start(payload))
