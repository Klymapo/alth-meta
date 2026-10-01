from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED={"blink_left","blink_right","mouth_open"}


def diagnose(candidate_report: str, structure_path: str, output: str) -> dict:
    candidate=json.loads(Path(candidate_report).read_text(encoding='utf-8'))
    structure=json.loads(Path(structure_path).read_text(encoding='utf-8'))
    controls=set((candidate.get('controls') or {}).keys())
    target_names={name for row in structure.get('rig',{}).get('morph_target_meshes',[]) for name in row.get('target_names',[])}
    rest_ok=bool(candidate.get('rest_vertices_unchanged'))
    moves=bool(candidate.get('all_controls_move_vertices'))
    exported=EXPECTED <= target_names
    ready=bool(EXPECTED<=controls and rest_ok and moves and exported and structure.get('counts',{}).get('morph_targets',0)>=3)
    result={
        'mode':'facial_control_learning','ready_for_m4_process':ready,
        'controls':sorted(controls),'exported_target_names':sorted(target_names),
        'rest_pose_stable':rest_ok,'all_controls_move_vertices':moves,'exported':exported,
        'next_action':'REVIEW_ACTIVE_CONTROL_PREVIEWS_AGAINST_REFERENCE',
        'promotion_allowed':False,
        'learning':'M4 demuestra controles localizados, reversibles y exportables. La semántica final de párpado/boca debe afinarse visualmente contra la referencia antes de M5.'
    }
    out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--candidate-report',required=True); p.add_argument('--structure',required=True); p.add_argument('--output',required=True)
    a=p.parse_args(); r=diagnose(a.candidate_report,a.structure,a.output); print(json.dumps(r,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
