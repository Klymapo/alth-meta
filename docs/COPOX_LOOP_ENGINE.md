# COPOX Loop Engine

COPOX es el motor genérico de iteración, evidencia, auditoría, aprendizaje y promoción. **No contiene reglas específicas de Theo ni de ALTH.**

La analogía de diseño es una videocasetera:

- **COPOX Loop Engine** = videocasetera.
- **Cassette** = trabajo concreto a iterar: personaje 3D, asset, rig, textura, interfaz, script, animación, shader, etc.
- **Profile** = conjunto de auditores aplicables a ese tipo de cassette.
- **Plugin/adapter** = integración con Blender, Godot, Python, etc.

## Principios no negociables

1. Un candidato rechazado nunca se convierte en baseline.
2. Los candidatos de un torneo son hermanos: parten de la misma baseline aceptada.
3. La promoción exige **100 % PASS de todos los auditores aplicables**. `N-A` no cuenta en el denominador.
4. El score sólo desempata candidatos que ya consiguieron unanimidad; nunca compensa un FAIL.
5. Debe existir evidencia requerida antes de auditar.
6. Un reporte visible sólo se publica después de promoción unánime y debe incluir captura.
7. Regiones/áreas fuera del foco pueden marcarse como congeladas y cualquier regresión fuera de tolerancia veta al candidato.
8. Si ningún candidato converge, la baseline se conserva y la campaña termina en `PLATEAU`.
9. La IA no pertenece al inner loop por defecto. Primero: algoritmos, parámetros, pruebas y auditores deterministas.
10. ChatGPT actúa como director: define campañas, cambia estrategia ante plateau y consume únicamente reportes consolidados.
11. Una campaña trabaja sobre el mismatch prioritario (o dos estrechamente acoplados). No se activan auditores especializados de regiones que el productor no está intentando mejorar.
12. La proyección/auditoría debe registrar explícitamente el sistema de coordenadas del artefacto. Blender Z-up y glTF Y-up no se consideran intercambiables.
13. Una promoción interna actualiza la **state branch del cassette**, no `main`. Publicar/release es un proceso distinto.

## Flujo

```text
seed en main
      │
      ▼
state branch del cassette
      │
      ▼
baseline aceptada
      │
      ├─ prepare (una vez por campaña)
      │
      ▼
torneo (N hermanos)
      │
      ├─ mutate
      ├─ execute
      ├─ capture
      └─ audit
             │
       ┌─────┴─────┐
       │           │
     FAIL       ALL PASS
       │           │
 learning      elegible
       │           │
 siguiente      torneo
 torneo          termina
       │           │
       └─────┬─────┘
             ▼
      escoger mejor PASS
             │
          promote
             │
      state branch nueva
             │
          report
```

## Contrato universal del cassette

Los cassettes son JSON y declaran configuración y comandos. El motor no conoce el dominio.

```json
{
  "id": "personaje-pelo",
  "kind": "alth_character",
  "profile": "copox/profiles/alth_character.json",
  "target": "personaje_x",
  "baseline": "copox/baselines/personaje_x.json",
  "variables": {
    "asset_dir": "assets/personaje_x",
    "reference": "refs/personajes/personaje_x.jpg",
    "search_space": "copox/search_spaces/personaje_x.json",
    "state_branch": "copox/state/personaje-pelo",
    "focus": "hair,profile"
  },
  "strategy": {
    "tournament_size": 3,
    "max_candidates": 6
  },
  "commands": {
    "prepare": ["python3", "..."],
    "mutate": ["python3", "..."],
    "execute": ["python3", "..."],
    "capture": ["python3", "..."],
    "learn": ["python3", "..."],
    "promote": ["python3", "..."],
    "report": ["python3", "..."]
  },
  "promotion": {"unanimous": true},
  "reporting": {
    "required_evidence": ["hoja.png", "overlay_front.png", "overlay_side.png"]
  }
}
```

Los comandos son listas de argumentos; no se ejecutan mediante shell. Variables universales disponibles:

- `{cassette_id}`
- `{cassette_path}`
- `{candidate_id}`
- `{candidate_dir}`
- `{evidence_dir}`
- `{audit_dir}`
- `{baseline}`
- `{target}`
- `{run_dir}`
- `{repo_root}`
- `{auditor_id}` / `{audit_result}` durante auditoría

Además, todos los valores escalares declarados dentro de `variables` pasan al contexto del cassette. El engine no interpreta su significado.

## Estado persistente por cassette

`copox/state.py` usa Git plumbing para mantener una rama mínima independiente por cassette:

```text
copox/state/theo-character
  commit N
    baseline.json
    state.json
  ↑
  commit N-1
    baseline.json
    state.json
```

Ventajas:

- historial completo de promociones internas;
- ningún commit intermedio ensucia `main`;
- Theo, Detective, HUD y rig no compiten por el mismo archivo/branch;
- el siguiente run carga exactamente la última baseline promovida;
- el seed versionado en `main` sigue siendo fallback reproducible;
- release/finalización sigue siendo una acción separada.

## Perfiles

Un perfil define auditores, no productores:

- `alth_character`: mesh, spec, likeness, silueta, anatomía, regiones, regresión, LearningArchitect.
- `alth_asset`: geometría, escala, dimensiones, silueta, materiales, referencia.
- `rig`: jerarquía, orientación, pesos, deformación, poses extremas, foot contact.
- `texture`: UV, seams, stretching, bleed, resolución, paleta, roughness/metallic.
- `godot_ui`: layout, overflow, clipping, contraste, tipografía, responsive, interacción, regresión visual.
- `godot_script`: sintaxis, unit, integration, headless, performance, arquitectura y regresión.

El cassette puede activar o desactivar auditores mediante `auditor_overrides`. Los gates globales siguen vigilando likeness, cambio positivo, anatomía y regresiones aunque un auditor regional esté en `N-A`.

## Adaptador ALTH Character

`copox/adapters/alth_character.py` implementa un productor determinista sin IA:

1. `prepare`: carga la state branch si existe; de lo contrario usa el seed de `main`; reproduce baseline y guarda GLB, hoja y reporte.
2. `mutate`: cambia parámetros declarados en un search space; no puede inventar parámetros fuera del contrato.
3. `execute`: Blender headless genera el candidato y un GLB de iteración.
4. `capture`: Audit V2 genérico compara baseline/candidato contra la referencia.
5. `learn`: usa `unresolved` + error budget; un fallo repetido rota técnica/parámetro en lugar de repetir una tercera vez lo mismo.
6. `promote`: sólo recibe candidatos ya unánimes; guarda la baseline paramétrica en la state branch del cassette. Persistir/publicar en la rama actual es opt-in separado.

`copox/adapters/alth_character_audit.py` trabaja sobre GLB exportado. El GLB de ALTH es glTF Y-up; esta transformación se declara en `reference_configs/*` y el auditor usa un **registro bloqueado a la baseline**, para que modificar pelo no parezca mover brazos/piernas por un reescalado automático del candidato.

Los landmarks del modelo se obtienen por nombres semánticos de geometría. Los landmarks de referencia pueden ser explícitos o detectarse automáticamente dentro de ROIs semánticas amplias. No se escriben coordenadas exactas inventadas a mano.

## Evidencia

```text
.copox/evidence/<cassette>/<run>/
  manifest.json
  baseline/
  candidates/
    t01-c01/
      candidate.json
      params.json
      model.glb
      reporte.json
      metrics.json
      evidence/
        hoja.png
        overlay_front.png
        ...
      audit/
```

Los renders fallidos son artefactos temporales. La trazabilidad persistente puede reducirse a manifiestos, métricas, parámetros/seed, commit y causa de rechazo. Un candidato debe poder reproducirse desde esos datos.

## Concurrencia

La unidad de exclusión es el **cassette**, no todo COPOX. Dos campañas que escriben la misma baseline no deben ejecutarse en paralelo.

```text
copox-theo       -> secuencial
copox-detective  -> secuencial
copox-hud        -> secuencial
```

pero esos grupos pueden ejecutarse simultáneamente. El scheduler actual consulta `copox/cassettes/enabled/*.json`; mientras esa carpeta no contenga un cassette productivo, no hay loops autónomos activos.

## Coste

El inner loop debe poder operar sin APIs de IA:

- GitHub Actions en runners estándar del repositorio público.
- Python y librerías open source.
- Blender headless para 3D.
- Godot headless para juego/UI/scripts.
- métricas y comparación de imágenes deterministas.

IA gratuita sólo puede ser un fallback explícito. ChatGPT no inspecciona cada candidato: recibe `PROMOTED` o `PLATEAU` y actúa como director del siguiente ciclo.

## Compatibilidad con ALTH/CHSP-X

`bucle.yml`, `aprobar.yml` y CHSP-X permanecen disponibles durante la migración. COPOX se introduce en paralelo.

Audit V2 conserva:

- candidatos hermanos desde la última baseline aceptada;
- LikenessLead;
- ClearDifferenceGate;
- AnatomyCoherence;
- regiones congeladas;
- LearningArchitect;
- máximo de candidatos antes de plateau.

COPOX cambia el criterio de aprobación a **unanimidad de todos los auditores aplicables**.

## Estado de implementación

### Fase A — núcleo: validada

- contrato de cassette;
- motor de torneo;
- evidencia;
- unanimidad;
- manifiesto;
- plateau;
- workflows manual/scheduler;
- smoke end-to-end en GitHub Actions;
- state branches independientes y con historial.

### Fase B — ALTH: validada para personaje/pelo

Validado en GitHub Actions real:

- adapter Blender headless;
- adapter Audit V2 configurable;
- baseline paramétrica;
- search space determinista;
- LearningArchitect heurístico;
- exportación GLB de iteración;
- overlays + métricas + verificación ALTH;
- coordenadas glTF Y-up;
- frozen regions con registro bloqueado;
- landmarks automáticos;
- torneo de tres hermanos;
- veto de candidatos fallidos;
- ganador 10/10 auditores aplicables PASS;
- reporte únicamente del ganador con capturas;
- persistencia de baseline en rama de estado.

El cassette real de ejemplo permanece fuera de `enabled/`: el scheduler está preparado pero no activo para assets productivos.

### Fase C — Godot

- UI cassette;
- script cassette;
- capturas headless;
- pruebas e integración.

### Fase D — rigs/texturas/animación

- baterías de poses;
- auditoría de deformación;
- UV/material audit;
- loops de animación.

COPOX debe poder crecer añadiendo perfiles/plugins sin modificar `copox/engine.py`.
