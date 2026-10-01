from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from copox.adapters.alth_character_audit import audit
from copox.adapters.global_axis_morph import morph


def check_view_regression(view_deltas: dict, max_drop_pp: float = 0.20) -> dict:
    required = ('front', 'side', 'back', 'threeq')
    failed = [view for view in required if view not in view_deltas or not math.isfinite(float(view_deltas[view])) or float(view_deltas[view]) < -max_drop_pp]
    return {'ok': not failed, 'max_drop_pp': max_drop_pp, 'failed_views': failed}


def study(baseline: str, reference: str, config: str, output_dir: str, step: float = 0.02) -> dict:
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    hypotheses=[
        ("baseline",[1.0,1.0,1.0]),
        ("width_less",[1.0-step,1.0,1.0]), ("width_more",[1.0+step,1.0,1.0]),
        ("depth_less",[1.0,1.0-step,1.0]), ("depth_more",[1.0,1.0+step,1.0]),
        ("height_less",[1.0,1.0,1.0-step]), ("height_more",[1.0,1.0,1.0+step]),
    ]
    results=[]
    for hid,scale in hypotheses:
        hdir=root/hid; hdir.mkdir(parents=True,exist_ok=True)
        model=hdir/'model.glb'
        if hid=='baseline':
            shutil.copy2(baseline,model)
            morph_report={"mode":"baseline","mesh_integrity":True,"scale_xyz":scale}
        else:
            morph_report=morph(baseline,str(model),str(hdir/'morph.json'),scale)
        metrics=audit(
            baseline,str(model),reference,"head,hair,arms,legs,feet",config,None,
            str(hdir/'metrics.json'),str(hdir/'evidence')
        )
        full=metrics['visual']['full']['candidate']
        results.append({
            "id":hid,"scale_xyz":scale,"weighted_iou":float(full['weighted']),
            "weighted_delta_pp":float(metrics['visual']['weighted_gain_pp']),
            "max_view_drop_pp":float(min(metrics['visual']['full']['delta_pp'][v] for v in ('front','side','back','threeq'))),
            "regression":check_view_regression(metrics['visual']['full']['delta_pp']),
            "morph":morph_report,
        })
    ranking=sorted(results,key=lambda x:x['weighted_iou'],reverse=True)
    base=next(x for x in results if x['id']=='baseline')
    eligible=[x for x in ranking if x['regression']['ok'] and x['morph']['mesh_integrity']]
    best=eligible[0]
    if best['id']=='baseline':
        conclusion='GLOBAL_AXIS_CHANGE_NOT_NEEDED'
    elif best['weighted_delta_pp']>0:
        conclusion='GLOBAL_AXIS_HYPOTHESIS_IMPROVES_MATCH'
    else:
        conclusion='LOCAL_REGIONS_SHOULD_BE_PRIORITIZED'
    result={
        "mode":"learning_only_no_promotion","results":results,"ranking":ranking,
        "eligible_hypotheses":[x['id'] for x in eligible],
        "best_hypothesis":best['id'],"baseline_weighted_iou":base['weighted_iou'],
        "conclusion":conclusion,"promotion_allowed":False,
        "learning":"Si un cambio global no supera a baseline, distribuir el error a regiones y evitar deformar zonas ya correctas."
    }
    (root/'study.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main()->int:
    p=argparse.ArgumentParser(description='Estudio learning-first de proporción/silueta global')
    p.add_argument('--baseline',required=True); p.add_argument('--reference',required=True)
    p.add_argument('--config',required=True); p.add_argument('--output-dir',required=True)
    p.add_argument('--step',type=float,default=0.02)
    a=p.parse_args(); r=study(a.baseline,a.reference,a.config,a.output_dir,a.step)
    print(json.dumps({"best":r['best_hypothesis'],"conclusion":r['conclusion']},ensure_ascii=False)); return 0

if __name__=='__main__': raise SystemExit(main())
