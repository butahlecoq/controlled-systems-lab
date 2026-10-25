import json
import argparse
from pathlib import Path
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser()
parser.add_argument('results',type=Path)
parser.add_argument('--output-directory',type=Path)
args=parser.parse_args()
root=args.results.parent
out=args.output_directory or root
out.mkdir(parents=True,exist_ok=True)
rows=[json.loads(line) for line in (root/'results.jsonl').read_text().splitlines()]
fig,axes=plt.subplots(len(rows),2,figsize=(12,25),constrained_layout=True)
for row,(flow,stock) in zip(rows,axes):
    pts=row['winner_terminal_vertices_x1_x3_x2_x4']
    flow.scatter([p[0] for p in pts],[p[1] for p in pts],s=5,alpha=.3,color='#167d9a')
    flow.scatter([30],[20],marker='*',s=75,color='#d1495b',label='target')
    flow.set(xlim=(29,31),ylim=(19.5,20.5),xlabel='oxidizer flow x1 (kg/s)',ylabel='fuel flow x3 (kg/s)',title=f"{row['case_id']} | J={row['value_norm']:.4f}")
    flow.grid(alpha=.2); flow.legend(loc='best',fontsize=8)
    stock.scatter([p[2] for p in pts],[p[3] for p in pts],s=5,alpha=.3,color='#167d9a')
    stock.scatter([0],[0],marker='*',s=75,color='#d1495b',label='target')
    stock.set(xlabel='oxidizer stock x2 (kg)',ylabel='fuel stock x4 (kg)',title='terminal stock projection')
    stock.grid(alpha=.2); stock.legend(loc='best',fontsize=8)
fig.suptitle('B07 fuel minimax reconstructions: terminal reachable set projections',fontsize=15)
for ext in ('png','svg'):
    fig.savefig(out/f'b07-eight-case-projections.{ext}',dpi=180)
