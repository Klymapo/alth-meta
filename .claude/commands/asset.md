---
description: Crea un asset ALTH-META completo (spec, modelo, renders, verificación y GLB) desde una descripción y una referencia
argument-hint: <nombre> "<qué es y tamaño real>" [ruta de referencia] [auto]
---

# /asset · asset ALTH-META de punta a punta

Argumentos: `$ARGUMENTS`
- `nombre`: carpeta del asset (minúsculas, sin espacios; p. ej. `plato`).
- descripción: qué es y su tamaño real si el usuario lo dio (p. ej. "plato de comida con filete, 26 cm").
- referencia (opcional): ruta en `refs/…`. Si el usuario adjuntó una imagen en el chat, esa es la referencia.
- `auto` (opcional): cerrar sin pedir aprobación si todo pasa (ver paso 7).

Sigue `CLAUDE.md` en todo. Este comando solo ordena el trabajo.

## 1. Preparar (sin gastar vueltas)
1. `git pull --ff-only origin main && bash tools/ensure_blender.sh`
2. Lee solo lo necesario: `spec/alth_spec.json`, el `build.py` de un asset parecido ya aprobado
   (`assets/manzana` para formas orgánicas de torno, `assets/lata` para torno con bandas y dibujo)
   y la referencia. No abras otras imágenes de `refs/`.
3. Si la referencia es una imagen adjunta que no está en el repo, describe en `spec.json` → `"referencia"`
   la forma, proporciones, colores y detalles que ves, para que las vueltas siguientes puedan compararse contra eso.

## 2. Clasificar
- `categoria` según `conversion_k` y `tipo_presupuesto` según la tabla de vueltas de `CLAUDE.md`.
- Tamaño real: si el usuario no lo dio, usa el de un objeto común de ese tipo y **dilo** en tu primer mensaje.
- Mensaje corto al usuario: qué vas a construir, categoría, medidas ALTH, tope de vueltas y de triángulos.

## 3. Planear en `assets/<nombre>/spec.json`
Mismos campos que `assets/manzana/spec.json`, más:
- `"cotas"`: medidas que la verificación debe comprobar, por pieza:
  `[{"pieza": "Plato_cuerpo", "eje": "W", "mm": 14.53}, {"pieza": "Plato_cuerpo", "eje": "H", "mm": 1.4}]`
  (ejes W=X, D=Y, H=Z; tolerancia ±2 %, o `"tolerancia"` por cota si hay razón).
- `"modulos"`: qué herramienta de `alth/` hace cada pieza.
- Colores: solo de la paleta. Si la referencia pide un color que no existe, usa el más cercano
  de la paleta y **propón** el nuevo en el reporte final; no lo agregues sin aprobación.
- `"permitir_flotantes"`: solo si una pieza flota a propósito (humo, chispas).

## 4. Construir `assets/<nombre>/build.py`
- Mismo esqueleto que los ya aprobados (modo `iteracion`/`final`, `estudio()`, exportar solo en `final`).
- Llama `alth.revisar(objs, …, asset=alth.RAIZ / "assets" / "<nombre>" / "spec.json")` para que corra la verificación.
- Nombres de pieza `<Nombre>_<parte>` (coinciden con `cotas`).
- Muebles, objetos anclados al cuerpo o cuando la escala sea dudosa: renderiza junto al maniquí con
  `extras=alth.junto_a_maniqui(objs)` y revisa las alturas contra `alturas_ancla` de la spec
  (asiento = rodilla 21, escritorio = cadera 33, barra = cintura 38.8).

## 5. Ciclo de vueltas (tope según tipo)
En cada vuelta:
1. Corre `alth-python assets/<nombre>/build.py`.
2. Lee la salida `VERIFICACION …` y `renders/<nombre>/iteracion/hoja.png`.
3. Autocrítica contra la referencia, en este orden:
   silueta y proporciones → piezas principales presentes → detalles legibles de **frente y 3/4** → color.
4. Muéstrale al usuario la hoja de contacto con 2–4 líneas: qué cambió, qué ves y qué cambiarías.
5. Corrige lo más importante primero. No gastes vueltas en detalles que no se ven en 400 px.

## 6. Cuándo está listo
Las dos cosas, no una:
- **Verificación OK** (cotas, triángulos, paleta, flotantes, apoyo).
- **Autocrítica sin pendientes importantes**: se reconoce qué es sin leer el nombre y coincide con la referencia
  en silueta, proporciones y colores. La verificación OK es necesaria, no suficiente.

## 7. Cierre
- Sin `auto`: muestra la hoja final de iteración, di "listo para aprobar" y **detente**. Cierra cuando el usuario apruebe.
- Con `auto`: si se cumple el paso 6, cierra sin preguntar y avisa.
- Si llegas al tope sin cumplir el paso 6: detente, muestra la hoja y lista qué falta. No cierres.

Pasos de cierre:
1. `alth-python assets/<nombre>/build.py final` → GLB y .blend; copia `renders/<nombre>/final/hoja.png` a `assets/<nombre>/final.png`.
2. Una fila por cota real en `data/medidas.csv` con `k_observado = alth_mm / (real_mm × 0.0559)`.
3. Historial en `spec.json` (una línea por vuelta y "aprobada").
4. Si construiste en el `build.py` una forma que se va a repetir, muévela a `alth/` y documéntala en `CLAUDE.md`.
5. Commit y `git push origin HEAD:main`. Si `main` avanzó: `git pull --rebase origin main` y vuelve a empujar.
6. Reporte final: hoja final, triángulos, medidas contra spec, tamaño del GLB y colores propuestos (si hubo).
