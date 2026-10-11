import ast,pathlib,json,numpy as np,scipy,contextlib,io
from scipy.optimize import minimize
root=pathlib.Path(__file__).resolve().parents[3]; inv=json.loads((root/'docs/research/inventory.json').read_text(encoding='utf8'));byid={r['id']:r for r in inv};report={'kind':'isolated characterization, not a repaired implementation','numpy':np.__version__,'scipy':scipy.__version__,'checks':[]}
def load(rid):
 s=(root/byid[rid]['path']).read_text(encoding='utf8');tree=ast.parse(s);nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))];ns={'np':np,'minimize':minimize};exec(compile(ast.Module(body=nodes,type_ignores=[]),rid,'exec'),ns);return ns,tree
ns,tree=load('L28');args=(np.array([1192.5,119500.,454.,45300.]),np.array([[1224,1176],[468,432]]),[0,100.],11,[1200.,1220.3,1241.1],[460.98,450.,440.01],.01,[-1.,1.]);A,B,X0,X1,U1,T=ns['LinearSystem'](*args)
report['checks'].append({'id':'uniform_grid_mass_memory','A0':A[0].tolist(),'rank':int(np.linalg.matrix_rank(A[0])),'actual_next_state_zero_u':(A[0]@X0).ravel().tolist(),'expected_mass_oxidizer':119500.-100./11*1192.5,'expected_mass_fuel':45300.-100./11*454.})
args2=list(args);args2[3]=[100./11*k for k in range(1,11)];Ar,Br,*_=ns['LinearSystem'](*args2);report['checks'].append({'id':'nonuniform_grid_mass_memory','rank':int(np.linalg.matrix_rank(Ar[0])),'diagonal':np.diag(Ar[0]).tolist()})
ns,tree=load('L19');p=ns['Polytope']([[0.],[2.]],[[1.,2.],[-1.,0.]],[]);p.isHRep=True;p.A=np.array([[1.],[-1.]]);p.b=np.array([[2.],[0.]]);p.Ae=np.empty((0,1));p.be=np.empty((0,1));cost=lambda x:float((x[0]-1.)**2)
with contextlib.redirect_stdout(io.StringIO()):val=ns['optimize_on_rs'](p,cost)
report['checks'].append({'id':'worst_case_positive_convex_cost','legacy_return':val,'true_max_over_vertices':max(cost(x) for x in [np.array([0.]),np.array([2.])]),'note':'Function minimizes supplied callable, then negates value. No caller sign inversion is present in the module.'})
source=(root/byid['L26']['path']).read_text(encoding='utf8')
try:ast.parse(source);parse='valid'
except SyntaxError as e:parse={'type':'SyntaxError','line':e.lineno,'message':e.msg}
report['checks'].append({'id':'python3_reachability_parse','result':parse})
ns,tree=load('L16');
try:ns['ClosedLoopControl']([],None,None,None,None,None)
except Exception as e:report['checks'].append({'id':'closed_loop_isolated_dependencies','type':type(e).__name__,'message':str(e)})
ns,tree=load('L19');report['checks'].append({'id':'finite_action_enumeration','sequences':ns['feasible_actions']([[-1,1],[-1,1]]),'number_q2_T16':2**16,'number_q9_T16':9**16})
for rid in ['L16','L19','L22','L28']:
 _,tree=load(rid);report.setdefault('definitions',{})[rid]=[{'name':n.name,'line':n.lineno} for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
(root/'docs/research/legacy-characterization.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
