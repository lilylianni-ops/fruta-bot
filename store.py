import json, datetime as dt
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
EPS = DATA / "episodes"
EPS.mkdir(parents=True, exist_ok=True)


def jload(path, default):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def jsave(path, obj):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def cfg():
    return jload(ROOT / "config.json", {})


def state():
    s = jload(DATA / "state.json", {})
    s.setdefault("paused", False)
    s.setdefault("slots", {})
    s.setdefault("uploads", {})
    s.setdefault("offset", 0)
    return s


def save_state(s):
    jsave(DATA / "state.json", s)


def today():
    return dt.date.today().isoformat()


def bible():
    default = jload(ROOT / "bible.default.json", {})
    return jload(DATA / "bible.json", default)


def save_bible(b):
    jsave(DATA / "bible.json", b)


def ep_dir(n):
    return EPS / f"ep{n:03d}"


def ep_load(n):
    return jload(ep_dir(n) / "episode.json", None)


def ep_save(e):
    ep_dir(e["n"]).mkdir(parents=True, exist_ok=True)
    jsave(ep_dir(e["n"]) / "episode.json", e)


def ep_list():
    out = []
    for d in sorted(EPS.glob("ep*")):
        e = jload(d / "episode.json", None)
        if e:
            out.append(e)
    return out
