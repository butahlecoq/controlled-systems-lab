"""Authored scalar-active 2D fixtures; no historical reproduction claim."""
import copy

def mode(name,T,control=(0,1),invariant=(-4,4),offset=0,terminal=(1,0)):
    return {'id':name,'flow_a':1,'flow_offset':offset,'control_bounds':list(control),'invariants':[list(invariant) for _ in range(T+1)],'terminal_linear':list(terminal)}

def edge(name,source,target,T,guard=(-4,4),reset=(1,0)):
    return {'id':name,'source':source,'target':target,'guards':[list(guard) for _ in range(T)],'reset':list(reset)}

def hybrid(name,T,modes,edges,initial=-1,terminal=None):
    return {'schema':'csl.mpc10.fixture/1','id':name,'product':'hybrid','dimension':2,'horizon':T,'initial_mode':modes[0]['id'],'initial_x':initial,'initial_y':0,'modes':modes,'edges':edges,'allowed_terminal_modes':terminal or [m['id'] for m in modes],'max_branches':256,'cancel':False}

def fixtures():
    result=[]
    for product,choices,control in [('finite',[0,1,1],[0,0]),('mixed',[-1,0,0],[0,1])]:
        for T in [0,1,2,3]:
            result.append({'schema':'csl.mpc10.fixture/1','id':f'{product}-T{T}','product':product,'dimension':2,'horizon':T,'initial_x':-1 if product=='finite' else 0,'initial_y':0,'catalogue':choices,'continuous_bounds':control,'state_bounds':[[-4,4] for _ in range(T)]+[[0,4]],'terminal_linear':[1,0],'max_branches':256,'cancel':False})
    for T in [0,1]:
        item=copy.deepcopy(result[T]);item.update(id=f'finite-empty-T{T}',catalogue=[]);result.append(item)
    source=mode('source',1,(1,1));target=mode('target',1,(1,1))
    result.append(hybrid('published-2d-identity',1,[source,target],[edge('switch','source','target',1)],terminal=['target']))
    a=mode('source',1,(0,2));b=mode('target',1,terminal=(1,0));b['invariants'][1]=[.5,1]
    result.append(hybrid('guard-negative-reset',1,[a,b],[edge('switch-a','source','target',1,(0,1),(-1,1)),edge('switch-b','source','target',1,(0,1),(-1,1))],terminal=['target']))
    for name in ['source-pre-invariant-fails','guard-fails','destination-invariant-fails','forbidden-transition']:
        f=copy.deepcopy(result[10]);f['id']=name
        if name=='source-pre-invariant-fails':f['modes'][0]['invariants'][1]=[-2,-1]
        if name=='guard-fails':f['edges'][0]['guards'][0]=[1,2]
        if name=='destination-invariant-fails':f['modes'][1]['invariants'][1]=[1,2]
        if name=='forbidden-transition':f['edges']=[]
        result.append(f)
    for T in [0,1,2,3]:
        a=mode('A',T,(0,1));b=mode('B',T,(0,1),offset=-1,terminal=(1,1))
        result.append(hybrid(f'hybrid-T{T}',T,[a,b],[edge('stay-A','A','A',T),edge('switch-a','A','B',T,reset=(-1,1)),edge('switch-b','A','B',T,reset=(-1,1)),edge('return','B','A',T),edge('stay-B','B','B',T)]))
    flat=copy.deepcopy(result[-3]);flat['id']='flat-continuous-ties'
    for m in flat['modes']:m['terminal_linear']=[0,0]
    result.append(flat)
    budget=copy.deepcopy(result[6]);budget.update(id='mixed-prefix-budget',max_branches=1);result.append(budget)
    for name,cancel,limit in [('hybrid-path-budget',False,1),('hybrid-cancelled',True,256)]:
        f=copy.deepcopy(result[11]);f.update(id=name,cancel=cancel,max_branches=limit);result.append(f)
    for name,kind in [('unsupported-dimension-change','dimension-changing'),('unsupported-relational-reset','relational-reset')]:
        f=copy.deepcopy(result[10]);f.update(id=name,external_unsupported=kind);result.append(f)
    return result
