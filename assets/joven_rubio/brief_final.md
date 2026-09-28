# RONDA ÚNICA · Theo (`joven_rubio`) · brief final v2 (28 sep 2026)

Ver `docs/diagnostico-theo-28sep.md` antes de empezar: explica por qué las vueltas 1-6 no
cerraron la brecha con la referencia (se pulieron detalles que ya estaban bien; el problema real
es volumen de ropa/cuerpo y densidad de pelo, no cotas del esqueleto). Esta ronda ataca
**solo** esos dos puntos, con números explícitos en vez de descripciones.

## Misión

Convierte la versión actual de Theo en una versión final reconocible en **una sola respuesta integral**. No hagas una corrección tímida ni optimices únicamente la coincidencia de silueta: resuelve conjuntamente identidad, pelo, cara, vestuario y lectura en cuatro vistas. Después de tu respuesta Blender correrá las pruebas y un humano revisará la hoja; tú no apruebas ni exportas el resultado final.

## Jerarquía de fuentes

Si dos fuentes parecen contradecirse, usa este orden:

1. `refs/personajes/joven-rubio-4-vistas.jpg`: silueta, volumen, colocación y lectura de frente, lateral, espalda y 3/4.
2. `refs/personajes/joven-rubio.jpg`: identidad, expresión, lenguaje de formas, pelo y vestuario.
3. `spec/alth_spec.json` y `assets/joven_rubio/spec.json`: medidas exactas, paleta, orientación y límites técnicos.
4. La hoja de la versión actual: es el punto de partida y evidencia de problemas, no el objetivo visual.

No inventes medidas tomadas de las imágenes. Cuando el estándar ya define una cota, consérvala. Cuando un detalle visual no tenga cota, decide su geometría comparando las cuatro vistas y documenta el valor elegido en `AUTOCOMPROBACIÓN`.

## Límites de edición

- La solución esperada vive principalmente en `assets/joven_rubio/build.py`.
- Excepción de esta ronda: **sí puedes modificar `alth/pelo.py`**. Dos intentos (casco+púas, corona+cuñas)
  no llegaron al volumen de la referencia; el diagnóstico apunta a que las cuñas son estructuralmente
  demasiado angostas para la escala, no a un ajuste de parámetros. Si lo cambias, corre `tests/test_pelo.py`
  y confirma que sigue siendo puro (sin Blender) y reusable por otros personajes (no hardcodees nada de Theo ahí).
- No modifiques `alth/personaje.py` ni `alth/ropa.py`: llama sus funciones públicas con parámetros distintos
  desde `build.py` (p. ej. `grosor_extremidades` más alto, o un `inflado` nuevo si `ropa.traje_formal` ya lo acepta).
- Conserva el modo `iteracion`, `alth.revisar(..., asset=...)`, el maniquí de escala y la exportación condicionada a `MODO == "final"`.
- No generes el render final ni el GLB. Eso ocurre sólo tras aprobación humana.

## Medidas congeladas

Mantén estas dimensiones del estándar y las cotas de `spec.json` dentro de ±2 %:

- altura total del cuerpo base: 95.0 mm; pies apoyados en Z=0; frente hacia −Y; centro X=0;
- cabeza: W 40.0 mm, H 34.5 mm; mandíbula W 36.2 mm y D 28.8 mm;
- torso D 17.8 mm; pierna H 24.0 mm y D 11.13 mm; zapato D 18.0 mm;
- ojos: 8.4 W × 9.7 H × 1.2 D mm; centros X ±6.15 mm, Z 78.5 mm;
- iris: 3.9 W × 6.5 H × 0.75 D mm;
- cejas: 9.2 W × 1.9 H × 0.85 D mm;
- nariz: 3.8 W × 2.7 H × 1.8 D mm;
- conserva longitudes y perfiles base de brazos, palma, piernas y zapatos. No declares definitiva la topología de cuello/hombros/cadera ni dedos.

La ropa y el pelo pueden ampliar la silueta fuera del cuerpo base siempre que sigan la referencia, no floten y no rompan la altura/personaje aprobada. Si el pelo eleva el bounding box total, cuantifica el valor final y explica por qué corresponde a la referencia.

## Correcciones que deben resolverse juntas

### 1. Identidad y cara

- Theo debe leerse como el joven rubio de la referencia, no como un maniquí genérico.
- Los ojos deben ser grandes, orgánicos y verticales, con blanco visible e iris café; no deben parecer pantallas o cajas pequeñas. Respeta las medidas congeladas y usa placas delgadas sobre la superficie real de la cara.
- Usa iris de 3.9 × 6.5 × 0.75 mm y cejas de 9.2 × 1.9 × 0.85 mm. Mantén la separación de centros de los ojos y evita que cejas, iris o boca floten o se entierren.
- Conserva la cabeza ancha, mandíbula más estrecha, nariz pequeña y sonrisa leve. La expresión debe ser amable y segura, sin exageración.

### 2. Pelo — prioridad visual máxima, con números

- Ancho total del pelo (punto más ancho, vista frontal) ≥ **1.5× el ancho de cabeza** (cabeza=40 mm → pelo ≥ 60 mm). Repórtalo medido, no estimado.
- Ningún mechón individual con base < **¼ del ancho total del pelo** en ese punto. Menos mechones más gruesos, no más mechones delgados: apunta a 6-9 masas, no 10-12 púas.
- Cero cuero cabelludo visible entre mechones en ninguna de las 4 vistas (frente, lateral, espalda, 3/4): cada mechón debe solapar al vecino en vista frontal.
- Frente: raya/abertura central legible, dos mechones largos que enmarquen la cara, capas superiores que suban y vuelvan hacia los lados sin tapar ojos ni cejas.
- Lateral: profundidad real, capas sobre sien y oreja, coronilla con volumen, nuca cubierta. El perfil no puede verse como una sola tapa.
- Espalda: mechones grandes en capas, centro y laterales diferenciados; no dejes superficie lisa ni huecos.
- 3/4: debe leerse el solapamiento de raíces, mechones frontales, volumen superior y masa posterior.
- Mantén las piezas conectadas o claramente solapadas con la corona/cabeza, sin flotantes ni intersecciones visuales graves.

### 3. Vestuario y silueta — con números

- La ropa debe sobresalir del esqueleto desnudo (cuerpo sin ropa) **35-45% en brazos y piernas** (ancho de manga/pantalón sobre ancho de brazo/pierna piel). Si usas `grosor_extremidades`, este parámetro solo, en 1.25, no alcanza: súbelo o suma un inflado extra específico de la ropa.
- Camisa blanca con mangas dobladas hasta el codo y puños legibles en frente, lateral y 3/4.
- Chaleco negro con forma clara, abertura en V, solapas, dos botones visibles y terminación inferior en punta suave. Su ancho en el pecho debe superar visiblemente el ancho del torso desnudo (no un forro pegado). No debe verse como un cilindro negro sin confección.
- Corbata azul con nudo y pala diferenciados, centrada y por encima de la camisa, sin atravesar el chaleco.
- Pantalón azul marino amplio, con volumen continuo desde la cadera, pliegue/facetado sobrio y dobladillos visibles sobre los zapatos.
- Zapatos negros gruesos, estables y coherentes con la referencia; ambos apoyados en Z=0.
- Conserva la pose neutral aprobada y la lectura clara de las manos. No uses la pose para ocultar errores del vestuario.
- Antes de reportar `LISTO`, compara el ancho de hombro a hombro (con ropa) contra el ancho de cabeza: en la referencia son casi iguales. Si tu resultado da hombros notablemente más angostos que la cabeza, no está listo.

### 4. Calidad técnica

- Usa sólo la paleta del repositorio y mantén el sombreado low-poly suave/facetado de ALTH-META.
- La verificación debe quedar `OK`: cotas, paleta, apoyo, piezas flotantes y presupuesto de triángulos.
- La referencia visual manda sobre IoU cuando el IoU premie una silueta incorrecta o pierda rasgos internos. Reporta el IoU, pero no sacrifiques identidad, cara, pelo o vestuario para subirlo.
- Evita geometría duplicada, caras invisibles innecesarias y detalles demasiado pequeños para leerse en la hoja de 400 px.

## Criterio de terminado

Responde `ESTADO: LISTO` sólo si, antes de renderizar, tu revisión razonada confirma simultáneamente:

1. todas las cotas congeladas y las cotas de `spec.json` quedan dentro de tolerancia;
2. la solución usa exclusivamente archivos editables y colores permitidos;
3. pelo, cara, chaleco, corbata, mangas, pantalón y zapatos son legibles en las cuatro vistas;
4. no detectas flotantes, intersecciones graves ni pérdida de apoyo;
5. una persona puede identificar a Theo comparando la hoja con las dos referencias, sin depender del nombre del asset.

Si hay un bloqueo técnico real, responde `ESTADO: SIGUE`, conserva una versión ejecutable y describe el único bloqueo con evidencia. No omitas correcciones deliberadamente para pedir otra ronda.

## Entrega obligatoria

Sigue el formato `RONDA ÚNICA` de `tools/bucle_sistema.md`: `DIAGNÓSTICO` completo y numerado, `AUTOCOMPROBACIÓN` D# por D#, `CAMBIOS`, `ESTADO` y cada archivo editable completo. En el diagnóstico separa hechos medidos de decisiones visuales. No devuelvas diffs, fragmentos, pseudocódigo ni texto del tipo “resto sin cambios”.
