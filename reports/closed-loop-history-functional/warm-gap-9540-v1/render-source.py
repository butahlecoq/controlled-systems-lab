"""Offline figures/reading page from immutable attempt archives; no controller runs."""
import argparse,hashlib,html,importlib.util,json,math,shutil,zipfile,sys
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt']='csl-history-warm-9540-v1'
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def render(bundle):
 bundle=bundle.resolve();spec=importlib.util.spec_from_file_location('saved_projection',bundle/'projection-source.py');projection=importlib.util.module_from_spec(spec);spec.loader.exec_module(projection)
 index=json.loads((bundle/'records.json').read_text());pre=json.loads((bundle/'source-build-receipt.json').read_text());tasks=json.loads((bundle/'tasks.json').read_text());out=bundle/'figures';out.mkdir(exist_ok=False);figures=[]
 for rec in index['records']:
  archivepath=bundle/'records'/rec['id']/'raw.zip';assert sha(archivepath)==rec['archive_sha256'];receipt=json.loads((archivepath.parent/'receipt.json').read_text())
  with zipfile.ZipFile(archivepath) as z:
   assert z.testzip() is None
   for name,expected in receipt['archive_members'].items():
    data=z.read(name);assert hashlib.sha256(data).hexdigest()==expected['sha256']
   episode=json.loads(z.read('attempt/attempt.json'));stage=json.loads(z.read('attempt/stage-000.json'));capture=stage.get('native_query_capture');response=None
   if capture:
    meta=json.loads(z.read('attempt/'+capture['path']))
    if meta.get('response'):response=json.loads(z.read('attempt/'+meta['response']['path']))
  task=tasks[rec['task']]
  labels=[(s['name'],s['unit']) for s in task['model']['states']]
  if rec['task']=='earth-orbit':
   planes=[(0,1),(2,3),(0,3)];target=task['objective']['target'];targets=[target['radius_km'],None,None,target['angular_rate_rad_s']]
  else:
   planes=[(0,1)] if rec['task']=='syn-nl-lv-01' else [(2,0),(3,1)];targets=task['objective']['source_definition']['terminal_target']
  nx=len(labels);trajectory=np.asarray(episode.get('physical_states') or [stage['observed_physical']],dtype=float);geometry=response.get('geometry',{}) if response else {};geometry=geometry if isinstance(geometry,dict) else {};projected=[];errors=[]
  for first,second in planes:
   sets=[]
   for gs in geometry.get('stages',[]):
    available={m['role']:m for m in gs.get('memberships',[])}
    for role in ('forward','backward','intersection'):
     if role not in available and role+'_h' in gs:available[role]={'kind':'h',**gs[role+'_h']}
    for role,m in available.items():
     try:
      p=projection.project_member(m,nx,first,second);sets.append({'stage':gs['stage'],'role':role,'points':p['points'],'method':p['method']})
     except ValueError as error:errors.append({'stage':gs['stage'],'role':role,'plane':[first,second],'reason':str(error)})
   projected.append(sets)
  for variant in ['screen','print']:
   dark=variant=='screen';bg='#16161e' if dark else '#ffffff';fg='#e0def4' if dark else '#202124';accent='#f6c177' if dark else '#8b5800';fig,axes=plt.subplots(1,len(planes),figsize=(5.1*len(planes),5.8),squeeze=False);fig.patch.set_facecolor(bg)
   for axis,(first,second),sets in zip(axes[0],planes,projected,strict=True):
    axis.set_facecolor(bg)
    for data in sets:
     points=np.asarray(data['points']);color=plt.get_cmap('viridis')(data['stage']/max(rec['original_intervals'],1));style={'forward':'-','backward':'--','intersection':':'}[data['role']]
     if len(points)==1:axis.scatter(points[:,0],points[:,1],s=6,color=color)
     else:
      closed=np.vstack([points,points[:1]]) if len(points)>2 else points;axis.plot(closed[:,0],closed[:,1],linestyle=style,color=color,alpha=.7,linewidth=.8)
    if len(trajectory)>1:axis.plot(trajectory[:,first],trajectory[:,second],color=accent,linewidth=2.1,zorder=5)
    axis.scatter([trajectory[0,first]],[trajectory[0,second]],s=38,c='#78b589',marker='o',edgecolor=fg,zorder=6)
    if len(trajectory)>1:axis.scatter([trajectory[-1,first]],[trajectory[-1,second]],s=65,c=accent,marker='*' if rec['full_episode'] else 'X',edgecolor=fg,zorder=7)
    if targets[first] is not None and targets[second] is not None:axis.scatter([targets[first]],[targets[second]],marker='+',s=75,c=fg,zorder=7)
    elif targets[first] is not None:axis.axvline(targets[first],linestyle='-.',color=fg,alpha=.5)
    elif targets[second] is not None:axis.axhline(targets[second],linestyle='-.',color=fg,alpha=.5)
    axis.set_xlabel(labels[first][0]+' ('+labels[first][1]+')',color=fg);axis.set_ylabel(labels[second][0]+' ('+labels[second][1]+')',color=fg);axis.tick_params(colors=fg)
    for spine in axis.spines.values():spine.set_color(fg)
    axis.ticklabel_format(style='plain',axis='both',useOffset=False)
    axis.grid(alpha=.12,color=fg)
   handles=[Line2D([0],[0],color=fg,linestyle=s,label=l) for s,l in [('-','Forward F'),('--','Forward-relevant backward B'),(':','Intersection I')]] if any(projected) else []
   handles += [Line2D([0],[0],color=accent,label='Observed nonlinear plant ('+str(rec['completed_holds'])+' holds)'),Line2D([0],[0],marker='o',color='#78b589',linestyle='none',label='Initial state'),Line2D([0],[0],marker='+',color=fg,linestyle='none',label='Soft source reference')]
   if len(trajectory)>1:handles.append(Line2D([0],[0],marker='*' if rec['full_episode'] else 'X',color=accent,linestyle='none',label='Executed final state' if rec['full_episode'] else 'Last accepted prefix state'))
   fig.legend(handles=handles,loc='lower center',ncol=3,fontsize=8,labelcolor=fg,frameon=False,bbox_to_anchor=(.5,.08));fig.suptitle(rec['task']+' · '+rec['family']+' · '+str(rec['completed_holds'])+'/'+str(rec['original_intervals'])+' holds · '+rec['outcome'],color=fg,fontsize=12)
   note='First observed query only; saved full-state sets precede projection. Original complete running/terminal objective.'
   if not geometry:note='No returned set geometry. Only saved observed states/reference shown; no reachable/backward sets invented.'
   elif geometry.get('status')!='complete':note='Geometry stopped: only available saved forward prefix drawn. Backward/intersection sets are unavailable.'
   elif not rec['full_episode']:note+=' Failed query retained; plotted path stops at last accepted hold.'
   fig.text(.5,.025,note+' Predicted-stage colors: purple 0 to yellow '+str(rec['original_intervals'])+'.\nFresh installed SDK source ab3fdba6; controller source 9540b8d0. Numerical affine sets; no nonlinear safety/global optimality certificate.',ha='center',color=fg,fontsize=7)
   fig.tight_layout(rect=(.01,.2,.99,.93));name=rec['id']+'-'+variant;svg=out/(name+'.svg');png=out/(name+'.png');fig.savefig(svg,facecolor=bg,metadata={"Date":None});fig.savefig(png,facecolor=bg,dpi=125);plt.close(fig)
   figures.append({'record_id':rec['id'],'variant':variant,'svg':'figures/'+svg.name,'png':'figures/'+png.name,'svg_sha256':sha(svg),'png_sha256':sha(png),'raw_state_projections':planes,'available_memberships_drawn':[len(x) for x in projected],'projection_failures':errors,'scope':'First query saved geometry only; actual executed path full or explicitly partial. Soft references are not terminal constraints.'})
  print('RENDERED',rec['id'],flush=True)
 (bundle/'figure-receipt.json').write_text(json.dumps({'source_commit':index['source_commit'],'sdk_source_commit':index['sdk_source_commit'],'renderer_sha256':sha(Path(__file__)),'projection_source_sha256':sha(bundle/'projection-source.py'),'figures':figures},indent=2)+'\n')
 title='Warm full-horizon MPC: initial functional outcomes';rows=[];cards=[]
 for rec in index['records']:
  objective=rec['physical_objective'];score=format(objective['total'],'.10g') if objective else '—';base='records/'+rec['id']+'/';rows.append('<tr><td>'+html.escape(rec['task'])+'</td><td>'+html.escape(rec['family'])+'</td><td>'+str(rec['completed_holds'])+'/'+str(rec['original_intervals'])+'</td><td>'+html.escape(rec['outcome'])+'</td><td>'+score+'</td><td><a href="'+base+'raw.zip">Raw ZIP</a> · <a href="'+base+'receipt.json">Receipt</a></td></tr>');f=next(x for x in figures if x['record_id']==rec['id'] and x['variant']=='screen');cards.append('<section id="'+rec['id']+'"><h2>'+html.escape(rec['task']+' · '+rec['family'])+'</h2><p>'+html.escape(rec['reason'])+'</p><a href="'+f['svg']+'"><img class="screen" src="'+f['svg']+'" alt="'+html.escape(rec['task']+' '+rec['family']+' saved sets and observed trajectory')+'"></a><img class="print" src="'+f['svg'].replace('-screen.svg','-print.svg')+'" alt="Print version"><p><a href="'+base+'raw.zip">Offline raw attempt and supervisor records</a> · <a href="'+base+'receipt.json">Exact per-member hashes and source identities</a></p></section>')
 page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><link rel="stylesheet" href="theme.css"><style>main{max-width:1300px;margin:auto;padding:2rem}img{width:100%;height:auto}.print{display:none}table{width:100%;min-width:760px;border-collapse:collapse}td,th{white-space:nowrap;text-align:left;padding:.5rem;border-bottom:1px solid var(--border)}.table-wrap{overflow:auto}section{margin:3rem 0}@media print{table{min-width:0;font-size:8pt}td,th{white-space:normal}.table-wrap{overflow:visible}.screen{display:none}.print{display:block}main{padding:0}section{break-inside:avoid}}</style></head><body><main class="page-content"><a href="../index.html">All affine-history functional evidence</a><h1>'+title+'</h1><p>Eight complete episodes; seven other selected profile outcomes. Sixteen archives retain the fifteen missing profile attempts plus one earlier nonterminal LV polytope lifecycle. This is issue 943 functional validation; issue 947 timing and exhaustive campaign requirements remain open.</p><p>Controller source <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/9540b8d0b441f3f3e544d2016abb4ee53c94da0b"><code>9540b8d0</code></a>; genuine installed SDK producer <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/ab3fdba672d9227e7631e7fec9b10bc91196c285"><code>ab3fdba6</code></a>. All original horizons, continuous actions and complete source costs are retained. The IPOPT route still uses Python/CasADi orchestration; model/history/cost/geometry are compiled through the C++ bridge. These one-off numerical observations provide no speed ranking, global optimum or nonlinear safety certificate.</p><p>The last ten attempts isolate only the numerical worker in 2 GiB memory + 2 GiB swap, with the recording parent outside. Earlier direct runs and the fuel zonotope run use separately disclosed envelopes. OOM, solver limits, geometry allocation stops and unknown lifecycle termination remain distinct. A local Infeasible_Problem_Detected status is not proof that the source control problem is infeasible.</p><div class="table-wrap" role="region" tabindex="0" aria-label="Attempt outcomes"><table><thead><tr><th>Original task</th><th>Profile</th><th>Holds</th><th>Outcome</th><th>Physical J</th><th>Evidence</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p>F/B/I drawings use every available stage from the first query, with intersections formed in full state space before projection. Failed paths end at the last accepted hold; initial-query failures show no executed trajectory. The soft source reference is not a hard terminal set.</p>'+''.join(cards)+'<p>Offline figure redraw: <code>python render-source.py --bundle . --output ../warm-gap-preview</code>. This reads saved ZIPs and never executes a controller.</p><p><a href="records.json">Machine-readable index</a> · <a href="source-build-receipt.json">SDK/source/configuration receipts</a> · <a href="figure-receipt.json">Figure provenance</a> · <a href="render-source.py">Offline renderer source</a></p></main></body></html>'
 (bundle/'index.html').write_text(page)
 shutil.copy2(Path(__file__),bundle/'render-source.py')
 for svg in out.glob('*.svg'):
  text=svg.read_text();svg.write_text(''.join(line.rstrip()+'\n' for line in text.replace('<svg ', '<svg role="img" ',1).splitlines()))
 # Hashes refer to final accessible SVG bytes.
 receipt=json.loads((bundle/'figure-receipt.json').read_text())
 for f in receipt['figures']:f['svg_sha256']=sha(bundle/f['svg'])
 (bundle/'figure-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 files={str(p.relative_to(bundle)):sha(p) for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='files.sha256' and '__pycache__' not in p.parts and p.suffix!='.pyc'};(bundle/'files.sha256').write_text(''.join(v+'  '+k+'\n' for k,v in files.items()))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args()
 if args.output:
  shutil.copytree(args.bundle,args.output,ignore=shutil.ignore_patterns('figures','index.html','figure-receipt.json','files.sha256'))
 render(args.output or args.bundle)
