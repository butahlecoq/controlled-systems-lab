"""Canonical exact offline artifacts consumed by the existing MPC06 nominal QP."""
from fractions import Fraction as Q
from itertools import product
import hashlib
import json
from pathlib import Path
from scripts.reports.mpc06_online import model

ROOT=Path(__file__).resolve().parents[3]
INPUT=Path(__file__).with_name('inputs.json')

def require(condition,message):
    if not condition:raise ValueError(message)
def encode(value):
    if isinstance(value,Q):return str(value)
    raise TypeError(type(value).__name__)
def encoded(value):return (json.dumps(value,default=encode,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def plain(value):return json.loads(encoded(value))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def mv(a,x):return [dot(row,x) for row in a]

def input_record():
    data=json.loads(INPUT.read_bytes());raw=(ROOT/data['upstream_raw_path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==data['upstream_raw_sha256'],'upstream native record hash differs')
    require(hashlib.sha256((ROOT/'scripts/reports/mpc06_online/model.py').read_bytes()).hexdigest()==data['legacy_model_sha256'],'consumed nominal-QP model differs')
    native=json.loads(raw);require(native['plant']==data['plant'] and native['policy']['gain']==data['K'],'offline/native plant or gain differs')
    rows=[dict(anchor=a['steps'][0]['anchor'],qp=a['steps'][0]['qp'],native_input=a['steps'][0]['native_input'],repetition=a['repetition'],method=a['method']) for a in native['attempts'] if a['method']=='polytope' and a['repetition']==0]
    require(rows==data['native_qp_ledger'] and len(rows)==3,'actual native input ledger differs')
    require(data['horizon']==3 and data['nominal_terminal']==[0,0] and data['K']==[-1,-2],'unsupported offline fixture')
    return data

def construct(data):
    """Fresh construction; prescribed gain copying is not gain optimization."""
    p=data['plant'];a=[[Q(v) for v in row] for row in p['A']];b=[Q(row[0]) for row in p['B']];e=[Q(row[0]) for row in p['E']];k=list(map(Q,data['K']));r=Q(p['W'][1])
    f=[[a[i][j]+b[i]*k[j] for j in range(2)] for i in range(2)]
    first=[v*r for v in e];second=mv(f,first);generators=[first,second]
    supports=[sum(abs(g[i]) for g in generators) for i in range(2)];input_support=sum(abs(dot(k,g)) for g in generators)
    bounds=[(Q(p['X'][0][1])-supports[0],Q(p['X'][1][1])-supports[1],Q(p['U'][1])-input_support)]*data['horizon']
    return dict(K=k,F=f,center=[Q(0),Q(0)],generators=generators,H=[[1,0],[-1,0],[1,1],[-1,-1]],h=[r]*4,
        state_support=supports,input_support=input_support,tightenings=bounds,terminal=list(map(Q,data['nominal_terminal'])),gain_origin='prescribed; no optimization')

def nominal_problem(anchor,artifact):
    """The unchanged operational nominal-QP constructor consumes these bounds."""
    return model.problem(tuple(map(Q,anchor)),artifact['tightenings'])

def verify(data,artifact):
    """Independent exact corner-image/support and actual consumer checks."""
    p=data['plant'];r=Q(p['W'][1]);a=[[Q(v) for v in row] for row in p['A']];b=[Q(row[0]) for row in p['B']];e=[Q(row[0]) for row in p['E']];k=list(map(Q,data['K']))
    require(artifact['K']==k and artifact['gain_origin']=='prescribed; no optimization','prescribed gain differs')
    f=artifact['F'];require(f==[[a[i][j]+b[i]*k[j] for j in range(2)] for i in range(2)],'A+BK differs')
    require(all(dot(f[i],[f[t][j] for t in range(2)])==0 for i in range(2) for j in range(2)),'nilpotent tail is not zero')
    ab=mv(a,b);require(b[0]*ab[1]-b[1]*ab[0]!=0,'controllability fails')
    require(artifact['center']==[0,0] and len(artifact['generators'])==2 and all(len(g)==2 for g in artifact['generators']),'tube generator shape differs')
    vertices={tuple(sum(sign*g[i] for sign,g in zip(signs,artifact['generators'])) for i in range(2)) for signs in product((-1,1),repeat=2)}
    expected={(s,t-s) for s,t in product((-r,r),repeat=2)};require(vertices==expected,'constructed tube differs from actual exact Z')
    require(artifact['H']==[[1,0],[-1,0],[1,1],[-1,-1]] and artifact['h']==[r]*4,'exact H relation differs')
    for x,w in product(vertices,(-r,r)):
        successor=[v+ew*w for v,ew in zip(mv(f,x),e)]
        require(all(dot(row,successor)<=rhs for row,rhs in zip(artifact['H'],artifact['h'])),'RPI image escapes Z')
    supports=[max(abs(x[i]) for x in vertices) for i in range(2)];us=max(abs(dot(k,x)) for x in vertices)
    require(artifact['state_support']==supports and artifact['input_support']==us,'support values differ')
    bounds=[(Q(p['X'][0][1])-supports[0],Q(p['X'][1][1])-supports[1],Q(p['U'][1])-us)]*3
    require(artifact['tightenings']==bounds==model.tightenings('polytope'),'consumed support tightening differs')
    require(artifact['terminal']==[0,0] and mv(a,artifact['terminal'])==[0,0] and all(all(v>=0 for v in row) for row in bounds),'nominal terminal continuation differs')
    matches=[]
    for row in data['native_qp_ledger']:
        qp=nominal_problem(row['anchor'],artifact);require(plain(qp)==row['qp'],'actual native nominal-QP coefficients differ')
        text=' '.join(format(float(qp[name]),'.17g') for name in ('quadratic','linear','offset','lower','upper'))+'\n'
        require(text==row['native_input'],'actual native request bytes differ');matches.append(hashlib.sha256(text.encode()).hexdigest())
    return dict(status='verified',native_input_matches=len(matches),native_input_sha256=matches,rpi_vertex_images=8,terminal='nominal zero with v=0; actual error remains in invariant Z',
        scope='exact nilpotent tube/corner/support certificate and unchanged nominal-QP consumer construction only; no native solve or old trajectory replay')
