import os
from pathlib import Path
from google import genai
from store import *
import video

IMG_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview",
    "gemini-2.0-flash-preview-image-generation",
]


def _gen_image(prompt, out_png):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    last = None
    for model in IMG_MODELS:
        try:
            r = client.models.generate_content(model=model, contents=prompt)
            for cand in r.candidates or []:
                for part in cand.content.parts or []:
                    data = getattr(getattr(part, "inline_data", None), "data", None)
                    if data:
                        Path(out_png).write_bytes(data)
                        return model
            last = RuntimeError(f"{model}: no devolvio imagen")
        except Exception as e:
            last = e
            if "429" in str(e).lower() or "404" in str(e).lower() or "not found" in str(e).lower():
                continue
            break
    raise last


def _clip_from_image(png, out_mp4, secs=6):
    vf = ("scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
          "zoompan=z='min(1+0.10*on/180,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,"
          "format=yuv420p")
    video._run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-t", str(secs), "-i", str(png),
                "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-an", str(out_mp4)], png.parent)


def ensure_clips(n):
    e = ep_load(n)
    if not e:
        return
    d = ep_dir(n)
    clips_dir = d / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    need = len(e["narration"])
    prompts = e.get("clips", [])
    have = len(video.find_clips(n))
    made = 0
    for i in range(have, min(need, len(prompts))):
        png = d / f"img{i + 1}.png"
        mp4 = clips_dir / f"clip{i + 1}.mp4"
        _gen_image(prompts[i], png)
        _clip_from_image(png, mp4)
        png.unlink(missing_ok=True)
        made += 1
        print(f"clip {i + 1}/{need} listo", flush=True)
    return made
