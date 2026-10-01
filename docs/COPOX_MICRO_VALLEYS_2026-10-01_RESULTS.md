# Micro-valley round — measured result, 2026-10-01

Source commit: 084a4e41ce01934e5fa6ac8c8a54700f5a2b8b85
Actions: https://github.com/Klymapo/alth-meta/actions/runs/36876087961
Full artifact: https://github.com/Klymapo/alth-meta/actions/runs/36876087961/artifacts/11169377370
Artifact expires 2026-10-02 14:32:54 UTC.

Exactly three siblings were generated and audited. All use working-parent SHA-256
d5000a33dcb368031ddbcd0ba9bd666e24c47800a3a95103b1a7a88526f5c81b.
Alpha SHA was verified at runtime, unchanged:
ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b.

| Variant | Depth factor | Target gain pp | Global gain pp | Worst view pp | Model valleys L/R | Mesh | Scope | Semantic | Local loops | Accepted |
|---|---:|---:|---:|---:|---|---|---|---|---|---|
| c01 | 0.75 | +4.078286 | +0.152548 | -0.078163 | 1/0 | PASS | FAIL | FAIL | FAIL | No |
| c02 | 1.00 | +9.429519 | +0.131665 | -0.189376 | 1/0 | FAIL | FAIL | FAIL | FAIL | No |
| c03 | 1.25 | +1.699999 | +0.150779 | -0.073825 | 2/0 | PASS | FAIL | PASS | FAIL | No |

All three have complete evidence. All fail regression_ok because they do not
preserve the required Valley advantage; c02 also exceeds the worst-view drop.
Valley Sculpt c01 remains target +6.112897 pp, global +0.151895 pp,
worst view -0.078163 pp, valleys 0/0. A candidate must not merely beat Alpha.

Best diagnostic candidate: c03, because it matches 2/0 semantics and retains
global likeness. It is rejected: its target gain falls far below Valley Sculpt,
scope is not certified and section cycles are not ready. c02 shows a protruding
block in the hand closeup despite the best target metric. Visual review rejects
all three.

The stop reason is MESH_INTEGRITY_FAILED. The workflow succeeded in executing
and recording the experiment; that success does not mean any model passed gates.
The round stops here according to the mesh-integrity stop rule. The review
workflow downloads and inspects the same three existing siblings only.

Learning:
- A correct valley count does not imply correct finger likeness.
- Target IoU can reward visually broken geometry.
- Narrow booleans on an existing open GLB do not ensure a clean connected patch.
- Section insertion must prove closed cycles; generic subdivision is insufficient.
- Keep the Valley Sculpt parent; rejected candidates never become parents.

Next hypothesis: research a minimal connected quad patch around the two valley
roots, anchored to the measured distal boundary, preserving palm depth and the
existing outer silhouette. Verify UV/material correspondence and closed section
cycles before any bridge or deformation operation.

No candidate is promoted. Theo's promotion adapter is locked by
automatic_promotion_enabled=false, the Theo workflow is shadow-only with
read-only permissions and scheduling is removed from that workflow. The generic
COPOX engine is not globally disabled for unrelated cassettes.
