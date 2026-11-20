import os, time, requests


def _api(method):
    return f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/{method}"


def enabled():
    return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send(text):
    print(text, flush=True)
    if enabled():
        try:
            requests.post(_api("sendMessage"), data={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": text[:4000]}, timeout=20)
        except Exception as e:
            print("telegram fallo:", e)


def send_video(path, caption=""):
    if not enabled():
        return
    try:
        with open(path, "rb") as f:
            requests.post(_api("sendVideo"), data={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "caption": caption[:900]}, files={"video": f}, timeout=300)
    except Exception as e:
        print("telegram video fallo:", e)


def send_animation(path, caption=""):
    """Manda un GIF/MP4 animado al chat."""
    if not enabled():
        return
    try:
        with open(path, "rb") as f:
            requests.post(_api("sendAnimation"),
                          data={"chat_id": os.getenv("TELEGRAM_CHAT_ID"),
                                "caption": caption[:1000]},
                          files={"animation": f}, timeout=120)
    except Exception as e:
        print("telegram animacion fallo:", e)


def status_gif(title, subtitle="", pct=0):
    """Genera un GIF animado tipo 'pantalla': gradientes de colores moviendose,
    titulo grande, subtitulo y barra de progreso. Devuelve el path o None."""
    try:
        import math
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    W, H, N = 640, 360, 14
    big = small = None
    for name, size in (("arialbd.ttf", 46), ("arial.ttf", 22),
                       ("DejaVuSans-Bold.ttf", 46), ("DejaVuSans.ttf", 22)):
        try:
            f = ImageFont.truetype(name, size)
            if name.endswith("Bold.ttf") or "bd" in name:
                big = big or f
            else:
                small = small or f
        except Exception:
            pass
    big = big or ImageFont.load_default()
    small = small or big

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    frames = []
    for i in range(N):
        t = i / N * 2 * math.pi
        r = (np.sin(xx * 0.018 + t) + np.cos(yy * 0.015 - t * 1.3) + 2) / 4
        g = (np.sin((xx + yy) * 0.014 - t) + 1) / 2
        b = (np.cos(xx * 0.012 - t * 0.7) + np.sin(yy * 0.02 + t) + 2) / 4
        arr = np.stack([r * 255, g * 255, b * 255], axis=-1).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
        shade = Image.new("RGBA", (W, H), (6, 6, 14, 110))
        img.paste(shade, (0, 0), shade)
        d = ImageDraw.Draw(img)
        d.text((W // 2, 118), title[:38], font=big, fill="white", anchor="mm")
        if subtitle:
            d.text((W // 2, 185), subtitle[:60], font=small, fill="#7ef9ff", anchor="mm")
        bw = 460
        bx, by = (W - bw) // 2, 262
        d.rounded_rectangle([bx, by, bx + bw, by + 20], radius=10,
                            fill=(255, 255, 255, 45))
        if pct > 0:
            d.rounded_rectangle([bx, by, bx + bw * pct / 100, by + 20],
                                radius=10, fill=(126, 249, 255, 255))
        frames.append(img)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "status")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"status_{int(time.time())}.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=80, loop=0, optimize=True)
    return path


def card(title, subtitle="", pct=0):
    """Manda la pantalla animada de estado si se pudo generar."""
    try:
        p = status_gif(title, subtitle, pct)
        if p:
            send_animation(p)
    except Exception as e:
        print("status card fallo:", e)


def download_file(file_id, dest):
    """Descarga un archivo enviado al bot (video/document) a `dest`."""
    if not enabled():
        raise RuntimeError("telegram no configurado")
    r = requests.get(_api("getFile"), params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    fpath = r.json()["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{os.getenv('TELEGRAM_TOKEN')}/{fpath}"
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    return dest


def updates(offset):
    if not enabled():
        return []
    try:
        r = requests.get(_api("getUpdates"), params={"offset": offset, "timeout": 0}, timeout=20)
        return r.json().get("result", [])
    except Exception:
        return []
