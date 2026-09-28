# alth-meta

Assets 3D en estilo **ALTH-META** (chibi-soft low-poly) para un videojuego en Godot.
Se modelan con scripts de Blender que corren sin interfaz en sesiones de Claude Code en la nube.

| Carpeta | Contenido |
|---|---|
| `spec/alth_spec.json` | Estándar: escala, arquetipos, cotas, conversión real→ALTH, paleta, luz, presupuesto |
| `alth/` | Librería de Blender: escena en mm, materiales, estudio de luz, renders de revisión, exportación GLB |
| `tools/` | `ensure_blender.sh` (instala Blender como módulo de Python), `fase0_cubo.py` (prueba del pipeline), `bucle.py` (ciclo con cualquier IA), `verificar_revision.py` (huellas antes de aprobar), `escala.py` (foto de familia) |
| `chsp-x/` | **CHSP-X**: página de revisión y aprobación de assets (antes "El Taller"). Ver `docs/CHSP-X.md` |
| `assets/<nombre>/` | Especificación, script, .blend, GLB y render final de cada asset aprobado |
| `refs/` | Referencias visuales: personajes, escenas e infografías |
| `data/medidas.csv` | Registro que recalibra los factores de conversión |

## Prueba rápida

```bash
bash tools/ensure_blender.sh
alth-python tools/fase0_cubo.py
```

Exporta a Godot como GLB con la raíz ×0.01: el personaje estándar (95 mm de maqueta) mide 0.95 m en el juego.

## Bucle con cualquier IA (sin depender de Claude)

`tools/bucle.py` corre el ciclo *construir → mirar → corregir* con cualquier modelo que hable la API de
OpenAI, o a mano copiando y pegando en un chat gratis. No corre el modo final ni exporta: eso lo apruebas tú.

| Forma | Comando | Costo |
|---|---|---|
| Manual (cualquier chat web) | `python3 tools/bucle.py paquete <asset> --unico` → pegar `prompt.md` + imágenes → `python3 tools/bucle.py aplicar <asset> respuesta.md` | cero |
| Local con Ollama | `python3 tools/bucle.py correr <asset> --proveedor ollama --modelo qwen2.5vl:7b` | cero (tu GPU) |
| API (Gemini, DeepSeek, OpenRouter, Groq) | `GEMINI_API_KEY=… python3 tools/bucle.py correr <asset> --proveedor gemini` | capa gratis o centavos |
| En la nube de GitHub | Actions → **Bucle ALTH** → Run workflow (también desde la app del celular) | cero (repo público) |

- Modelos sin visión reciben números en vez de imágenes: la verificación y la **silueta**
  (`alth/silueta.py`: IoU y ancho por bandas contra la referencia, p. ej. "arriba: 40 % más angosto").
- Opciones por asset en su `spec.json` → `"bucle": {"ref": "refs/…", "recorte": [0,0,0.5,0.5], "vista": "frente", "editables": ["alth/pelo.py"], "nota": "…"}`.
- Cada vuelta queda en `renders/<asset>/bucle/vNN/` y el resumen en `renders/<asset>/bucle/resumen.md`.
- Las reglas que recibe el modelo están en `tools/bucle_sistema.md` + la sección *Convenciones* de `CLAUDE.md`.
- `--unico` (solo en `paquete`) pide **todas** las correcciones en una sola respuesta, cada una con su cota
  numérica y una autocomprobación: pensado para copiar y pegar a mano sin gastar 20 mensajes.
- Aprobar un resultado: CHSP-X o Actions → **Aprobar ALTH** (render final + GLB → `main`).
