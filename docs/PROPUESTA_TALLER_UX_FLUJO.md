# El Taller · propuesta de UX y flujo

Esta copia vive en `propuesta-taller-ux-flujo`. La página `taller/index.html` envía fotos y workflows a esa rama y aprueba, por defecto, en la misma rama. La biblioteca muestra los assets de esa versión junto con las ramas `bucle/*`.

## Recorrido

1. Abre `taller/index.html` desde un servidor local y guarda un token de GitHub con los permisos que pide la página. GitHub Pages continúa sirviendo la versión de `main`; esta propuesta todavía no está publicada como sitio.
2. Selecciona un asset en la biblioteca. Su ficha carga el commit de la rama, la hoja de ese commit, su manifiesto `revision.json` y la verificación.
3. Escribe una corrección en **Pedir otra vuelta** o aprueba la versión. La aprobación envía el SHA exacto del commit revisado.
4. El workflow rechaza una rama que cambió desde la revisión, comprueba las huellas del código, la hoja y el reporte, renderiza el resultado final y lo sube a `propuesta-taller-ux-flujo`.

Las ramas anteriores sin `revision.json` se pueden consultar, pero requieren una nueva corrida para usar la aprobación desde esta interfaz. Ningún asset se aprobó durante la preparación de esta propuesta.

## Cambios de proceso

- La hoja de revisión sale del código que queda finalmente en la rama, incluso cuando el bucle restaura una vuelta anterior. El manifiesto conserva su procedencia y huellas SHA-256.
- Una versión con verificación completa tiene prioridad sobre una que solo mejora la silueta. La aprobación exige verificación completa.
- El presupuesto máximo por corrida es 3, 4, 5 u 8 intentos según el tipo de asset. El usuario puede pedir menos. Una corrida posterior constituye un presupuesto nuevo.
- El build generado por la IA no recibe claves de API en su entorno.

## Estado y límites

Se verificaron las pruebas automatizadas de Python, la sintaxis JavaScript y la lectura de los workflows. Queda una prueba real con token, GitHub Actions, Blender y una rama `bucle/*` nueva. No se desplegó esta página ni se ejecutó una aprobación.

Las fotos de referencia se guardan como archivos en la rama de propuesta; si la llamada posterior a Actions falla, la foto queda allí y se puede reutilizar. El token se guarda en el navegador como en la versión previa; conviene usar uno limitado a este repositorio.
