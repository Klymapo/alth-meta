# alth-meta

Assets 3D en estilo **ALTH-META** (chibi-soft low-poly) para un videojuego en Godot.
Se modelan con scripts de Blender que corren sin interfaz en sesiones de Claude Code en la nube.

| Carpeta | Contenido |
|---|---|
| `spec/alth_spec.json` | Estándar: escala, arquetipos, cotas, conversión real→ALTH, paleta, luz, presupuesto |
| `alth/` | Librería de Blender: escena en mm, materiales, estudio de luz, renders de revisión, exportación GLB |
| `tools/` | `ensure_blender.sh` (instala Blender como módulo de Python) y `fase0_cubo.py` (prueba del pipeline) |
| `assets/<nombre>/` | Especificación, script, .blend, GLB y render final de cada asset aprobado |
| `refs/` | Referencias visuales: personajes, escenas e infografías |
| `data/medidas.csv` | Registro que recalibra los factores de conversión |

## Prueba rápida

```bash
bash tools/ensure_blender.sh
alth-python tools/fase0_cubo.py
```

Exporta a Godot como GLB con la raíz ×0.01: el personaje estándar (95 mm de maqueta) mide 0.95 m en el juego.
