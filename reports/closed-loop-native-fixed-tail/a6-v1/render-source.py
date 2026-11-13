"""Render saved native fixed-tail sets and nonlinear observed trajectories."""
import argparse,hashlib,json,pathlib,sys,numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=pathlib.Path);p.add_argument('--root',required=True,type=pathlib.Path);p.add_argument('--task',required=True);p.add_argument('--output',required=True,type=pathlib.Path);a=p.parse_args()
W=a.source_root.resolve(strict=True);sys.path.insert(0,str(W/'scripts/reports'));sys.path.insert(0,str(W/'benchmarks/reporting/closed_loop'))
from plot_feedback_history import project_member
from figure_style import configure_numeric_axis
from contracts import load_task
T=load_task(a.task);target=T['objective'].get('source_definition',{}).get('terminal_target');target_map=dict(enumerate(target)) if target else {0:T['objective']['target']['radius_km'],3:T['objective']['target']['angular_rate_rad_s']};n=len(T['model']['states']);N=T['episode']['intervals'];planes=[(0,1)] if n==2 else [(0,2),(1,3)] if a.task=='syn-nl-fuel-01' else [(0,3),(1,2)]
a.output.mkdir(parents=True,exist_ok=False);provenance=[]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','figure.facecolor':'#16161e','axes.facecolor':'#16161e','text.color':'#e0def4','axes.labelcolor':'#e0def4','xtick.color':'#e0def4','ytick.color':'#e0def4','axes.edgecolor':'#8290a3','axes.spines.top':False,'axes.spines.right':False})
for plane_number,(first,second) in enumerate(planes):
 fig,axes=plt.subplots(2,3,figsize=(12,8),sharex=True,sharey=True,constrained_layout=True)
 for ax,family in zip(axes.flat,['polytope','box','zonotope','parallelotope','ellipsoid']):
  attempts=list((a.root/'runs'/f'{a.task}-{family}'/'records'/a.task/'attempts').glob('*/attempt.json'))
  if len(attempts)!=1:raise ValueError('Expected one frozen attempt')
  attempt_path=attempts[0];episode=json.loads(attempt_path.read_text());response_path=attempt_path.parent/'native-query-000-response.jsonl';d=json.loads(response_path.read_text());states=np.array(d['history'][:(N+1)*n]).reshape(-1,n);actual=np.array(episode['physical_states']);stage_receipts=[]
  for region in d['regions']:
   j=region['stage'];color=plt.cm.viridis(j/N);lo=region['carrier_lower'];hi=region['carrier_upper'];ax.add_patch(plt.Rectangle((lo[first],lo[second]),hi[first]-lo[first],hi[second]-lo[second],fill=False,edgecolor=color,alpha=.18,lw=.55))
   if j==0:continue
   member=region['membership']
   if family=='polytope':converted={'kind':'h',**region['reference']}
   else:converted={'kind':'ellipsoid' if member['factor_domain_norm']=='l2' else 'zonotope','center':member['center'],'factor':member['factor'],'factor_count':len(member['factor'][0])}
   projected=project_member(converted,n,first,second);points=np.array(projected['points']);stage_receipts.append({'stage':j,**projected})
   if len(points)>1:
    closed=np.vstack([points,points[0]]);ax.plot(closed[:,0],closed[:,1],color=color,lw=.7,alpha=.8)
   else:ax.scatter(points[:,0],points[:,1],color=color,s=2)
  ax.plot(states[:,first],states[:,second],color='#e0def4',lw=1,ls='--',alpha=.65);ax.plot(actual[:,first],actual[:,second],color='#f6c177',lw=1.7);ax.scatter(*actual[0,[first,second]],color='#eb6f92',s=22,zorder=5);ax.scatter(*actual[-1,[first,second]],marker='*',color='#f6c177',s=55,zorder=5)
  if first in target_map and second in target_map:ax.scatter(target_map[first],target_map[second],marker='+',color='#e0def4',s=55,zorder=5)
  ax.set_title(f'{family.capitalize()} · {episode["completed_holds"]}/{N} holds');ax.set_xlabel(f'{T["model"]["states"][first]["name"]} ({T["model"]["states"][first]["unit"]})');ax.set_ylabel(f'{T["model"]["states"][second]["name"]} ({T["model"]["states"][second]["unit"]})');configure_numeric_axis(ax)
  provenance.append({'task':a.task,'family':family,'raw_indices':[first,second],'attempt_sha256':hashlib.sha256(attempt_path.read_bytes()).hexdigest(),'response_sha256':hashlib.sha256(response_path.read_bytes()).hexdigest(),'projections':stage_receipts})
 axes.flat[-1].axis('off');axes.flat[-1].text(.02,.96,f'Native C++ fixed-tail policy\n\nAll {N+1} state stages from query 0.\nStage colour: purple → yellow.\n\nPale: all-control axis carrier F.\nSolid: fixed-tail inner region B.\nF ∩ B = B for this construction.\nDashed: query-0 affine history.\nGold: actual nonlinear closed loop.\nRed: initial point; star: final point.\nWhite cross: soft target, where defined.\n\nThe policy recomputes B at every hold.\nQuery-0 sets do not certify the\nsubsequent nonlinear trajectory.\nNo global backward-set, optimum\nor nonlinear-safety claim.\n\nNative stderr retained in the shared\nsupervised worker/native stream.',va='top',transform=axes.flat[-1].transAxes,linespacing=1.45)
 fig.suptitle(f'{a.task}: five physical families on the same nonlinear task',fontsize=14)
 fig.canvas.draw()
 for ax,family in zip(axes.flat,['polytope','box','zonotope','parallelotope','ellipsoid']):
  bounds=ax.get_tightbbox(fig.canvas.get_renderer()).transformed(fig.dpi_scale_trans.inverted()).expanded(1.03,1.03)
  fig.savefig(a.output/f'{family}-plane-{plane_number+1}.svg',bbox_inches=bounds)
 fig.savefig(a.output/f'plane-{plane_number+1}.svg');fig.savefig(a.output/f'plane-{plane_number+1}.png',dpi=140);plt.close(fig)
(a.output/'projection-receipt.json').write_text(json.dumps({'source_root_commit':'a6b7d1cb','renderer_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'projection_helper_sha256':hashlib.sha256((W/'scripts/reports/plot_feedback_history.py').read_bytes()).hexdigest(),'scope':'Saved initial-query conditional inner regions and carriers with actual nonlinear closed-loop trajectory; not global backward sets or a nonlinear safety proof','plots':provenance},indent=2)+'\n')
