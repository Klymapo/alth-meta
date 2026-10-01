# Integración ALTH-META / AlasTheo · 2026-10-01

Destino operativo: `Klymapo/alth-meta`. Origen documental: `Klymapo/ALASTHEO`, commit `de50876221bb547065cea2a234aaeb50b40777f8`. No se borra ni archiva el repositorio de origen y su historial permanece disponible.

Se importan sus 19 archivos, incluido el libro XLSX binariamente idéntico. El README del origen pasa a [ALASTHEO.md](../ALASTHEO.md); se combinan reglas de ignore y se adaptan estructura, contribuciones, estado histórico y enlaces locales. El [manifiesto](alastheo-import.json) registra cada blob original y su destino. Los builds actuales conservan sus rutas en `assets/`; `models/` y `scripts/` son una organización propuesta, no una migración geométrica.

La auditoría valida identidad de archivos importados, preservación del resto de ALTH, enlaces locales, CRC y estructura del XLSX, SHA protegido de Alpha y promoción automática deshabilitada. Actions además compila Python, valida JSON/YAML y ejecuta toda la suite con pytest y Blender headless.

Se corrigieron interpolaciones directas de inputs en el shell de los workflows manuales históricos `bucle.yml` y `aprobar.yml`, usando variables de entorno. Los proveedores externos documentados y los secrets de automatizaciones históricas no se utilizan en esta auditoría. No se considera revalidado el contenido de todas las conversaciones, notebooks históricos ni las cifras comerciales del libro.

Esta fusión de código/documentación no aprueba Theo ni promociona candidatos. La última campaña de dedos continúa rechazada; la siguiente mutación requiere investigación nueva y revisión visual.
