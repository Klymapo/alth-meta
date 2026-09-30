# COPOX · validación real 2026-09-30

## Alcance

Esta validación usa GitHub Actions + Blender headless + el adapter ALTH Character. No usa APIs de IA.

## Integración baseline + candidato

Run: `36742622298` — **PASS**.

Comprobado:

- Blender/bpy se instala y corre sin PC local.
- baseline reproducible desde JSON paramétrico;
- candidato exportado a GLB;
- `VERIFICACION OK` de ALTH;
- hoja de cuatro vistas;
- overlays front/side/back/3/4;
- coordenadas glTF declaradas como Y-up;
- registro visual bloqueado a baseline;
- landmarks de referencia detectados automáticamente;
- un cambio sólo de pelo no crea regresiones ficticias en torso/piernas y mantiene brazos dentro de tolerancia de prueba.

## Torneo real de tres candidatos

Run: `36743177348` — **PASS**.

Los tres candidatos partieron de la misma baseline `hair.escala = 1.30`.

| candidato | cambio | resultado | vetos |
|---|---|---|---|
| `t01-c01` | `hair.escala 1.30 → 1.25` | REJECTED | LikenessLead, PositiveChangeAuditor, OrganicSilhouette, AnatomyCoherence, HairAgent, LearningArchitect |
| `t01-c02` | `hair.escala 1.30 → 1.35` | ELIGIBLE / PROMOTED | ninguno |
| `t01-c03` | `hair.sesgo_atras 2.5 → 3.5` | REJECTED | LikenessLead, ClearDifferenceGate, HairAgent, LearningArchitect |

### Ganador

`t01-c02` obtuvo:

- weighted gain: `+0.1479 pp`;
- hair regional gain: `+0.6737 pp`;
- visible delta: `4.5934 %`;
- `OrganicSilhouette = PASS`;
- `AnatomyCoherence = PASS`;
- **10/10 auditores aplicables PASS**;
- 5 auditores regionales no aplicables quedaron `N-A`.

Sólo el ganador produjo `report.md`, y el reporte incluyó `hoja.png` y los cuatro overlays. Los candidatos rechazados no fueron promovidos ni publicados.

## Conclusión técnica

Validado en runner real:

`baseline → 3 siblings → build → capture → audit → veto → unanimous winner → report`

El workflow de torneo quedó después de la prueba como `workflow_dispatch` para evitar consumir runners en cada commit.

## Pendiente antes de habilitar scheduler productivo

La baseline interna de una campaña autónoma debe persistir entre runs sin convertir cada promoción interna en un release de `main`. Se recomienda una rama de estado por cassette (`copox/state/<cassette-id>`) o mecanismo equivalente con historial reproducible. Hasta resolver esta persistencia, los cassettes reales permanecen fuera de `copox/cassettes/enabled/`.
