from __future__ import annotations

import argparse, json, shutil, subprocess
from pathlib import Path

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_robust_extrude_plan import plan_robust_extruded_fingers
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _read, _sha256
from copox.production.finger_semantic_finish_trial import run_trial as run_semantic
from copox.production.module_gate import evaluate

VARIANTS=(0.65,0.75,0.85)


def run_trial(baseline, reference, config, policy_path, slot, output_dir):
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    frac=float(VARIANTS[slot-1])
    semantic_root=root/'semantic_base'
    semantic=run_semantic(baseline,reference,config,policy_path,2,str(semantic_root))
    semantic_model=semantic_root/'model.glb'
    plan=plan_robust_extruded_fingers(reference,config,str(root/'robust_plan.json'),side='left')
    repo=Path.cwd().resolve(); alth=ensure_runtime(repo)
    model=root/'model.glb'; report=root/'robust_build.json'
    subprocess.run([alth,str((repo/'copox/adapters/finger_reference_extrude_build.py').resolve()),
        '--input',str(semantic_model.resolve()),'--plan',str((root/'robust_plan.json').resolve()),
        '--output',str(model.resolve()),'--report',str(report.resolve()),
        '--segments','2','--depth-scale','0.45','--tip-scale','0.88','--length-scale','0.90',
        '--delete-distal-fraction',str(frac)],cwd=repo,check=True)
    build=_read(report)
    regional=audit_regions(baseline,str(model),reference,config,str(root/'regional_metrics.json'),str(root/'evidence'))
    target=regional['regions']['fingers']; cfg=_read(config)
    tol=float((cfg.get('approval') or {}).get('freeze_tolerance_pp',-0.20))
    failures=[]
    for name,data in regional['regions'].items():
        if name in {'fingers','hands'}: continue
        if float(data.get('delta_pp',0.0))<tol: failures.append({'region':name,'delta_pp':float(data['delta_pp'])})
    full=audit_full(baseline,str(model),reference,'hair,profile',config,None,str(root/'full_metrics.json'),str(root/'full_evidence'))
    detail=hand_probe(str(model),reference,config,str(root/'hand_detail.json'),str(root/'hand_detail_evidence'))
    topology=topology_probe(str(model),str(root/'topology_report.json'))
    labels={'learning','finger_detail','topology_report'}
    for side in ('left','right'):
        src=root/'hand_detail_evidence'/f'hand_detail_{side}.png'
        if src.exists():
            (root/'evidence').mkdir(parents=True,exist_ok=True); shutil.copy2(src,root/'evidence'/f'hand_{side}.png'); labels.add(f'hand_{side}')
    semantic_ready=bool(detail['summary'].get('definition_match',False))
    learning={'mode':'semantic_finish_plus_scoped_robust_extrusion','delete_distal_fraction':frac,
      'reference_valleys':detail['summary'].get('reference_valleys'),'model_valleys':detail['summary'].get('model_valleys'),
      'frozen_region_failures':failures,'promotion_executed':False}
    (root/'learning.json').write_text(json.dumps(learning,indent=2)+'\n')
    vd=full['visual']['full']['delta_pp']
    result={'module':'fingers','baseline_sha256':_sha256(baseline),'mesh_integrity':bool(build.get('mesh_integrity')),
      'scope_safe':bool(not failures),'regression_ok':bool(not failures),'evidence_complete':{'hand_left','hand_right','finger_detail','topology_report','learning'}<=labels,
      'semantic_ready':semantic_ready,'target_gain_pp':float(target.get('delta_pp',0.0)),'global_gain_pp':float(full['visual'].get('weighted_gain_pp',0.0)),
      'worst_view_delta_pp':float(min(float(vd[v]) for v in ('front','side','back','threeq'))),'evidence':sorted(labels),
      'flags':sorted(set(['bridge_pending','scoped_robust_extrude']+([] if semantic_ready else ['mitten_shape']))),
      'params':{'technique':'semantic_plus_scoped_robust_extrusion','delete_distal_fraction':frac,'segments':2,'depth_scale':0.45,'tip_scale':0.88,'length_scale':0.90}}
    (root/'module_result.json').write_text(json.dumps(result,indent=2)+'\n')
    gate=evaluate(_read(policy_path),result,baseline_model=baseline); (root/'gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    trial={'slot':slot,'semantic_base':semantic['result'],'plan':plan,'build':build,'topology':topology,'hand_detail':detail,'learning':learning,'result':result,'gate':gate,'promotion_executed':False}
    (root/'trial.json').write_text(json.dumps(trial,indent=2)+'\n')
    return trial


def main():
    p=argparse.ArgumentParser(); p.add_argument('--baseline',required=True); p.add_argument('--reference',required=True); p.add_argument('--config',required=True); p.add_argument('--policy',required=True); p.add_argument('--slot',type=int,required=True); p.add_argument('--output-dir',required=True); a=p.parse_args()
    t=run_trial(a.baseline,a.reference,a.config,a.policy,a.slot,a.output_dir); r=t['result']; d=t['hand_detail']['summary']
    print(json.dumps({'slot':a.slot,'delete_distal_fraction':VARIANTS[a.slot-1],'semantic_ready':r['semantic_ready'],'reference_valleys':d.get('reference_valleys'),'model_valleys':d.get('model_valleys'),'target_gain_pp':r['target_gain_pp'],'global_gain_pp':r['global_gain_pp'],'worst_view_delta_pp':r['worst_view_delta_pp'],'regression_ok':r['regression_ok'],'gate':t['gate']['promotion_allowed']},ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
