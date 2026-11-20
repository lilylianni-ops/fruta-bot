"""
Generación de voz con Edge-TTS, mezcla con música de fondo, auto-ducking.
"""
import asyncio
import os
import subprocess
import random
from pathlib import Path
from typing import List, Optional, Dict
import edge_tts


# Voces disponibles en Edge-TTS (español e inglés)
EDGE_TTS_VOICES = {
    "es": {
        "female": [
            "es-MX-DaliaNeural",      # México femenina
            "es-CO-SalomeNeural",     # Colombia femenina
            "es-ES-ElviraNeural",     # España femenina
            "es-AR-ElenaNeural",      # Argentina femenina
            "es-CL-CatalinaNeural",   # Chile femenina
        ],
        "male": [
            "es-MX-JorgeNeural",      # México masculina
            "es-CO-GonzaloNeural",    # Colombia masculina
            "es-ES-AlvaroNeural",     # España masculina
            "es-AR-TomasNeural",      # Argentina masculina
        ]
    },
    "en": {
        "female": [
            "en-US-AriaNeural",       # US femenina
            "en-US-JennyNeural",      # US femenina
            "en-GB-SoniaNeural",      # UK femenina
            "en-AU-NatashaNeural",    # Australia femenina
        ],
        "male": [
            "en-US-GuyNeural",        # US masculina
            "en-US-DavisNeural",      # US masculina
            "en-GB-RyanNeural",       # UK masculina
            "en-AU-WilliamNeural",    # Australia masculina
        ]
    }
}

# Estilos de voz disponibles
VOICE_STYLES = {
    "es-MX-DaliaNeural": ["cheerful", "empathetic", "narration-professional"],
    "es-CO-SalomeNeural": ["cheerful", "empathetic"],
    "es-ES-ElviraNeural": ["cheerful", "empathetic", "narration-professional"],
    "es-MX-JorgeNeural": ["cheerful", "empathetic", "narration-professional"],
    "es-CO-GonzaloNeural": ["cheerful", "empathetic"],
    "en-US-AriaNeural": ["cheerful", "empathetic", "narration-professional", "excited"],
    "en-US-GuyNeural": ["cheerful", "empathetic", "narration-professional"],
}


class AudioTTS:
    def __init__(self, work_dir: Path, socketio=None, task_id: str = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.socketio = socketio
        self.task_id = task_id
        self.temp_dir = self.work_dir / "temp_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def _emit(self, phase: int, total: int, message: str, progress: float = None):
        if self.socketio and self.task_id:
            data = {"phase": phase, "total": total, "message": message, "progress": progress or (phase/total*100)}
            self.socketio.emit("progress", data, room=self.task_id)
        print(f"[AUDIO {phase}/{total}] {message}")

    def _run_ffmpeg(self, cmd: List[str], desc: str = "FFmpeg Audio") -> subprocess.CompletedProcess:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"{desc} falló: {result.stderr[-500:]}")
        return result

    async def _generate_tts_edge(self, text: str, voice: str, rate: str, volume: str, 
                                  output_path: Path, style: str = None) -> Path:
        """Genera TTS con Edge-TTS."""
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        if style and voice in VOICE_STYLES and style in VOICE_STYLES[voice]:
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, style=style)
        await communicate.save(str(output_path))
        return output_path

    def generate_voice(self, text: str, config: Dict) -> Path:
        """
        Genera archivo de voz con Edge-TTS.
        config: {
            'language': 'es' | 'en',
            'gender': 'female' | 'male',
            'voice': 'specific_voice_name' (opcional, sobrescribe language/gender),
            'rate': '+0%' (ej: '-10%', '+20%'),
            'volume': '+0%' (ej: '-20%', '+10%'),
            'style': 'cheerful' | 'empathetic' | 'narration-professional' (opcional)
        }
        """
        self._emit(3, 5, "Generando voz con Edge-TTS...")
        
        lang = config.get("language", "es")
        gender = config.get("gender", "female")
        voice = config.get("voice")
        
        if not voice:
            voices = EDGE_TTS_VOICES.get(lang, {}).get(gender, [])
            if not voices:
                voices = EDGE_TTS_VOICES["es"]["female"]
            voice = random.choice(voices)
        
        rate = config.get("rate", "+0%")
        volume = config.get("volume", "+0%")
        style = config.get("style")
        
        output_path = self.temp_dir / f"voice_{voice.replace('-', '_')}.mp3"
        
        # Ejecutar async
        asyncio.run(self._generate_tts_edge(text, voice, rate, volume, output_path, style))
        
        self._emit(3, 5, f"Voz generada: {voice} ({rate}, {volume})")
        return output_path

    def get_audio_duration(self, audio_path: Path) -> float:
        """Obtiene duración de audio en segundos."""
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def mix_voice_music(self, voice_path: Path, music_path: Path, output_path: Path,
                        music_volume: float = 0.15, ducking: bool = True) -> Path:
        """
        Mezcla voz + música de fondo con auto-ducking.
        music_volume: 0.0 a 1.0 (volumen base de la música)
        ducking: baja la música cuando hay voz
        """
        self._emit(3, 5, "Mezclando voz con música de fondo (auto-ducking)...")
        
        # Obtener duraciones
        voice_dur = self.get_audio_duration(voice_path)
        music_dur = self.get_audio_duration(music_path)
        
        # Si la música es más corta, hacer loop
        if music_dur < voice_dur:
            loops = int(voice_dur / music_dur) + 1
            looped_music = self.temp_dir / "music_looped.mp3"
            cmd = [
                "ffmpeg", "-y", "-stream_loop", str(loops), "-i", str(music_path),
                "-t", str(voice_dur + 1), "-c:a", "libmp3lame", "-b:a", "192k",
                str(looped_music)
            ]
            self._run_ffmpeg(cmd, "Loop Music")
            music_path = looped_music
        
        if ducking:
            # Auto-ducking: sidechain compression - la música baja cuando hay voz
            # Usamos sidechaincompress con la voz como trigger
            cmd = [
                "ffmpeg", "-y",
                "-i", str(music_path),   # [0] música
                "-i", str(voice_path),   # [1] voz
                "-filter_complex",
                f"[0:a]volume={music_volume}[music];"
                f"[1:a]volume=1.0[voice];"
                "[music][voice]sidechaincompress="
                "threshold=0.003:ratio=20:attack=5:release=100:makeup=1[out]",
                "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
                str(output_path)
            ]
        else:
            # Mezcla simple sin ducking
            cmd = [
                "ffmpeg", "-y",
                "-i", str(music_path), "-i", str(voice_path),
                "-filter_complex",
                f"[0:a]volume={music_volume}[music];"
                "[1:a]volume=1.0[voice];"
                "[music][voice]amix=inputs=2:duration=first:dropout_transition=0[out]",
                "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
                str(output_path)
            ]
        
        self._run_ffmpeg(cmd, "Mix Voice + Music")
        self._emit(3, 5, "Audio final mezclado listo")
        return output_path

    def add_silence_padding(self, audio_path: Path, output_path: Path, 
                            start_silence: float = 0.5, end_silence: float = 1.0) -> Path:
        """Añade silencio al inicio y final para respiración."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={start_silence}",
            "-i", str(audio_path),
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={end_silence}",
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
            "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k",
            str(output_path)
        ]
        self._run_ffmpeg(cmd, "Add Silence Padding")
        return output_path

    def change_voice_pitch(self, audio_path: Path, output_path: Path, 
                           semitones: float = 0.0) -> Path:
        """
        Cambia el tono de la voz (en semitonos) para evitar detección de copyright.
        Positivo = más agudo, Negativo = más grave.
        Rango recomendado: -3 a +3 semitonos.
        """
        if abs(semitones) < 0.1:
            return audio_path
            
        self._emit(3, 5, f"Cambiando tono de voz: {semitones:+.1f} semitonos...")
        
        # rubberband para pitch shifting de alta calidad
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-af", f"rubberband=pitch={semitones}",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(output_path)
        ]
        try:
            self._run_ffmpeg(cmd, "Pitch Shift")
        except RuntimeError:
            # Fallback: asetrate (más rápido pero cambia duración)
            ratio = 2 ** (semitones / 12)
            cmd = [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-af", f"asetrate=44100*{ratio},aresample=44100",
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(output_path)
            ]
            self._run_ffmpeg(cmd, "Pitch Shift (fallback)")
        return output_path

    def transform_music(self, music_path: Path, output_path: Path, fx: Dict) -> Path:
        """
        Transforma la música para que suene distinta: tempo/BPM, pitch y EQ.
        fx: {'tempo': 1.0-2.0, 'pitch_semitones': -12 a 12, 'bass': dB, 'treble': dB}
        """
        filters = []
        pitch = float(fx.get("pitch_semitones", 0) or 0)
        tempo = float(fx.get("tempo", 1.0) or 1.0)
        if abs(pitch) > 0.1:
            ratio = 2 ** (pitch / 12)
            filters += [f"asetrate=44100*{ratio:.6f}", "aresample=44100", f"atempo={1/ratio:.6f}"]
        if abs(tempo - 1.0) > 0.01:
            filters.append(f"atempo={min(max(tempo, 0.5), 2.0):.4f}")
        if fx.get("bass"):
            filters.append(f"bass=g={fx['bass']}")
        if fx.get("treble"):
            filters.append(f"treble=g={fx['treble']}")
        filters += [str(x) for x in (fx.get("extra_filters") or [])]
        if not filters:
            import shutil
            shutil.copy2(music_path, output_path)
            return output_path
        cmd = [
            "ffmpeg", "-y", "-i", str(music_path),
            "-af", ",".join(filters),
            "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
            str(output_path)
        ]
        self._run_ffmpeg(cmd, "Transform Music")
        return output_path

    def get_available_music(self, music_dir: Path) -> List[Path]:
        """Lista archivos de música disponibles."""
        music_dir = Path(music_dir)
        if not music_dir.exists():
            return []
        exts = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
        return [f for f in music_dir.iterdir() if f.suffix.lower() in exts]

    def pick_random_music(self, music_dir: Path) -> Optional[Path]:
        """Selecciona una pista de música aleatoria."""
        tracks = self.get_available_music(music_dir)
        return random.choice(tracks) if tracks else None


def generate_complete_audio(script_text: str, config: Dict, work_dir: Path,
                            socketio=None, task_id: str = None) -> Path:
    """
    Función principal: genera audio completo (voz + música + ducking + pitch shift).
    config: {
        'language', 'gender', 'voice', 'rate', 'volume', 'style',
        'music_volume': 0.0-1.0,
        'pitch_shift': -3.0 a +3.0,
        'music_dir': Path,
        'add_silence': bool
    }
    """
    tts = AudioTTS(work_dir, socketio, task_id)
    
    # 1. Generar voz
    voice_path = tts.generate_voice(script_text, config)
    
    # 2. Cambiar pitch si se pide (anti-copyright)
    if config.get("pitch_shift", 0) != 0:
        pitched_path = tts.temp_dir / "voice_pitched.mp3"
        voice_path = tts.change_voice_pitch(voice_path, pitched_path, config["pitch_shift"])
    
    # 3. Añadir silencio de respiración
    if config.get("add_silence", True):
        padded_path = tts.temp_dir / "voice_padded.mp3"
        voice_path = tts.add_silence_padding(voice_path, padded_path)
    
    # 4. Seleccionar y mezclar música
    music_dir = Path(config.get("music_dir", work_dir.parent / "bg_music"))
    music_path = config.get("music_path") or tts.pick_random_music(music_dir)

    # Transformar la música (BPM/pitch/EQ) para que suene distinta
    music_fx = config.get("music_fx")
    if music_path and music_path.exists() and music_fx:
        fx_path = tts.temp_dir / "music_fx.mp3"
        music_path = tts.transform_music(music_path, fx_path, music_fx)

    final_audio = tts.temp_dir / "final_audio.mp3"
    
    if music_path and music_path.exists():
        tts.mix_voice_music(
            voice_path, music_path, final_audio,
            music_volume=config.get("music_volume", 0.15),
            ducking=config.get("ducking", True)
        )
    else:
        # Solo voz
        import shutil
        shutil.copy2(voice_path, final_audio)

    # 5. Mezcla opcional del audio original (voces/ambiente del video fuente).
    #    Se filtra a banda de voz (corta graves/agudos de la música) y se
    #    atenúa cuando habla la narración (sidechain ducking).
    orig_path = config.get("original_audio_path")
    orig_vol = float(config.get("original_audio_volume", 0) or 0)
    if orig_path and Path(orig_path).exists() and orig_vol > 0:
        try:
            dur = tts.get_audio_duration(final_audio)
            mixed = tts.temp_dir / "final_audio_with_orig.mp3"
            cmd = [
                "ffmpeg", "-y",
                "-i", str(orig_path), "-i", str(final_audio),
                "-filter_complex",
                f"[0:a]highpass=f=250,lowpass=f=3400,volume={orig_vol},apad,atrim=0:{dur:.3f}[o];"
                f"[o][1:a]sidechaincompress=threshold=0.003:ratio=15:attack=5:release=120:makeup=1[out]",
                "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
                str(mixed)
            ]
            tts._run_ffmpeg(cmd, "Mix Original Audio (ducking)")
            final_audio = mixed
        except Exception as e:
            print(f"[AudioTTS] No se pudo mezclar audio original: {e}")

    return final_audio