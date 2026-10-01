# Fixtures de `tools/investigar.py` (pruebas sin red)

- `bmesh_opdefines_v5.2.2.cc`: copia real de
  https://raw.githubusercontent.com/blender/blender/v5.2.2/source/blender/bmesh/intern/bmesh_opdefines.cc
  (fuente de la página bmesh.ops de la API), descargada el 1 oct 2026.
- `bmesh_ops.html`, `modificadores.html`: reproducción **reducida** del marcado Sphinx de
  docs.blender.org (pocas secciones, texto tomado de la fuente oficial) para probar el parser.
  No es una copia de la página: docs.blender.org no era alcanzable desde la sesión que las escribió.
- `github_search.json` y `ejemplo_*.py`: respuesta con la forma de la API de búsqueda de código de
  GitHub y dos archivos de ejemplo escritos para la prueba (no son repos reales).
La prueba real con red corre en Actions (`.github/workflows/linea-unica.yml`, job t1).
