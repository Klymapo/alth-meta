# COPOX: corrección y ronda local final · 2026-10-01

Estado: **ningún candidato aceptado**. Se conservaron Alpha y el working parent Valley Sculpt c01. La última generación contiene exactamente tres hermanos; ninguno deriva de otro candidato.

Alpha SHA256: `ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b`.
Working parent SHA256: `d5000a33dcb368031ddbcd0ba9bd666e24c47800a3a95103b1a7a88526f5c81b`.

## Research antes de las correcciones

- [Brief conectado](../copox/research/fingers-connected-micro-valleys-20261001.json): BMesh/API oficial, implementación bisect y join triangles; Manual por espejo identificado. Investigación de influencia acotada de deformación.
- [Brief de pose preservada](../copox/research/fingers-pose-preserving-micro-valleys-20261001.json): implementación oficial de weld/remove doubles y protección de alias geométricos.
- Fuentes se consultaron realmente mediante GitHub. No se afirma visita a docs.blender.org ni un tutorial chibi no consultado. Aplicación a Theo es una hipótesis propia.
- Actions valida el brief vigente; no navega ni finge research. Técnica ausente, malformada, futura o caducada: RESEARCH_REQUIRED.

La calibración real mostró que el primer valle cae en Z normalizada 0.5072–0.5314 y no hay vértices distales allí. La ronda de ajuste vertical logró 2/0 y target ≈ +19 pp, pero levantó la mano y creó costuras; se rechazó visualmente. Esta ronda conserva pose y utiliza correspondencia **intrínseca** entre contornos de mano: no pretende resolver el desfase global de pose.

## Qué se corrigió

Se eliminó el booleano global. El adaptador usa BMesh local, conserva UV/materiales, bloquea también posiciones/aristas geométricas duplicadas por GLB y compara caras exteriores antes/después. Además audita posiciones+UV de triángulos exteriores **después** del transporte GLB.

Multiplicidad de face-corner vertices no equivale a superficie modificada: se registran duplicados compactados por separado. Scope requiere conservar caras y posiciones protegidas, otros objetos y el auditor GLB independiente. En esta ronda los 27443 triángulos protegidos se conservan en los tres.

El ajuste vertical común se descartó. Secciones por dedo prueban ciclos concretos; no se llama rig-ready a una triangulación refinada. Bridge/rig siguen false. Un candidato con auditoría numérica PASS y visual PENDING ya no puede ser ganador.

Los runners históricos de dedos/manos son manuales, para evitar relanzar técnicas agotadas con cada commit del PR. Ningún runner nuevo modifica Alpha, hace merge ni promueve baseline.

## Última generación real

Sola variable: profundidad relativa 0.75/1.0/1.25. Anchos/posiciones proceden de los dos valles de referencia; escala de profundidad deriva del tamaño medido de mano. Mano derecha no se modifica.

| Candidato | Target pp | Global pp | Peor vista pp | Diferencia target a Valley, registro Alpha | Valles L/R |
|---|---:|---:|---:|---:|---|
| c01 | +3.778748 | +0.150596 | −0.071984 | −2.334149 | 1/0 |
| c02 | +2.980746 | +0.150326 | −0.070932 | −3.132151 | 1/0 |
| c03 | +2.635660 | +0.149134 | −0.068960 | −3.477237 | 1/0 |

Todos: scope_safe=true, evidence_complete=true, ganancias positivas y peor vista dentro del límite. Ninguna región congelada cae bajo −0.20 pp contra Alpha o Valley.

Todos: semantic_ready=false, mesh_integrity=false, regression_ok=false por pérdida de ventaja Valley, loops incompletos y decisión visual REJECTED. No hay candidato serio ni ganador aceptado. c01 es mejor en las métricas, pero es inferior a Valley (+6.112897 pp). c03 es menos defectuoso en degeneración/non-manifold, sin superar el veto.

| Topología soldada para auditoría | Parent | c01 | c02 | c03 |
|---|---:|---:|---:|---:|
| Boundary edges |228|310|310|310|
| Non-manifold edges |0|9|6|0|
| Degenerate faces |0|10|6|0|

No se declara watertight al parent: ya tiene228 boundary edges. Los 310 de candidatos son una señal que requiere investigar; no se rebaja el gate para pintar verde. Auditor local de intersecciones detecta 0 en los tres, con limitaciones declaradas para coplanar/adyacencia; no sustituye el veto topológico.

## Evidencia

- [Ronda vertical rechazada](https://github.com/Klymapo/alth-meta/actions/runs/36883548374).
- [Última generación, GLB/blend y todos los reportes](https://github.com/Klymapo/alth-meta/actions/runs/36886096110/artifacts/11174088076).
- [Revisión multivista de los GLB existentes](https://github.com/Klymapo/alth-meta/actions/runs/36887264686/artifacts/11174633435).
- La revisión final vuelve a encuadrar exclusivamente finger_region con bounds de la superficie medida; los cinco GLB usados se verifican inmutables.

Incluye trial/module_result/gate/learning, topology, regional/full metrics, hand probe, renders front/side/back/3/4, closeups izquierda/derecha/dedos y hoja REFERENCE/ALPHA/C01/C02/C03, además de hoja con Valley. Revisión exporta gates finales con veto visual y reviewed_loop.json. Retención 7 días, hasta el 8 de octubre UTC.

Validación: 46 tests pasan, incluida prohibición de promoción incluso con gate PASS, investigación obligatoria, parentesco, veto visual pendiente y detección de drift exterior. La ejecución exitosa del workflow sólo acredita ejecución de auditoría.

## Aprendizaje y siguiente hipótesis

Aumentar profundidad no crea el material distal superior ausente, y reduce la silueta buena. Registro global detecta el problema de pose; el ajuste completo de contorno no es una solución aceptable bajo las regiones congeladas. Deben separarse correspondencia de rasgos, volumen disponible y validación de límites del patch.

Siguiente investigación: localizar y reparar sólo las costuras/borde mínimo, y evaluar una extrusión conectada o patch de quads **del segmento distal superior** con borde y UV emparejados. Mantener palma, pose, grosor, mano derecha y antebrazo. No reconstruir mano completa, no dedos flotantes, no aumentar densidad global ni profundidad indiscriminada. No ejecutar esta técnica sin un nuevo brief vigente.

Stop real: MESH_INTEGRITY_FAILED. Tres rondas técnicas registradas (booleano, contorno conectado, pose preservada), siempre desde el mismo working parent; ninguna promoción. promotion_executed=false.

El runner manual no depende de artifacts temporales: por defecto reproduce Valley c01 desde Alpha protegido. Reutilizar un artifact auditado es una entrada opcional verificada por SHA. [Historial de las tres rondas](../copox/research/fingers-micro-valleys-20261001-campaign.json).
