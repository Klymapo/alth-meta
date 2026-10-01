# ALASTHEO

Repositorio maestro de **producción visual y 3D** de AlasTheo.

Su objetivo es mantener separadas y trazables las referencias, archivos fuente, exportaciones, documentación técnica y evidencia de validación. El proyecto jugable de Godot puede evolucionar de forma independiente en `Klymapo/peso-de-los-nombres`.

## Empieza aquí

- **Qué queremos lograr visualmente:** [`assets/references/`](../assets/references/README.md)
- **Qué métodos ya probamos y qué aprendimos:** [`docs/METHODS.md`](METHODS.md)
- **Dónde debe ir cada archivo:** [`docs/STRUCTURE.md`](STRUCTURE.md)
- **Cómo nombrar versiones:** [`docs/NAMING.md`](NAMING.md)
- **Libro de producción:** `docs/production/AlasTheo - Libro de producción.xlsx`

## Estructura

```text
ALASTHEO/
├─ assets/          # catálogo de referencias y material visual de entrada
├─ models/          # archivos 3D fuente, exports y previews
├─ scripts/         # Blender, pipeline y utilidades
├─ tests/           # validaciones, capturas y evidencia
├─ docs/            # producción, métodos, diseño, pipeline y decisiones
├─ archive/         # iteraciones obsoletas o experimentos preservados
├─ .github/         # plantillas y flujo de colaboración
├─ .gitattributes
└─ .gitignore
```

## Regla principal

- **Fuente editable** → `models/source/`
- **Entregable reproducible** → `models/exports/`
- **Imagen de revisión** → `models/previews/`
- **Referencia visual** → `assets/references/`
- **Script** → `scripts/`
- **Medición, prueba o evidencia** → `tests/`
- **Documento de decisión o especificación** → `docs/`
- **Material que ya no forma parte del flujo activo** → `archive/`

## Referencias visuales

Las imágenes originales ya existentes permanecen en `Klymapo/alth-meta/refs/` para mantener una sola fuente de verdad. `assets/references/` funciona como el índice maestro de ALASTHEO: muestra Theo, Detective/Alastor, escala y referencias experimentales, además de explicar qué fuente tiene prioridad.

## Memoria técnica

`docs/METHODS.md` registra los procesos intentados: ALTH-META procedural, SAM 3D, proxy procedural, TripoSR, limpieza de GLB, Pixal3D multivista, refinado manual en Blender, Stylizer, CHSP-X/COPOX, rondas de agentes y derivación de Detective. Cada método conserva objetivo, resultado, limitaciones y decisión de uso.

## Versionado recomendado

Usa versiones de tres dígitos para modelos: `theo_v010.blend`, `theo_v010.glb`, `theo_v010_front.png`.

No uses nombres como `final`, `final2`, `nuevo_final` o similares. La versión identifica el estado; Git conserva el historial.

## Criterio de avance

Una versión no se considera mejor solo porque tenga una malla más limpia o un score superior en una vista. Debe mejorar la lectura del personaje en frente, perfil, espalda y 3/4 sin romper medidas ya validadas. El estado `final` requiere aprobación humana.