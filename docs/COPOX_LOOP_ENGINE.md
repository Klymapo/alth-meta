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

## Flujo

```text
baseline aceptada
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
          report
```

## Contrato universal del cassette

Los cassettes son JSON y declaran únicamente configuración y comandos. El motor no conoce el dominio.

Campos principales:

```json
{
  "id": "theo-profile-refinement",
  "kind": "character_3d",
  "profile": "copox/profiles/alth_character.json",
  "target": "assets/joven_rubio",
  "baseline": "main",
  "strategy": {
    "tournament_size": 3,
    "max_candidates": 6
  },
  "commands": {
    "mutate": ["python3", "..."],
    "execute": ["python3", "..."],
    "capture": ["python3", "..."],
    "learn": ["python3", "..."],
    "promote": ["python3", "..."],
    "report": ["python3", "..."]
  },
  "promotion": {
    "unanimous": true
  },
  "reporting": {
    "required_evidence": ["front.png", "side.png", "back.png", "threeq.png"]
  }
}
```

Los comandos son listas de argumentos; no se ejecutan mediante shell. Variables disponibles:

- `{cassette_id}`
- `{candidate_id}`
- `{candidate_dir}`
- `{evidence_dir}`
- `{audit_dir}`
- `{baseline}`
- `{target}`
- `{run_dir}`
- `{repo_root}`
- `{auditor_id}` / `{audit_result}` durante auditoría

## Perfiles

Un perfil define auditores, no productores. Ejemplos previstos:

- `alth_character`: mesh, spec, likeness, silueta, anatomía, regiones, regresión, LearningArchitect.
- `alth_asset`: geometría, escala, dimensiones, silueta, materiales, referencia.
- `rig`: jerarquía, orientación, pesos, deformación, poses extremas, foot contact.
- `texture`: UV, seams, stretching, bleed, resolución, paleta, roughness/metallic.
- `godot_ui`: layout, overflow, clipping, contraste, tipografía, responsive, interacción, regresión visual.
- `godot_script`: sintaxis, unit, integration, headless, performance, arquitectura y regresión.

El cassette puede activar o desactivar auditores mediante `auditor_overrides`. Así un cambio de pelo puede activar `HairAgent` y mantener brazos/piernas en `N-A`, mientras `RegressionGuard` vigila las regiones congeladas.

## Evidencia

Ruta por defecto:

```text
.copox/evidence/<cassette>/<run>/
  manifest.json
  candidates/
    t01-c01/
      candidate.json
      metrics.json
      evidence/
      audit/
```

Los renders fallidos son artefactos temporales. La trazabilidad persistente puede reducirse a manifiestos, métricas, parámetros/seed, commit y causa de rechazo. Un candidato debe poder reproducirse desde esos datos.

## Concurrencia

La unidad de exclusión es el **cassette**, no todo COPOX. Dos campañas que escriben la misma baseline no deben ejecutarse en paralelo.

Ejemplo conceptual:

```text
copox-theo       -> secuencial
copox-detective  -> secuencial
copox-hud        -> secuencial
```

pero esos tres grupos pueden ejecutarse simultáneamente.

## Coste

El inner loop debe poder operar sin APIs de IA. Herramientas preferidas:

- GitHub Actions en runners estándar del repositorio público.
- Python y librerías open source.
- Blender headless para 3D.
- Godot headless para juego/UI/scripts.
- métricas y comparación de imágenes deterministas.

IA gratuita sólo puede ser un fallback explícito. ChatGPT no inspecciona cada candidato: recibe `PROMOTED` o `PLATEAU` y actúa como director del siguiente ciclo.

## Compatibilidad con ALTH/CHSP-X

`bucle.yml`, `aprobar.yml` y CHSP-X permanecen inicialmente intactos. COPOX se introduce en paralelo y los adaptadores ALTH irán sustituyendo gradualmente la lógica específica del bucle antiguo.

La auditoría V2 de personajes se migra como plugin/perfil, manteniendo:

- candidatos hermanos desde la última baseline aceptada;
- LikenessLead;
- ClearDifferenceGate;
- AnatomyCoherence;
- regiones congeladas;
- LearningArchitect;
- máximo de candidatos antes de plateau.

La diferencia es que COPOX sube el criterio de aprobación a unanimidad de todos los auditores aplicables.

## Fases de implementación

### Fase A — núcleo

- contrato de cassette;
- motor de torneo;
- evidencia;
- unanimidad;
- manifiesto;
- plateau;
- workflows manual/scheduler.

### Fase B — ALTH

- adapter de render actual;
- adapter Audit V2;
- parametrización de personajes/assets;
- promoción automática a baseline interna;
- CHSP-X sólo muestra versiones unánimes.

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
