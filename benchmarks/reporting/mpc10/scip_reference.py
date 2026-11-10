"""Independent one-hot/linear-indicator encoding; no guessed big-M rows."""
import math
from pathlib import Path
import time
from pyscipopt import Model,quicksum,SCIP_PARAMSETTING


def formulate(s,folder,path=None,interrupted=False):
    model=Model(s['id']);model.setLogfile(str(folder/'solver.log'))
    for key,value in [('limits/time',15.),('limits/memory',512.),('parallel/maxnthreads',1),('numerics/feastol',1e-9),('randomization/randomseedshift',0)]:model.setParam(key,value)
    model.setParam('limits/nodes',0 if interrupted else 10000)
    if interrupted:model.setPresolve(SCIP_PARAMSETTING.OFF)
    T=s['horizon'];binary={}
    if s['product']!='hybrid':
        x=[model.addVar(f'x_{k}',lb=b[0],ub=b[1]) for k,b in enumerate(s['state_bounds'])]
        bounds=[0,0] if s['product']=='finite' else s['continuous_bounds']
        u=[model.addVar(f'u_{k}',lb=bounds[0],ub=bounds[1]) for k in range(T)]
        for k in range(T):
            choice=[model.addVar(f'action_{k}_{j}',vtype='B') for j in range(len(s['catalogue']))]
            binary[k]=choice;model.addCons(quicksum(choice)==1)
            model.addCons(x[k+1]==x[k]+u[k]+quicksum(a*z for a,z in zip(s['catalogue'],choice)))
            if path is not None:
                for j,z in enumerate(choice):model.addCons(z==int(j==path['actions'][k]))
        model.addCons(x[0]==s['initial_x']);c,offset=s['terminal_linear'];model.setObjective(c*x[-1]+offset)
        return model,{'x':x,'u':u,'actions':binary}
    modes={m['id']:m for m in s['modes']};edges=s['edges']
    union=[(min(m['invariants'][k][0] for m in modes.values()),max(m['invariants'][k][1] for m in modes.values())) for k in range(T+1)]
    x=[model.addVar(f'x_{k}',lb=b[0],ub=b[1]) for k,b in enumerate(union)]
    pre=[model.addVar(f'pre_{k}',lb=union[k+1][0],ub=union[k+1][1]) for k in range(T)]
    lower=min(m['control_bounds'][0] for m in modes.values());upper=max(m['control_bounds'][1] for m in modes.values())
    u=[model.addVar(f'u_{k}',lb=lower,ub=upper) for k in range(T)]
    z={(k,name):model.addVar(f'mode_{k}_{name}',vtype='B') for k in range(T+1) for name in modes}
    w={(k,e['id']):model.addVar(f'edge_{k}_{e["id"]}',vtype='B') for k in range(T) for e in edges}
    def le(expr,rhs,selector):model.addConsIndicator(expr<=rhs,binvar=selector)
    def eq(expr,rhs,selector):le(expr,rhs,selector);le(-expr,-rhs,selector)
    def bound(value,b,selector):le(value,b[1],selector);le(-value,-b[0],selector)
    for k in range(T+1):
        model.addCons(quicksum(z[k,name] for name in modes)==1)
        for name,m in modes.items():
            bound(x[k],m['invariants'][k],z[k,name])
            if path is not None:model.addCons(z[k,name]==int(name==path['modes'][k]))
    model.addCons(x[0]==s['initial_x']);model.addCons(z[0,s['initial_mode']]==1)
    for k in range(T):
        model.addCons(quicksum(w[k,e['id']] for e in edges)==1)
        for name,m in modes.items():
            model.addCons(quicksum(w[k,e['id']] for e in edges if e['source']==name)==z[k,name])
            model.addCons(quicksum(w[k,e['id']] for e in edges if e['target']==name)==z[k+1,name])
            eq(pre[k]-m['flow_a']*x[k]-u[k],m['flow_offset'],z[k,name]);bound(u[k],m['control_bounds'],z[k,name]);bound(pre[k],m['invariants'][k+1],z[k,name])
        for e in edges:
            selector=w[k,e['id']];bound(pre[k],e['guards'][k],selector);r,d=e['reset'];eq(x[k+1]-r*pre[k],d,selector)
            if path is not None:model.addCons(selector==int(e['id']==path['edges'][k]))
    objective_bounds=[]
    for name,m in modes.items():
        c,offset=m['terminal_linear'];objective_bounds.extend([c*union[-1][0]+offset,c*union[-1][1]+offset])
        if name not in s['allowed_terminal_modes']:model.addCons(z[T,name]==0)
    q=model.addVar('terminal_objective',lb=min(objective_bounds),ub=max(objective_bounds))
    for name,m in modes.items():
        c,offset=m['terminal_linear'];eq(q-c*x[T],offset,z[T,name])
    model.setObjective(q)
    return model,{'x':x,'pre':pre,'u':u,'modes':z,'edges':w}


def solve(s,folder,path=None,interrupted=False):
    folder.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();model,variables=formulate(s,folder,path,interrupted);setup=time.monotonic()-started
    counts={'variables':model.getNVars(),'constraints':model.getNConss(),'binary_variables':sum(v.vtype()=='BINARY' for v in model.getVars())}
    model.writeProblem(str(folder/'model.cip'));model.writeParams(str(folder/'parameters.set'),onlychanged=True);started=time.monotonic();model.optimize();elapsed=time.monotonic()-started
    def finite(value):return float(value) if math.isfinite(value) and abs(value)<1e19 else None
    result={'status':str(model.getStatus()),'formulation_and_setup_seconds':setup,'optimization_seconds':elapsed,'counts':counts,'nodes':model.getNNodes(),'primal_bound':finite(model.getPrimalbound()),'dual_bound':finite(model.getDualbound()),'gap':finite(model.getGap()),'fixed_path':path,'interrupted_request':interrupted,'assurance':'SCIP numerical incumbent/bound, not complete continuous-family evidence','scip_version':[model.getMajorVersion(),model.getMinorVersion(),model.getTechVersion()]}
    if model.getNSols():
        model.writeBestSol(str(folder/'solution.sol'),write_zeros=True)
        best=model.getBestSol();result['objective']=float(model.getSolObjVal(best));result['states']=[float(model.getSolVal(best,v)) for v in variables['x']];result['controls']=[float(model.getSolVal(best,v)) for v in variables['u']]
        if 'actions' in variables:result['path']={'actions':[next(j for j,v in enumerate(variables['actions'][k]) if model.getSolVal(best,v)>.5) for k in range(s['horizon'])]}
        else:result['path']={'modes':[next(name for name in [m['id'] for m in s['modes']] if model.getSolVal(best,variables['modes'][k,name])>.5) for k in range(s['horizon']+1)],'edges':[next(e['id'] for e in s['edges'] if model.getSolVal(best,variables['edges'][k,e['id']])>.5) for k in range(s['horizon'])]}
    model.freeProb();return result
