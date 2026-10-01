# Métodos y procesos intentados

Registro de los enfoques que se han probado o preparado para llevar las referencias de AlasTheo a modelos 3D utilizables. Este documento evita repetir experimentos sin recordar qué problema resolvían, qué falló y qué merece reutilizarse.

## Estado comprobado al integrar (2026-10-01)

Este documento incluye memoria histórica de ALASTHEO, no resultados reejecutados de todos sus métodos. La rama SAM 3D se comprobó en el commit `cd486312ffda675b3c7103c1a5132c3311e5f268`: existen 11 GLB de referencia; permanecen en esa rama histórica.

COPOX ya ejecutó rondas reales con Blender y auditoría visual en Actions. La última ronda de micro-valles produjo exactamente tres hermanos y rechazó los tres por semántica/topología y pérdida de ventaja frente a Valley Sculpt. Ninguno fue promovido. Véanse [resultados auditados](COPOX_MICRO_VALLEYS_2026-10-01_CORRECTION.md) y [registro de investigación](../copox/research/README.md). El texto histórico sobre beta no equivale a ausencia de esas ejecuciones verificadas ni a aprobación final de Theo.

Los proveedores comerciales mencionados son antecedentes; la integración y los runners de auditoría no usan tokens ni APIs comerciales.

## Leyenda de estado

- **ACTIVO** — forma parte del flujo recomendado actual.
- **ÚTIL COMO APOYO** — aporta una parte del proceso, pero no produce por sí solo el resultado final.
- **EXPERIMENTAL** — hubo pruebas reales, pero aún no es estable o suficientemente validado.
- **BLOQUEADO / LIMITADO** — el enfoque mostró una limitación estructural para el objetivo de likeness.
- **PENDIENTE** — diseñado o integrado parcialmente, sin validación completa con Theo.

## Resumen rápido

| Método | Objetivo | Resultado | Estado |
|---|---|---|---|
| Referencias maestras + cuatro vistas | Definir likeness y volumen | Base visual más fiable | ACTIVO |
| Medidas/anclas + ALTH-META procedural | Controlar proporciones exactas y reproducibilidad | Muy bueno para cotas; insuficiente por sí solo para likeness fino | ACTIVO / APOYO |
| SAM 3D de Meta | Inferir proporciones desde reconstrucciones | 11 GLB útiles como evidencia; sin escala real ni rig | ÚTIL COMO APOYO |
| Proxy procedural Theo v5 | Crear maniquí controlado de 95 mm | Buen scaffold de medidas, no image-derived | ÚTIL COMO APOYO |
| TripoSR single-image en Colab | Obtener un teacher 3D rápido | Generó coarse teacher; frente mejor que perfil/espalda | ÚTIL COMO APOYO |
| Limpieza conservadora de GLB | Mejorar superficies sin rediseñar | Mejora técnica, no mejora identidad | ACTIVO / APOYO |
| Pixal3D multivista en Colab | Reconstruir usando frente/perfil/espalda | Pipeline preparado y parcialmente ejecutado; stack complejo | EXPERIMENTAL |
| Modelado/refinado manual en Blender | Corregir geometría según referencia | Máximo control, pero requiere trabajo manual | ACTIVO |
| Stylizer: texto/imagen → 2D → 3D | Pipeline modular general | Funcional como arquitectura; Theo no validado como likeness final | EXPERIMENTAL |
| CHSP-X / COPOX / bucle IA-Blender | Automatizar iteraciones, pruebas y aprobación | Flujo técnico construido; aprobación completa aún beta | EXPERIMENTAL |
| Ronda única de agentes | Reducir llamadas de IA y corregir integralmente | Buen proceso de dirección; no sustituye el modelado | ACTIVO / APOYO |
| Derivar Detective desde Theo | Reutilizar una base corporal aprobada | Método razonable, pero Detective debe conservar identidad propia | PENDIENTE DE VALIDACIÓN |

---

## 1. Referencias visuales maestras y turnaround

### Idea
Usar una referencia individual para identidad y una hoja de cuatro vistas para silueta/volumen. La referencia visual no se reemplaza por renders intermedios.

### Cómo se usó
- `joven-rubio-4-vistas.jpg`: autoridad de silueta, perfil, espalda, volumen y colocación.
- `joven-rubio.jpg`: autoridad de identidad, expresión, cara, pelo y vestuario.
- Comparativas de personajes y objetos: escala relativa.
- Renders del modelo: solo evidencia del estado actual.

### Resultado
Es el criterio más estable para juzgar likeness. Evita optimizar una sola vista y descubrir tarde que el perfil o la espalda no funcionan.

### Limitación
Una imagen estilizada no debe usarse para inventar cotas cuando ya existen medidas congeladas.

Estado: **ACTIVO**.

---

## 2. ALTH-META procedural con medidas y anclas

### Idea
Construir personajes mediante Python/Blender a partir de una especificación: cabeza, torso, extremidades, pelo, ropa, paleta y límites técnicos reproducibles.

### Qué aporta
- Medidas explícitas.
- Builds repetibles.
- Verificación automática.
- Hojas de revisión multivista.
- Posibilidad de cambiar parámetros sin editar manualmente cada vértice.

### Resultado con Theo
El enfoque dio una base cuantificada y permitió congelar cotas importantes. Sin embargo, una versión puede cumplir medidas y aun no parecerse lo suficiente al personaje; la identidad visual exige pelo, cara, ropa y lectura en cuatro vistas.

El brief actual de Theo fija, entre otras cotas, cuerpo base de 95 mm, cabeza de 40 × 34.5 mm, pierna de 24 mm y profundidades específicas. Esas medidas se consideran restricciones, no una garantía de likeness.

Fuente histórica: `Klymapo/alth-meta`.

Estado: **ACTIVO**, especialmente para restricciones y reproducibilidad.

---

## 3. SAM 3D (Meta) como fuente de proporciones

### Idea
Generar varias reconstrucciones desde imágenes de Theo y comparar sus proporciones, en lugar de confiar en una sola reconstrucción.

### Qué se intentó
En `sam3d-proporciones-theo` se conservaron 11 GLB y vistas de inspección. Cinco modelos se usaron como candidatos para anclas; otros fueron descartados o quedaron sin filtrar.

### Resultado
Sirvió para estimar relaciones de altura, profundidad y proporciones generales. También mostró por qué una reconstrucción automática no puede tomarse como verdad geométrica: las mallas venían normalizadas a una caja unitaria, sin escala real, sin rig y sin separación semántica de partes.

Un modelo se descartó para mediciones de altura porque un pico de pelo alteraba el máximo del bounding box. Tampoco se pudo aislar con seguridad el ancho del torso en modelos donde brazo y torso quedaban unidos visualmente.

### Decisión
SAM 3D es evidencia estadística/geométrica auxiliar, no asset final y no autoridad visual.

Estado: **ÚTIL COMO APOYO**.

---

## 4. Proxy procedural de Theo v5

### Idea
Construir un proxy controlado usando las medidas ya derivadas: cabeza, mandíbula/mejillas, ojos, pupilas, sonrisa, orejas, nariz, cabello por capas, extremidades, manos, puños y zapatos.

### Resultado
Se obtuvo un scaffold de 95 mm con anclas conocidas. Es útil para comparar proporciones y como base para una reconstrucción posterior.

### Limitaciones conocidas
- No deriva su geometría directamente de la imagen.
- No tiene rig.
- No tiene UV de producción.
- Materiales planos.
- Requiere validación visual en Blender contra las cuatro vistas.

### Decisión
Conservarlo como **maniquí/proxy**, no como modelo final.

Estado: **ÚTIL COMO APOYO**.

---

## 5. TripoSR single-image en Google Colab

### Idea
Obtener rápidamente una malla 3D desde una sola imagen limpia de Theo y usarla como *teacher* o referencia geométrica.

### Configuración aprendida
- Google Colab con Tesla T4.
- Mantener el stack CUDA/PyTorch de Colab cuando sea posible.
- Evitar instalar el `requirements.txt` completo si rompe dependencias.
- Usar `scikit-image` como alternativa cuando `torchmcubes` da problemas.
- `rembg` opcional.
- Entrada frontal limpia: fondo y sombra mal preparados pueden producir una malla tipo placa.
- Validar orientación XYZ después de marching cubes.

### Resultado
TripoSR sí produjo un GLB útil como **coarse teacher**. La coincidencia era mejor de frente que en perfil/espalda y el cabello posterior quedó condicionado por lo que la imagen única podía inferir.

Una versión del teacher se normalizó a 95 mm, se centró y se apoyó en Z=0. La lección principal fue que TripoSR puede resolver volumen inicial, pero no debe tratarse como reconstrucción definitiva de un personaje estilizado con referencias multivista.

Estado: **ÚTIL COMO APOYO**.

---

## 6. Limpieza conservadora del GLB generado

### Idea
Mejorar un GLB existente sin alterar sus proporciones: limpiar topología, recalcular normales y aplicar suavizado ligero.

### Qué se probó
Sobre el teacher de TripoSR se hizo una limpieza conservadora y Taubin ligero, evitando rediseñar la malla.

### Resultado
Las superficies quedaron más limpias y coherentes, pero el likeness prácticamente no cambia si la geometría base está equivocada. Es una etapa de **calidad de malla**, no de identidad.

### Decisión
Usar después de obtener una forma razonable; nunca esperar que “limpiar” arregle una cabeza, pelo o perfil incorrectos.

Estado: **ACTIVO / APOYO**.

---

## 7. Pixal3D multivista en Google Colab

### Idea
Superar la limitación single-image usando frente, perfil y espalda; añadir 3/4 cuando el pipeline sea estable.

### Pipeline preparado
- Entorno aislado Python 3.10.
- Torch/CUDA compatibles con T4.
- `ATTN_BACKEND=sdpa`.
- Modo `--low_vram`.
- Resolución objetivo 1024.
- Primera corrida: frente/perfil/espalda.
- Segunda corrida opcional: 3/4.

Durante las iteraciones se trabajó con dependencias como NATTEN, MoGe, CuMesh, FlexGEMM, O-Voxel, nvdiffrast/nvdiffrec y backend de atención.

### Resultado
El pipeline llegó a etapas reales de ejecución, pero presentó fricción de dependencias/memoria y no quedó demostrado como proceso end-to-end estable y repetible para Theo en T4. Fue prometedor porque ataca directamente el problema multivista, pero el coste técnico fue alto.

### Decisión
Mantenerlo documentado como ruta experimental; no volver a instalar componentes al azar. Partir del notebook/stack que ya registró las incompatibilidades aprendidas.

Estado: **EXPERIMENTAL**.

---

## 8. Refinado manual en Blender

### Idea
Usar el GLB/proxy como punto de partida y corregirlo directamente contra las referencias.

### Flujo probado
- Trabajar en vistas ortográficas.
- Superponer o consultar referencias con opacidad.
- Corregir silueta y perfiles primero.
- Refinar extremidades para evitar aspecto “masudo”.
- Limpiar uniones cubo-esfera o transiciones demasiado mecánicas.
- Tratar ojos, boca y cabello pensando desde temprano en futuras piezas animables.
- Comprobar frente, laterales, espalda y 3/4 después de cada cambio importante.

### Resultado
Es el método con mayor control para arreglar errores específicos de likeness. También es el que más depende de intervención humana y habilidad de modelado.

### Decisión
Debe ser la capa de acabado cuando el modelo automático/procedural ya esté suficientemente cerca. Automatizar tareas repetitivas, no las decisiones visuales finas.

Estado: **ACTIVO**.

---

## 9. Pipeline Stylizer: idea → prompt → imagen → 3D

### Arquitectura
`Idea en español → prompt técnico → imagen 2D → modelo 3D (.glb) → Blender`

Componentes experimentados/preparados:
- Ollama + Qwen para estilizar prompts.
- Agnes AI para imagen 2D cuando se parte de texto.
- TRELLIS.2 como proveedor 3D.
- three.ws como adaptador alternativo/draft.
- MeshForge3D y multivista contemplados como extensiones.
- Preparación posterior para Godot mediante Blender.

### Resultado
La arquitectura modular es buena: cada proveedor puede cambiarse sin romper todo el sistema. También permite partir de una imagen propia y saltarse la generación 2D.

### Limitación para Theo
Un pipeline general de image-to-3D no garantiza likeness estilizado ni consistencia multivista. Debe evaluarse contra las referencias maestras.

Repositorio: `Klymapo/stylizer`.

Estado: **EXPERIMENTAL para Theo**, útil como infraestructura general.

---

## 10. CHSP-X / COPOX / bucle IA ↔ Blender

### Idea
Reducir intervención manual y coste de IA automatizando:

`encargo → modificación → Blender headless → pruebas → renders/evidencia → revisión humana → autorización → export/commit`

Durante la evolución del proyecto se usaron nombres como COPOX y CHSP-X para este concepto de mesa/bucle de revisión.

### Qué ya existe
- Ramas `bucle/*`.
- Pruebas Python.
- Hojas de revisión.
- `revision.json` y huellas SHA-256.
- Interfaz CHSP-X.
- Workflow de aprobación.
- Reglas para impedir exportar/mergear un asset distinto del revisado.
- Posibilidad de pedir otra vuelta o aprobar el SHA exacto.

### Resultado
El sistema técnico está construido y sus pruebas internas pasan, pero el propio repositorio lo considera **beta** hasta completar una corrida real de Actions con Blender/token y una aprobación completa. Ningún asset había sido aprobado todavía mediante el flujo documentado; Theo seguía explícitamente marcado como no final.

### Decisión
Conservar como capa de orquestación y trazabilidad. No confundir automatización del flujo con generación de likeness.

Estado: **EXPERIMENTAL**.

---

## 11. Ronda única con agentes especializados

### Idea
En lugar de gastar muchas llamadas corrigiendo un detalle por turno, pedir una revisión integral de cabeza/rostro, pelo, torso/ropa, brazos/manos, piernas/pies, coherencia anatómica y verificación.

### Regla importante
La IA propone/corrige, Blender ejecuta pruebas y renders, y una persona aprueba. El agente no declara el asset final por su cuenta.

### Resultado
Es un buen método de dirección para reducir iteraciones tímidas y mantener todas las correcciones coordinadas. El brief final de Theo exige resolver identidad, pelo, cara, vestuario y cuatro vistas en conjunto.

### Limitación
Si la herramienta base no puede representar correctamente la forma, repetir prompts no arregla el cuello de botella. Después de una segunda revisión claramente fallida conviene cambiar el brief, la geometría base o la herramienta.

Estado: **ACTIVO / APOYO**.

---

## 12. Derivar Detective desde Theo

### Idea
Una vez que Theo tenga una base corporal suficientemente buena, reutilizar estructura, silueta general, extremidades y proporciones técnicas para construir Detective cambiando tamaños, masas, cabeza/rostro, pelo, paleta y vestuario.

### Qué se ha intentado
Se han generado versiones de Detective tomando como guía la versión reciente de Theo para conservar lenguaje de formas y coherencia entre personajes.

### Riesgo
Un “recolor + resize” no basta. Si la silueta de Theo domina demasiado, Detective pierde edad e identidad. La referencia individual de Detective manda sobre la reutilización.

### Decisión
Reutilizar únicamente lo que realmente sea común (topología/base corporal/convenciones), y volver a validar likeness desde cero contra la referencia de Detective.

Estado: **PENDIENTE DE VALIDACIÓN**.

---

# Flujo recomendado a partir de lo aprendido

1. Fijar las referencias maestras y las cotas que no pueden cambiar.
2. Elegir la mejor base disponible: modelo procedural/teacher/malla existente.
3. Comparar las cuatro vistas antes de añadir detalle fino.
4. Corregir primero silueta, cabeza, profundidad y extremidades.
5. Resolver identidad: cara, pelo y vestuario.
6. Ejecutar limpieza técnica sin confundirla con likeness.
7. Generar renders de frente/perfil/espalda/3-4 y revisar contra las referencias.
8. Registrar medidas, decisiones y limitaciones.
9. Solo después: rig, ojos/boca animables, optimización y export final.
10. La aprobación humana precede a cualquier estado `final`.

# Fuentes históricas principales

- `Klymapo/alth-meta` — referencias, medidas, ALTH procedural, SAM 3D, CHSP-X y agentes.
- `Klymapo/stylizer` — pipeline modular idea/imagen → 3D.
- Notebooks de Colab del proyecto — TripoSR y Pixal3D.
- Conversaciones de producción del proyecto 3D — refinamiento manual, teacher cleanup y derivación de Detective.

Este archivo es un registro vivo: cuando se pruebe un método nuevo, añadir **objetivo, entrada, configuración relevante, resultado, limitaciones y decisión**, no solo el nombre de la herramienta.