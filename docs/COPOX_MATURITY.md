# COPOX · Madurez transversal M0–M5

La madurez es una propiedad verificable de cada módulo, no una etiqueta manual. COPOX calcula el nivel a partir de capacidades existentes y bloquea loops generales cuando una región crítica no alcanza el mínimo requerido.

## Niveles

| Nivel | Significado | Capacidades mínimas |
|---|---|---|
| M0 | Sin cobertura | ninguna |
| M1 | Observable | evidencia |
| M2 | Auditable | evidencia + auditor |
| M3 | Editable | M2 + mutador |
| M4 | Aprendizaje seguro | M3 + learning + regression guard |
| M5 | Loop autónomo | M4 + persistencia + loop gate |

No se permite saltar niveles. Tener persistencia, por ejemplo, no convierte a un módulo sin auditor en M5.

## Learning-first

La prioridad antes de mutar es entender qué cambio requiere la referencia. Cada módulo declara:

- preguntas de diagnóstico;
- señales/mediciones disponibles;
- procesos existentes;
- capacidades reales;
- qué falta para subir al siguiente nivel.

`python3 -m copox.maturity copox/maturity/theo.json --min-level M4 --output maturity.md`

genera la matriz y el learning backlog ordenado por madurez y prioridad.

## Cobertura de personaje

`copox/maturity/theo.json` registra todas las áreas relevantes del modelo:

- silueta y proporciones globales;
- cabeza, pelo, orejas, rostro y cuello;
- torso y hombros;
- brazos, codos/antebrazos;
- manos, dedos/pulgar;
- pelvis, piernas, rodillas, tobillos, pies/calzado;
- materiales/color blocking;
- malla/topología;
- orientación;
- preparación para rig.
- controles de ojos y boca animables.

Las regiones no implementadas no se ocultan con `N-A`: quedan con su nivel real (M0/M1/M2...).

## Gate de ejecución

Un cassette puede declarar:

```json
"maturity": {
  "coverage": "copox/maturity/theo.json",
  "min_level": "M4",
  "critical_only": true,
  "block_execution": true
}
```

El engine evalúa la cobertura **antes de `prepare` y antes de producir candidatos**. Si falla:

- crea manifiesto `MATURITY_BLOCKED`;
- genera `maturity.json` con blockers y learning backlog;
- no ejecuta mutadores;
- no produce candidatos;
- devuelve código 4.

El scheduler usa `copox.discover`: los cassettes bloqueados por madurez no entran en la matrix de ejecución.

## Validaciones técnicas

Una workflow de integración/tournament puede establecer `block_execution=false` en una copia temporal del cassette para validar un proceso concreto. Esto no cambia el coverage ni desbloquea producción. El manifiesto conserva `maturity.ready=false` para que la excepción sea explícita.

## Catálogo general

`copox/maturity/modules.json` aplica el mismo modelo a todos los tipos principales del motor:

- ALTH Character GLB;
- ALTH Character legacy;
- ALTH Asset;
- Rig;
- Texture/material;
- Godot UI;
- Godot Script;
- Smoke/framework.

Así el concepto de madurez se reutiliza con cualquier cassette futuro: personajes, assets, texturas, rigs, UI o scripts.

## Política para Theo Alpha

Antes de arrancar el loop general de Theo, todas las áreas críticas deben alcanzar al menos **M4**. El objetivo estable es M5. Una campaña local puede desarrollarse y validarse mientras tanto, pero no puede presentarse como mejora integral del personaje.

## Validación M4 de Theo Alpha

La cobertura actual contiene 23 áreas: 22 en M4 y pelo en M5. Los procesos globales,
materiales, topología, rig y controles faciales fueron ejercitados con el GLB aprobado.
Los workflows reproducen evidencia, auditoría, mutación, diagnóstico y regresión.

M4 certifica la disponibilidad del proceso técnico. La aprobación artística y la
calidad final de pesos, dedos, ojos y boca requieren revisión de sus resultados.
El cassette de Theo continúa fuera de `copox/cassettes/enabled/`.

Orientación tiene un gate de render; su corrección/promoción autónoma todavía
no tiene una validación completa. Por eso su capacidad `loop_gate` queda en
`false` y su nivel es M4.

Resultados y limitaciones: [COPOX_M4_VALIDATION_2026-09-30.md](COPOX_M4_VALIDATION_2026-09-30.md).
