import asyncio, re, subprocess
import edge_tts
from store import *


def _dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("ffmpeg: " + r.stderr[-400:])


def _t(t):
    return f"{int(t // 3600):02}:{int(t % 3600 // 60):02}:{t % 60:06.3f}".replace(".", ",")


def find_clips(n):
    d = ep_dir(n) / "clips"
    d.mkdir(parents=True, exist_ok=True)
    fs = [f for f in d.iterdir() if f.suffix.lower() in (".mp4", ".mov", ".webm")]
    return sorted(fs, key=lambda f: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", f.name)])


def assemble(n):
    c, e, d = cfg(), ep_load(n), ep_dir(n)
    clips = find_clips(n)[: len(e["narration"])]
    srt, concat, t = [], [], 0.0
    for i, (clip, line) in enumerate(zip(clips, e["narration"]), 1):
        audio, seg = f"a{i}.mp3", f"seg{i}.mp4"
        asyncio.run(edge_tts.Communicate(line, c["voice"], rate=c.get("voice_rate", "+0%")).save(str(d / audio)))
        L = max(_dur(d / audio) + 0.25, 3.0)
        vf = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,"
              "tpad=stop_mode=clone:stop_duration=10[v];[1:a]apad[a]")
        _run(["ffmpeg", "-y", "-i", str(clip.resolve()), "-i", audio, "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
              "-t", f"{L:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", seg], d)
        srt.append(f"{i}\n{_t(t)} --> {_t(t + L - 0.1)}\n{line}\n")
        concat.append(f"file '{seg}'")
        t += L
    (d / "subs.srt").write_text("\n".join(srt), encoding="utf-8")
    (d / "list.txt").write_text("\n".join(concat), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "joined.mp4"], d)
    style = "FontSize=16,Alignment=2,MarginV=220,Outline=3,Bold=1"
    name = "".join(ch for ch in c.get("channel_name", "") if ch not in ":,'\\%")
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    wm = (f",drawtext=fontfile={font}:text='{name}':fontsize=15:fontcolor=white@0.55:x=12:y=12"
          f":box=1:boxcolor=black@0.25:boxborderw=8,"
          f"drawtext=fontfile={font}:text='Suscríbete':fontsize=34:fontcolor=white:"
          f"x=(w-text_w)/2:y=h-text_h-160:box=1:boxcolor=black@0.45:boxborderw=12"
          f":enable='gte(t,{max(t - 3.0, 0):.2f})'")
    _run(["ffmpeg", "-y", "-i", "joined.mp4", "-vf", f"subtitles=subs.srt:force_style='{style}'{wm}",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", "final.mp4"], d)
    return d / "final.mp4", t
