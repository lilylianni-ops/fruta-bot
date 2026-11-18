import os, json, re, random, difflib, datetime as dt
from google import genai
from google.genai import types
from store import *

HOOKS = [
    "pregunta que duele", "secreto revelado", "cliffhanger inmediato", "traición en el primer segundo",
    "confesión inesperada", "apuesta o reto", "contradicción", "rumor que se riega", "descubrimiento en el colmado",
]


def _candidates(client):
    names = [m.name.split("/")[-1] for m in client.models.list()]
    bad = ("image", "tts", "live", "audio", "embedding", "robotics", "omni", "preview", "exp")
    flash = [n for n in names if "flash" in n and not any(x in n for x in bad)]
    flash.sort(key=lambda n: ("lite" not in n, n), reverse=True)
    return flash


def _gen(prompt, system=None, search=False, as_json=False):
    conf = types.GenerateContentConfig(
        system_instruction=system, max_output_tokens=8192,
        response_mime_type="application/json" if as_json else None,
        tools=[types.Tool(google_search=types.GoogleSearch())] if search else None,
    )
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    model = cfg()["model"]
    models = [model] + [m for m in _candidates(client) if m != model]
    last = None
    for model in models:
        for attempt in (1, 2):
            try:
                r = client.models.generate_content(model=model, contents=prompt, config=conf)
                if model != cfg()["model"]:
                    c = cfg(); c["model"] = model
                    jsave(ROOT / "config.json", c)
                    print("Modelo cambiado a", model, flush=True)
                return r.text or ""
            except Exception as e:
                last = e
                msg = str(e).lower()
                if "429" in msg or "resource_exhausted" in msg or "404" in msg or "not found" in msg:
                    break
                if attempt == 1 and ("503" in msg or "unavailable" in msg):
                    continue
                break
    raise last


def _json(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def refresh_trends():
    c = cfg()
    try:
        txt = _gen(f"Busca qué formatos, temas y ganchos están funcionando hoy en YouTube Shorts para este nicho: {c['niche']}. "
                   "Resume en 6 viñetas cortas y accionables, en español. Incluye solo lo que encontraste.", search=True).strip()
        if txt:
            jsave(DATA / "trends.json", {"date": today(), "text": txt})
    except Exception as e:
        print("tendencias fallo:", e)


def trends_text():
    return jload(DATA / "trends.json", {}).get("text", "(sin tendencias todavía)")


def new_episode():
    c, b = cfg(), bible()
    n = len(ep_list()) + 1
    N = c["clips_per_episode"]
    hook_style = random.choice([h for h in HOOKS if h not in b["used_hooks"][-4:]] or HOOKS)
    system = (
        f"Eres el guionista de una novela corta de frutas para YouTube Shorts, en {c['language']}. "
        "Cada episodio debe ser NUEVO: trama, giro y gancho distintos a los anteriores. Continúa la historia "
        "sin repetir escenas, chistes ni frases. Nada de contenido de odio, sexual explícito ni sobre personas reales. "
        "Responde SOLO con JSON válido."
    )
    user = json.dumps({
        "episodio": n, "mundo": b["setting"], "personajes": b["characters"],
        "episodios_anteriores": b["episodes"][-8:],
        "tendencias_de_hoy": trends_text(), "estilo_de_gancho": hook_style,
        "formato": {
            "title": "máx 60 caracteres, sin #", "hook": "primera frase hablada, máx 10 palabras, golpea en 2 segundos",
            "narration": f"lista de EXACTAMENTE {N} líneas habladas, máx 14 palabras cada una",
            "clips": f"lista de EXACTAMENTE {N} objetos {{prompt}}: escena de 5 segundos, describe los personajes con su aspecto visual completo",
            "summary": "2 frases", "cliffhanger": "1 frase", "description": "2 líneas", "tags": "hasta 8 palabras clave",
        },
    }, ensure_ascii=False)
    feedback = ""
    for _ in range(4):
        try:
            d = _json(_gen(user + feedback, system=system, as_json=True))
        except Exception:
            feedback = "\nTu respuesta anterior no fue JSON válido. Devuelve SOLO el JSON."
            continue
        if len(d.get("narration", [])) != N or len(d.get("clips", [])) != N:
            feedback = f"\nDebe haber EXACTAMENTE {N} líneas de narración y {N} clips."
            continue
        sim = max([difflib.SequenceMatcher(None, d["title"].lower(), t.lower()).ratio() for t in b["used_titles"]] or [0])
        if sim > 0.7:
            feedback = "\nEse título se parece demasiado a uno anterior. Cambia la trama y el título."
            continue
        break
    else:
        raise RuntimeError("No se pudo generar un episodio válido")

    suffix = f" Estilo: {b['style']}. Vertical 9:16, 5 segundos, sin texto en pantalla, sin logos, sin marcas de agua."
    clips = [(x["prompt"] if isinstance(x, dict) else str(x)).strip() + suffix for x in d["clips"]]
    e = {
        "n": n, "title": d["title"][:60], "hook": d["hook"], "narration": d["narration"], "clips": clips,
        "summary": d["summary"], "cliffhanger": d["cliffhanger"], "description": d["description"],
        "tags": d.get("tags", [])[:8], "hook_style": hook_style, "status": "waiting_clips",
        "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    ep_save(e)
    (ep_dir(n) / "clips").mkdir(exist_ok=True)
    (ep_dir(n) / "prompts.txt").write_text(
        "\n\n".join(f"CLIP {i}\n{p}" for i, p in enumerate(clips, 1)), encoding="utf-8")
    b.setdefault("episodes", []).append({"n": n, "title": e["title"], "summary": e["summary"], "cliffhanger": e["cliffhanger"]})
    b["used_titles"].append(e["title"])
    b["used_hooks"].append(hook_style)
    save_bible(b)
    return e
