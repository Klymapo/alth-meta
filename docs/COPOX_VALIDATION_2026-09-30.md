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

## Persistencia entre campañas

`copox/state.py` implementa una rama Git mínima por cassette, por ejemplo `copox/state/theo-character`.

Cada promoción interna guarda únicamente:

- `baseline.json` — parámetros de la baseline aceptada;
- `state.json` — cassette, candidato, run y commit padre.

La rama de estado es independiente de `main`: una promoción interna no publica un GLB final ni ensucia la rama de release.

La CI `36744495033` validó:

1. creación de la primera baseline de estado;
2. lectura de esa baseline por el siguiente ciclo;
3. segunda promoción;
4. lectura de la segunda baseline;
5. que el segundo commit de estado tiene al primero como padre.

Así se conserva un historial reproducible y no se mezclan estados de cassettes distintos.

## Conclusión técnica

Validado:

`seed/main → state branch → baseline → sibling tournament → build → capture → audit → veto → unanimous winner → state branch siguiente → report`

El workflow de torneo quedó después de la prueba como `workflow_dispatch` para evitar consumir runners en cada commit.

## Estado de activación

La infraestructura necesaria para campañas autónomas ya existe, pero **ningún cassette productivo está todavía en `copox/cassettes/enabled/`**. Por tanto el scheduler no está modificando Theo ni ningún otro asset en segundo plano.

Antes de activarlo conviene hacer una decisión explícita separada: qué cassette(s) habilitar, con qué frecuencia y si la campaña debe detenerse después de N promociones o al alcanzar plateau.
