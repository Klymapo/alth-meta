# Estructura unificada ALTH-META / AlasTheo

| Ruta | Uso vigente |
|---|---|
| `alth/` | Librería Blender headless, unidades en mm |
| `copox/` | Motor de investigación, candidatos hermanos y auditoría |
| `assets/<nombre>/` | Contratos y builds ejecutables ALTH existentes |
| `assets/references/` | Catálogo documental de referencias de AlasTheo |
| `refs/` | Imágenes originales; una sola copia |
| `spec/`, `data/` | Estándar visual y medidas |
| `tools/` | Herramientas ejecutables del pipeline actual |
| `tests/` | Pruebas Python y fixtures pequeños |
| `docs/production/` | Libro de producción original de ALASTHEO |
| `models/`, `scripts/` | Organización propuesta para nuevos proyectos independientes |
| `archive/` | Material histórico preservado |

Los directorios sugeridos por ALASTHEO no sustituyen los contratos ejecutables existentes. No mover Alpha ni reconstruir assets al reorganizar documentación. La evidencia temporal de COPOX vive en `.copox/` y en artifacts de Actions, no dentro de las pruebas versionadas.

Las instrucciones de agentes están en [AGENTS.md](../AGENTS.md) y [CLAUDE.md](../CLAUDE.md). Las convenciones de nombres se aplican a archivos nuevos; no renombrar automáticamente entregables protegidos.
