from __future__ import annotations

import argparse
import json
from pathlib import Path


def diagnose(report_path: str, output: str) -> dict:
    report=json.loads(Path(report_path).read_text(encoding='utf-8'))
    o=report.get('orientation') or {}
    vertical=bool(o.get('vertical_ok',False)); hair=bool(o.get('hair_above_body',False)); ok=bool(o.get('ok',False))
    if ok:
        action='KEEP_CANONICAL_CORRECTION'; reason='La importación queda vertical y el cabello está sobre el cuerpo.'
    elif not vertical:
        action='RECALCULATE_UP_AXIS'; reason='El eje longitudinal no quedó en +Z; inferir eje mayor antes de render/auditoría.'
    elif not hair:
        action='FLIP_VERTICAL_SIGN'; reason='El personaje está vertical pero invertido; usar el cabello como marcador semántico de arriba.'
    else:
        action='BLOCK_UNKNOWN_ORIENTATION'; reason='La orientación no cumple los invariantes conocidos.'
    result={'mode':'orientation_learning','ready':ok,'action':action,'reason':reason,'observed':o,'promotion_allowed':False}
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--report',required=True); p.add_argument('--output',required=True)
    a=p.parse_args(); r=diagnose(a.report,a.output); print(json.dumps(r,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
