"""
Transcripción con Faster-Whisper y generación de subtítulos .ass animados (estilo TikTok/Reels).
"""
import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class WordSegment:
    """Segmento de palabra con timestamps."""
    word: str
    start: float
    end: float
    probability: float = 1.0


@dataclass
class SubtitleLine:
    """Línea de subtítulo compuesta por palabras."""
    words: List[WordSegment]
    start: float
    end: float
    text: str


class SubtitleGenerator:
    """Genera subtítulos .ass animados con estilos tipo TikTok/Reels/Hormozi."""
    
    # Estilos predefinidos
    STYLES = {
        "hormozi": {
            "name": "Hormozi (Amarillo/Blanco, borde negro grueso)",
            "font": "Arial Black",
            "fontsize": 28,
            "primary_color": "&H00FFFF00",    # Amarillo (ABGR)
            "secondary_color": "&H00FFFFFF",   # Blanco
            "outline_color": "&H00000000",     # Negro
            "back_color": "&H00000000",
            "outline": 4,
            "shadow": 2,
            "alignment": 2,  # Centro-abajo
            "margin_v": 180,
            "bold": True,
            "italic": False,
            "spacing": 1.5,
            "karaoke": True,
            "pop_up": True,
        },
        "neon": {
            "name": "Neón (Cyan/Rosa, glow)",
            "font": "Arial Black",
            "fontsize": 30,
            "primary_color": "&H00FFFF00",    # Cyan
            "secondary_color": "&H00FF00FF",  # Magenta
            "outline_color": "&H00000000",
            "back_color": "&H80000000",
            "outline": 3,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 180,
            "bold": True,
            "italic": False,
            "spacing": 2.0,
            "karaoke": True,
            "pop_up": True,
            "blur": 1.5,
        },
        "minimal": {
            "name": "Minimalista (Caja oscura, texto blanco)",
            "font": "Helvetica Neue",
            "fontsize": 26,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H00DDDDDD",
            "outline_color": "&H00000000",
            "back_color": "&HAA000000",
            "outline": 0,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 160,
            "bold": False,
            "italic": False,
            "spacing": 1.0,
            "karaoke": False,
            "pop_up": False,
            "box": True,
        },
        "telenovela": {
            "name": "Telenovela/Dramático (Blanco con sombra dramática)",
            "font": "Georgia",
            "fontsize": 28,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H00F0F0F0",
            "outline_color": "&H00000000",
            "back_color": "&H00000000",
            "outline": 2,
            "shadow": 4,
            "alignment": 2,
            "margin_v": 200,
            "bold": True,
            "italic": True,
            "spacing": 1.0,
            "karaoke": True,
            "pop_up": False,
        },
        "tiktok": {
            "name": "TikTok Nativo (Blanco, contorno negro, centro)",
            "font": "Proxima Nova",
            "fontsize": 32,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "back_color": "&H00000000",
            "outline": 5,
            "shadow": 0,
            "alignment": 5,  # Centro
            "margin_v": 0,
            "bold": True,
            "italic": False,
            "spacing": 1.0,
            "karaoke": True,
            "pop_up": True,
            "per_word": True,
        }
    }
    
    # Posiciones predefinidas
    POSITIONS = {
        "center": {"alignment": 5, "margin_v": 0},
        "center-bottom": {"alignment": 2, "margin_v": 180},
        "top": {"alignment": 8, "margin_v": 100},
        "bottom": {"alignment": 2, "margin_v": 80},
    }

    def __init__(self, work_dir: Path, socketio=None, task_id: str = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.socketio = socketio
        self.task_id = task_id
        self.temp_dir = self.work_dir / "temp_subs"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def _emit(self, phase: int, total: int, message: str, progress: float = None):
        if self.socketio and self.task_id:
            data = {"phase": phase, "total": total, "message": message, "progress": progress or (phase/total*100)}
            self.socketio.emit("progress", data, room=self.task_id)
        print(f"[SUBS {phase}/{total}] {message}")

    def _run_ffmpeg(self, cmd: List[str], desc: str = "FFmpeg Subs") -> subprocess.CompletedProcess:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"{desc} falló: {result.stderr[-500:]}")
        return result

    def transcribe_audio(self, audio_path: Path, model_size: str = "base",
                         language: str = "es", device: str = "auto") -> List[WordSegment]:
        """
        Transcribe audio con Faster-Whisper y devuelve palabras con timestamps.
        """
        self._emit(4, 5, f"Transcribiendo con Faster-Whisper ({model_size})...")
        
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError("faster-whisper no instalado. Ejecuta: pip install faster-whisper")
        
        # Configurar dispositivo
        if device == "auto":
            device = "cuda" if self._has_cuda() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
        else:
            compute_type = "float16" if device == "cuda" else "int8"
        
        self._emit(4, 5, f"Cargando modelo Whisper en {device} ({compute_type})...")
        
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        
        self._emit(4, 5, "Transcribiendo audio...")
        segments, info = model.transcribe(
            str(audio_path),
            language=language if language != "auto" else None,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        
        words = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    words.append(WordSegment(
                        word=w.word.strip(),
                        start=w.start,
                        end=w.end,
                        probability=getattr(w, 'probability', 1.0)
                    ))
        
        self._emit(4, 5, f"Transcripción completa: {len(words)} palabras detectadas")
        return words

    def _has_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False

    def group_words_into_lines(self, words: List[WordSegment], 
                                max_words_per_line: int = 3,
                                max_line_duration: float = 2.5,
                                max_chars_per_line: int = 40) -> List[SubtitleLine]:
        """
        Agrupa palabras en líneas de subtítulo respetando límites.
        """
        lines = []
        current_words = []
        line_start = None
        
        for word in words:
            if not current_words:
                line_start = word.start
            
            current_words.append(word)
            
            # Verificar si debemos cortar la línea
            should_break = (
                len(current_words) >= max_words_per_line or
                (word.end - line_start) >= max_line_duration or
                sum(len(w.word) for w in current_words) >= max_chars_per_line
            )
            
            # También cortar en puntuación fuerte
            if word.word.strip().endswith(('.', '!', '?', '。', '！', '？')):
                should_break = True
            
            if should_break:
                line_text = " ".join(w.word for w in current_words)
                lines.append(SubtitleLine(
                    words=current_words.copy(),
                    start=line_start,
                    end=word.end,
                    text=line_text.strip()
                ))
                current_words = []
                line_start = None
        
        # Última línea si queda algo
        if current_words:
            line_text = " ".join(w.word for w in current_words)
            lines.append(SubtitleLine(
                words=current_words,
                start=line_start,
                end=current_words[-1].end,
                text=line_text.strip()
            ))
        
        return lines

    def _format_ass_time(self, seconds: float) -> str:
        """Formatea tiempo para ASS (H:MM:SS.cc)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"

    def _ass_color(self, color: str) -> str:
        """Convierte color hex a formato ASS (ABGR)."""
        # ASS usa formato &HAABBGGRR
        if color.startswith("&H"):
            return color
        if color.startswith("#"):
            color = color[1:]
        if len(color) == 6:
            r, g, b = color[0:2], color[2:4], color[4:6]
            return f"&H{b}{g}{r}"
        return "&H00FFFFFF"

    def generate_ass(self, lines: List[SubtitleLine], style_name: str = "hormozi",
                      position: str = "center-bottom",
                      words_per_block: int = 3,
                      font_override: str = None,
                      fontsize_override: int = None,
                      custom_colors: Dict = None) -> Path:
        """
        Genera archivo .ass con animaciones karaoke/pop-up.
        """
        self._emit(4, 5, f"Generando subtítulos .ass estilo {style_name}...")
        
        style = self.STYLES.get(style_name, self.STYLES["hormozi"]).copy()
        pos = self.POSITIONS.get(position, self.POSITIONS["center-bottom"])
        
        # Aplicar overrides
        if font_override:
            style["font"] = font_override
        if fontsize_override:
            style["fontsize"] = fontsize_override
        style["alignment"] = pos["alignment"]
        style["margin_v"] = pos["margin_v"]
        
        if custom_colors:
            if "primary" in custom_colors:
                style["primary_color"] = self._ass_color(custom_colors["primary"])
            if "secondary" in custom_colors:
                style["secondary_color"] = self._ass_color(custom_colors["secondary"])
            if "outline" in custom_colors:
                style["outline_color"] = self._ass_color(custom_colors["outline"])
        
        # Header ASS
        ass_lines = [
            "[Script Info]",
            "Title: AutoViral Studio Pro Subtitles",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{style['font']},{style['fontsize']},{style['primary_color']},{style['secondary_color']},{style['outline_color']},{style['back_color']},{1 if style['bold'] else 0},{1 if style['italic'] else 0},0,0,100,100,{style['spacing']},0,1,{style['outline']},{style['shadow']},{style['alignment']},40,40,{style['margin_v']},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        
        for i, line in enumerate(lines):
            if style.get("karaoke", False):
                # Estilo karaoke: cada palabra se ilumina progresivamente
                if style.get("per_word", False):
                    # Una línea por palabra (estilo TikTok nativo)
                    for j, word in enumerate(line.words):
                        start_time = self._format_ass_time(word.start)
                        end_time = self._format_ass_time(word.end)
                        duration_cs = int((word.end - word.start) * 100)
                        
                        # Efecto karaoke por palabra
                        if style.get("pop_up", False):
                            # Pop-up: escala de 0 a 100
                            effect = f"\\t(0,{duration_cs},\\fscx100\\fscy100)"
                            text = f"{{\\an{style['alignment']}\\fscx0\\fscy0{effect}}}{word.word}"
                        else:
                            # Karaoke clásico: color change
                            text = f"{{\\an{style['alignment']}\\k{duration_cs}}}{word.word}"
                        
                        ass_lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
                else:
                    # Karaoke por línea completa
                    inline_words = []
                    for word in line.words:
                        duration_cs = int((word.end - word.start) * 100)
                        inline_words.append(f"{{\\k{duration_cs}}}{word.word}")
                    
                    start_time = self._format_ass_time(line.start)
                    end_time = self._format_ass_time(line.end)
                    text = " ".join(inline_words)
                    ass_lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
            else:
                # Sin karaoke, línea estática (estilo minimalista)
                start_time = self._format_ass_time(line.start)
                end_time = self._format_ass_time(line.end)
                
                if style.get("box", False):
                    # Con caja de fondo
                    text = f"{{\\an{style['alignment']}\\shad0\\blur0\\bord0\\4c{style['back_color']}\\3c{style['primary_color']}}}{line.text}"
                else:
                    text = f"{{\\an{style['alignment']}}}{line.text}"
                
                ass_lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
        
        # Guardar archivo
        output_path = self.temp_dir / f"subs_{style_name}.ass"
        output_path.write_text("\n".join(ass_lines), encoding="utf-8-sig")  # UTF-8 con BOM para ASS
        
        self._emit(4, 5, f"Subtítulos .ass generados: {len(lines)} líneas")
        return output_path

    def burn_subtitles(self, video_path: Path, ass_path: Path, output_path: Path) -> Path:
        """
        Quema subtítulos .ass en el video con FFmpeg.
        """
        self._emit(5, 5, "Quemando subtítulos en video...")
        
        # Escapar ruta para FFmpeg (especialmente en Windows)
        ass_escaped = str(ass_path).replace("'", "'\\''").replace(":", "\\:")
        if os.name == 'nt':
            # Windows: usar ruta con barras normales y escapar dos puntos
            ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass='{ass_escaped}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path)
        ]
        
        self._run_ffmpeg(cmd, "Burn Subtitles")
        self._emit(5, 5, "Subtítulos quemados correctamente")
        return output_path

    def generate_srt(self, lines: List[SubtitleLine], output_path: Path) -> Path:
        """Genera archivo .srt estándar."""
        srt_lines = []
        for i, line in enumerate(lines, 1):
            start = self._format_srt_time(line.start)
            end = self._format_srt_time(line.end)
            srt_lines.append(f"{i}\n{start} --> {end}\n{line.text}\n")
        
        output_path.write_text("\n".join(srt_lines), encoding="utf-8")
        return output_path

    def _format_srt_time(self, seconds: float) -> str:
        """Formato SRT: HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def process_subtitles_complete(audio_path: Path, video_path: Path, output_path: Path,
                                config: Dict, work_dir: Path,
                                socketio=None, task_id: str = None) -> Path:
    """
    Pipeline completo: transcribe -> agrupa -> genera .ass -> quema en video.
    config: {
        'model_size': 'base' | 'small' | 'medium',
        'language': 'es' | 'en' | 'auto',
        'device': 'auto' | 'cpu' | 'cuda',
        'style': 'hormozi' | 'neon' | 'minimal' | 'telenovela' | 'tiktok',
        'position': 'center' | 'center-bottom' | 'top' | 'bottom',
        'words_per_line': 1-4,
        'max_line_duration': 2.0-4.0,
        'font': str (opcional),
        'fontsize': int (opcional),
        'custom_colors': {'primary': '#RRGGBB', 'secondary': '#RRGGBB', 'outline': '#RRGGBB'}
    }
    """
    gen = SubtitleGenerator(work_dir, socketio, task_id)
    
    # 1. Transcribir
    words = gen.transcribe_audio(
        audio_path, 
        model_size=config.get("model_size", "base"),
        language=config.get("language", "es"),
        device=config.get("device", "auto")
    )
    
    # 2. Agrupar en líneas
    lines = gen.group_words_into_lines(
        words,
        max_words_per_line=config.get("words_per_line", 3),
        max_line_duration=config.get("max_line_duration", 2.5),
        max_chars_per_line=40
    )
    
    # 3. Generar .ass
    ass_path = gen.generate_ass(
        lines,
        style_name=config.get("style", "hormozi"),
        position=config.get("position", "center-bottom"),
        words_per_block=config.get("words_per_line", 3),
        font_override=config.get("font"),
        fontsize_override=config.get("fontsize"),
        custom_colors=config.get("custom_colors")
    )
    
    # 4. Quemar en video
    gen.burn_subtitles(video_path, ass_path, output_path)
    
    return output_path