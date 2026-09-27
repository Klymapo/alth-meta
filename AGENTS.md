# ALTH-META · instrucciones para cualquier agente de IA

Este archivo es para agentes que no son Claude Code (OpenCode, Aider, Cline/Roo, Codex, Gemini CLI, Goose…).
Las reglas completas están en **`CLAUDE.md`** y aplican igual a cualquier agente: léelo primero.
Responde en español, en tono cercano.

## En corto

- Repo de assets 3D chibi-soft low-poly para un videojuego en Godot. Fuente de verdad: `spec/alth_spec.json`.
- Blender corre **sin interfaz** como módulo de Python: el comando es `alth-python`
  (si no existe: `bash tools/ensure_blender.sh`). Nunca uses `bpy.ops` de interfaz.
- Cada asset vive en `assets/<nombre>/` con `spec.json` (qué es, medidas, colores, cotas) y `build.py`
  (lo construye con la librería `alth/` y termina llamando `alth.revisar(..., asset=spec.json)`).
- `alth-python assets/<nombre>/build.py` deja en `renders/…/iteracion/` la `hoja.png` (4 vistas)
  y `reporte.json` (medidas y verificación).
- 1 unidad = 1 mm, pies en Z=0, frente hacia −Y. Colores solo de la paleta. Tope de vueltas por tipo en `CLAUDE.md`.

## Si tu modelo NO ve imágenes

No pasa nada, hay números:
- `reporte.json` → `verificacion`: cotas (±2 %), triángulos, paleta, piezas flotantes, apoyo en Z=0.
- `python3 tools/bucle.py medir <asset>`: silueta contra la referencia (coincidencia 0–1 y, por bandas de
  altura, cuánto más ancho o angosto es el modelo; p. ej. "banda 1 (arriba): 57 % más angosto" = falta pelo arriba).

## Bucle automático (lo más barato)

`tools/bucle.py` hace el ciclo solo, sin gastar el agente (detalles en el README):

```bash
python3 tools/bucle.py correr <asset> --proveedor gemini|deepseek|openrouter|groq|ollama [--vueltas N] [--modelo X]
python3 tools/bucle.py paquete <asset>              # modo manual para pegar en cualquier chat
python3 tools/bucle.py aplicar <asset> respuesta.md
```

También corre en GitHub Actions (`.github/workflows/bucle.yml`), sin tu PC encendida.
Usa el agente para diseñar herramientas nuevas en `alth/` (pelo, rig, ropa) y el bucle para las vueltas repetitivas.

## Configurar tu agente para que lea este archivo

- OpenCode, Codex, Cline, Roo y Goose leen `AGENTS.md` solos.
- Aider: `aider --read AGENTS.md --read CLAUDE.md`.
- Gemini CLI: en `.gemini/settings.json` pon `{"contextFileName": ["AGENTS.md", "CLAUDE.md"]}`.
