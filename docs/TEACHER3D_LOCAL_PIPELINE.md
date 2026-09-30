# Teacher3D local-only pipeline

Goal: use free/open-source image-to-3D code as **teacher geometry** for ALTH without paid APIs, tokens, quotas, weekly limits or subscriptions.

## Allowed engines

- Pixal3D — MIT — primary multiview teacher.
- TRELLIS.2 — MIT — high-quality secondary teacher.
- TRELLIS — MIT — architectural/secondary teacher.
- InstantMesh — Apache-2.0 — independent sparse-view teacher.
- TripoSR — MIT — fast single-view sanity teacher.
- Hunyuan3D 2.1 — excluded from the default pipeline because its community license is more restrictive.

The third-party repositories are **not vendored into ALTH**. `alth.teacher3d.bootstrap` clones their source code into a local `_vendor/teacher3d` folder. This preserves upstream licenses and keeps this repository small.

## Hard rules

1. Inference runs locally.
2. No paid API provider may be used by the Teacher3D package.
3. No token/quota/subscription service may be required.
4. Prefer local model weights at runtime.
5. Generated teachers are evidence, not ground truth.
6. Original references outrank any teacher mesh.
7. A teacher must pass the existing 2D likeness audit before its 3D geometry is trusted.
8. Consensus across independent teachers/seeds raises confidence; disagreement lowers it.

## Theo pipeline

```text
Theo references
    -> camera calibration
    -> Pixal3D multiview teacher
    -> optional TRELLIS.2 / InstantMesh / TripoSR teachers
    -> teacher consensus + confidence map
    -> 2D teacher validation
    -> 3D surface likeness audit
    -> ReferenceToParameterFitting
    -> ALTH procedural model
    -> existing strict agent audit
```

## Camera calibration

Pixal3D multiview expects camera-to-world matrices and horizontal FOV. Theo's turnaround is close to orthographic, so start with low FOV values (5–25 degrees) at a comparatively long distance. `alth.teacher3d.camera` generates Blender/NeRF-style transforms and provides a first-pass FOV sweep.

The full calibration gate should render a provisional teacher/candidate through all known views and select the camera setup that best reproduces the source silhouettes.

## Visibility-aware multiview fusion

The upstream Pixal3D multiview path averages projected view features. ALTH adds a stricter fusion concept:

```text
fused = sum(feature_i * valid_i * confidence_i * facing_i)
        / sum(valid_i * confidence_i * facing_i)
```

Invalid projections should not influence the result. `alth.teacher3d.fusion.visibility_aware_fusion` implements the local reference logic. When patching a local Pixal3D checkout, retain upstream MIT attribution.

## Teacher consensus

`alth.teacher3d.consensus` estimates agreement among teacher meshes using symmetric nearest-neighbour distance. A single teacher is never treated as high confidence. Use multiple seeds and preferably more than one architecture when a region is ambiguous.

Recommended hierarchy:

1. Original Theo reference images.
2. Consistency among real views.
3. Consensus among teacher meshes.
4. Individual teacher output.

## 3D likeness audit

`alth.teacher3d.audit3d` currently provides:

- symmetric Chamfer-style distance;
- radial signed-error proxy;
- semantic-region depth comparison;
- cross-section extents.

Planned semantic regions for Theo:

- hair;
- head/face;
- torso;
- arms/hands;
- pelvis;
- thighs;
- shins;
- shoes.

These metrics supplement, never replace, the four-view 2D silhouette and landmark audits.

## Source bootstrap

```bash
python -m alth.teacher3d.bootstrap --root _vendor/teacher3d
```

This clones source code only. Each external project may require its own environment because CUDA/PyTorch/compiled extension requirements can conflict.

## No-token runtime

Provider helpers in `alth.teacher3d.providers` intentionally accept local source paths and, where practical, local weight paths. If a model needs one-time public weight downloads, cache them locally first; production inference should not depend on a hosted generation service.

## Current provider strategy

### Pixal3D
Use `inference_mv.py` with a generated `transforms.json`. This is the primary path because it accepts explicit camera poses and projects DINO features into a shared 3D grid.

### TripoSR
Use `run.py` with a local pretrained model directory. Good for rapid sanity checks, not authoritative likeness.

### InstantMesh
The stock `run.py` first generates synthetic sparse views through Zero123++. Keep it as an independent teacher. A later ALTH adapter should bypass synthetic view generation and feed Theo's known views/cameras directly into `forward_planes(images, cameras)`.

### TRELLIS
Use `run_multi_image` as a secondary teacher. Its multiview strategy is not explicit camera-aligned reconstruction, so it should carry lower confidence than Pixal3D for Theo.

### TRELLIS.2
Keep in a separate local environment. It is a high-quality secondary teacher but its standard example is single-image oriented; use it primarily for cross-checking shape until a reliable multiview adapter is validated.

## Approval gate for teacher use

A teacher mesh is usable only when:

- its renders are measurably consistent with the original references;
- it does not introduce a major anatomy/style contradiction;
- its ambiguous regions are marked low-confidence;
- it improves the evidence available to an ALTH body-part agent.

If those conditions fail, the teacher is discarded rather than forcing the procedural Theo model toward it.
