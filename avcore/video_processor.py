"""
Motor de procesamiento de video: detección de escenas, cortes, zoom, limpieza de marcas de agua,
filtros anti-copyright y renderizado final con FFmpeg.
"""
import os
import subprocess
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import cv2
from scenedetect import detect, ContentDetector, SceneManager, open_video
from scenedetect.scene_manager import save_images


class VideoProcessor:
    def __init__(self, work_dir: Path, socketio=None, task_id: str = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.socketio = socketio
        self.task_id = task_id
        self.temp_dir = self.work_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def _emit(self, phase: int, total: int, message: str, progress: float = None):
        """Emite progreso via WebSocket si está disponible."""
        if self.socketio and self.task_id:
            data = {
                "phase": phase,
                "total": total,
                "message": message,
                "progress": progress or (phase / total * 100)
            }
            self.socketio.emit("progress", data, room=self.task_id)
        print(f"[{phase}/{total}] {message}")

    def _run_ffmpeg(self, cmd: List[str], desc: str = "FFmpeg") -> subprocess.CompletedProcess:
        """Ejecuta FFmpeg con manejo de errores y rutas escapadas para Windows."""
        # Escapar rutas en Windows para filtros complejos
        cmd_str = " ".join(f'"{c}"' if " " in c and not c.startswith("-") else c for c in cmd)
        self._emit(0, 0, f"{desc}: {cmd_str[:200]}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"{desc} falló (code {result.returncode}): {result.stderr[-500:]}")
            return result
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{desc} timeout después de 5 minutos")

    def get_video_info(self, video_path: Path) -> Dict:
        """Obtiene info del video con ffprobe."""
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,r_frame_rate",
            "-of", "json", str(video_path)
        ]
        result = self._run_ffmpeg(cmd, "ffprobe info")
        info = json.loads(result.stdout)
        stream = info["streams"][0]
        fps_num, fps_den = map(int, stream["r_frame_rate"].split("/"))
        return {
            "width": stream["width"],
            "height": stream["height"],
            "duration": float(stream["duration"]),
            "fps": fps_num / fps_den if fps_den else 30,
            "aspect": stream["width"] / stream["height"]
        }

    def detect_scenes(self, video_path: Path, threshold: float = 27.0) -> List[Tuple[float, float]]:
        """Detecta cambios de escena con PySceneDetect. Retorna lista de (inicio, fin) en segundos."""
        self._emit(1, 5, "Analizando escenas con PySceneDetect...")
        video = open_video(str(video_path))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video, show_progress=False)
        scenes = scene_manager.get_scene_list()
        return [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]

    def extract_keyframes(self, video_path: Path, scenes: List[Tuple[float, float]], 
                          output_dir: Path) -> List[Path]:
        """Extrae fotogramas clave de cada escena."""
        self._emit(1, 5, f"Extrayendo {len(scenes)} fotogramas clave...")
        output_dir.mkdir(parents=True, exist_ok=True)
        keyframes = []
        video = open_video(str(video_path))
        for i, (start, end) in enumerate(scenes):
            mid = (start + end) / 2
            frame_path = output_dir / f"keyframe_{i:03d}.jpg"
            # Usar ffmpeg para extraer frame exacto
            cmd = [
                "ffmpeg", "-y", "-ss", str(mid), "-i", str(video_path),
                "-vframes", "1", "-q:v", "2", str(frame_path)
            ]
            self._run_ffmpeg(cmd, f"Keyframe {i}")
            keyframes.append(frame_path)
        return keyframes

    def smart_crop_9_16(self, input_path: Path, output_path: Path, 
                        zoom_range: Tuple[float, float] = (1.05, 1.35),
                        blur_zones: List[str] = None) -> Path:
        """
        Recorte inteligente 9:16 con zoom progresivo (Ken Burns) y blur de zonas.
        zoom_range: (inicio, fin) ej. 1.05 a 1.35 = 5% a 35% de zoom
        blur_zones: lista de 'top', 'bottom', 'left', 'right', 'topleft', etc.
        """
        self._emit(2, 5, "Aplicando Smart Crop 9:16 con zoom Ken Burns...")
        
        # Construir filter_complex
        vf_parts = []
        
        # 1. Escala base a 1080x1920 manteniendo aspecto, luego crop central
        vf_parts.append(
            "scale=2160:3840:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
        
        # 2. Zoom progresivo (Ken Burns) - zoompan
        zoom_start, zoom_end = zoom_range
        vf_parts.append(
            f"zoompan=z='min({zoom_start}+({zoom_end}-{zoom_start})*on/180,{zoom_end})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=180:s=1080x1920:fps=30"
        )
        
        # 3. Blur de zonas específicas para marcas de agua
        if blur_zones:
            for zone in blur_zones:
                if zone == "top":
                    vf_parts.append("drawbox=x=0:y=0:w=iw:h=150:color=black@0.8:t=fill")
                elif zone == "bottom":
                    vf_parts.append("drawbox=x=0:y=ih-150:w=iw:h=150:color=black@0.8:t=fill")
                elif zone == "left":
                    vf_parts.append("drawbox=x=0:y=0:w=200:h=ih:color=black@0.8:t=fill")
                elif zone == "right":
                    vf_parts.append("drawbox=x=iw-200:y=0:w=200:h=ih:color=black@0.8:t=fill")
                elif zone == "topleft":
                    vf_parts.append("drawbox=x=0:y=0:w=200:h=150:color=black@0.8:t=fill")
                elif zone == "topright":
                    vf_parts.append("drawbox=x=iw-200:y=0:w=200:h=150:color=black@0.8:t=fill")
                elif zone == "bottomleft":
                    vf_parts.append("drawbox=x=0:y=ih-150:w=200:h=150:color=black@0.8:t=fill")
                elif zone == "bottomright":
                    vf_parts.append("drawbox=x=iw-200:y=ih-150:w=200:h=150:color=black@0.8:t=fill")
                elif zone == "blur_top":
                    vf_parts.append("gblur=sigma=20:enable='lt(y,150)'")
                elif zone == "blur_bottom":
                    vf_parts.append("gblur=sigma=20:enable='gt(y,ih-150)'")
        
        # 4. Filtros anti-reutilización: micro-ajustes de color, espejo aleatorio
        vf_parts.append("eq=contrast=1.02:brightness=0.01:saturation=1.05")
        
        vf = ",".join(vf_parts)
        
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            str(output_path)
        ]
        self._run_ffmpeg(cmd, "Smart Crop 9:16")
        return output_path

    def remove_audio(self, input_path: Path, output_path: Path) -> Path:
        """Elimina audio original completamente."""
        self._emit(2, 5, "Eliminando audio original...")
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-an", "-c:v", "copy", str(output_path)
        ]
        self._run_ffmpeg(cmd, "Remove Audio")
        return output_path

    def apply_visual_dynamism(self, input_path: Path, output_path: Path,
                              mirror: bool = False,
                              reorder_scenes: bool = False,
                              scene_duration: float = 3.0) -> Path:
        """
        Aplica dinamismo visual anti-copyright:
        - Micro-zoom Ken Burns
        - Espejo horizontal opcional
        - Reordenamiento de escenas
        - Ajustes sutiles de color
        """
        self._emit(2, 5, "Aplicando dinamismo visual anti-copyright...")
        
        vf_parts = []
        
        # Ken Burns suave
        vf_parts.append(
            "zoompan=z='min(1.02+0.03*on/180,1.05)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=180:s=1080x1920:fps=30"
        )
        
        # Espejo horizontal si se pide
        if mirror:
            vf_parts.append("hflip")
        
        # Ajustes de color sutiles (anti-huella digital)
        vf_parts.append("eq=contrast=1.015:brightness=0.005:saturation=1.03:gamma=1.01")
        
        # Ruido muy sutil para romper matching de contenido
        vf_parts.append("noise=alls=2:allf=t+u")
        
        vf = ",".join(vf_parts)
        
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy" if not mirror else "aac", "-b:a", "128k",
            str(output_path)
        ]
        self._run_ffmpeg(cmd, "Visual Dynamism")
        return output_path

    def concat_clips(self, clip_paths: List[Path], output_path: Path, 
                     target_duration: float = None) -> Path:
        """Concatena múltiples clips con transiciones suaves."""
        self._emit(2, 5, f"Concatenando {len(clip_paths)} clips...")
        
        # Crear lista de archivos para concat demuxer
        list_file = self.temp_dir / "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                f.write(f"file '{clip.resolve()}'\n")
        
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        ]
        
        if target_duration:
            cmd.extend(["-t", str(target_duration)])
            
        cmd.append(str(output_path))
        self._run_ffmpeg(cmd, "Concat Clips")
        return output_path

    def burn_subtitles_ass(self, video_path: Path, ass_path: Path, output_path: Path) -> Path:
        """Quema subtítulos .ass en el video (Windows-safe paths)."""
        self._emit(4, 5, "Quemando subtítulos animados .ass...")
        
        # En Windows, las rutas en filter_complex necesitan escaping especial
        ass_str = str(ass_path.resolve()).replace("\\", "\\\\").replace(":", "\\:")
        
        vf = f"ass='{ass_str}'"
        
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path)
        ]
        self._run_ffmpeg(cmd, "Burn Subtitles")
        return output_path

    def add_watermark(self, video_path: Path, output_path: Path, 
                      text: str = "@AutoViralStudio", position: str = "bottom-right") -> Path:
        """Añade marca de agua de texto semitransparente."""
        self._emit(5, 5, "Añadiendo marca de agua...")
        
        pos_map = {
            "top-left": "x=12:y=12",
            "top-right": "x=w-tw-12:y=12",
            "bottom-left": "x=12:y=h-th-12",
            "bottom-right": "x=w-tw-12:y=h-th-12",
            "center": "x=(w-tw)/2:y=(h-th)/2"
        }
        
        pos = pos_map.get(position, pos_map["bottom-right"])
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if not Path(font).exists():
            font = "C:/Windows/Fonts/arialbd.ttf"
        
        vf = (
            f"drawtext=fontfile={font}:text='{text}':fontsize=28:"
            f"fontcolor=white@0.7:{pos}:box=1:boxcolor=black@0.3:boxborderw=8"
        )
        
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path)
        ]
        self._run_ffmpeg(cmd, "Watermark")
        return output_path

    def render_final(self, video_path: Path, audio_path: Path, output_path: Path,
                     target_duration: float = None) -> Path:
        """Mezcla video final con audio (voz + música) y renderiza MP4 final."""
        self._emit(5, 5, "Renderizando video final...")
        
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-shortest"
        ]
        
        if target_duration:
            cmd.extend(["-t", str(target_duration)])
            
        cmd.append(str(output_path))
        self._run_ffmpeg(cmd, "Final Render")
        return output_path

    def cleanup_temp(self):
        """Limpia archivos temporales."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


def process_video_pipeline(input_path: Path, output_dir: Path, config: Dict, 
                           socketio=None, task_id: str = None) -> Path:
    """
    Pipeline completo de procesamiento de video.
    config debe contener:
    - mode: 'story' | 'summary' | 'compilation'
    - remove_audio: bool
    - smart_crop: bool
    - zoom_range: (float, float)
    - blur_zones: list
    - visual_dynamism: bool
    - mirror: bool
    - scene_duration: float
    - target_duration: float
    - subtitles_ass: Path (opcional)
    - audio_path: Path (voz + música ya mezclada)
    - watermark_text: str
    """
    processor = VideoProcessor(output_dir, socketio, task_id)
    
    try:
        # Fase 1: Análisis
        processor._emit(1, 5, "Fase 1/5: Analizando video de entrada...")
        info = processor.get_video_info(input_path)
        
        # Fase 2: Limpieza y transformación visual
        processor._emit(2, 5, "Fase 2/5: Limpiando video y aplicando transformaciones anti-copyright...")
        
        current_video = input_path
        stage = 0
        
        # 2a. Eliminar audio original si se pide
        if config.get("remove_audio", True):
            stage += 1
            no_audio = processor.temp_dir / f"stage{stage}_noaudio.mp4"
            processor.remove_audio(current_video, no_audio)
            current_video = no_audio
        
        # 2b. Smart Crop 9:16
        if config.get("smart_crop", True):
            stage += 1
            cropped = processor.temp_dir / f"stage{stage}_cropped.mp4"
            processor.smart_crop_9_16(
                current_video, cropped,
                zoom_range=config.get("zoom_range", (1.05, 1.35)),
                blur_zones=config.get("blur_zones", [])
            )
            current_video = cropped
        else:
            # Al menos forzar 9:16
            stage += 1
            forced = processor.temp_dir / f"stage{stage}_forced916.mp4"
            processor.smart_crop_9_16(current_video, forced, zoom_range=(1.0, 1.0), blur_zones=[])
            current_video = forced
        
        # 2c. Dinamismo visual
        if config.get("visual_dynamism", True):
            stage += 1
            dynamic = processor.temp_dir / f"stage{stage}_dynamic.mp4"
            processor.apply_visual_dynamism(
                current_video, dynamic,
                mirror=config.get("mirror", False),
                reorder_scenes=config.get("reorder_scenes", False),
                scene_duration=config.get("scene_duration", 3.0)
            )
            current_video = dynamic
        
        # Fase 3: Si hay múltiples clips, concatenar
        if isinstance(input_path, list) and len(input_path) > 1:
            stage += 1
            concat = processor.temp_dir / f"stage{stage}_concat.mp4"
            processor.concat_clips(input_path, concat, config.get("target_duration"))
            current_video = concat
        
        # Fase 4: Quemar subtítulos si existen
        if config.get("subtitles_ass") and Path(config["subtitles_ass"]).exists():
            stage += 1
            with_subs = processor.temp_dir / f"stage{stage}_subs.mp4"
            processor.burn_subtitles_ass(current_video, Path(config["subtitles_ass"]), with_subs)
            current_video = with_subs
        
        # Fase 5: Marca de agua + render final con audio
        if config.get("watermark_text"):
            stage += 1
            watermarked = processor.temp_dir / f"stage{stage}_wm.mp4"
            processor.add_watermark(current_video, watermarked, config["watermark_text"])
            current_video = watermarked
        
        # Render final con audio
        final_output = output_dir / f"final_{Path(input_path).stem}.mp4"
        processor.render_final(
            current_video, 
            Path(config["audio_path"]), 
            final_output,
            config.get("target_duration")
        )
        
        processor._emit(5, 5, "✅ ¡Video completado!", 100)
        return final_output
        
    finally:
        processor.cleanup_temp()