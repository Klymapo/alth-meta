# COPOX

Motor genérico de loops auditados para ALTH-META y el resto del desarrollo del juego.

COPOX no modela, no riggea y no construye UI por sí mismo. Orquesta un **cassette** que declara cómo producir candidatos, ejecutar el dominio, capturar evidencia, auditar, aprender, promover y reportar.

## Ejecutar el smoke test

```bash
python3 -m copox.engine copox/cassettes/examples/smoke.json
```

El smoke crea tres candidatos. `t01-c01` falla deliberadamente; `t01-c02` y `t01-c03` pasan; `t01-c03` debe ganar por score. Sólo entonces se genera `report.md` con captura.

## Habilitar un cassette para el scheduler

Los cassettes activos viven en:

```text
copox/cassettes/enabled/*.json
```

El workflow `COPOX · Scheduler` los descubre cada 15 minutos. Cassettes diferentes pueden correr en paralelo; el mismo cassette queda serializado por `concurrency.group`.

No hay cassettes reales habilitados de fábrica en esta primera fase para evitar modificar assets automáticamente antes de instalar sus adaptadores.

## Estados

- `RUNNING`: campaña en curso.
- `REJECTED`: candidato vetado por evidencia o auditor.
- `ELIGIBLE`: todos los auditores aplicables dieron PASS.
- `APPROVED_INTERNAL`: ganador seleccionado; aún ejecutando promoción.
- `PROMOTED`: promoción completada; puede publicarse reporte.
- `PLATEAU`: se agotó el presupuesto sin unanimidad; baseline intacta.

## Regla de publicación

Un resultado visible necesita simultáneamente:

1. candidato `ELIGIBLE`;
2. todos los auditores aplicables en `PASS`;
3. manifiesto `APPROVED_INTERNAL` o `PROMOTED`;
4. al menos una captura;
5. evidencia requerida por el cassette.

Si falta cualquiera, `copox.report` se niega a generar el reporte.

## Perfiles incluidos

- `alth_character.json`
- `alth_asset.json`
- `rig.json`
- `texture.json`
- `godot_ui.json`
- `godot_script.json`
- `smoke.json`

Consulta `docs/COPOX_LOOP_ENGINE.md` para la arquitectura completa.
