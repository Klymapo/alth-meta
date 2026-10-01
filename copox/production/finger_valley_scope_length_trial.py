from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.adapters.finger_valley_sculpt import sculpt_valleys as real_sculpt
from copox.production import finger_valley_sculpt_trial as base


FINGER_X1 = 0.115
LENGTH_SCALES = (1.10, 1.20, 1.25)
SCULPT_STRENGTH = 0.55


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    if slot not in (1,2,3):
        raise ValueError("slot debe ser 1..3")
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(Path(config).read_text(encoding='utf-8'))
    original_x1=float(cfg['morph_regions']['fingers']['boxes'][0][3])
    hand_x1=float(cfg['morph_regions']['hands']['boxes'][0][3])
    if not (original_x1 < FINGER_X1 < hand_x1):
        raise RuntimeError('FINGER_X1 experimental fuera del límite de hand')
    cfg['morph_regions']['fingers']['boxes'][0][3]=FINGER_X1
    exp_cfg=root/'expanded_config.json'
    exp_cfg.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    length=LENGTH_SCALES[slot-1]
    original_sculpt=base.sculpt_valleys
    original_strengths=base.SCULPT_STRENGTHS
    def scoped_sculpt(baseline_model,input_model,reference_sheet,config_path,output,report_path,strength=SCULPT_STRENGTH,length_scale=1.0):
        return real_sculpt(baseline_model,input_model,reference_sheet,config_path,output,report_path,
                           strength=SCULPT_STRENGTH,length_scale=length)
    try:
        base.sculpt_valleys=scoped_sculpt
        base.SCULPT_STRENGTHS=(SCULPT_STRENGTH,SCULPT_STRENGTH,SCULPT_STRENGTH)
        trial=base.run_trial(baseline,reference,str(exp_cfg),policy,slot,output_dir)
    finally:
        base.sculpt_valleys=original_sculpt
        base.SCULPT_STRENGTHS=original_strengths

    trial['scope_length_experiment']=True
    trial['experimental_finger_x1']=FINGER_X1
    trial['length_scale']=length
    trial['promotion_executed']=False
    trial['result']['params'].update({'experimental_finger_x1':FINGER_X1,'length_scale':length})
    trial['learning'].update({'experimental_finger_x1':FINGER_X1,'length_scale':length})
    Path(output_dir,'trial.json').write_text(json.dumps(trial,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return trial


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',required=True); p.add_argument('--reference',required=True)
    p.add_argument('--config',required=True); p.add_argument('--policy',required=True)
    p.add_argument('--slot',type=int,required=True); p.add_argument('--output-dir',required=True)
    a=p.parse_args(); t=run_trial(a.baseline,a.reference,a.config,a.policy,a.slot,a.output_dir)
    first=(t['sculpt'].get('targets') or [{}])[0]; d=t['hand_detail']['summary']; r=t['result']
    print(json.dumps({
      'slot':a.slot,'length_scale':LENGTH_SCALES[a.slot-1],
      'first_selected':first.get('selected_vertices',0),'first_moved':first.get('moved_vertices',0),
      'first_max_shift_mm':first.get('max_shift_mm',0.0),'model_valleys':d.get('model_valleys'),
      'semantic_ready':r['semantic_ready'],'target_gain_pp':r['target_gain_pp'],
      'global_gain_pp':r['global_gain_pp'],'worst_view_delta_pp':r['worst_view_delta_pp'],
      'scope_safe':r['scope_safe'],'regression_ok':r['regression_ok'],
      'promotion_allowed':t['gate']['promotion_allowed'],'reasons':t['gate']['reasons']},ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
