# alth-meta

Assets 3D en estilo **ALTH-META** (chibi-soft low-poly) para un videojuego en Godot.
Se modelan con scripts de Blender que corren sin interfaz en sesiones de Claude Code o GitHub Actions.

| Carpeta | Contenido |
|---|---|
| `spec/alth_spec.json` | Estándar: escala, arquetipos, cotas, conversión real→ALTH, paleta, luz, presupuesto |
| `alth/` | Librería de Blender: escena en mm, materiales, estudio de luz, renders de revisión, exportación GLB |
| `tools/` | `ensure_blender.sh`, herramientas ALTH y el bucle histórico `bucle.py` |
| `copox/` | **COPOX Loop Engine**: videocasetera genérica de torneos, evidencia, auditores, aprendizaje y state branches. Ver `docs/COPOX_LOOP_ENGINE.md` |
| `chsp-x/` | **CHSP-X**: página de revisión y aprobación de assets (antes "El Taller"). Ver `docs/CHSP-X.md` |
| `assets/<nombre>/` | Especificación, script, .blend, GLB y render final de cada asset aprobado |
| `refs/` | Referencias visuales: personajes, escenas e infografías |
| `data/medidas.csv` | Registro que recalibra los factores de conversión |

## Prueba rápida ALTH

```bash
bash tools/ensure_blender.sh
alth-python tools/fase0_cubo.py
```

Exporta a Godot como GLB con la raíz ×0.01: el personaje estándar (95 mm de maqueta) mide 0.95 m en el juego.

## COPOX Loop Engine

COPOX desacopla el proceso iterativo del contenido que se quiere iterar. El engine no sabe si el cassette es Theo, un rig, una textura, una UI o un script.

```text
seed/main → state branch → baseline → candidatos hermanos → ejecutar → capturar → auditar
                                                           │
                                                    unanimidad total
                                                           │
                                                nueva state → reporte
```

Reglas clave:

- 100 % de auditores aplicables deben dar PASS;
- un FAIL jamás se compensa con score;
- candidatos rechazados nunca se convierten en baseline;
- reportes sólo después de unanimidad y con capturas;
- inner loops deterministas y sin APIs de IA por defecto;
- baseline interna por cassette en `copox/state/<id>`, independiente de `main`;
- scheduler preparado para varios cassettes en paralelo, con exclusión por cassette.

La validación real de personaje ALTH está documentada en `docs/COPOX_VALIDATION_2026-09-30.md`.

**COPOX está preparado pero no activado para cassettes productivos:** mientras `copox/cassettes/enabled/` permanezca vacío, el scheduler no modifica Theo, Detective, rigs, UI ni otros assets automáticamente.

## Bucle ALTH histórico con cualquier IA

`tools/bucle.py` sigue disponible durante la migración y corre el ciclo *construir → mirar → corregir* con modelos compatibles o de forma manual. COPOX no lo elimina todavía.

| Forma | Comando | Costo |
|---|---|---|
| Manual (cualquier chat web) | `python3 tools/bucle.py paquete <asset> --unico` → pegar `prompt.md` + imágenes → `python3 tools/bucle.py aplicar <asset> respuesta.md` | cero |
| Local con Ollama | `python3 tools/bucle.py correr <asset> --proveedor ollama --modelo qwen2.5vl:7b` | cero (tu GPU) |
| API (Gemini, DeepSeek, OpenRouter, Groq) | `GEMINI_API_KEY=… python3 tools/bucle.py correr <asset> --proveedor gemini` | depende del proveedor |
| En la nube de GitHub | Actions → **Bucle ALTH** → Run workflow | runners estándar del repo público |

- Modelos sin visión reciben números en vez de imágenes: la verificación y la **silueta** (`alth/silueta.py`) permiten evaluar IoU y ancho por bandas.
- Opciones por asset siguen en su `spec.json` → `"bucle": {...}`.
- Cada vuelta histórica queda en `renders/<asset>/bucle/vNN/`.
- Aprobar por la vía histórica: CHSP-X o Actions → **Aprobar ALTH**.
