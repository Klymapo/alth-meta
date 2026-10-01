# Pruebas y evidencia

Las pruebas reproducibles existentes son `test_*.py`. La auditoría de integración ejecuta la suite completa con Blender headless en GitHub Actions y verifica importación, referencias, libro de producción y SHA de Alpha.

Comando en el runner con sus dependencias instaladas:

```bash
alth-python -m pytest tests -q
python3 tools/audit_repository_integration.py
```

Capturas y GLB de campañas viven en artifacts y `.copox/`; no se consideran tests ni modelos aprobados. Fixtures pequeños pueden incorporarse a `tests/fixtures/`.
