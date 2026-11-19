"""Rebuild only HiGHS' start-point selection TU to observe the branch in a diagnostic binary."""
from pathlib import Path
import json, shlex, subprocess,sys
build=Path(sys.argv[1]).resolve(); workload=Path(sys.argv[2]).resolve(); r=Path(sys.argv[3]).resolve()
probe=r/"backend-probe"; (probe/"qpsolver").mkdir(parents=True,exist_ok=True)
src=build/"_deps/csl_highs-src/highs/qpsolver"
for name in ('a_quass.cpp','feasibility_highs.hpp'):
    (probe/"qpsolver"/name).write_bytes((src/name).read_bytes())
p=probe/"qpsolver/feasibility_highs.hpp"
s=p.read_text()
needle='  if (have_starting_point) {\n    use_basis = highs_basis;'
assert s.count(needle)==1
p.write_text(s.replace(needle,'''  std::fprintf(stderr, "CSL_START n=%d offered=%d accepted=%d\\n", int(instance.num_var), int(highs_basis.debug_origin_name == "shifted control history"), int(have_starting_point));
'''+needle))
commands=subprocess.check_output(['ninja','-C',str(build),'-t','commands','csl_mpc08_crossover'],text=True).splitlines()
c=shlex.split(next(l for l in commands if l.endswith('/qpsolver/a_quass.cpp')))
for flag in ('-MT','-MF'):
    i=c.index(flag);del c[i:i+2]
c.remove('-MD')
c.insert(1,'-I'+str(probe))
c[c.index('-o')+1]=str(probe/'probe.o')
c[c.index('-c')+1]=str(probe/'qpsolver/a_quass.cpp')
subprocess.run(c,cwd=build,check=True)
link=shlex.split(commands[-1])[2:-2]
link=[x for x in link if not x.startswith('-Wl,--dependency-file=')]
link.insert(link.index('lib/libhighs.a'),str(probe/'probe.o'))
link[link.index('-o')+1]=str(probe/'driver')
subprocess.run(link,cwd=build,check=True)
work=json.loads(workload.read_text());work['queries']=[];work['counts']=[1]
(probe/'one.json').write_text(json.dumps(work))
with (probe/'branches.log').open('w') as log:
    subprocess.run([str(probe/'driver'),str(probe/'one.json'),str(probe/'result.jsonl')],stderr=log,check=True)
events=(probe/'branches.log').read_text().splitlines()
from collections import Counter
print(Counter(events))
for n in (1,2):
    assert events.count(f"CSL_START n={n} offered=1 accepted=1")==6
assert events.count("CSL_START n=3 offered=0 accepted=0")==6
