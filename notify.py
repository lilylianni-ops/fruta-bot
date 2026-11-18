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


def updates(offset):
    if not enabled():
        return []
    try:
        r = requests.get(_api("getUpdates"), params={"offset": offset, "timeout": 0}, timeout=20)
        return r.json().get("result", [])
    except Exception:
        return []
