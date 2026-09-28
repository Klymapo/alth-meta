# Diagnóstico · por qué Theo no se parece a la referencia (28 sep 2026)

Este documento responde a la pregunta directa del usuario: "¿por qué no se parece nada lo que
tenemos al Blender del chico rubio?". Compara `renders/pruebas/joven_rubio_v1/hoja_v1.png`
contra `refs/personajes/joven-rubio-4-vistas.jpg` y `refs/personajes/joven-rubio.jpg`.

## El PDF no es la fuente única

`docs/ALTH_META_Modelado.pdf` dio las cotas **del esqueleto** (anchos y largos en mm de cada
hueso/bloque): cabeza, torso, brazos, piernas. Nunca fue pensado para decidir volumen, densidad
de pelo ni caída de ropa — esas cosas no están en un PDF de cotas, están en las imágenes. El
`brief_final.md` de vuelta 6 ya lo decía ("no inventes medidas... cuando un detalle no tenga
cota, decide comparando las cuatro vistas"), pero las cotas congeladas del cuerpo siguen
pesando más que las imágenes en la práctica, porque son números exactos y lo visual es
descriptivo. Resultado: el esqueleto queda correcto en mm, pero la lectura visual no, porque el
esqueleto solo no es el personaje.

## Diagnóstico concreto (comparando las dos hojas)

1. **Cuerpo: esqueleto flaco, no chibi-soft.** En la referencia, hombros, brazos y torso tienen
   masa — se leen "rellenos". En `hoja_v1.png` los brazos y piernas son varillas: `grosor_extremidades=1.25`
   más una ropa que no infla lo suficiente no alcanza para el efecto "chibi-soft" que piden las
   imágenes. Este es un problema de volumen, no de una cota mal puesta.
2. **Pelo: tercer intento con el mismo síntoma.** La referencia es una masa ancha, gruesa,
   de mechones que se superponen sin dejar ver el cuero cabelludo, con ancho total ≈1.5-1.6×
   el ancho de la cabeza. `alth/pelo.py` (corona + cuñas, vuelta "pelo nuevo") produce puntas
   delgadas y separadas con hueco entre ellas — la misma silueta de "casco con púas" que el
   propio `brief_final.md` pedía evitar, solo que ahora en un solo mesh. El algoritmo actual
   genera cuñas demasiado angostas en su base para la escala real.
3. **Cara: rasgos correctos en mm, ilegibles en conjunto.** Ojos e iris están a la medida
   congelada, pero sin el volumen de cabeza/pelo alrededor que les da contexto, se ven como
   parches flotando en una caja.
4. **Por qué se estanca:** las últimas vueltas (4-6 en el historial) corrigieron detalles
   puntuales (botones, dobladillo, cotas D) que **ya estaban bien** en vez de atacar volumen y
   pelo, que es donde está el 90% de la diferencia visual. Se gastaron vueltas en pulir lo que
   no era el problema.

## Medidas unificadas (todas las referencias, no solo el PDF)

Cruzando `joven-rubio-4-vistas.jpg` (proporción visual), `refs/infografias/comparativa-personajes-unidades.png`
y `refs/infografias/hoja-de-vistas-personaje.png` contra las cotas del PDF ya en `spec/alth_spec.json`:

- Las cotas de **esqueleto** (cabeza 40×34.5×29.8, torso, piernas, pies) coinciden razonablemente
  con las cuatro vistas y se mantienen — no es ahí donde está el error.
- Lo que falta expresar como número, y que hoy solo vive como texto descriptivo:
  - **Volumen de ropa sobre el esqueleto:** en la referencia, el contorno de la manga/chaleco/pantalón
    es visiblemente más ancho que el esqueleto desnudo — no un forro ajustado. Propuesta: la ropa
    debe sobresalir del esqueleto un 35-45% en brazos y piernas (hoy `grosor_extremidades=1.25`
    ≈ 25%, y aun así la ropa no llega a ese ancho en el render).
  - **Ancho total del pelo:** ≥1.5× el ancho de cabeza (40 mm → pelo ≥60 mm de ancho en su punto
    más ancho), sin huecos de cuero cabelludo visibles en ninguna de las 4 vistas.
  - **Grosor de cada mechón en la base:** en la referencia ningún mechón individual se ve más
    delgado que ~1/4 del ancho total del pelo. Las cuñas actuales (`ancho_base=(8.0, 12.0)` mm
    sobre una corona de ~52 mm de ancho) son proporcionalmente delgadas — de ahí el efecto púa.

## Recomendación para desatorar

No es una corrección más de detalle: es redirigir la vuelta 7 a volumen + pelo únicamente, con
números explícitos en vez de lenguaje descriptivo (ver `assets/joven_rubio/brief_final.md`,
actualizado en este mismo commit). Nada de esto compite con la escala congelada v1.0 (altura,
cabeza, anclas) — esas cotas están bien y no se tocan.
