# Propuestas de malla en Kaggle (TripoSG, GPU gratuita)

Aprobado por el dueño el 1 oct 2026 como **proveedor opcional de propuestas**. Genera una malla densa
desde la imagen de referencia en la GPU gratuita de Kaggle. Esa malla **no es un asset**: entra a la
post-producción clásica (remesh, simetría, manos, flat shading, presupuesto de triángulos) y a la
auditoría visual como cualquier otro candidato, y no hereda ninguna aprobación.

Uso esperado decreciente: Kaggle es para formas que la librería `alth/` todavía no sabe hacer. Con el
chasis de personaje aprobado, un personaje nuevo es variación del chasis y no necesita GPU.

## Configuración (una sola vez)

1. Crea una cuenta gratuita en [kaggle.com](https://www.kaggle.com) y **verifica tu teléfono**
   (Settings → Phone verification). Sin eso Kaggle no da GPU ni internet al kernel, y el push se rechaza.
2. En Kaggle: tu perfil → **Settings** → sección **API**. Hay dos formas; cualquiera sirve:
   - **Generate New Token** (forma actual): muestra un token. Cópialo (sólo se ve una vez).
   - **Create Legacy API Key**: descarga `kaggle.json` con `{"username": "...", "key": "..."}`.
3. En GitHub: el repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `KAGGLE_USERNAME`: tu usuario de Kaggle (**siempre**; el token nuevo no lo trae y hace falta para el
     id del kernel).
   - `KAGGLE_API_TOKEN`: el token de "Generate New Token", **o bien**
   - `KAGGLE_KEY`: el `key` de `kaggle.json`.

No subas el token ni `kaggle.json` al repo: es público.

## Uso

Actions → **Propuesta en Kaggle (TripoSG, GPU gratuita)** → Run workflow, con:

| Campo | Ejemplo | Nota |
|---|---|---|
| imagen | `refs/personajes/joven-rubio.jpg` | ya subida al repo |
| nombre | `theo` | carpeta de salida `propuestas/theo/` |
| caras | `20000` | reducción en Kaggle; el tope ALTH se aplica después |
| recorte | `0.52,0.1,1,1` | sólo para infografías |

El GLB, `meta.json` (tiempos, caras, GPU, error si lo hubo), `resumen.json` y la imagen de entrada sin
fondo quedan como artifact de la corrida durante 14 días.

Desde una terminal con la CLI de Kaggle instalada y credenciales:

```bash
python3 tools/kaggle_proveedor.py lanzar refs/personajes/joven-rubio.jpg --nombre theo
python3 tools/kaggle_proveedor.py armar  refs/personajes/joven-rubio.jpg --nombre theo \
    --usuario TU_USUARIO --carpeta /tmp/kernel      # solo arma, sin red
```

## Qué pasa por dentro

1. **Fondo y sombra con código del repo** (`tools/mascaras.py`, el mismo que usa la auditoría visual): `separar_figura` + `quitar_sombra_pegada`
   (sombra = gris neutro, en la parte baja, sin figura debajo y con borde que se desvanece; una pieza
   gris de borde nítido, como el aro de la lata, se conserva). Se escribe un PNG RGBA.
2. **TripoSG nunca usa RMBG-1.4**: su script oficial quita el fondo con `briaai/RMBG-1.4`, cuyo uso
   comercial exige licencia de pago de BRIA. Si la imagen trae un alfa válido (≥ 1 % transparente y
   ≥ 1 % opaco), `prepare_image` lo usa y no llama a RMBG. El kernel no descarga RMBG.
3. **Kernel privado** con GPU T4 ×2 (16 GB cada una; TripoSG pide ≥ 8 GB y usa una) e internet: clona
   TripoSG en el commit fijo `fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c`, instala `requirements.txt` sin
   `numpy==1.22.3` (no instala en el Python de Kaggle) ni `diso` (ver Licencias), restringido a las
   versiones que ya trae la imagen (si eso falla, reintenta sin restricción y lo anota), descarga los
   pesos `VAST-AI/TripoSG` (~8 GB, sin token), genera con `use_flash_decoder=False`, reduce con pymeshlab
   y escribe `propuesta.glb`, `meta.json` y `pip_freeze.txt`.
4. **Vigilancia**: el push lleva `-t` = el tiempo máximo (la CLI no puede cancelar un kernel, así que el
   tope se pone en Kaggle mismo). Se lee la versión que devolvió el push y se consulta el estado cada
   30 s (la CLI 2.2.x consulta siempre la última versión del kernel); un estado final no se acepta hasta
   haber visto el kernel en cola o corriendo (o tras 4 consultas), y 5 fallos seguidos de la CLI abortan.
   Al terminar se baja la salida y se exige que `meta.json` traiga el mismo `pedido_id` que se generó al
   armar: nunca se toma por buena la malla de una corrida anterior.

Códigos de salida: 0 ok · 2 entrada inválida · 5 falló en Kaggle (push rechazado, kernel con error o la
CLI de estado falla seguido) · 6 tiempo agotado · 7 faltan credenciales o CLI · 8 terminó sin
`propuesta.glb` o con la de otro pedido.

Un push rechazado (teléfono sin verificar, cuota agotada) **sale con código 0 en la CLI de Kaggle**; por
eso se revisa el texto ("Kernel version N successfully pushed" / "Kernel push error").

## Licencias

- TripoSG: código MIT, pesos `VAST-AI/TripoSG` MIT.
- RMBG-1.4: **no se usa** (comercial con licencia de pago).
- `diso` (CC BY-NC 4.0, **no comercial**): TripoSG lo importa siempre, pero sólo lo usa su "flash decoder".
  **No se instala**: se sustituye por un módulo vacío y se genera con `use_flash_decoder=False`, que extrae
  la malla con `skimage.measure.marching_cubes` (más lento, misma licencia permisiva de scikit-image).
- Kaggle: servicio gratuito sujeto a sus términos. Sus páginas de términos y de cuotas no se pudieron
  leer el 1 oct 2026 (cargan con JavaScript). Fuentes secundarias indican ~30 h/semana de GPU (T4×2; la P100
  ya está retirada en la CLI) y sesiones de hasta 12 h. Revisa los términos en tu cuenta antes de usarlo a escala.

## Riesgos conocidos (sin probar todavía en Kaggle)

- Verificado contra el código fuente (1 oct 2026): flag `--accelerator NvidiaTeslaT4`, campos de
  `kernel-metadata.json`, texto de `kernels status`, que `push` ejecuta por defecto, imports de TripoSG,
  que con alfa válido no se llama a RMBG, fp16 en T4 y que los pesos no piden token.
- Sin verificar hasta la primera corrida: versiones de Python/pip de la imagen de Kaggle, disco libre
  (pesos ~8 GB + dependencias), compatibilidad con `diffusers`/`transformers` recientes y tiempo real de
  la extracción jerárquica.
- Cada corrida reinstala dependencias y re-descarga pesos: consume minutos de la cuota.
- El script lleva la imagen incrustada (~0.8 MB). Si Kaggle rechazara el tamaño, pasar la imagen como
  Dataset privado.
- TripoSG está entrenado con objetos de Objaverse: su respuesta a personajes chibi y a dedos separados
  no tiene evidencia publicada. La auditoría visual decide.
