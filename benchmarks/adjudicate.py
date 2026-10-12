#!/usr/bin/env python3
"""Regrade archived snapshots uniformly; preserve original observations.

Historical two-arm rows have no case name and use <scenario>-<arm>; repeated
runs name each case (<scenario>-<arm>-r<rep>) in results.json.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import time

def main(out):
    protocol=json.loads((out/'protocol.json').read_text())
    source=json.loads((out/'results.json').read_text())
    result=copy.deepcopy(source)
    expected=len(protocol['order'])
    if len(result['rows'])!=expected:raise RuntimeError(f'Wait until all {expected} coding cases finish')
    for row in result['rows']:
        key=row.get('case') or row['scenario']+'-'+row['arm'];case=out/'cases'/key
        target=case/'adjudicated';target.mkdir(exist_ok=True)
        row['primary_phase1_passed']=row['phase1_passed'];row['primary_final_passed']=row['final_passed']
        grades=[];elapsed=0
        for stage in [1,2]:
            t=time.monotonic()
            p=subprocess.run(['node',str(out/'grade-v2.mjs'),str(case/f'snapshot-{stage}'),row['scenario'],str(stage),str(target/f'grade-{stage}.json'),protocol['playwright']],capture_output=True,text=True,timeout=100)
            (target/f'grader-{stage}.log').write_text(p.stdout+'\n'+p.stderr)
            if p.returncode:raise RuntimeError(key+': evaluator failed: '+p.stderr[-1500:])
            elapsed+=time.monotonic()-t
            grades.append(json.loads((target/f'grade-{stage}.json').read_text()))
        row['phase1_passed']=grades[0]['passed'];row['phase1_total']=grades[0]['total']
        row['final_passed']=grades[1]['passed'];row['final_total']=grades[1]['total']
        row['failed_requirement_groups']=[g for g in grades[1]['groups'] if not g['passed']]
        row['adjudication_seconds']=elapsed
        row['tokens_per_passed_requirement']=row['total_tokens']/row['final_passed'] if row['total_tokens'] is not None and row['final_passed'] else None
        print(json.dumps({'case':key,'primary_final':row['primary_final_passed'],'adjudicated_final':row['final_passed'],'total':row['final_total']}),flush=True)
    result['adjudication']=json.loads((out/'evaluator-correction.json').read_text())
    (out/'adjudicated-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();main(Path(a.output).resolve())
