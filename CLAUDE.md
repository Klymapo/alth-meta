# ALTH-META · instrucciones para cada sesión

Repositorio de assets 3D chibi-soft low-poly para un videojuego en **Godot**.
El estándar completo está en `spec/alth_spec.json` (fuente de verdad).
Responde en español, en tono cercano.

## Arranque ALTH

1. Blender corre como módulo de Python. El comando es `alth-python`.
2. Si `alth-python` no existe o falla, corre `bash tools/ensure_blender.sh`.
3. Nunca uses `bpy.ops` que dependan de interfaz/viewport. Todo va por datos o por `alth`.

## COPOX Loop Engine

COPOX (`copox/`) es la capa genérica para loops auditados y multi-dominio. ALTH es uno de sus posibles cassettes/adaptadores; Theo no es el centro del engine.

Flujo:

`seed/main → state branch → baseline → sibling candidates → execute → capture → audit → learn → unanimous promote → state branch → report`

Reglas no negociables:

- 100 % de auditores aplicables deben dar PASS; `N-A` se excluye.
- Un FAIL veta; score nunca compensa un FAIL.
- Rechazados nunca son padres de la siguiente versión.
- Candidatos de un torneo son hermanos desde la misma baseline.
- Reporte sólo después de unanimidad y sólo si existen capturas.
- Promoción interna actualiza `copox/state/<cassette-id>`; no equivale a release en `main`.
- Inner loop determinista y sin APIs de IA por defecto. IA/ChatGPT = dirección/escalamiento ante plateau o cambio de técnica.
- Una campaña se enfoca en el mismatch principal o dos estrechamente acoplados; auditores regionales fuera del foco son N-A, pero RegressionGuard/Anatomy siguen activos.
- Un mismo cassette es secuencial; cassettes distintos pueden correr en paralelo.
- Un cassette productivo sólo está activo si aparece explícitamente en `copox/cassettes/enabled/`.

Ver `docs/COPOX_LOOP_ENGINE.md` y `docs/COPOX_VALIDATION_2026-09-30.md`.

## Convenciones ALTH

- 1 unidad de Blender = 1 mm. Pies en Z=0, frente hacia −Y, centrado en X=0.
- Usa la librería `alth/` antes de construir geometría a mano.
- Colores solo de `spec/alth_spec.json` → `paleta`. Un color nuevo se propone antes de usarlo.
- Medidas de objetos: `mm_alth = mm_real × 0.0559 × k` con el `k` de su categoría.
- Sombreado plano con variación por cara según estándar. Ojos, cejas y boca se mantienen compatibles con animación según el asset.

## Verificación automática ALTH

`alth.revisar(..., asset=<spec.json>)` genera `reporte.json` con cotas, triángulos, paleta, piezas flotantes y apoyo Z=0. Es necesaria, pero no sustituye la comparación visual.

En COPOX, el adapter `alth_character_audit.py` añade comparación contra referencia: IoU por vista/región, cambios visibles, anatomy/regression gates, landmarks y error budget.

El GLB exportado es glTF Y-up. Los reference configs deben declarar ejes; no asumas Z-up al auditar GLB.

## Ciclo manual/histórico ALTH

El comando `/asset` y `tools/bucle.py` continúan disponibles para compatibilidad, ajustes puntuales y assets que aún no tengan cassette COPOX.

`tools/bucle.py` puede medir silueta y usar proveedores externos/manuales según README. Para loops repetitivos nuevos con cassette disponible, prefiere COPOX.

## CHSP-X

La página de revisión histórica está en `chsp-x/index.html`. COPOX no la elimina todavía; puede evolucionar después a dashboard de estado/evidencia.

## Presupuesto y stop rules

No malgastes límites de IA. Usa primero algoritmos, parámetros, tests, métricas y runners gratuitos.

Para el bucle histórico siguen vigentes los topes por tipo (3/4/5/8). Para COPOX el cassette declara su máximo de candidatos. Al alcanzar el máximo sin unanimidad: `PLATEAU`, conserva baseline y escala a dirección; no sigas creando versiones por inercia.

## Git / estado / release

- `main`: fuente de verdad de código, seeds, specs y releases.
- `copox/state/<cassette-id>`: historial mínimo de baselines internas promovidas (`baseline.json` + `state.json`).
- ramas `propuesta-*`: herramientas nuevas; no fusionarlas hasta pasar pruebas reales y aprobación del usuario.
- renders de iteración no se versionan; evidencia completa puede vivir temporalmente como artifact de Actions.
- release final de un asset sigue siendo una acción separada de una promoción interna COPOX.

## Referencias

- `refs/personajes/`: referencias de personajes.
- `refs/escenas/`: escala relativa/contexto.
- `refs/infografias/`: comparativas antiguas; no usar medidas antiguas si la spec las reemplaza.
- `docs/ALTH_META_Modelado.pdf`: cotas originales del cuerpo base cuando aplique.
