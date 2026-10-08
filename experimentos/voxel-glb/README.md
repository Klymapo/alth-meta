# Laboratorio voxel → GLB | AlasTheo

Prototipo **aislado en rama**: no altera `main`, Theo Alpha ni modelos aprobados.

## Abrir en GitHub Codespaces

1. En GitHub, cambia a `experimentos/voxel-glb-codespaces`.
2. Pulsa **Code → Codespaces → Create codespace on ...**.
3. En la terminal ejecuta:

```bash
python experimentos/voxel-glb/entrega.py --lado 1 --color '#5089C6' --salida salidas/entrega_001
```

Cada entrega produce **obligatoriamente** `cubo.glb`, **4 capturas PNG** (frente, derecha, superior e isométrica), una lámina `cubo_4_vistas.png` y `manifiesto.json` con SHA-256.

El GLB se genera solo con Python estándar; para las capturas el Codespace instala Pillow. Abre los PNG desde el explorador de Codespaces; descárgalos junto con el GLB desde Actions cuando haya una ejecución.

## Archivos

- `generar_cubo.py`: geometría GLB 2.0, cubo paramétrico.
- `render_glb.py`: lee el **GLB real** y captura su malla.
- `entrega.py`: unifica modelo, capturas, manifiesto.
- `requirements.txt`: única dependencia para capturas.
- `.devcontainer/devcontainer.json`: configuración de Codespaces (raíz de la rama).
- `.github/workflows/voxel_glb_capturas.yml`: evidencias en Actions.
- `bitacora/001-cubo-glb.md`: registro inicial.

## Política de entregas

1. No publicar modelo sin capturas de 4 vistas.
2. Comparar con anterior antes de aprobar.
3. Registrar fecha, parámetros, SHA-256 y resultado de revisión.
4. No sustituir Theo Alpha ni otras baselines aprobadas sin autorización.
5. Sin APIs de IA. GitHub Codespaces y Actions están sujetos a cupos y costes según cuenta.
