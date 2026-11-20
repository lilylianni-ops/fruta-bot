"""Edición local de videos para GitHub Actions (sin servidor autoviral).
Replica el pipeline de autoviral-studio-pro usando avcore/ directamente."""
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

from store import cfg, ROOT
from avcore.script_writer import ScriptWriter, ScriptMode, ScriptTone
from avcore.audio_tts import generate_complete_audio
from avcore.video_processor import process_video_pipeline
from avcore.subtitles import process_subtitles_complete

BGM_DIR = ROOT / "bgm"
WORK_ROOT = ROOT / "data" / "remix_work"


def _dur(p):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _jitter():
    fx = {
        "tempo": round(random.uniform(1.05, 1.15), 3),
        "pitch_semitones": round(random.uniform(1, 3), 1),
        "bass": 3,
        "treble": -1,
        "extra_filters": [
            "equalizer=f=3000:t=q:w=1:g=2",
            "acompressor=threshold=-18dB:ratio=3:attack=10:release=100",
        ],
    }
    return {
        "pitch_shift": round(random.uniform(1.0, 2.5), 1),
        "scene_duration": round(random.uniform(1.0, 4.0), 1),
        "zoom_range": [round(random.uniform(1.10, 1.30), 2),
                       round(random.uniform(1.40, 1.70), 2)],
        "music_fx": fx,
    }


def edit_video(src, topic="", work=None):
    """Edita un video: guion 'Sabías que...', voz nueva, música transformada,
    subtítulos, anti-copyright, 9:16. Devuelve Path del mp4 final."""
    c = cfg()
    src = Path(src)
    work = Path(work) if work else WORK_ROOT / f"remix_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)

    # 1. Guion
    writer = ScriptWriter({
        "llm_provider": c.get("remix_llm", "offline"),
        "llm": {"model": "llama3.2:1b"},
        "language": "es",
    })
    target = int(min(_dur(src), c.get("remix_duration", 60)))
    script = writer.generate(
        topic=topic or "video viral",
        mode=ScriptMode.STORY,
        tone=ScriptTone.VIRAL,
        target_duration=target,
    )
    script_text = script.full_text()

    # 2. Audio original del video (para mezcla con ducking)
    orig_wav = work / "original.wav"
    orig_audio = None
    r = subprocess.run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ac", "2",
                        "-ar", "44100", str(orig_wav)], capture_output=True)
    if r.returncode == 0 and orig_wav.exists():
        orig_audio = str(orig_wav)

    # 3. Audio completo (voz + música + original)
    j = _jitter()
    audio_cfg = {
        "language": "es",
        "voice": c.get("voice", "es-DO-RamonaNeural"),
        "rate": c.get("voice_rate", "+5%"),
        "volume": "+0%",
        "music_volume": c.get("music_volume", 0.15),
        "pitch_shift": j["pitch_shift"],
        "music_fx": j["music_fx"],
        "music_dir": BGM_DIR,
        "ducking": True,
        "add_silence": True,
        "original_audio_path": orig_audio,
        "original_audio_volume": c.get("original_audio_volume", 0.10),
    }
    final_audio = generate_complete_audio(script_text, audio_cfg, work)

    # 4. Video
    z = j["zoom_range"]
    video_config = {
        "target_duration": target,
        "remove_audio": True,
        "smart_crop": True,
        "zoom_range": (min(z), max(z)),
        "visual_dynamism": True,
        "mirror": c.get("remix_mirror", False),
        "reorder_scenes": c.get("remix_reorder", True),
        "scene_duration": j["scene_duration"],
        "audio_path": str(final_audio),
        "watermark_text": (topic or "")[:40],
        "subtitles_ass": None,
    }
    video_no_subs = work / "video_no_subs"
    video_no_subs.mkdir(exist_ok=True)
    process_video_pipeline(src, video_no_subs, video_config)
    base_video = video_no_subs / f"final_{src.stem}.mp4"

    # 5. Subtítulos
    final_out = work / "final.mp4"
    subs_cfg = {
        "model_size": c.get("autoviral_whisper", "base"),
        "language": "es",
        "device": "auto",
        "style": "hormozi",
        "position": "center-bottom",
        "words_per_line": 3,
        "max_line_duration": 2.5,
    }
    final_video = process_subtitles_complete(
        final_audio, base_video, final_out, subs_cfg, work, None, None
    )

    # 6. Guardar copia en data/remix/output
    out_dir = ROOT / "data" / "remix" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"remix_{int(time.time())}.mp4"
    shutil.copy2(final_video, dest)
    return dest
