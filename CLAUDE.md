# ALTH-META · instrucciones para cada sesión

Repositorio de assets 3D chibi-soft low-poly para un videojuego en **Godot**.
El estándar completo está en `spec/alth_spec.json` (fuente de verdad) y en la página "ALTH-META · Estándar unificado".
Responde en español, en tono cercano.

## Arranque (siempre primero)

1. Blender corre como módulo de Python. El comando es `alth-python`.
2. Si `alth-python` no existe o `alth-python -c "import bpy"` falla, corre `bash tools/ensure_blender.sh`
   (tarda 1–3 min la primera vez; puede que el hook de inicio ya lo esté instalando, el script espera su turno).
3. Nunca uses `bpy.ops` que dependan de la interfaz (viewport, `context.area`). Todo va por datos o por `alth`.

## Convenciones

- 1 unidad de Blender = 1 mm. Pies en Z=0, frente hacia −Y, centrado en X=0.
- Usa la librería `alth/` (`nueva_escena`, `caja`, `material`, `chaflan`, `estudio`, `revisar`, `exportar_glb`).
- Colores solo de `spec/alth_spec.json` → `paleta`. Un color nuevo se propone al usuario antes de usarlo.
- Medidas de objetos: `mm_alth = mm_real × 0.0559 × k` con el `k` de su categoría en `conversion_k`.
- Sombreado plano, chaflán 0.4 mm, rugosidad 0.85. Ojos, cejas y boca van como placas con textura, no geometría.

## Ciclo por asset

1. Escribe `assets/<nombre>/spec.json`: categoría, medidas reales, medidas ALTH, colores, módulos.
2. Escribe `assets/<nombre>/build.py` y córrelo con `alth-python`.
3. Revisa **solo** `renders/<nombre>/iteracion/hoja.png` (una imagen con las 4 vistas) y `reporte.json`.
4. Compara contra la referencia y la spec; corrige; repite.
5. Al aprobar el usuario: render `final`, `exportar_glb` a `assets/<nombre>/<nombre>.glb`,
   agrega una fila a `data/medidas.csv` y haz commit.

## Presupuesto (no negociable)

El usuario acepta gastar límite de uso, pero **un asset simple nunca debe consumir una ventana de uso completa**.

| Tipo | Vueltas máximas antes de preguntar |
|---|---|
| Objeto simple (moneda, manzana, vaso) | 3 |
| Objeto | 4 |
| Mueble / vehículo | 5 |
| Personaje | 8 |

- Iteraciones en modo `iteracion` (400 px, 16 muestras). El modo `final` solo una vez, tras aprobación.
- Mira la hoja de contacto, no las vistas sueltas. No abras renders de iteraciones anteriores salvo que haga falta comparar.
- Si al llegar al tope no converge: detente, muestra la hoja y di qué falta. No sigas iterando por tu cuenta.
- No ejecutes búsquedas web ni lecturas largas durante el ciclo; todo lo necesario está en `spec/` y `refs/`.

## Git

- Los renders de iteración (`renders/`) no se versionan; solo `assets/<nombre>/` con el render final, el GLB y el .blend.
- Commits pequeños y descriptivos en español.
- Las sesiones en la nube arrancan en una rama `claude/...` sin upstream. Para traer lo último de `main`:
  `git pull --ff-only origin main` (un `git pull` a secas no trae nada).
- Un asset aprobado por el usuario se sube directo a `main`: `git push origin HEAD:main`. Sin PR, salvo que el usuario lo pida.
- Tras actualizar desde `main`, corre `bash tools/ensure_blender.sh` para regenerar `alth-python` con la versión nueva.

## Referencias

- `refs/personajes/`: renders de estudio de los personajes.
- `refs/escenas/`: los mismos personajes en escenas con luz ambiental (sirven para escala relativa, no para color).
- `refs/infografias/`: comparativas antiguas. **No** usar sus medidas en "u"; la spec las reemplaza.
- `docs/ALTH_META_Modelado.pdf`: cotas originales del cuerpo base (v0.8.4b).
