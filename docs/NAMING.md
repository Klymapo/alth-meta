# Convenciones de nombres

## Principios

1. Usa minúsculas para carpetas y nombres técnicos.
2. Usa `snake_case` para separar palabras.
3. Usa versiones de tres dígitos: `v001`, `v002`, … `v025`.
4. El personaje o asset debe aparecer al inicio del nombre cuando ayude a identificarlo fuera de su carpeta.
5. Evita `final`, `latest`, `new`, `fix`, `final_final` y fechas como sustituto del versionado.

## Modelos

```text
theo_v010.blend
theo_v010.glb
detective_v003.blend
detective_v003.glb
```

## Previews

```text
theo_v010_front.png
theo_v010_side_left.png
theo_v010_back.png
theo_v010_three_quarter.png
theo_v010_turnaround.png
```

## Referencias

```text
theo_face_reference_01.png
theo_hair_reference_02.png
apple_scale_reference.png
```

## Scripts

Usa nombres orientados a acción:

```text
export_glb.py
validate_mesh.py
render_turnaround.py
compare_proportions.py
```

## Ramas

```text
art/theo-v011
art/detective-v004
pipeline/blender-validation
feature/turnaround-renderer
fix/theo-head-profile
chore/repository-structure
```

## Commits

Mensajes breves que expliquen el cambio, por ejemplo:

```text
art: refine Theo head profile v011
pipeline: add GLB validation
fix: preserve materials during export
chore: organize repository structure
```
