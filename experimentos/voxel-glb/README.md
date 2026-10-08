# Laboratorio voxel → GLB | AlasTheo

Laboratorio aislado en rama `experimentos/voxel-glb-codespaces`, separado de `main`, Theo Alpha y otras baselines aprobadas.

## Abrir en GitHub Codespaces

GitHub → esta rama → **Code → Codespaces → Create codespace on ...**. Tras crear el entorno, ejecuta:

```bash
# Entrega 002: base 3x3 azul, 4 verdes en Y=1 y amarillo en Y=2.
python experimentos/voxel-glb/entrega_voxeles.py --salida salidas/entrega_002

# Pruebas del culling, GLB y materiales.
python -m unittest discover -s experimentos/voxel-glb -p 'test_voxeles.py' -v

# Entrega 001 original:
python experimentos/voxel-glb/entrega.py --lado 1 --color '#5089C6' --salida salidas/entrega_001
```

También puedes ejecutar **GitHub Actions → Voxel GLB - Modelos, capturas y pruebas → Run workflow**. El workflow produce un artefacto ZIP con ambos modelos, cuatro capturas por modelo y manifiestos. No necesita llamadas a APIs de IA, aunque los runners y Codespaces están sujetos a límites/cuotas de tu cuenta.

## Entrega 002: especificación

- Y=0: 9 vóxeles azules en todas las coordenadas `(x,0,z)`, con `x,z=0,1,2`.
- Y=1: 4 vóxeles verdes en `x,z=1,2`, formando 2×2.
- Y=2: 1 vóxel amarillo en `(1,2,1)`.
- **Culling transversal:** cara no exportada si hay un vóxel vecino a ±X, ±Y o ±Z, independientemente de su color.
- Resultado de referencia: **14 vóxeles, 42 caras externas, 42 internas omitidas, 84 triángulos**.
- Nota geométrica: un bloque de 2×2 no puede estar perfectamente centrado sobre 3×3 con celdas de un mismo tamaño y posiciones enteras; se usa el cuadrante positivo para conservar las caras coincidentes.

Archivos:
- `generar_voxeles.py`: genera GLB desde un mapa de posiciones (sin dependencias).
- `render_voxeles.py`: lee el GLB exportado y renderiza correctamente sus **tres materiales**.
- `entrega_voxeles.py`: genera GLB, capturas frente/derecha/superior/isométrica, lámina y manifiesto con SHA-256.
- `test_voxeles.py`: pruebas de distribución, eliminación de caras ocultas y lectura de GLB.
- `bitacora/002-estructura-voxel.md`: bitácora de entrega 002.

### Posiciones personalizadas

Crea un archivo JSON, por ejemplo `mi_layout.json`:

```json
{
  "voxeles": [
    {"x": 0, "y": 0, "z": 0, "color": "azul"},
    {"x": 1, "y": 0, "z": 0, "color": "verde"},
    {"x": 1, "y": 1, "z": 0, "color": "amarillo"}
  ]
}
```

Ejecuta:

```bash
python experimentos/voxel-glb/entrega_voxeles.py --layout mi_layout.json --salida salidas/entrega_personalizada
```

El JSON exige coordenadas enteras únicas y colores: `azul`, `verde` y `amarillo`.

## Política de versiones

Todas las entregas llevan capturas de cuatro vistas **derivadas del GLB**, lámina, manifiesto y revisión geométrica. Nunca promover un candidato automáticamente a Theo Alpha ni fusionar a `main` sin aprobación.
