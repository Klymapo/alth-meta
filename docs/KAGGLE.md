# Propuestas de malla en Kaggle (TripoSG, GPU gratuita)

Aprobado por el dueño el 1 oct 2026 como **proveedor opcional de propuestas**. Genera una malla densa
desde la imagen de referencia en la GPU gratuita de Kaggle. Esa malla **no es un asset**: entra a la
post-producción clásica (remesh, simetría, manos, flat shading, presupuesto de triángulos) y a la
auditoría visual como cualquier otro candidato, y no hereda ninguna aprobación.

Uso esperado decreciente: Kaggle es para formas que la librería `alth/` todavía no sabe hacer. Con el
chasis de personaje aprobado, un personaje nuevo es variación del chasis y no necesita GPU.

## Configuración (una sola vez)

1. Crea una cuenta gratuita en [kaggle.com](https://www.kaggle.com). Kaggle pide **verificar el teléfono**
   para usar GPU.
2. En Kaggle: tu perfil → **Settings** → sección **API** → **Create New Token**. Se descarga `kaggle.json`
   con `{"username": "...", "key": "..."}`.
3. En GitHub: el repo → **Settings → Secrets and variables → Actions → New repository secret**, y crea:
   - `KAGGLE_USERNAME` con el `username`
   - `KAGGLE_KEY` con el `key`

No subas `kaggle.json` al repo: es público.

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

1. **Fondo y sombra con código del repo**: `tools/reconocer.separar_figura` + `quitar_sombra_pegada`
   (sombra = gris neutro, en la parte baja, sin figura debajo y con borde que se desvanece; una pieza
   gris de borde nítido, como el aro de la lata, se conserva). Se escribe un PNG RGBA.
2. **TripoSG nunca usa RMBG-1.4**: su script oficial quita el fondo con `briaai/RMBG-1.4`, cuyo uso
   comercial exige licencia de pago de BRIA. Si la imagen trae un alfa válido (≥ 1 % transparente y
   ≥ 1 % opaco), `prepare_image` lo usa y no llama a RMBG. El kernel no descarga RMBG.
3. **Kernel privado** con GPU T4 (16 GB; TripoSG pide ≥ 8 GB) e internet: clona TripoSG en el commit
   fijo `fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c`, instala `requirements.txt` sin el `numpy==1.22.3`
   fijado, descarga los pesos `VAST-AI/TripoSG`, genera, reduce con pymeshlab y escribe
   `propuesta.glb` + `meta.json`.
4. **Vigilancia**: `kaggle kernels status` cada 30 s hasta completar, fallar o agotar el tiempo;
   después `kaggle kernels output`.

Códigos de salida: 0 ok · 2 entrada inválida · 5 falló en Kaggle · 6 tiempo agotado · 7 faltan
credenciales o CLI · 8 terminó sin `propuesta.glb`.

## Licencias

- TripoSG: código MIT, pesos `VAST-AI/TripoSG` MIT.
- RMBG-1.4: **no se usa** (comercial con licencia de pago).
- Kaggle: servicio gratuito sujeto a sus términos. Sus páginas de términos y de cuotas no se pudieron
  leer el 1 oct 2026 (cargan con JavaScript). Fuentes secundarias indican ~30 h/semana de GPU (T4×2 o
  P100) y sesiones de hasta 12 h. Revisa los términos en tu cuenta antes de usarlo a escala.

## Riesgos conocidos (sin probar todavía en Kaggle)

- `diso` (dependencia de TripoSG) compila extensiones CUDA: la primera instalación puede tardar o fallar
  en la imagen de Kaggle. Si falla, el error queda en `meta.json`.
- Cada corrida reinstala dependencias y re-descarga pesos (varios GB): consume minutos de la cuota.
- El script lleva la imagen incrustada (~0.8 MB). Si Kaggle rechazara el tamaño, pasar la imagen como
  Dataset privado.
- TripoSG está entrenado con objetos de Objaverse: su respuesta a personajes chibi y a dedos separados
  no tiene evidencia publicada. La auditoría visual decide.
