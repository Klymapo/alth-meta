# Research-first micro valleys (review only)

This campaign continues PR #14 on its existing branch. It cannot promote an asset,
update a state branch, merge a PR, or overwrite its parent. Alpha is pinned to
SHA-256 ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b.

## Research and diagnosis

Read copox/research/fingers-micro-valleys-20261001.json. Research was prepared by
Codex using online GitHub sources. Official BMesh/API source takes precedence;
Blender Manual pages were consulted through an explicitly identified mirror.
The runtime does not browse or pretend to browse. A missing, malformed, expired,
future-dated or technique-incompatible brief produces RESEARCH_REQUIRED before
mutation. Research validity is 45 days.

The reference is refs/personajes/joven-rubio-4-vistas.jpg. finger_valley_probe and
_side_spec derive the asymmetry. If reference counts change from left=2/right=0,
the campaign stops for a new diagnosis. It does not force the reference to match
hardcoded geometry.

## Parent and siblings

Alpha remains the accepted baseline. Valley Sculpt c01 is reproduced once as a
working parent (contour strength 1.20, sculpt strength 0.55, one local refinement).
That artifact is not promoted or accepted as a replacement baseline.

All three candidates read the same immutable working-parent GLB:

- c01: reference valley depth × 0.75
- c02: reference valley depth × 1.00
- c03: reference valley depth × 1.25

Valley positions and widths use the local correspondence between the detected
reference-hand bounding box and the measured working-parent hand. Depth is
derived from reference valley width / reference hand width × model hand width.
It is capped by fingers scope and distal hand fraction; no absolute hand
dimension is invented. The report records the cap and actual depth in mm.

Narrow U-root prisms subtract only the two distal-left gaps. No new floating
finger geometry, right-hand edits, forearm edits or complete hand replacement
are part of this mutation. BMesh inserts four local cross-sections (distal,
middle, proximal, base), records closed cycles explicitly and triangulates new
local n-gons. These sections are preparation, not evidence of rig readiness or
all-quad topology. The editable .blend preserves local topology; GLB is
triangulated for transport.

## Audit and ranking

Each sibling compares against Alpha AND the working parent. Artifacts include:

- model.glb and model.blend
- trial.json, module_result.json, gate.json, learning.json
- mutation_report.json with outside-face/UV fingerprint and section cycles
- topology_report.json and hand_detail.json
- regional_metrics.json, full_metrics.json and their parent comparisons
- real shaded front, side, back and three-quarter renders
- left/right hand and left finger-region closeups
- comparison.png: REFERENCE / ALPHA / C01 / C02 / C03, front / 3/4 / left hand

Evidence gates check actual nonempty files. Semantic readiness needs exactly 2/0
model valleys, matching reference counts, and no component mismatch.
New boundary/nonmanifold/degenerate failures veto mesh integrity. Local
self-intersection probing records its method and limitations; it does not claim
a full coplanar or adjacent-foldover certificate.

Global gain must be at least +0.05 pp; worst view at least -0.10 pp; frozen
regions cannot fall below -0.20 pp. Parent preservation additionally requires
finger delta ≥ -0.20 pp, global delta ≥ -0.05 pp and worst-view delta ≥ -0.10 pp
relative to Valley Sculpt c01. These are declared audit tolerances, not observed
results. Local section cycles are also a gate.

A candidate passing technical audit may be marked the technical winner. Visual
review remains PENDING until a reviewer inspects actual renders. Metrics cannot
authorize promotion. A diagnostic best candidate is not an accepted winner.

## Bounded loop

research_iteration_loop.run_generations accepts explicit generation specs and
a mutation/audit callback. It validates research before every generation,
executes exactly three siblings from the same immutable parent and records
generation_id, parent_sha, research_id, module, technique, parameters, metrics,
winner, rejected candidates, learning and next hypothesis.

The maximum is three generations. Stops include CANDIDATE_PASSED_GATES,
NO_SIGNIFICANT_IMPROVEMENT, REPEATED_REGRESSION, RESEARCH_REQUIRED,
TECHNIQUE_EXHAUSTED, MESH_INTEGRITY_FAILED and ITERATION_LIMIT.
This campaign supplies one researched generation, so it creates exactly three
new variants. It does not repeat the same technique merely to exhaust a budget.

Bridge-to-palm and rig/deformation cleanup are deferred. Each needs a new,
specific research brief, verified boundary correspondence and actual evidence.
The campaign never sets rig_ready=true.

## Running without paid services

Use the manually dispatched COPOX · Researched micro valleys Actions workflow.
It does not regenerate the three variants on unrelated PR updates. It runs on standard
ubuntu-latest in this public repository, uses read-only repository permissions,
installs open-source tools and calls no paid API or commercial token. The runner
uploads evidence with one-day retention. No installation is needed on the
user's PC.

The equivalent cloud command is:

    python3 -m copox.production.finger_micro_valley_campaign

The contract tests are:

    python3 -m unittest discover -s tests -p test_copox_research_iteration.py -v
