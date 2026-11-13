"""Plot only the saved native toy point and its analytic equality; never optimize."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
record = json.loads((root/'records/analytic-result.json').read_text())
point = record['observed_x']
plt.rcParams.update({'svg.hashsalt':'csl-row-diagnostic-v1', 'font.size':11})
fig, ax = plt.subplots(figsize=(6.6,4.8), layout='constrained')
ax.plot([0,3],[3,0],color='#40526b',label='Original feasible line: x + y = 3')
ax.scatter(*point,s=150,facecolors='none',edgecolors='#006e84',linewidths=2.4,label='Recorded native point (1.5, 1.5)',zorder=3)
ax.scatter(*record['analytic_x'],s=50,marker='x',color='#a24119',label='Analytic optimum (same point)',zorder=4)
ax.annotate('Original objective: x² + y² = 4.5',xy=point,xytext=(.1,2.55),arrowprops={'arrowstyle':'->','color':'#536270'},fontsize=10)
ax.set(xlabel='Original coordinate x',ylabel='Original coordinate y',xlim=(-.2,3.3),ylim=(-.2,3.3),title='Positive row scaling preserves the analytic toy')
ax.set_aspect('equal');ax.grid(alpha=.23);ax.legend(loc='upper right',bbox_to_anchor=(1.02,-.15),fontsize=9)
fig.savefig(root/'toy.svg',metadata={'Date':None,'Description':'Exact dyadic input 2^-50(x+y)=3*2^-50; positive row scaling by 2^50. Native observed point and analytic optimum shown in original coordinates.'})
fig.savefig(root/'toy.png',dpi=160,metadata={'Description':'Saved native point and analytic equality in original coordinates'})
plt.close(fig)
