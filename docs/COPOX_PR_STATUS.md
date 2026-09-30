# COPOX · estado de la propuesta

PR: `#7 propuesta: COPOX Loop Engine universal`

## Validado

- núcleo genérico y contratos;
- unanimidad 100 %;
- reportes sólo tras promoción con captura;
- perfiles multi-dominio;
- scheduler cada 15 min, cassettes distintos en paralelo y exclusión por cassette;
- ALTH Character adapter real en GitHub Actions;
- Audit V2 configurable y coordenadas glTF Y-up;
- landmarks automáticos y frozen regions;
- torneo real de tres candidatos;
- vetos reales y ganador 10/10 PASS;
- state branch por cassette con historial de baseline;
- regresión ALTH verde después de añadir persistencia.

## Deliberadamente NO activado

- no hay cassettes productivos dentro de `copox/cassettes/enabled/`;
- no hay loops productivos ejecutándose por cron;
- PR #7 no debe fusionarse automáticamente sólo por pasar CI: sigue siendo una propuesta hasta aprobación explícita.

## Siguiente expansión

1. Adapter Godot UI + screenshots/headless.
2. Adapter Godot script + tests/headless.
3. Rig audit (poses/deformación).
4. Texture/material audit.
5. Dashboard CHSP-X/COPOX opcional.
