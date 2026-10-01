# ALTH-META · instrucciones para cualquier agente de IA

Este archivo es para agentes que no son Claude Code (OpenCode, Aider, Cline/Roo, Codex, Gemini CLI, Goose…).
Las reglas completas están en **`CLAUDE.md`** y aplican igual a cualquier agente: léelo primero.
Responde en español, en tono cercano.

## En corto

- Repo de assets 3D chibi-soft low-poly para un videojuego en Godot. Fuente de verdad: `spec/alth_spec.json`.
- Blender corre **sin interfaz** como módulo de Python: el comando es `alth-python`
  (si no existe: `bash tools/ensure_blender.sh`). Nunca uses `bpy.ops` de interfaz.
- Cada asset vive en `assets/<nombre>/` con `spec.json` y `build.py`.
- `alth-python assets/<nombre>/build.py` deja en `renders/…/iteracion/` la `hoja.png` y `reporte.json`.
- 1 unidad = 1 mm, pies en Z=0, frente hacia −Y. Colores solo de la paleta. Tope de vueltas por tipo en `CLAUDE.md`.

## COPOX Loop Engine

`copox/` es el orquestador genérico de loops auditados. No contiene reglas específicas de Theo ni de ALTH: recibe cassettes y ejecuta `prepare → mutate → execute → capture → audit → learn → promote → report`.

Reglas:

- candidatos de un torneo son hermanos desde la misma baseline;
- un rechazado nunca se vuelve padre;
- promoción = 100 % PASS de auditores aplicables; `N-A` no cuenta;
- score sólo desempata candidatos que ya pasaron todo;
- reporte sólo tras promoción unánime y con capturas;
- baseline interna se guarda en una state branch por cassette, no en `main`;
- `main` conserva seeds, contratos y releases;
- inner loop determinista/sin APIs de IA por defecto;
- si no converge, `PLATEAU`: no inventes más versiones;
- ningún cassette productivo se considera activado salvo que esté explícitamente en `copox/cassettes/enabled/`.

Documentación: `docs/COPOX_LOOP_ENGINE.md` y `docs/COPOX_VALIDATION_2026-09-30.md`.

## Si tu modelo NO ve imágenes

No pasa nada, hay números:
- `reporte.json` → `verificacion`: cotas (±2 %), triángulos, paleta, piezas flotantes, apoyo en Z=0.
- `python3 tools/bucle.py medir <asset>`: silueta contra la referencia.

## Bucle histórico automático

`tools/bucle.py` se conserva como compatibilidad durante la migración:

```bash
python3 tools/bucle.py correr <asset> --proveedor gemini|deepseek|openrouter|groq|ollama [--vueltas N] [--modelo X]
python3 tools/bucle.py paquete <asset>
python3 tools/bucle.py aplicar <asset> respuesta.md
```

También corre en GitHub Actions (`.github/workflows/bucle.yml`). Para nuevos loops multi-dominio (personajes, rigs, texturas, UI, scripts), prefiere COPOX cuando exista un cassette/adaptador adecuado.

## Configurar tu agente para que lea este archivo

- OpenCode, Codex, Cline, Roo y Goose leen `AGENTS.md` solos.
- Aider: `aider --read AGENTS.md --read CLAUDE.md`.
- Gemini CLI: en `.gemini/settings.json` pon `{"contextFileName": ["AGENTS.md", "CLAUDE.md"]}`.

## Protección vigente de Theo

`assets/joven_rubio/theo_alpha.glb` tiene SHA-256 `ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b`. No se reemplaza al fusionar código, importar documentación ni auditar. La política M5 mantiene promoción automática deshabilitada. Antes de cada técnica geométrica nueva se exige un research brief válido; sin él, `RESEARCH_REQUIRED`. Las campañas de manos generan exactamente tres hermanos por generación y publican también los rechazos con evidencia; el score no sustituye revisión visual. La aprobación final del modelo sigue siendo separada de una fusión de repositorios.
