---
name: revisar-alth
description: Revisa de forma independiente una iteración visual ALTH-META contra referencias, brief, medidas y reportes, sin editar código. Úsala al evaluar una hoja de cuatro vistas, decidir si un personaje es aprobable o producir bloqueos concretos para una única corrección.
---

# Revisar un asset ALTH-META

Actuar en modo de solo lectura. Leer `CLAUDE.md`, `docs/agentes/finalizar_personaje.md`, la spec y el brief del asset. Comparar la referencia principal y secundaria con la hoja actual y, si existe, la anterior. Leer `reporte.json`, `revision.json` y el resumen de cambios.

Priorizar identidad; silueta en cuatro vistas; cara, pelo y vestuario; después intersecciones, flotantes, apoyo, paleta, cotas y triángulos. No inventar medidas desde imágenes. Separar hechos medidos de juicios visuales. No tratar `VERIFICACION OK` ni IoU como aprobación artística.

Entregar `VEREDICTO: APROBABLE | UNA_CORRECCIÓN | REHACER`, bloqueos numerados con evidencia, lectura de frente/lateral/espalda/3/4, estado técnico, archivos modificados y una única siguiente acción. No escribir archivos, devolver código ni aprobar en nombre del usuario.
