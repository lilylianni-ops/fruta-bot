"""
Generador de guiones estilo '¿Sabías que...?' con ganchos de retención, 
plantillas inteligentes offline y soporte para LLM (Ollama/OpenAI/Gemini).
"""
import os
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class ScriptMode(Enum):
    STORY = "story"              # ¿Sabías que...? Historia completa
    FACTS = "facts"              # Curiosidades rápidas
    COMPILATION = "compilation"  # Compilación de clips


class ScriptTone(Enum):
    CASUAL = "casual"           # Amigable, cercano
    DRAMATIC = "dramatic"       # Telenovela, suspenso
    EDUCATIONAL = "educational" # Informativo, autoridad
    VIRAL = "viral"             # Clickbait ético, energía alta
    MYSTERIOUS = "mysterious"   # Misterio, intriga


@dataclass
class ScriptSegment:
    """Segmento individual del guión."""
    text: str
    duration_estimate: float  # segundos
    visual_cue: str = ""      # Qué mostrar en pantalla
    b_roll_keywords: List[str] = None  # Palabras clave para buscar b-roll
    
    def __post_init__(self):
        if self.b_roll_keywords is None:
            self.b_roll_keywords = []


@dataclass
class GeneratedScript:
    """Guión completo generado."""
    title: str
    hook: str
    segments: List[ScriptSegment]
    cta: str
    total_duration_estimate: float
    mode: ScriptMode
    tone: ScriptTone
    language: str
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def full_text(self) -> str:
        """Texto completo para TTS."""
        parts = [self.hook]
        for seg in self.segments:
            parts.append(seg.text)
        parts.append(self.cta)
        return " ".join(parts)
    
    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "hook": self.hook,
            "segments": [asdict(s) for s in self.segments],
            "cta": self.cta,
            "total_duration_estimate": self.total_duration_estimate,
            "mode": self.mode.value,
            "tone": self.tone.value,
            "language": self.language,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GeneratedScript':
        segments = [ScriptSegment(**s) for s in data.get("segments", [])]
        return cls(
            title=data["title"],
            hook=data["hook"],
            segments=segments,
            cta=data["cta"],
            total_duration_estimate=data["total_duration_estimate"],
            mode=ScriptMode(data["mode"]),
            tone=ScriptTone(data["tone"]),
            language=data["language"],
            metadata=data.get("metadata", {})
        )


class ScriptWriter:
    """Generador de guiones con plantillas y LLM opcional."""
    
    # Plantillas de ganchos por modo y tono
    HOOK_TEMPLATES = {
        (ScriptMode.STORY, ScriptTone.VIRAL): [
            "¿Sabías que {topic} oculta un secreto que cambió todo?",
            "Nadie te contó la verdad sobre {topic}... hasta hoy.",
            "Esto es lo que pasa cuando {topic} y por qué te importa.",
            "El descubrimiento sobre {topic} que los expertos ocultaron.",
        ],
        (ScriptMode.STORY, ScriptTone.DRAMATIC): [
            "En las sombras de {topic} acecha algo inesperado...",
            "Una historia de {topic} que parece mentira, pero es real.",
            "Lo que descubrirás sobre {topic} te quitará el sueño.",
        ],
        (ScriptMode.STORY, ScriptTone.EDUCATIONAL): [
            "La ciencia detrás de {topic} te va a sorprender.",
            "¿Qué pasa realmente con {topic}? La respuesta te va a impactar.",
            "Entender {topic} cambia tu forma de ver el mundo.",
        ],
        (ScriptMode.STORY, ScriptTone.MYSTERIOUS): [
            "Hay algo en {topic} que nadie explica...",
            "Un enigma sobre {topic} que lleva décadas sin resolver.",
            "Las pistas sobre {topic} apuntan a algo imposible.",
        ],
        (ScriptMode.FACTS, ScriptTone.VIRAL): [
            "3 cosas sobre {topic} que NO sabías (la #2 te va a volar la cabeza)",
            "Datos curiosos de {topic} que parecen falsos pero son 100% reales",
            "{number} secretos de {topic} que te harán el más listo de la sala",
        ],
        (ScriptMode.FACTS, ScriptTone.EDUCATIONAL): [
            "{number} hechos fascinantes sobre {topic} explicados en 60 segundos",
            "Lo que la escuela nunca te enseñó sobre {topic}",
            "La verdad científica sobre {topic} en {number} puntos",
        ],
        (ScriptMode.COMPILATION, ScriptTone.VIRAL): [
            "Los mejores momentos de {topic} que tienes que ver",
            "Esto es {topic} como nunca lo habías visto",
            "Top {number} clips de {topic} que rompen internet",
        ],
    }
    
    # Cierres / Call to Action
    CTA_TEMPLATES = {
        ScriptTone.VIRAL: [
            "Sígueme para más secretos como este 👉",
            "Comenta 'SÍ' si te sorprendió y comparte con quien necesite saber esto",
            "Dale like si aprendiste algo nuevo hoy 🔥",
        ],
        ScriptTone.EDUCATIONAL: [
            "Suscríbete para más contenido educativo como este",
            "¿Quieres saber más? Déjame tu pregunta en comentarios",
            "Activa la campanita para no perderte el próximo video",
        ],
        ScriptTone.DRAMATIC: [
            "La historia continúa... ¿quieres saber el final? Sígueme",
            "Esto no termina aquí. Dale a seguir para la parte 2",
            "El misterio sigue. ¿Te atreves a descubrir más?",
        ],
        ScriptTone.CASUAL: [
            "Si te gustó, dale like y suscríbete 😊",
            "Cuéntame en comentarios qué opinas",
            "Nos vemos en el próximo video, ¡chao!",
        ],
    }
    
    # Transiciones entre segmentos
    TRANSITIONS = {
        ScriptTone.VIRAL: ["Pero espera, hay más...", "Y eso no es todo...", "Aquí viene lo bueno...", "Pero lo CRAZY es esto..."],
        ScriptTone.DRAMATIC: ["Sin embargo...", "Pero la verdad es más oscura...", "Lo que sigue te helará la sangre...", "Y entonces pasó lo impensable..."],
        ScriptTone.EDUCATIONAL: ["Además...", "Por otro lado...", "Lo interesante es...", "Los estudios revelan..."],
        ScriptTone.MYSTERIOUS: ["Pero hay una pista más...", "Y aquí es donde se pone extraño...", "Lo que nadie te dice...", "La siguiente pieza del rompecabezas..."],
        ScriptTone.CASUAL: ["También...", "Por cierto...", "Dato curioso...", "Mira esto..."],
    }
    
    # Temas predefinidos para GTA 6 (ejemplo solicitado)
    GTA6_TOPICS = [
        {"topic": "GTA 6", "subtopics": [
            "el mapa de Vice City es 3 veces más grande que GTA 5",
            "podrás entrar a TODOS los edificios por primera vez",
            "la IA de los NPCs recuerda lo que haces y reacciona días después",
            "el sistema de clima afecta la jugabilidad real (lluvia, huracanes)",
            "habrá dos protagonistas jugables estilo Bonnie & Clyde",
            "el modo online se lanza separado y gratis",
            "Rockstar tardó 10 años y $2 billones en desarrollarlo",
            "los gráficos usan ray tracing en tiempo real en consolas",
            "la economía del juego es dinámica: precios suben/bajan según jugadores",
            "habrá más de 500 canciones licenciadas en la radio",
        ]},
    ]
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.llm_provider = self.config.get("llm_provider", "offline")  # offline, ollama, openai, gemini
        self.llm_config = self.config.get("llm", {})
        self.language = self.config.get("language", "es")
        
        # Cargar plantillas personalizadas si existen
        self.custom_templates_path = Path(self.config.get("templates_path", "templates/scripts"))
        self.custom_templates_path.mkdir(parents=True, exist_ok=True)
    
    def generate(self, topic: str, mode: ScriptMode = ScriptMode.STORY,
                 tone: ScriptTone = ScriptTone.VIRAL,
                 target_duration: int = 60,
                 num_segments: int = None,
                 custom_data: Dict = None) -> GeneratedScript:
        """
        Genera un guión completo.
        
        Args:
            topic: Tema principal (ej. "GTA 6")
            mode: Modo de guión (STORY, FACTS, COMPILATION)
            tone: Tono (VIRAL, DRAMATIC, EDUCATIONAL, MYSTERIOUS, CASUAL)
            target_duration: Duración objetivo en segundos
            num_segments: Número de segmentos (auto si None)
            custom_data: Datos extra para inyectar en plantillas
        """
        # Intentar LLM primero si está configurado
        if self.llm_provider != "offline":
            script = self._generate_with_llm(topic, mode, tone, target_duration, custom_data)
            if script:
                return script
        
        # Fallback a plantillas offline
        return self._generate_offline(topic, mode, tone, target_duration, num_segments, custom_data)
    
    def _generate_offline(self, topic: str, mode: ScriptMode, tone: ScriptTone,
                          target_duration: int, num_segments: int,
                          custom_data: Dict) -> GeneratedScript:
        """Genera guión usando plantillas inteligentes offline."""
        
        # Obtener datos del tema
        topic_data = custom_data or self._get_topic_data(topic)
        subtopics = topic_data.get("subtopics", [f"aspecto {i+1} de {topic}" for i in range(5)])
        
        # Calcular segmentos
        if num_segments is None:
            # ~10-15 seg por segmento + hook + CTA
            num_segments = max(3, min(8, target_duration // 12))
        
        # Seleccionar subtopics
        selected_subtopics = random.sample(subtopics, min(num_segments, len(subtopics)))
        
        # Gancho
        hook = self._select_hook(topic, mode, tone, topic_data)
        
        # Segmentos
        segments = []
        transitions = self.TRANSITIONS.get(tone, self.TRANSITIONS[ScriptTone.VIRAL])
        duration_per_segment = (target_duration - 8) / num_segments  # -8 para hook+CTA
        
        for i, subtopic in enumerate(selected_subtopics):
            text = self._build_segment_text(subtopic, mode, tone, i, transitions)
            visual_cue = self._suggest_visual(subtopic, mode)
            b_roll = self._extract_keywords(subtopic)
            
            segments.append(ScriptSegment(
                text=text,
                duration_estimate=duration_per_segment,
                visual_cue=visual_cue,
                b_roll_keywords=b_roll
            ))
        
        # CTA
        cta = random.choice(self.CTA_TEMPLATES.get(tone, self.CTA_TEMPLATES[ScriptTone.VIRAL]))
        
        total_duration = sum(s.duration_estimate for s in segments) + 8
        
        return GeneratedScript(
            title=self._generate_title(topic, mode, tone),
            hook=hook,
            segments=segments,
            cta=cta,
            total_duration_estimate=total_duration,
            mode=mode,
            tone=tone,
            language=self.language,
            metadata={
                "topic": topic,
                "subtopics_used": selected_subtopics,
                "generator": "offline_templates"
            }
        )
    
    def _get_topic_data(self, topic: str) -> Dict:
        """Obtiene datos estructurados del tema."""
        topic_lower = topic.lower()
        
        # Buscar en temas predefinidos
        for t in self.GTA6_TOPICS:
            if t["topic"].lower() in topic_lower or topic_lower in t["topic"].lower():
                return t
        
        # Generar genérico
        return {
            "topic": topic,
            "subtopics": [
                f"la historia secreta de {topic}",
                f"cómo funciona realmente {topic}",
                f"el impacto de {topic} en la industria",
                f"lo que viene para {topic} en el futuro",
                f"datos que nadie sabe sobre {topic}",
            ]
        }
    
    def _select_hook(self, topic: str, mode: ScriptMode, tone: ScriptTone, topic_data: Dict) -> str:
        """Selecciona y rellena un gancho."""
        templates = self.HOOK_TEMPLATES.get((mode, tone), 
                  self.HOOK_TEMPLATES.get((ScriptMode.STORY, ScriptTone.VIRAL)))
        
        template = random.choice(templates)
        
        # Rellenar placeholders
        number = random.randint(3, 7)
        subtopic = random.choice(topic_data.get("subtopics", [topic]))
        
        return template.format(
            topic=topic,
            subtopic=subtopic,
            number=number
        )
    
    def _build_segment_text(self, subtopic: str, mode: ScriptMode, tone: ScriptTone,
                            index: int, transitions: List[str]) -> str:
        """Construye el texto de un segmento."""
        starters = [
            "",  # Primer segmento sin transición
            random.choice(transitions),
            random.choice(transitions),
            "Además, ",
            "Lo increíble es que ",
        ]
        
        starter = starters[min(index, len(starters)-1)]
        
        # Plantillas por modo
        if mode == ScriptMode.STORY:
            templates = [
                f"{starter}{subtopic}.",
                f"{starter}Descubrieron que {subtopic.lower()}.",
                f"{starter}Lo que pasó con {subtopic.lower()} cambió las reglas del juego.",
            ]
        elif mode == ScriptMode.FACTS:
            templates = [
                f"{starter}Dato: {subtopic}.",
                f"{starter}¿Sabías que {subtopic.lower()}?",
                f"{starter}Hecho confirmado: {subtopic}.",
            ]
        else:  # COMPILATION
            templates = [
                f"{starter}Mira esto: {subtopic}.",
                f"{starter}Este clip muestra {subtopic.lower()}.",
                f"{starter}Impresionante: {subtopic}.",
            ]
        
        return random.choice(templates)
    
    def _suggest_visual(self, subtopic: str, mode: ScriptMode) -> str:
        """Sugiere qué mostrar en pantalla."""
        visuals = [
            "Gameplay cinemático",
            "Mapa del juego",
            "Interfaz de usuario",
            "Personajes en acción",
            "Entorno detallado",
            "Comparativa gráfica",
            "Detalle de física",
            "Sistema de clima",
        ]
        return random.choice(visuals)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extrae palabras clave para búsqueda de b-roll."""
        # Palabras clave comunes en gaming
        keywords = []
        gaming_terms = ["gta", "vice city", "gameplay", "mapa", "personaje", "misión", 
                       "coche", "arma", "ciudad", "online", "gráficos", "fps", "ray tracing",
                       "npc", "ia", "clima", "edificio", "interior", "radio", "música"]
        
        text_lower = text.lower()
        for term in gaming_terms:
            if term in text_lower:
                keywords.append(term)
        
        # Añadir sustantivos principales
        words = re.findall(r'\b\w{4,}\b', text_lower)
        keywords.extend([w for w in words if w not in keywords][:3])
        
        return list(set(keywords))[:5]
    
    def _generate_title(self, topic: str, mode: ScriptMode, tone: ScriptTone) -> str:
        """Genera título atractivo."""
        if mode == ScriptMode.FACTS:
            return f"{random.randint(3,7)} Secretos de {topic} Que NADIE Te Contó"
        elif mode == ScriptMode.STORY:
            prefixes = ["La Verdad Oculta de", "Lo Que Nadie Te Dice Sobre", "El Secreto de", "Descubrí Que"]
            return f"{random.choice(prefixes)} {topic}"
        else:
            return f"Lo Mejor de {topic} - Compilación Épica"
    
    def _generate_with_llm(self, topic: str, mode: ScriptMode, tone: ScriptTone,
                           target_duration: int, custom_data: Dict) -> Optional[GeneratedScript]:
        """Intenta generar con LLM (Ollama/OpenAI/Gemini)."""
        try:
            if self.llm_provider == "ollama":
                return self._generate_ollama(topic, mode, tone, target_duration, custom_data)
            elif self.llm_provider == "openai":
                return self._generate_openai(topic, mode, tone, target_duration, custom_data)
            elif self.llm_provider == "gemini":
                return self._generate_gemini(topic, mode, tone, target_duration, custom_data)
        except Exception as e:
            print(f"[ScriptWriter] LLM falló ({self.llm_provider}): {e}, usando offline...")
        return None
    
    def _generate_ollama(self, topic: str, mode: ScriptMode, tone: ScriptTone,
                         target_duration: int, custom_data: Dict) -> GeneratedScript:
        """Genera con Ollama local."""
        import requests
        
        model = self.llm_config.get("model", "llama3.1:8b")
        url = self.llm_config.get("url", "http://localhost:11434/api/generate")
        
        prompt = self._build_llm_prompt(topic, mode, tone, target_duration, custom_data)
        
        response = requests.post(url, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.8, "top_p": 0.9}
        }, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            return self._parse_llm_response(data.get("response", "{}"), topic, mode, tone)
        raise RuntimeError(f"Ollama error: {response.status_code}")
    
    def _generate_openai(self, topic: str, mode: ScriptMode, tone: ScriptTone,
                         target_duration: int, custom_data: Dict) -> GeneratedScript:
        """Genera con API OpenAI-compatible."""
        from openai import OpenAI
        
        client = OpenAI(
            api_key=self.llm_config.get("api_key"),
            base_url=self.llm_config.get("base_url", "https://api.openai.com/v1")
        )
        
        prompt = self._build_llm_prompt(topic, mode, tone, target_duration, custom_data)
        
        response = client.chat.completions.create(
            model=self.llm_config.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Eres un guionista experto en videos virales tipo '¿Sabías que...?'. Responde SOLO JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            response_format={"type": "json_object"}
        )
        
        return self._parse_llm_response(response.choices[0].message.content, topic, mode, tone)
    
    def _generate_gemini(self, topic: str, mode: ScriptMode, tone: ScriptTone,
                         target_duration: int, custom_data: Dict) -> GeneratedScript:
        """Genera con Gemini API."""
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=self.llm_config.get("api_key"))
        model = self.llm_config.get("model", "gemini-1.5-flash")
        
        prompt = self._build_llm_prompt(topic, mode, tone, target_duration, custom_data)
        
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.8
            )
        )
        
        return self._parse_llm_response(response.text, topic, mode, tone)
    
    def _build_llm_prompt(self, topic: str, mode: ScriptMode, tone: ScriptTone,
                          target_duration: int, custom_data: Dict) -> str:
        """Construye prompt para LLM."""
        tone_desc = {
            ScriptTone.VIRAL: "energético, clickbait ético, retención máxima",
            ScriptTone.DRAMATIC: "suspenso, telenovela, misterio, emocional",
            ScriptTone.EDUCATIONAL: "autoridad, claro, informativo, estructurado",
            ScriptTone.MYSTERIOUS: "intriga, enigmático, sugerente, atmosférico",
            ScriptTone.CASUAL: "amigable, conversacional, cercano, natural",
        }
        
        mode_desc = {
            ScriptMode.STORY: "historia narrativa con gancho, desarrollo y cliffhanger",
            ScriptMode.FACTS: "lista de curiosidades rápidas (3-7 datos) con gancho inicial",
            ScriptMode.COMPILATION: "introducción a clips virales con contexto y reacciones",
        }
        
        return f"""
Genera un guión para video vertical (Shorts/Reels/TikTok) de {target_duration} segundos.

TEMA: {topic}
MODO: {mode.value} - {mode_desc[mode]}
TONO: {tone.value} - {tone_desc[tone]}
IDIOMA: {self.language}

ESTRUCTURA REQUERIDA (JSON):
{{
  "title": "Título viral < 60 chars",
  "hook": "Primera frase gancho (< 10 palabras, impacto inmediato)",
  "segments": [
    {{"text": "Texto narrado segmento 1", "visual_cue": "Qué mostrar", "b_roll_keywords": ["kw1", "kw2"]}},
    ...
  ],
  "cta": "Call to action final",
  "total_duration_estimate": {target_duration}
}}

REGLAS:
- Segmentos: 3-7, cada uno 8-15 seg de narración
- Gancho: pregunta, secreto, contradicción o promesa
- Transiciones naturales entre segmentos
- CTA: seguir, comentar, like, compartir
- Keywords para b-roll: términos visuales concretos
- SOLO JSON, sin markdown, sin explicaciones
"""
    
    def _parse_llm_response(self, response: str, topic: str, mode: ScriptMode, tone: ScriptTone) -> GeneratedScript:
        """Parsea respuesta JSON del LLM."""
        import re
        
        # Extraer JSON
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No se encontró JSON en respuesta")
        
        data = json.loads(match.group(0))
        
        segments = []
        for s in data.get("segments", []):
            segments.append(ScriptSegment(
                text=s.get("text", ""),
                duration_estimate=10.0,  # Default, se ajusta después
                visual_cue=s.get("visual_cue", ""),
                b_roll_keywords=s.get("b_roll_keywords", [])
            ))
        
        # Recalcular duraciones
        total_segments = len(segments)
        if total_segments > 0:
            per_seg = (data.get("total_duration_estimate", 60) - 8) / total_segments
            for s in segments:
                s.duration_estimate = per_seg
        
        return GeneratedScript(
            title=data.get("title", f"Video sobre {topic}"),
            hook=data.get("hook", f"¿Sabías que {topic}...?"),
            segments=segments,
            cta=data.get("cta", "¡Sígueme para más!"),
            total_duration_estimate=data.get("total_duration_estimate", 60),
            mode=mode,
            tone=tone,
            language=self.language,
            metadata={"generator": f"llm_{self.llm_provider}", "raw_response": response[:500]}
        )
    
    def save_script(self, script: GeneratedScript, path: Path) -> Path:
        """Guarda guión en JSON."""
        path.write_text(json.dumps(script.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    
    def load_script(self, path: Path) -> GeneratedScript:
        """Carga guión desde JSON."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return GeneratedScript.from_dict(data)


# Función de conveniencia para uso directo
def quick_script(topic: str, mode: str = "story", tone: str = "viral",
                 duration: int = 60, llm: str = "offline") -> GeneratedScript:
    """Genera guión rápido con parámetros simples."""
    config = {"llm_provider": llm}
    writer = ScriptWriter(config)
    return writer.generate(
        topic=topic,
        mode=ScriptMode(mode),
        tone=ScriptTone(tone),
        target_duration=duration
    )


if __name__ == "__main__":
    # Test rápido
    writer = ScriptWriter({"llm_provider": "offline"})
    
    print("=== TEST GTA 6 STORY VIRAL ===")
    script = writer.generate("GTA 6", ScriptMode.STORY, ScriptTone.VIRAL, 60)
    print(f"Título: {script.title}")
    print(f"Gancho: {script.hook}")
    for i, seg in enumerate(script.segments):
        print(f"  {i+1}. [{seg.duration_estimate:.1f}s] {seg.text} | Visual: {seg.visual_cue} | B-roll: {seg.b_roll_keywords}")
    print(f"CTA: {script.cta}")
    print(f"Duración total: {script.total_duration_estimate:.1f}s")
    
    print("\n=== TEST FACTS EDUCATIONAL ===")
    script2 = writer.generate("GTA 6", ScriptMode.FACTS, ScriptTone.EDUCATIONAL, 45)
    print(f"Título: {script2.title}")
    print(f"Gancho: {script2.hook}")
    for i, seg in enumerate(script2.segments):
        print(f"  {i+1}. [{seg.duration_estimate:.1f}s] {seg.text}")
    print(f"CTA: {script2.cta}")