#!/usr/bin/env python3
"""Cross-platform functional public-port smoke; no benchmark claim."""
import argparse
from fractions import Fraction as Q
import json
from pathlib import Path
import subprocess
from study import exact_approximation_check

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('driver',type=Path);args=parser.parse_args()
    result=subprocess.run([str(args.driver.resolve(strict=True))],input='1 -2 1 0 3\n1 -6 9 0 2\n',text=True,capture_output=True,timeout=30,check=True)
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    if len(rows)!=3:raise ValueError('native runner omitted records')
    exact_approximation_check(rows[0])
    for i,(a,cost) in enumerate(((1,0),(2,1))):
        row=rows[i+1]
        if row['status']!='completed' or row['backend']!='csl.convex.highs' or row['program']!='nominal-qp/'+str(i):raise ValueError('native binding failed')
        if abs(Q(row['a'])-a)>Q(1,1000000) or abs(Q(row['objective'])-cost)>Q(1,1000000):raise ValueError('native objective failed literal reference')
    print(json.dumps({'native_qps':2,'APP04_outer_but_not_RPI':'verified','status':'passed'}))
