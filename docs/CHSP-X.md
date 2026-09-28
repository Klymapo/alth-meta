# CHSP-X · revisión y aprobación de assets

CHSP-X (antes "El Taller") es la página de revisión de ALTH-META. Vive en `chsp-x/index.html` sobre `main`
y GitHub Pages la sirve en `klymapo.github.io/alth-meta/chsp-x/`. La ruta vieja `taller/` redirige ahí.

## Recorrido

1. Abre CHSP-X y guarda un token de GitHub limitado a este repositorio (contenido + Actions).
2. Elige un asset en la biblioteca. La ficha carga el commit de su rama `bucle/*`, la hoja de ese commit,
   su manifiesto `revision.json` y la verificación.
3. Escribe una corrección en **Pedir otra vuelta** o aprueba la versión. La aprobación envía el SHA exacto
   del commit revisado.
4. El workflow **Aprobar ALTH** rechaza una rama que cambió desde la revisión, comprueba las huellas del
   código, la hoja y el reporte, renderiza en modo final, exporta el GLB y lo sube a `main`
   (campo **Sube a**; se puede cambiar por otra rama si quieres probar antes).

Las ramas anteriores sin `revision.json` se pueden consultar, pero necesitan una corrida nueva para aprobarse desde CHSP-X.

## Reglas del proceso

- La hoja de revisión sale del código que queda al final en la rama, incluso cuando el bucle restaura una
  vuelta anterior. El manifiesto conserva su procedencia y huellas SHA-256.
- Una versión con verificación completa tiene prioridad sobre una que solo mejora la silueta. Aprobar exige verificación completa.
- Presupuesto por corrida: 3, 4, 5 u 8 intentos según el tipo de asset (tabla en `CLAUDE.md`). Una corrida posterior es un presupuesto nuevo.
- El build generado por la IA no recibe claves de API en su entorno.
- La única vía para llevar un asset a `main` es la aprobación (CHSP-X o Actions → Aprobar ALTH). Una sesión
  de Claude puede hacerlo a mano solo si el usuario lo aprueba en la conversación, con el mismo resultado:
  render final, GLB y `revision_aprobada.json` o nota equivalente en el commit.

## Estado verificado

- Pasan las pruebas Python (`python3 -m unittest discover -s tests`), la sintaxis JavaScript y la lectura de los workflows.
- **Pendiente de probar en real:** una corrida de Actions con token, Blender y una rama `bucle/*` nueva, y una aprobación completa.
  Hasta entonces, trata el flujo de aprobación como beta.
- Ningún asset se ha aprobado con este flujo todavía. `joven_rubio` (Theo) **no** es la versión objetivo:
  hay que rehacerlo antes de aprobar nada de ese personaje.

## Correcciones en una sola ronda

`python3 tools/bucle.py paquete <asset> --unico` arma un prompt que pide a la IA **todas** las correcciones
en una sola respuesta, cada una con su cota numérica, en vez de una o dos por vuelta. Úsalo cuando copias y
pegas a mano en un chat: ahorra vueltas. El bucle automático sigue con el modo normal (cambios pequeños por vuelta).
