"""Continuous local notch mapping; independent of Blender for contract verification."""
from __future__ import annotations
import math

DEPTH_SCALES = (0.85, 1.0, 1.15)
SECTION_FRACTIONS = (("distal", .20), ("middle", .40), ("proximal", .60), ("base", .80))

def notch_weight(z, za, zb):
    if not za < z < zb:
        return 0.0
    phase = (z - za) / (zb - za)
    # Narrow softened V with a short root plateau; grid vertices lie at these breaks.
    if phase < .40:
        return phase / .40
    if phase <= .60:
        return 1.0
    return (1.0 - phase) / .40

def notch_x(x, z, *, tip, support_root, depth, z_range):
    if not all(math.isfinite(v) for v in (x,z,tip,support_root,depth,*z_range)):
        raise ValueError("PARAMETER_INVALID: nonfinite notch coordinate")
    support = support_root - tip
    if support <= 0 or not 0 <= depth <= support * .85 or z_range[1] <= z_range[0]:
        raise ValueError("SCOPE_UNSAFE: notch leaves insufficient proximal material")
    if x >= support_root or x < tip:
        return x
    amount = depth * notch_weight(z, *z_range)
    # For each z, dx'/dx >= .15. Tip moves inward, proximal support remains fixed.
    return x + amount * (support_root - x) / support
