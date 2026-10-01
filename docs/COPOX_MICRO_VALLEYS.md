# COPOX · micro-valles locales

Estado actual: última generación ejecutada y revisada; los tres candidatos rechazados. [Resultados, gates y siguiente hipótesis](COPOX_MICRO_VALLEYS_2026-10-01_CORRECTION.md). [Ronda inicial histórica](COPOX_MICRO_VALLEYS_2026-10-01_RESULTS.md).

El baseline aceptado sigue siendo Theo Alpha, SHA256 `ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b`. Working parent de la estrategia es Valley Sculpt c01 (.55), una copia de trabajo sin promoción. Cada generación crea exactamente tres hermanos desde ese parent.

## Flujo

RESEARCH → DIAGNOSTIC → SELECT MODULE → GENERATE3SIBLINGS → AUDIT → RANK → LEARN → STOP/NEXT ITERATION.

`research_gate.py` valida cada técnica nombrada antes de mutar; brief preparado por Codex con fuentes verificadas, vigencia45días, sin fingir browsing en Actions. Investigación insuficiente: RESEARCH_REQUIRED.

`research_iteration_loop.py` limita a tres generaciones internas, verifica SHA de parentesco, registra métricas/winner/rechazos/aprendizaje y detiene por integridad, falta de mejora, regresión repetida, investigación, agotamiento o límite. Un PASS computacional con visual PENDING no gana. No tiene función de promoción.

`finger_micro_valley_campaign.py` prepara/reutiliza Valley c01, deriva los dos valles reales L2/R0 y varía sólo depth_scale .75/1.0/1.25. El adaptador actual mantiene pose, protege aliases geométricos de costuras y aplica BMesh local; nunca reemplaza la mano completa.

Scope se verifica por caras+UV/posiciones exteriores, otros objetos y transporte GLB independiente. Mesh, regional/full visual, probe de manos, secciones por dedo y comparación contra Alpha y Valley son vetos separados. No se confunde número de cortes con topología all-quads, bridge ni rig listos.

## Ejecución gratuita/cloud

El workflow `copox-finger-connected-valleys.yml` es manual y usa ubuntu estándar/Open Source. Por defecto reproduce Valley desde Alpha; opcionalmente descarga un artifact auditado como parent, verifica SHA y copia únicamente su working parent. No hereda candidatos rechazados. Si el artifact expiró, usar el modo predeterminado.

El workflow de revisión `copox-finger-local-notch-review.yml` descarga los tres GLB ya auditados, encuadra evidencia de dedos sin alterar archivos GLB y aplica las decisiones visuales registradas. Genera reviewed_loop.json y gates finales; no genera geometría.

Artifacts incluyen GLB/blend, trial/module_result/gate/learning, topology, regional/full metrics, hand probe, cuatro vistas, closeups y comparison.png (REFERENCE/ALPHA/C01/C02/C03). comparison_with_valley.png añade el parent. Retención7días.

## Protecciones

automatic_promotion_enabled=false. El adaptador Theo veta promoción incluso si gate PASS. Theo loop sólo shadow y permisos de lectura; sin schedule. Alpha nunca se reemplaza, sin merge, sin nueva rama/PR. No APIs de pago, créditos comerciales, tokens de investigación ni instalación en PC local. Blender/BMesh corre en Actions.

Bridge a palma y cleanup para rig requieren research específico nuevo. La siguiente hipótesis investigable está en el reporte; no se ejecuta técnica ausente del brief válido.
