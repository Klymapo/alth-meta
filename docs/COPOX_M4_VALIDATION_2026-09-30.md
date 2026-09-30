# COPOX · Validación M4 de Theo Alpha · 2026-09-30

Las 23 áreas de Theo disponen de procesos de evidencia, auditoría, edición,
diagnóstico y control de regresiones. La matriz registra 22 áreas M4 y pelo M5.
El cassette productivo permanece desactivado y la baseline artística sigue siendo Theo Alpha.

## Fuentes

- Modelo: `assets/joven_rubio/theo_alpha.glb`.
- SHA-256 aprobado: `ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b`.
- Referencia: `refs/personajes/joven-rubio-4-vistas.jpg`.
- SHA-256 de referencia: `129a609fc2e562eb993f9f8414198717e7c4f7332998d2844c3b490279b43b40`.
- Matriz: `copox/maturity/theo.json`.

## Pruebas reales

| Proceso | Evidencia comprobada | Workflow |
|---|---|---|
| Anatomía | 15 regiones deformables; close-ups y error por vista; hipótesis de orejas sin promoción | `copox-anatomy-maturity.yml` |
| Silueta/proporciones | 7 hipótesis globales; veto por regresión en una vista antes de seleccionar dirección | `copox-global-maturity.yml` |
| Materiales | 1,441 polígonos seleccionados; geometría y cotas intactas; selección exacta; render | `copox-material-maturity.yml` |
| Topología | Densidad local mayor; todas las posiciones originales preservadas; superficie, área y UV conservadas | `copox-alth-integration.yml` |
| Rig | 18 huesos exportados; cobertura de pesos 100%; pose real de antebrazo; rest pose estable | `copox-rig-maturity.yml` |
| Ojos/boca | `blink_left`, `blink_right`, `mouth_open` exportados con sus nombres; rest pose y previews activos | `copox-facial-maturity.yml` |
| Orientación | Personaje vertical, pelo sobre el cuerpo; corrección aplicada sólo al render; diagnóstico | `copox-orientation-maturity.yml` |

Los workflows están en `.github/workflows/`. Todos fueron ejecutados sobre Theo Alpha
en el entorno de recuperación; sus artefactos de Actions permiten reproducir la evidencia.
La suite de CI añade pruebas negativas para exports incompletos, poses no finitas,
regresiones que se cancelan al promediar vistas y modificaciones de la superficie.

## Corrección de topología

`subdivide_edges` puede invalidar referencias `BMVert`. La verificación conserva
valores antes de subdividir y compara el multiconjunto de coordenadas posterior,
incluidas posiciones duplicadas. No descarta vértices inválidos para declarar éxito.
Además, comprueba los nuevos puntos contra la superficie original con BVH y compara área y cotas.

- Vértices del objeto: 76,872 → 78,930.
- Polígonos Blender: 25,624 → 27,682.
- Caras seleccionadas: 686.
- Posiciones originales faltantes: 0.
- Cambio de cotas: 0.
- Distancia máxima de nuevos puntos a superficie original: aproximadamente `4.17e-9` unidades locales.
- Cambio relativo de área: aproximadamente `5.83e-10`.
- Máximo delta regional de raster: `0.0328` puntos porcentuales, bajo el límite existente de `0.05`.

El rasterizador cuantiza los puntos añadidos al subdividir. En ROIs pequeñas,
un delta por vista puede llegar a `0.3693` puntos porcentuales, aun con superficie
preservada; se registra junto al delta regional. La comprobación geométrica independiente
evita usar el promedio de vistas como única prueba de estabilidad.

## Alcance de M4

La disponibilidad técnica del proceso permite experimentar y diagnosticar cambios.
Los candidatos de estas pruebas tienen `promotion_allowed=false`. El estudio global
mantiene la baseline entre las hipótesis elegibles y veta candidatos que empeoran una vista
más de `0.20` puntos porcentuales, aunque aumente su media global.

Las pruebas de rig cubren skin y una pose corporal; faltan revisar otras articulaciones
y los controles finos del rig final. Los morphs faciales conservan nombres, rest pose y
previews activos; su semejanza con párpados y boca requiere revisión visual. La subdivisión
añade grados de libertad, y el modelado final de dedos requiere trabajo posterior.

El gate de orientación impide renders inválidos; la corrección/promoción autónoma de
orientación conserva `loop_gate=false`. M4 y activación productiva son decisiones separadas.
