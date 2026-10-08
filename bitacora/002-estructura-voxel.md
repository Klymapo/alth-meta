# Bitácora 002 · Vóxeles multicapa con caras internas eliminadas

**Fecha:** 2026-10-08  
**Rama:** `experimentos/voxel-glb-codespaces`  
**Estado:** experimental (no fusionado ni aprobado para Theo Alpha)

## Encargo

Construir un archivo GLB con nueve vóxeles azules en Y=0, cuatro verdes en Y=1, uno amarillo en Y=2, y eliminar caras que toquen otro vóxel, incluso si son materiales diferentes.

## Coordenadas

- Azules: `(x,0,z)` para `x,z∈{0,1,2}`.
- Verdes: `(x,1,z)` para `x,z∈{1,2}`.
- Amarillo: `(1,2,1)`.

Las cuatro celdas verdes ocupan un cuadrante sobre la base 3×3 (no centrado geométricamente), decisión explícita para no introducir contactos de caras parciales ni subdividir la malla.

## Resultados locales

- 14 vóxeles en total: 9 azul, 4 verde, 1 amarillo.
- 21 pares de celdas adyacentes → 42 caras internas eliminadas.
- 42 caras externas exportadas (26 azul, 11 verde, 5 amarillo).
- 84 triángulos y 168 vértices en la malla GLB de tres materiales.
- 5/5 pruebas locales superadas: capas, culling, readback, vecinos multicolor y layout personalizado.
- Capturas producidas **leyendo la malla exportada**: frente, derecha, superior, isométrica y lámina 2×2.

## Entregables reproducibles

```bash
python -m unittest discover -s experimentos/voxel-glb -p test_voxeles.py -v
python experimentos/voxel-glb/entrega_voxeles.py --salida salidas/entrega_002
```

`salidas/entrega_002/` contendrá el GLB, PNGs y `manifiesto.json` con hash SHA-256 y coordenadas detalladas. GitHub Actions sube las dos entregas como ZIP descargable.

## Reglas siguientes

- Cada entrega debe incluir capturas reales y pruebas de geometría.
- No mezclar ni aprobar automáticamente modelos del juego.
- Próximo: layouts JSON personalizados y editor de posiciones para crear anatomía de Theo y Alastor.
