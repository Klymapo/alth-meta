from __future__ import annotations

import argparse
import json
from pathlib import Path


def diagnose(uv_path: str, candidate_report: str, output: str) -> dict:
    uv=json.loads(Path(uv_path).read_text(encoding='utf-8'))
    report=json.loads(Path(candidate_report).read_text(encoding='utf-8'))
    comparison=uv.get('comparison') or {}
    hair_like=bool(comparison.get('body_ear_neighborhood_is_closer_to_hair'))
    safe=bool(report.get('geometry_unchanged') and report.get('scope_exact') and float(report.get('bounds_delta',1.0))<=1e-9)
    selected=int(report.get('selected_polygons',0))
    if hair_like and safe and selected>0:
        action='TEST_REFERENCE_DERIVED_SKIN_MATERIAL'
        reason='La zona embebida de oreja se parece cromáticamente más al cabello que a la oreja explícita; existe una mutación material localizada sin cambio geométrico.'
    elif not hair_like:
        action='DO_NOT_RECOLOR_FROM_THIS_HYPOTHESIS'
        reason='El diagnóstico UV no respalda que la zona embebida sea hair-like.'
    else:
        action='FIX_MATERIAL_SCOPE_FIRST'
        reason='La hipótesis puede ser válida, pero el mutador no demostró scope/regresión seguros.'
    result={
        'mode':'material_learning','ready_for_m4_process':bool(hair_like and safe and selected>0),
        'action':action,'reason':reason,'promotion_allowed':False,
        'evidence':{'uv_comparison':comparison,'selected_polygons':selected,'safe_scope':safe}
    }
    out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--uv',required=True); p.add_argument('--candidate-report',required=True); p.add_argument('--output',required=True)
    a=p.parse_args(); r=diagnose(a.uv,a.candidate_report,a.output); print(json.dumps(r,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
