/* Read plotted data only; every full-state region was checked by the publisher. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const families = ['polytope', 'box', 'zonotope', 'parallelotope', 'ellipsoid'];
  const colors = ['#9ccfd8', '#c4a7e7', '#f6c177', '#eb6f92', '#a6da95'];
  const ns = 'http://www.w3.org/2000/svg';
  const svg = $('geometry');
  let task, domain, drag, request = 0;
  const enabled = id => new Set([...$(id).querySelectorAll('input:checked')].map(x => x.value));
  const element = (tag, attrs = {}, text) => {
    const e = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const link = (href, text) => {
    const a = document.createElement('a'); a.href = href; a.textContent = text; return a;
  };
  const planeIndex = () => Number($('plane-choice').value);
  const selectedStage = () => $('stage-choice').value === 'all' ? null : Number($('stage-choice').value);
  const planePoint = p => task.planes[planeIndex()].indices.map(i => p[i]);
  const stages = run => selectedStage() === null ? run.stages : run.stages.filter(s => s.stage === selectedStage());
  const paths = run => {
    const k = selectedStage();
    return {
      candidate: k === null ? run.candidate.map(planePoint) : [planePoint(run.candidate[k])],
      execution: k === null ? run.execution.map(planePoint) : run.execution.slice(Math.max(0, k-1), k+1).map(planePoint)
    };
  };
  const carrier = (s, bounds = null) => {
    const [a, b] = task.planes[planeIndex()].indices;
    const lo = bounds ? bounds.map(x => x && x[0]) : s.lower;
    const hi = bounds ? bounds.map(x => x && x[1]) : s.upper;
    if ([lo[a], lo[b], hi[a], hi[b]].some(v => v === null || !Number.isFinite(v))) return [];
    return [[lo[a],lo[b]],[hi[a],lo[b]],[hi[a],hi[b]],[lo[a],hi[b]]];
  };
  const visibleRuns = () => task.runs.filter(r => enabled('family-controls').has(r.family));
  const pointsInView = () => {
    const roles = enabled('layer-controls'), points = [];
    for (const run of visibleRuns()) {
      for (const s of stages(run)) {
        if (roles.has('F')) points.push(...carrier(s));
        if (roles.has('B') || roles.has('I')) points.push(...s.projections[planeIndex()].B);
      }
      const p = paths(run);
      if (roles.has('candidate')) points.push(...p.candidate);
      if (roles.has('execution')) points.push(...p.execution);
      if (roles.has('bounds')) points.push(...carrier(null, run.state_bounds));
    }
    if (roles.has('target')) {
      const p = planePoint(task.soft_reference);
      if (p.every(Number.isFinite)) points.push(p);
    }
    return points.length ? points : [[0,0],[1,1]];
  };
  function fit() {
    const points = pointsInView(), values = [0,1].map(i => points.map(p => p[i]));
    domain = values.map(v => {
      const lo = Math.min(...v), hi = Math.max(...v), pad = Math.max((hi-lo)*.07, Math.abs(lo)*1e-6, 1e-9);
      return [lo-pad, hi+pad];
    });
  }
  const stageColor = k => {
    const t = k / task.horizon, a = t < .5 ? [196,167,231] : [156,207,216], b = t < .5 ? [156,207,216] : [246,193,119];
    const f = t < .5 ? 2*t : 2*t-1;
    return `rgb(${a.map((v,i) => Math.round(v+(b[i]-v)*f)).join(',')})`;
  };
  function draw() {
    if (!task) return;
    if (!domain) fit();
    svg.replaceChildren(element('title', {id:'plot-title'}, task.title + ' saved query 0'),
      element('desc', {id:'plot-description'}, 'Projected full-state carriers and conditional inner regions; I equals B. Affine candidate and nonlinear execution are separate paths.'));
    const roles = enabled('layer-controls'), runs = visibleRuns();
    const width=Math.max(320,svg.clientWidth), height=width<650?440:640;
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
    const ticks=width<650?3:5, tickLabels=element('g',{visibility:'hidden'});
    const tickPairs=Array.from({length:ticks+1},(_,i)=>{
      const values=domain.map(([lo,hi])=>lo+i*(hi-lo)/ticks);
      const labels=values.map(value=>element('text',{},Number(value.toPrecision(5)).toString()));
      tickLabels.append(...labels);
      return {values,labels};
    });
    svg.append(tickLabels);
    const tickHeight=Math.max(...tickPairs.flatMap(({labels})=>labels.map(label=>label.getBBox().height)));
    const yTickWidth=Math.max(...tickPairs.map(({labels})=>labels[1].getComputedTextLength()));
    const xTickWidth=Math.max(...tickPairs.map(({labels})=>labels[0].getComputedTextLength()));
    const box = {left:Math.ceil(yTickWidth+2*tickHeight+20),
      right:width-Math.ceil(Math.max(25,xTickWidth/2+8)),top:35,bottom:height-85};
    const x = v => box.left+(v-domain[0][0])/(domain[0][1]-domain[0][0])*(box.right-box.left);
    const y = v => box.bottom-(v-domain[1][0])/(domain[1][1]-domain[1][0])*(box.bottom-box.top);
    const defs = element('defs'), clip = element('clipPath',{id:'plot-clip'});
    clip.append(element('rect',{x:box.left,y:box.top,width:box.right-box.left,height:box.bottom-box.top}));defs.append(clip);svg.append(defs);
    for (const {values:[vx,vy],labels:[xLabel,yLabel]} of tickPairs) {
      svg.append(element('path',{d:`M${x(vx)},${box.top}V${box.bottom} M${box.left},${y(vy)}H${box.right}`,stroke:'#59566d','stroke-width':.5}));
      Object.entries({x:x(vx),y:box.bottom+27,'text-anchor':'middle'}).forEach(([key,value])=>xLabel.setAttribute(key,value));
      Object.entries({x:box.left-12,y:y(vy)+5,'text-anchor':'end'}).forEach(([key,value])=>yLabel.setAttribute(key,value));
    }
    tickLabels.removeAttribute('visibility');svg.append(tickLabels);
    const labels = task.planes[planeIndex()].labels;
    svg.append(element('text',{x:width/2,y:height-20,'text-anchor':'middle'},labels[0]));
    svg.append(element('text',{transform:`translate(${tickHeight+8},${(box.top+box.bottom)/2}) rotate(-90)`,'text-anchor':'middle'},labels[1]));
    const group = element('g',{'clip-path':'url(#plot-clip)'});svg.append(group);
    const line = (points, attrs, title) => {
      if (!points.length) return;
      const e = points.length === 1 ? element('circle',{cx:x(points[0][0]),cy:y(points[0][1]),r:3,...attrs}) :
        element('polyline',{points:points.map(p => `${x(p[0])},${y(p[1])}`).join(' '),fill:'none',...attrs});
      e.append(element('title',{},title));group.append(e);
    };
    const shape = (points, attrs, title) => line(points.length > 2 ? [...points,points[0]] : points,attrs,title);
    for (const run of runs) {
      const color = colors[families.indexOf(run.family)];
      for (const s of stages(run)) {
        if (roles.has('F')) shape(carrier(s),{stroke:color,'stroke-width':.8,opacity:.24},`${run.family} outer carrier F, stage ${s.stage}`);
        const points = s.projections[planeIndex()].B;
        if (roles.has('B')) shape(points,{stroke:color,'stroke-width':1.2,fill:stageColor(s.stage),'fill-opacity':.06},`${run.family} conditional inner B, stage ${s.stage}`);
        if (roles.has('I')) shape(points,{stroke:color,'stroke-width':2,'stroke-dasharray':'5 3',opacity:.8},`${run.family} I = F ∩ B = B, stage ${s.stage}`);
      }
      const p = paths(run);
      if (roles.has('candidate')) line(p.candidate,{stroke:color,'stroke-dasharray':'7 4','stroke-width':1.4,opacity:.75},`${run.family} query-0 affine candidate`);
      if (roles.has('execution')) line(p.execution,{stroke:color,'stroke-width':2.7},`${run.family} actual nonlinear execution`);
      if (roles.has('bounds')) shape(carrier(null,run.state_bounds),{stroke:color,'stroke-width':1.5,'stroke-dasharray':'10 3 2 3'},`${run.family} admissible state bounds, not a terminal target`);
      if (roles.has('execution')) {
        const k = selectedStage();
        if (k === null || k === 0) {
          const p = planePoint(run.execution[0]);group.append(element('circle',{cx:x(p[0]),cy:y(p[1]),r:5,fill:color,stroke:'#16161e'}));
        }
        if (k === null || k === task.horizon) {
          const p = planePoint(run.execution.at(-1)), points = [];
          for(let j=0;j<10;j++){const angle=j*Math.PI/5-Math.PI/2, radius=j%2?3.5:8;points.push(`${x(p[0])+Math.cos(angle)*radius},${y(p[1])+Math.sin(angle)*radius}`);}
          const star=element('polygon',{points:points.join(' '),fill:color,stroke:'#16161e'});star.append(element('title',{},run.family+' final executed state'));group.append(star);
        }
      }
    }
    if (roles.has('target')) {
      const p = planePoint(task.soft_reference);
      if(p.every(Number.isFinite)) line([[p[0],p[1]]],{stroke:'#ffffff',fill:'none','stroke-width':2,r:7},'Soft objective reference, not a hard terminal set');
      if(p.every(Number.isFinite)) group.append(element('path',{d:`M${x(p[0])-8},${y(p[1])}h16 M${x(p[0])},${y(p[1])-8}v16`,stroke:'#ffffff','stroke-width':2}));
    }
    const s = selectedStage();
    $('status').textContent = `${task.title} · query 0 · ${runs.length}/5 families · ${s === null ? `all ${task.horizon+1} state stages` : `state stage ${s}/${task.horizon}, t = ${Number((s*task.runs[0].dt).toPrecision(6))} ${task.time_unit}`} · inner B and I coincide by full-state construction`;
  }
  function downloads() {
    const i=planeIndex(), links=$('downloads');links.replaceChildren();
    links.append(link(`${task.id}.json`,'Exact plotted data + full-state memberships'),link(`${task.id}-plane-${i}.svg`,'Standalone SVG · all stages'),link(`${task.id}-plane-${i}.png`,'PNG · all stages'),link('../native-fixed-tail-episodes-a6/index.html','Original immutable A6 report'));
  }
  async function selectTask() {
    const token=++request;
    task=null;
    $('status').textContent='Loading authenticated saved geometry…';
    $('stage-choice').disabled=true;
    $('plane-choice').disabled=true;
    try {
      const response=await fetch(`${$('task-choice').value}.json`);
      if(!response.ok) throw new Error('Saved geometry download failed');
      const loaded=await response.json();if(token!==request)return;task=loaded;
      const planes=$('plane-choice');planes.replaceChildren();
      task.planes.forEach((p,i)=>planes.add(new Option(p.labels.join(' / '),i)));
      const stage=$('stage-choice');stage.replaceChildren(new Option('All stages','all'));
      for(let i=0;i<=task.horizon;i++)stage.add(new Option(`${i}${i===0?' · initial':i===task.horizon?' · terminal':''}`,i));
      stage.disabled=false;planes.disabled=false;
      $('terminal-label').textContent=`Stage ${task.horizon} · terminal`;
      $('coordinate-note').textContent=task.id==='syn-nl-fuel-01' ? 'Fuel: stored (mₒₓ, m_f, qₒₓ, q_f) → displayed (qₒₓ, mₒₓ, q_f, m_f), permutation [2,0,3,1]. Oxidizer indices [2,0]; fuel indices [3,1]. Flow in kg/s; mass in kg. These are physical states; no scaling is reapplied.' : `Stored physical coordinates: ${task.coordinates.map(c=>`${c.name} (${c.unit})`).join(', ')}. No scaling is reapplied.`;
      const identities=document.createElement('div');identities.className='identities';
      for(const run of task.runs){
        const article=document.createElement('article');article.className='identity';
        const title=document.createElement('h3');title.textContent=run.family;article.append(title,link(run.raw,'Original raw ZIP'));
        for(const [label,value] of [['Task',run.task_sha256],['Objective',run.objective_id],['Action domain',run.action_profile_id],['Affine model',run.affine_model_sha256],['Fixed-tail stage lifts',run.tail_stage_lifts_sha256],['Saved source history',run.source_history_sha256],['Native response',run.response_sha256],['Policy graph',run.graph_id]]){
          const p=document.createElement('p');p.textContent=label+': ';const span=document.createElement('span');span.className='hash';span.textContent=value;p.append(span);article.append(p);
        }
        identities.append(article);
      }
      $('identities').replaceChildren(identities);
      $('source-summary').textContent=`Saved episode source ${task.source.episode_source_commit}; native C++ source ${task.source.native_cpp_source_commit}. Local numerical fixed-tail policy; query 0 only.`;
      $('source-note').textContent=`Episode/recorder source ${task.source.episode_source_commit}; native C++ source ${task.source.native_cpp_source_commit}. Same original horizon ${task.horizon}; query 0 only. Later observed queries remain in each original ZIP.`;
      const print=$('print-figures');print.replaceChildren();
      task.planes.forEach((p,i)=>{const f=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');image.src=`${task.id}-plane-${i}.svg`;image.alt=task.title+' all-stage matched-family conditional regions and execution';caption.textContent=p.labels.join(' / ');f.append(image,caption);print.append(f);});
      downloads();domain=null;draw();
    } catch(error) {
      if(token!==request)return;
      $('status').textContent=error.message+' — open this page through the reproduction HTTP server.';
    }
  }
  families.forEach((f,i)=>{const label=document.createElement('label'),input=document.createElement('input'),swatch=document.createElement('span');input.type='checkbox';input.value=f;input.checked=true;swatch.className='swatch';swatch.style.background=colors[i];label.append(input,swatch,document.createTextNode(f));$('family-controls').append(label);});
  $('task-choice').addEventListener('change',selectTask);
  $('plane-choice').addEventListener('change',()=>{domain=null;downloads();draw();});
  $('stage-choice').addEventListener('change',()=>{domain=null;draw();});
  ['family-controls','layer-controls'].forEach(id=>$(id).addEventListener('change',()=>{domain=null;draw();}));
  $('fit-visible').addEventListener('click',()=>{domain=null;draw();});
  const zoom = factor => {if(!domain)return;domain=domain.map(([a,b])=>{const m=(a+b)/2,r=(b-a)*factor/2;return [m-r,m+r];});draw();};
  $('zoom-in').addEventListener('click',()=>zoom(.65));$('zoom-out').addEventListener('click',()=>zoom(1.5));
  svg.addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY<0?.85:1.18);},{passive:false});
  svg.addEventListener('pointerdown',e=>{if(!domain)return;drag={x:e.clientX,y:e.clientY,domain:domain.map(x=>[...x])};svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;const r=svg.getBoundingClientRect(),v=svg.viewBox.baseVal,plot=svg.querySelector('#plot-clip rect'),dx=(e.clientX-drag.x)/r.width*v.width/Number(plot.getAttribute('width')),dy=(e.clientY-drag.y)/r.height*v.height/Number(plot.getAttribute('height'));domain=drag.domain.map(([a,b],i)=>{const d=(i?dy:-dx)*(b-a);return[a+d,b+d];});draw();});
  svg.addEventListener('pointerup',()=>{drag=null;});svg.addEventListener('pointercancel',()=>{drag=null;});
  window.addEventListener('resize',()=>draw());
  selectTask();
})();
