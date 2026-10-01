from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from copox.adapters.finger_gap_plan import plan_gaps as base_plan


def plan_gaps(
    baseline: str,
    reference_sheet: str,
    config_path: str,
    output: str,
    width_scale: float = 1.0,
    length_scale: float = 1.0,
) -> dict[str, Any]:
    """Variante experimental: abre las ranuras a través de toda la profundidad.

    La posición X/Z sigue derivándose de la referencia y limitada a fingers. Sólo Y
    se extiende fuera del cuerpo para impedir que una tapa frontal/posterior rellene
    la silueta proyectada. No es promotable por sí sola: primero debe demostrar que
    cambia la lectura de dedos sin regresiones regionales.
    """
    plan = base_plan(
        baseline, reference_sheet, config_path, output,
        width_scale=width_scale, length_scale=length_scale,
    )
    for cutter in plan.get("cutters") or []:
        box = list(cutter["box_normalized"])
        box[1] = -0.02
        box[4] = 1.02
        cutter["box_normalized"] = box
        cutter["depth_mode"] = "full_projection_depth"
    plan["mode"] = "finger_reference_gap_plan_full_depth_experiment"
    plan["full_depth_projection_cut"] = True
    plan["promotion_allowed"] = False
    plan["learning"] = (
        "Misma X/Z derivada de la referencia, pero el cutter atraviesa toda la profundidad. "
        "Sirve para probar si tapas residuales explicaban el mitten_shape; requiere gate de scope específico antes de producción."
    )
    Path(output).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan
