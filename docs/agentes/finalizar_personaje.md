# Protocolo ALTH · finalizar un personaje con IA

Este protocolo reduce rondas sin eliminar el control humano. Se usa cuando un personaje ya tiene `spec.json`, `build.py`, referencias y al menos una hoja renderizada.

## Roles

| Rol | Responsabilidad | No puede hacer |
|---|---|---|
| Constructor IA | Proponer el código completo conforme al brief | Aprobarse a sí mismo, exportar final o ampliar el alcance |
| Blender + verificadores | Construir, medir y producir evidencia repetible | Decidir semejanza o intención artística |
| Revisor visual IA | Comparar evidencia y enumerar bloqueos | Editar código o dar aprobación humana |
| Humano | Aceptar, pedir una corrección o cancelar | — |

## Flujo de ronda única

1. Leer `CLAUDE.md`, la spec global, la spec del asset y `assets/<asset>/brief_final.md`.
2. Partir de la mejor rama verificada disponible, no necesariamente de la última vuelta.
3. Ejecutar una sola propuesta integral con `tools/bucle.py`; el brief se incorpora al prompt automáticamente.
4. Ejecutar Blender y la verificación determinista. Si el build falla, permitir una reparación técnica que no rediseñe el personaje.
5. Entregar al revisor la referencia, hoja nueva, hoja anterior, `reporte.json`, `revision.json` y resumen de cambios.
6. El revisor emite `APROBABLE`, `UNA_CORRECCIÓN` o `REHACER`. Sólo `UNA_CORRECCIÓN` habilita un segundo intento visual.
7. El humano revisa las cuatro vistas. Sólo su aprobación habilita render final, GLB y commit a `main`.

## Presupuesto de uso

- 1 intento integral de construcción.
- 1 corrección visual opcional, limitada a los bloqueos concretos del revisor.
- Reparaciones técnicas sólo cuando el código no ejecuta; no deben convertirse en rediseños encubiertos.
- Si el segundo render sigue en `REHACER`, detenerse y corregir el brief o la herramienta. No gastar más llamadas repitiendo el mismo enfoque.

## Comando recomendado para Theo

Desde CHSP-X: elegir `assets/joven_rubio`, una vuelta, proveedor gratuito disponible y base automática. El bucle encadena desde la mejor rama del asset e incluye `assets/joven_rubio/brief_final.md` sin pegarlo en la nota.

En terminal, el equivalente es:

```bash
python3 tools/bucle.py correr assets/joven_rubio --vueltas 1 --proveedor gemini \
  --nota "Usa la mejor versión verificada como punto de partida. Ejecuta el brief final completo."
```

El proveedor es reemplazable. El contrato del prompt, las pruebas de Blender y la revisión no dependen de una marca de IA.

## Evidencia mínima para decidir

- hoja de contacto de la versión elegida, con cuatro vistas;
- referencia principal de cuatro vistas y referencia 3/4;
- estado de build y `VERIFICACION OK / CON FALLAS`;
- cotas fallidas, triángulos, colores, flotantes y apoyo;
- lista exacta de archivos modificados y resumen de cambios;
- huella/manifest de la revisión para asegurar que la aprobación corresponde al código visto.

Una verificación `OK` es necesaria, pero no equivale a semejanza visual. Un IoU mayor tampoco vence por sí solo a una versión con mejor identidad, cara, pelo y vestuario.
