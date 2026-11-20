import os, requests


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
