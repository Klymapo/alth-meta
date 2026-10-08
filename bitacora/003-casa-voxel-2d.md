# Bitácora 003 · Casa voxel 2D (16×17)

**Fecha de la entrega:** 2026-10-08  
**Proyecto:** AlasTheo / ALTH-META · Laboratorio de modelado GLB  
**Estado:** modelo generado localmente, pendiente de revisión visual y de subir el código de la entrega 003 al repositorio. Bitácora conservada en la rama experimental, sin fusionar a `main`.

## Objetivo
Reconstruir, a partir de la imagen de referencia del usuario, un paisaje de estilo pixel art como **mosaico voxel de una sola capa**: casa con techo rojo, puerta, ventana y chimenea; árbol, sol, nube, cielo y césped.

## Especificación
- Resolución: **16 columnas × 17 filas**.
- Profundidad: **1 vóxel** (todas las celdas en `z=0`).
- Origen: esquina inferior izquierda del mosaico.
- Geometría: una celda cúbica de tamaño 1 por píxel lógico.
- Referencia de medidas: casa 7×4, techo 9×5, puerta 1×2, ventana 1×1, chimenea 1×2, tronco 1×2, copa 5×5, nube 4×3, sol 2×2, césped 16×2, cielo 16×12.
- **Interpretación:** algunas dimensiones de los elementos se solapan y no describen un mosaico 16×17 completamente libre de ambigüedades. Esta primera entrega es una **aproximación estilizada**, no una réplica píxel a píxel certificada de la referencia.

## Resultados medidos del GLB
- **272 vóxeles** (16×17×1).
- **610 caras exteriores** exportadas.
- **1022 caras interiores** omitidas al encontrar vóxeles adyacentes, independientemente del color.
- **511 pares de vóxeles adyacentes**.
- **1220 triángulos** y **2440 vértices** en los polígonos externos.
- **15 materiales** definidos en la paleta.
- GLB versión **2.0**, tamaño **76 736 bytes**.
- SHA-256 del modelo: `a5aa2ff87cb19a16024adf8d4a1d82aade09001b714ee4c621178f1afaba4d0b`.

## Evidencia de la entrega
Cuatro **capturas del GLB real**: frontal, isométrica, superior y lateral, además de una lámina con las cuatro vistas. Validación local: cabecera GLB, longitud, SHA-256, 272 celdas y presencia de los cinco PNG: **correctos**.

Archivos locales:
- `experimentos/voxel-glb/layout_casa_16x17.json` — coordenadas, 15 colores y medidas.
- `experimentos/voxel-glb/generar_mosaico_voxel.py` — exportador paramétrico GLB sin caras compartidas.
- `experimentos/voxel-glb/render_mosaico.py` — genera capturas leyendo materiales y mallas del GLB.
- `experimentos/voxel-glb/entrega_mosaico.py` — salida automatizada.
- `salidas/entrega_003_casa_2d/casa_2d_voxel.glb`.
- `salidas/entrega_003_casa_2d/capturas/mosaico_4_vistas.png`.
- `salidas/entrega_003_casa_2d/manifiesto.json`.

## Revisión y pendientes
1. Comparar la vista frontal con la imagen original y corregir posición y contorno de sol, nube, árbol, techo y chimenea según la revisión del usuario.
2. Publicar también los scripts, el layout y los artefactos de la entrega 003 en GitHub; por ahora **solamente esta bitácora** está subida al repositorio.
3. Integrar un trabajo de GitHub Actions para regenerar automáticamente los cinco PNG.
4. No modificar los modelos aprobados de Theo, Alastor ni `main`.

**Resultado:** entrega local funcional, con evidencia visual; fidelidad de la composición todavía sujeta a revisión.
