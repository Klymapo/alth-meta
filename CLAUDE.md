# ALTH-META · instrucciones para cada sesión

Repositorio de assets 3D chibi-soft low-poly para un videojuego en **Godot**.
El estándar completo está en `spec/alth_spec.json` (fuente de verdad) y en la página "ALTH-META · Estándar unificado".
Responde en español, en tono cercano.

## Arranque (siempre primero)

1. Blender corre como módulo de Python. El comando es `alth-python`.
2. Si `alth-python` no existe o `alth-python -c "import bpy"` falla, corre `bash tools/ensure_blender.sh`
   (tarda 1–3 min la primera vez; puede que el hook de inicio ya lo esté instalando, el script espera su turno).
3. Nunca uses `bpy.ops` que dependan de la interfaz (viewport, `context.area`). Todo va por datos o por `alth`.

## Convenciones

- 1 unidad de Blender = 1 mm. Pies en Z=0, frente hacia −Y, centrado en X=0.
- Usa la librería `alth/` antes de construir geometría a mano:
  - `torno(perfil)`: sólidos de revolución facetados (frutas, latas, vasos, tazas, cabezas de bastón).
    `bandas=[(z_max, color[, "metal"]), …]` pinta franjas por altura en una sola malla;
    `giro="frente"` deja una cara plana hacia −Y (etiquetas), `giro=0` deja una arista.
  - `anillo(...)`: toroide low-poly (lengüetas, argollas, asas, pulseras, llaves).
  - `calcomania(nombre, contorno, radio, lados)`: dibujo plano que ENVUELVE un torno facetado
    (etiquetas, logos). Se diseña en la etiqueta desenrollada (u = 0 centro de la cara frontal, z = altura)
    con `contorno_ovalo`, `contorno_gota` y `contorno_tira` (ramas, rayas); se corta solo en las aristas.
    Es una superficie de una cara (sin canto) a 0.02 mm, y cada calcomanía siguiente sube 0.006 mm:
    la que llamas después queda encima. No uses prismas/tornos sueltos para dibujos.
  - `prisma(...)`: piezas cónicas delgadas (tallos, patas, mangos). `hoja(...)`: hojas en gota con nervio.
  - `caja(...)`, `material`, `chaflan` (proporcional al tamaño), `estudio`, `revisar`, `exportar_glb`.
  - `maniqui(arquetipo)` / `junto_a_maniqui(objs)`: maniquí de bloques con las cotas del cuerpo base
    (`alth/cuerpo.py`). Pásalo como `revisar(..., extras=…)`: sale en el render pero no en medidas ni verificación.
    Alturas de anclaje en `spec` → `cuerpo_base_95mm.alturas_ancla` (rodilla 21, cadera 33, cintura 38.8,
    muñeca 35.5, hombro 56, cuello 60.5).
  - Si un asset necesita una forma que se repetirá (asa, rueda, pliegue), agrégala a `alth/` en vez de dejarla en el `build.py`.
- Colores solo de `spec/alth_spec.json` → `paleta`. Un color nuevo se propone al usuario antes de usarlo.
- Medidas de objetos: `mm_alth = mm_real × 0.0559 × k` con el `k` de su categoría en `conversion_k`.
- Sombreado plano con variación de ±3 % por cara, chaflán según tamaño (0.4 / 0.15 / ninguno), rugosidad 0.85. Ojos, cejas y boca van como placas con textura, no geometría.

## Comando `/asset` (forma normal de trabajar)

`/asset <nombre> "<qué es y tamaño real>" [ruta de referencia] [auto]` corre el ciclo completo
(ver `.claude/commands/asset.md`). El ciclo manual de abajo sigue valiendo para ajustes puntuales.

## Verificación automática

`alth.revisar(..., asset=<ruta a spec.json>)` imprime `VERIFICACION OK / CON FALLAS` y la guarda en `reporte.json`:
cotas (±2 % contra `"cotas"` del spec del asset), triángulos contra su tope, colores dentro de la paleta,
piezas flotantes y apoyo en Z=0. Es necesaria para cerrar un asset, pero no suficiente: la hoja de contacto
se sigue revisando contra la referencia. Lógica en `alth/verificacion.py`, pruebas en `tests/` (sin Blender).

`alth-python tools/escala.py` renderiza todos los assets aprobados junto al maniquí (foto de familia de escala).

## Bucle con otros modelos

`tools/bucle.py` repite el ciclo con cualquier IA (ver README). Si el usuario pide "córrelo con otro modelo",
"arma el paquete" o "usa el bucle", usa esa herramienta en vez de iterar tú. `python3 tools/bucle.py medir <asset>`
da la silueta contra la referencia en números: úsala también en tus propias vueltas antes de abrir imágenes.
Si el usuario va a copiar y pegar en un chat, arma el paquete con `--unico`: una sola respuesta con todas las
correcciones (ver `docs/CHSP-X.md`).

## CHSP-X

La página de revisión y aprobación (antes "El Taller") está en `chsp-x/index.html`; detalles en `docs/CHSP-X.md`.
`joven_rubio` (Theo) no es la versión objetivo del personaje: no lo apruebes ni lo exportes sin que el usuario lo pida.

## Ciclo por asset

1. Escribe `assets/<nombre>/spec.json`: categoría, medidas reales, medidas ALTH, colores, módulos.
   Si el usuario usa un apodo para el asset (p. ej. "Theo" para `joven_rubio`), agrégalo en
   `"alias": [...]`: CHSP-X lo usa para reconocer que ya existe antes de crear uno nuevo.
2. Escribe `assets/<nombre>/build.py` y córrelo con `alth-python`.
3. Revisa **solo** `renders/<nombre>/iteracion/hoja.png` (una imagen con las 4 vistas) y `reporte.json`.
4. Compara contra la referencia y la spec; corrige; repite.
5. Al aprobar el usuario: render `final`, `exportar_glb` a `assets/<nombre>/<nombre>.glb`,
   agrega una fila a `data/medidas.csv` y haz commit.

## Presupuesto (no negociable)

El usuario acepta gastar límite de uso, pero **un asset simple nunca debe consumir una ventana de uso completa**.

| Tipo | Vueltas máximas antes de preguntar |
|---|---|
| Objeto simple (moneda, manzana, vaso) | 3 |
| Objeto | 4 |
| Mueble / vehículo | 5 |
| Personaje | 8 |

- Iteraciones en modo `iteracion` (400 px, 16 muestras). El modo `final` solo una vez, tras aprobación.
- Mira la hoja de contacto, no las vistas sueltas. No abras renders de iteraciones anteriores salvo que haga falta comparar.
- Si al llegar al tope no converge: detente, muestra la hoja y di qué falta. No sigas iterando por tu cuenta.
- No ejecutes búsquedas web ni lecturas largas durante el ciclo; todo lo necesario está en `spec/` y `refs/`.

## Git

- Los renders de iteración (`renders/`) no se versionan; solo `assets/<nombre>/` con el render final, el GLB y el .blend.
- Commits pequeños y descriptivos en español.
- Las sesiones en la nube arrancan en una rama `claude/...` sin upstream. Para traer lo último de `main`:
  `git pull --ff-only origin main` (un `git pull` a secas no trae nada).
- Un asset llega a `main` solo por aprobación del usuario. La vía normal es CHSP-X (o Actions → Aprobar ALTH),
  que verifica el SHA revisado, renderiza en modo final y exporta el GLB. Si el usuario aprueba en la conversación,
  puedes hacerlo tú con el mismo resultado (render `final`, GLB y la fila en `data/medidas.csv`) y
  `git push origin HEAD:main`. Sin PR, salvo que el usuario lo pida.
- Las ramas `propuesta-*` son para revisar herramientas: no se fusionan a `main` hasta que su prueba real
  (Actions/Blender) haya pasado y el usuario lo diga.
- Tras actualizar desde `main`, corre `bash tools/ensure_blender.sh` para regenerar `alth-python` con la versión nueva.

## Referencias

- `refs/personajes/`: renders de estudio de los personajes.
- `refs/escenas/`: los mismos personajes en escenas con luz ambiental (sirven para escala relativa, no para color).
- `refs/infografias/`: comparativas antiguas. **No** usar sus medidas en "u"; la spec las reemplaza.
- `docs/ALTH_META_Modelado.pdf`: cotas originales del cuerpo base (v0.8.4b).
