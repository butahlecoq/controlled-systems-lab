import json,sys
from fractions import Fraction as Q
from itertools import combinations
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from matplotlib import pyplot as plt
from matplotlib.collections import PolyCollection

data=json.loads(Path(sys.argv[1]).read_text())
H={}
def matrix(v): return np.array([[float(Q(x)) for x in row] for row in v])
def edges(poly): return np.roll(poly,-1,axis=0)-poly
def contains(poly,x):
    delta=x-poly; e=edges(poly)
    return np.all(e[:,0]*delta[:,1]-e[:,1]*delta[:,0]>=-2e-10)
def feedback(n,x):
    for poly,U in H[n]:
        if contains(poly,x): return U@[*x,1]
def rollout(x,w):
    states=[np.array(x)]
    for u in w:
        p,v=states[-1];states.append(np.array([p+v,v+u]))
    return np.array(states)
def cost(x,w):
    z=rollout(x,w)[-1]
    return z@z+0.25*(w@w)
def slack(x,w):
    s=rollout(x,w);p,v=s.T;a,b=s[-1]
    return np.r_[3-p,3+p,2-v,2+v,1-a-b,1+a+b,1-a-2*b,1+a+2*b]
stats=[]
for h in data['horizons']:
    n=h['remaining'];H[n]=[(matrix(c['vertices']),matrix(c['controls'])) for c in h['cells']]
    samples=[poly.mean(0) for poly,_ in H[n]]
    sides=0
    for (p,_),(q,_) in combinations(H[n],2):
        hits=[a for a in p if contains(q,a)]+[a for a in q if contains(p,a)]
        if len(hits)<2: continue
        pair=max(combinations(hits,2), key=lambda ab:np.linalg.norm(ab[0]-ab[1]))
        if np.linalg.norm(pair[0]-pair[1])<1e-7: continue
        mid=(pair[0]+pair[1])/2
        samples.extend([mid,mid+(p.mean(0)-mid)/1024,mid+(q.mean(0)-mid)/1024]);sides+=1
    errs=[]
    for x in samples:
        U=feedback(n,x); assert U is not None
        res=minimize(lambda u:cost(x,u),np.zeros(n),bounds=[(-1,1)]*n,
                     constraints=[dict(type='ineq',fun=lambda u:slack(x,u))],
                     method='SLSQP', options={'ftol':1e-12,'maxiter':200})
        assert res.success, (n,x,res.message)
        err=[np.max(np.abs(res.x-U)),abs(cost(x,res.x)-cost(x,U))]
        assert err[0]<2e-6 and err[1]<1e-8 and np.min(slack(x,U))>-1e-10,(n,x,err)
        errs.append(err)
    stats.append({'remaining':n,'regions':len(H[n]),'boundaries_sampled':sides,'queries':len(samples),
                  'max_history_difference':max(e[0] for e in errs),'max_cost_difference':max(e[1] for e in errs)})
print(json.dumps(stats,indent=2))
fig,axes=plt.subplots(1,3,figsize=(12,4.5),sharex=True,sharey=True,layout='constrained')
for ax,n in zip(axes,(3,2,1)):
    polys=[p for p,_ in H[n]]; actions=[float((u@[*p.mean(0),1])[0]) for p,u in H[n]]
    cm=PolyCollection(polys,array=np.array(actions),cmap='coolwarm',edgecolors='#606468',linewidths=.85,clim=(-1,1))
    ax.add_collection(cm); ax.set(xlim=(-3.1,3.1),ylim=(-2.1,2.1),xlabel='Position',aspect='equal',title=f'{n} remaining step'+('s' if n>1 else ''))
    ax.grid(alpha=.12)
    for x0 in [(-2.,.5),(2.,-1.25)]:
        x=np.array(x0); path=[x.copy()]
        for j in range(3,n-1,-1):
            u=feedback(j,x); assert u is not None
            x=rollout(x,u[:1])[-1]; path.append(x.copy())
        pts=np.array(path); ax.plot(*pts.T,'k.-',lw=1.2,ms=5)
        ax.plot(*pts[-1],'ko',ms=3.2)
axes[0].set_ylabel('Velocity')
fig.colorbar(cm,ax=axes,orientation='horizontal',shrink=.5,label='First acceleration at cell centroid')
fig.suptitle('Three-step constrained double integrator · exact feedback regions',fontsize=14)
fig.savefig(Path(sys.argv[1]).with_name('feedback-regions.png'),dpi=170)
plt.close(fig)
