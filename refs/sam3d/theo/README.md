# SAM 3D — reconstrucciones de Theo (joven_rubio)

11 reconstrucciones GLB generadas por el usuario con el demo de Meta
(SAM 3D Objects / SAM 3D Body) a partir de imágenes de referencia de Theo.
No están segmentadas, no tienen rig, y vienen normalizadas a una caja
unitaria (sin escala real) — solo sirven como referencia de proporción,
no como asset final. Nunca pasan directo a `assets/`.

Usadas en el análisis de `alturas_ancla_sam3d_candidato` (ver `spec/alth_spec.json`):

- `fba550bc-object_1.glb`
- `2f639739-object_1.glb`
- `2a3facb9-object_2.glb`
- `5ed925a3-object_2.glb`
- (una quinta del lote de 6, pose relajada, brazos abajo)

Descartadas del análisis de proporción:

- `a501b501-object_3.glb` — pico de pelo anormalmente alto que se vuelve el punto
  más alto de la caja delimitadora y descalibra toda la normalización por altura.
  Se conserva solo como referencia visual de cara/pelo.
- una segunda del lote con geometría/proporciones degradadas.

El resto (`70ef0058-object_0.glb`, `6e95d62d-object_4.glb`, `38448021-object_5.glb`,
`5dc9e0d5-object_0.glb`, `80c13944-object_3.glb`, `2b65e967-object_0-1.glb`) son
tomas adicionales del mismo lote, sin filtrar a fondo todavía.

## Método y resultados

Ver `alturas_ancla_sam3d_candidato` en `spec/alth_spec.json` (estado AMARILLO,
no reemplaza `alturas_ancla` hasta validarse en Blender) para las alturas de
ancla. Las medidas de profundidad (Z), ancho de cabeza y longitudes de
brazo/pierna elaboradas después están en `docs/CHSP-X.md` / el doc de traspaso
del proyecto — no se pudo aislar el ancho de torso (X) porque la malla es una
superficie continua sin separación real entre torso y brazo en pose de brazos
abajo; se necesitaría una referencia con los brazos ligeramente separados
(A-pose leve) para resolverlo.
