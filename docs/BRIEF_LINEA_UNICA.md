# Brief para la sesión de Claude Code: construir la "Línea única" (no los assets)

Este archivo es el encargo para una sesión de Claude Code con el entorno **ALTH Blender**, sobre el repo `Klymapo/alth-meta`. **Parte de la rama `propuesta-reconocimiento`**, que ya trae el reconocimiento de imagen **solo con código** y el registro de capacidades. Antes de empezar lee `CLAUDE.md`, `spec/alth_spec.json`, `docs/COPOX_LOOP_ENGINE.md`, `docs/COPOX_MICRO_VALLEYS_2026-10-01_CORRECTION.md`, `copox/production/research_gate.py`, `tools/reconocer.py` y `tools/capacidades.py`.

## Regla principal
**Tu trabajo es construir el motor una sola vez. Después, cada asset lo produce el repo en GitHub Actions, sin que tú ni ningún chat de Claude intervengan.** No modeles a mano ningún asset de producción: lo único que modelas son las pruebas de aceptación, y salen del motor. **No le entregues al motor respuestas ya investigadas** (p. ej. cómo modelar dedos): debe encontrarlas solo. **Sin IA ni modelos dentro del proceso** (decisión del usuario, 1 oct): ni APIs, ni modelos locales, ni claves, ni cuotas. Solo código y herramientas gratuitas (numpy, scipy, Pillow, Blender, la API pública de GitHub). No hagas más de lo pedido: si algo no cabe, déjalo anotado y detente.

## Decisiones vigentes (1 oct 2026)
- La escala de 95 mm queda descartada. **Theo Alpha** (`assets/joven_rubio/theo_alpha.glb`) es la base de medidas. No se modifica (SHA-256 `ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b`).
- Theo mide ≈1.80 m en el mundo real **sin contar el pelo** (confirmado por el usuario). `s0 = altura del cuerpo de Alpha sin pelo / 1800`; medido en el GLB: 95.7 mm → `s0 ≈ 0.0532` (antes 0.0559). Confírmalo midiendo en Blender en T0. Ya lo usa `reconocer.py` como respaldo hasta que la spec traiga `escala_alpha.s0`. La manzana pasa de 8.94 a ≈8.51 mm.
- Los 5 assets aprobados (manzana, lata, taza, vaso, vaso de café) **solo se re-dimensionan**; no se rehacen.
- Alpha: GLB en pose T, Z-up, sin raíz ×0.01. 26 913 triángulos en 16 mallas; **`theo_v3_v11` concentra 25 624 (95 %)**, viene de SAM 3D, con 76 872 vértices sin soldar. Tope de personaje en la spec: 6000.
- **Dedos SEPARADOS en todos los personajes** (decisión del usuario, 1 oct), aunque sus referencias los dibujen juntos. Ya está en `spec/capacidades_vocab.json` → `requeridas_por_tipo`. El motor debe encontrar por sí mismo un método nuevo (no parchar la malla de mano vieja).
- Vara de calidad: **superar la manzana actual** (`assets/manzana`).
- El usuario manda **imagen + nombre + tamaño real** (p. ej. "manzana, 8cm"). Nunca necesita saber el tamaño en GLB: lo calcula el código.
- Herramientas congeladas: nada nuevo en COPOX/CHSP-X que no sirva a esta línea.

## Cómo piensa el proceso
1. **Reconocer (hecho, solo código).** `tools/reconocer.py` mide la imagen y escribe una **ficha JSON**: tipo, partes, capacidades que exige (vocabulario controlado + decisiones de diseño por tipo), colores ajustados a la paleta, tamaño ALTH, parecido con la memoria y lo que no pudo medir (`no_medible`).
2. **¿Ya sé hacerlo? (hecho).** `tools/capacidades.py comparar` contra `kb/capacidades.json`: `dominada` (con evidencia en el repo), `parcial`, `fallida` (con intentos y motivo) o `desconocida`. "Ya sé" lo decide la evidencia.
3. **Cerrar las brechas** con `investigar` (por construir, sin IA; abajo). Máximo de brechas y de tiempo por corrida; lo que no cierre se reporta como faltante.
4. **Construir** con lo dominado más lo recién investigado, probar y esperar la aprobación del usuario.
5. **Aprender.** Al aprobar: `capacidades.py aprender … --estado dominada --evidencia <asset>/final.png` y `reconocer.py memorizar <asset>`. Si una prueba falla: `aprender … --estado fallida --motivo … --tecnica …`.

## Estado al 1 oct 2026 (rama `propuesta-reconocimiento`, 40 pruebas en verde, ~20 s)
**Hecho:**
- `tools/reconocer.py` (numpy + scipy + Pillow, ~2.4 s por imagen):
  - separa la figura del fondo por conectividad con el borde, sin perder objetos claros, y quita sombras de borde suave sin perder objetos grises;
  - mide silueta (proporción, solidez, redondez, simetría, huecos, piezas que sobresalen) y la traduce a torno / anillo / prisma / hoja / simetría;
  - colores dominantes en Lab ajustados a la paleta;
  - personaje = cabeza de piel con ojos (los lentes ya no parten la cara); separa pelo de piel por a*/b*; ropa (holgada si se abre hacia abajo), calzado, lentes;
  - dedos = huecos entre dedos (defectos de convexidad), calibrado: mano abierta de `mano-con-regla.jpg` → 4; manos de Theo → 0;
  - personajes: `dedos` se exige siempre por decisión de diseño (confianza 1.0), aunque la medición dé 0. La ficha de Theo ya marca "dedos" como brecha `fallida` con sus 3 intentos previos;
  - el nombre activa lo que no se ve en pixeles (vidrio, líquido, metal, vehículo…; `palabras` en `spec/capacidades_vocab.json`); metal no se deduce del color;
  - tamaño: un número = medida mayor, la otra sale de la proporción; sin número usa la memoria si el nombre coincide;
  - memoria `kb/huellas.json` con las huellas de los 5 assets aprobados; compara solo con huellas del mismo tipo.
- `spec/capacidades_vocab.json` (25 capacidades; `medible`, `palabras`, `requeridas_por_tipo`), `kb/capacidades.json`, `tools/capacidades.py`, `tests/test_reconocer.py` (figuras sintéticas + imágenes reales).

**Límites conocidos (no los escondas):**
- No sabe qué ES algo nuevo sin el nombre.
- De frente no distingue cilindro de caja (por eso `caja` no es medible).
- No ve lo que está oculto.
- Con infografías hay que usar `--recorte`.
- La memoria depende de la vista: la manzana de la infografía (3/4) se parece solo 0.28 a la memorizada (frente). Mejora si se memorizan las 4 vistas de `final.png`. Hazlo en T4.
- Las referencias de Theo dibujan los dedos juntos: **no sirven para medir cómo deben verse los dedos separados** (largo, grosor, separación). Esas cotas salen de `spec/alth_spec.json` → `cuerpo_base_95mm.dedos_L` reescaladas a Alpha en T0, y de la mano abierta de `refs/infografias/mano-con-regla.jpg` (con regla, 4 huecos medibles).

## Qué hay que construir (en orden; reporta al terminar cada bloque)

### T0 · Escala nueva
1. Medir Alpha por piezas con Blender (cabeza, torso, brazos, piernas, palma, anclas) y escribir `spec/alth_spec.json` v2 con `escala_alpha.s0` (cuerpo sin pelo / 1800 mm), arquetipos relativos a Alpha, k de conversión, cotas de dedos reescaladas y la altura real de Theo como parámetro. Al existir `escala_alpha.s0`, `reconocer.py` deja de usar el provisional (ya está programado).
2. `tools/redimensionar.py`: escala uniforme de los 5 assets y unifica unidades/eje; actualiza `data/medidas.csv`.

### T1 · Investigación sin IA: `tools/investigar.py <capacidad> "<problema>"`
Sin modelo de lenguaje, "investigar" es **encontrar candidatos y probarlos**, no "entender" textos:
1. Busca en `kb/`. Entrada `verified` vigente (misma versión de Blender) → la usa y termina. `failed`/`intentos_fallidos` con el mismo problema → la reporta y **no repite esa técnica**.
2. Si no hay nada útil: descarga páginas públicas (manual y API de Blender) con HTTP desde el runner y busca código publicado con la API de GitHub (token de Actions). Puntúa fragmentos por palabras clave de la capacidad (p. ej. BM25) y **extrae candidatos concretos de los ejemplos de código**: operadores y funciones (`bmesh.ops.*`, `bpy.ops.mesh.*`, modificadores) con sus parámetros, más la URL de donde salieron.
3. Escribe el brief en el formato de `copox/research/*.json` (fuentes con URL, técnicas encontradas y descartadas), lo pasa por `validate_research` y lo guarda como `unverified`.
4. **Solo una prueba real en Blender lo sube a `verified`.** Cada candidato se prueba con los auditores existentes; uno rechazado queda `failed` con el motivo.
5. Sin red, sin hallazgos o sin brief válido: se detiene con `RESEARCH_REQUIRED`. Nunca finge haber investigado.
- Pruebas sin red con fixtures (HTML y respuestas de la API guardadas); prueba real en Actions.

### T2 · Entrada única y receta (sin IA)
- Workflow `crear-asset.yml`: imagen (ruta o adjunta en un issue), nombre y tamaño real. Funciona desde la app de GitHub en el celular. Encadena `reconocer` → `capacidades comparar` → (`investigar` si hay brechas) → receta → construir.
- `spec/receta.schema.json` + validador. **La receta la arma código a partir de la ficha**: p. ej. el perfil de `alth.torno` sale de los anchos por banda de la silueta (`alth/silueta.py` → `perfil_anchos`), las piezas de las protuberancias, los colores del ajuste a paleta y las medidas de `tamano_alth_mm`.
- `tools/construir_receta.py` arma el asset, renderiza la hoja de 4 vistas y corre la verificación existente.

### T3 · Ajuste numérico
Búsqueda sobre los parámetros de la receta contra la silueta de la referencia (IoU), máx. 3 rondas, reutilizando el torneo de COPOX con variaciones de parámetros como candidatos. En estancamiento: `PLATEAU` y se reporta al usuario. No hay IA de respaldo.

### T4 · Revisión y publicación
- Hoja nueva junto a la referencia (y a la versión anterior si existe) como comentario del issue. El usuario aprueba o rechaza con una etiqueta.
- Al aprobar: GLB (raíz ×0.01, eje correcto), .blend, final.png y fila en `data/medidas.csv`, a `main`. Luego `capacidades.py aprender` con el asset como evidencia y `reconocer.py memorizar` (amplíalo a las 4 vistas).
- Sin aprobación no se publica nada.

### T5 · Prueba de aceptación 1: la manzana
- Misma imagen que la manzana actual (`refs/infografias/objeto-01-manzana.png --recorte 0.52,0.1,1,1`), "manzana, 8cm", escala nueva, sin intervención manual.
- Criterios automáticos: dimensiones ±2 %, tris ≤ 500, paleta, sin flotantes, apoyo Z=0, IoU ≥ el de la manzana actual.
- **Que "supera" a la manzana lo decide el usuario** con la hoja lado a lado. Meta: menos de 15 minutos de corrida.

### T6 · Prueba de aceptación 2: dedos separados en Theo
- Entrada: `refs/personajes/joven-rubio.jpg`, "Theo, 180cm". La ficha ya marca "dedos" como brecha `fallida` (decisión de diseño + 3 intentos previos en `kb/`).
- El proceso investiga solo (T1), sin repetir las 3 técnicas fallidas, y propone un candidato en una rama aparte. Alpha nunca se modifica ni se reemplaza; el candidato no se promueve solo.
- Criterio automático mínimo: en la hoja de 4 vistas del candidato, `reconocer.py` debe contar ≥ 3 huecos entre dedos en al menos una mano visible (la misma medición que da 4 en `mano-con-regla.jpg`), sin romper mesh integrity ni las regiones congeladas. La aprobación final es visual y del usuario.
- Incluye el candidato reducido de la malla de SAM a un tope razonable, también investigado por el proceso (soldar vértices, decimar/retopologizar protegiendo cara y dedos), con IoU y volumen medidos contra Alpha.

## Reglas de cierre
- Trabaja en una rama que parta de `propuesta-reconocimiento` (p. ej. `propuesta-linea-unica`); nada a `main` sin aprobación del usuario.
- Pruebas (`pytest`) en verde y al menos una corrida real en Actions por bloque.
- Reporte de 5 líneas por bloque: qué quedó, qué se probó, qué falló, qué falta, cuánto tardó la corrida.
- Si un bloque no avanza en dos intentos, detente y dilo; no encadenes versiones por inercia.
