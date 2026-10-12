"""Read-only old/new observations. Does not run subjects or alter grading."""
import argparse,json,re
from pathlib import Path


def load(path):return json.loads(path.read_text())
def delta(new,old):return round(100*(new/old-1),2) if old and new is not None else None

def overhead(root,scenarios=None):
 result={'commands_containing_runtime':0,'skill_reference_reads':0,'skill_reference_output_characters':0,'runtime_error_counts':{},'compact_command_kinds':{}}
 for case in sorted((root/'cases').glob('*-workflow')):
  if scenarios is not None and case.name.rsplit('-',1)[0] not in scenarios:continue
  for stage in (1,2):
   p=case/f'events-{stage}.jsonl'
   if not p.exists():continue
   for line in p.read_text().splitlines():
    try:event=json.loads(line)
    except json.JSONDecodeError:continue
    item=event.get('item',{})
    if event.get('type')!='item.completed' or item.get('type')!='command_execution':continue
    cmd=item.get('command','');output=item.get('aggregated_output','')
    if 'session.py' in cmd:result['commands_containing_runtime']+=1
    if any(s in cmd for s in ['/SKILL.md','/references/','/templates/']):
     result['skill_reference_reads']+=1;result['skill_reference_output_characters']+=len(output)
    if 'session.py' in cmd:
     for error in re.findall(r'"code"\s*:\s*"([a-z_]+)"',output):
      result['runtime_error_counts'][error]=result['runtime_error_counts'].get(error,0)+1
    for kind in ['begin','batch','status','handover','end']:
     if 'session.py' in cmd and re.search(r'\b'+kind+r'\b',cmd):
      result['compact_command_kinds'][kind]=result['compact_command_kinds'].get(kind,0)+1
 return result

def eligible(row):
 return row.get('total_tokens') is not None and all(s['exit_code']==0 and not s['timed_out'] and s.get('usage') for s in row['stages'])

def totals(rows):
 keys=['elapsed_seconds','total_tokens','uncached_input_tokens','commands','runtime_commands','final_passed','final_total']
 return {key:sum(r[key] for r in rows) if rows and all(r.get(key) is not None for r in rows) else None for key in keys}

def main(old,new,confirmation=None):
 previous=load(old/('adjudicated-results.json' if (old/'adjudicated-results.json').exists() else 'results.json'))['rows']
 original=load(new/'results.json')['rows']
 current=original
 if confirmation:
  repeated=load(confirmation/'results.json')['rows']
  assert {r['arm'] for r in repeated if r['scenario']=='website'}=={'baseline','workflow'},'Both predeclared confirmation arms are required'
  current=[r for r in original if r['scenario']!='website']+[r for r in repeated if r['scenario']=='website']
 comparisons=[]
 for scenario in ('website','game','app'):
  oldpair={r['arm']:r for r in previous if r['scenario']==scenario}
  pair={r['arm']:r for r in current if r['scenario']==scenario}
  a,b=pair['baseline'],pair['workflow'];o=oldpair['workflow']
  valid=eligible(a) and eligible(b)
  comparisons.append({'scenario':scenario,'comparison_eligible':valid,'source':'website-confirmation' if confirmation and scenario=='website' else 'optimized-round', 'current_baseline':a,'current_workflow':b,
    'historical_workflow':o,'current_workflow_vs_baseline_percent':{
      key:delta(b[key],a[key]) if valid else None for key in ('elapsed_seconds','total_tokens','uncached_input_tokens','commands')},
    'optimized_vs_historical_workflow_percent':{
      key:delta(b[key],o[key]) if eligible(b) else None for key in ('elapsed_seconds','total_tokens','uncached_input_tokens','commands','runtime_commands')}})
 aggregates={}
 qualified={c['scenario'] for c in comparisons if c['comparison_eligible']}
 for label,rows in [('old',previous),('new',current)]:
  aggregates[label]={}
  for arm in ('baseline','workflow'):
   subset=[r for r in rows if r['arm']==arm and r['scenario'] in qualified]
   aggregates[label][arm]=totals(subset)
 for label in ('old','new'):
  aggregates[label]['workflow_vs_baseline_percent']={key:delta(aggregates[label]['workflow'][key],aggregates[label]['baseline'][key]) for key in ('elapsed_seconds','total_tokens','uncached_input_tokens','commands')}
 result={'comparisons':comparisons,'aggregates':aggregates,'aggregate_scenarios':sorted(qualified),
         'original_round_observations':original,'website_confirmation_observations':repeated if confirmation else [],
         'overhead':{'old':overhead(old),'original_round':overhead(new),'confirmation':overhead(confirmation) if confirmation else None},
         'limits':'Only complete paired observations enter aggregates. A predeclared repeat of BOTH website arms is separately identified; the original capacity-failed observation is retained with unknown usage. One complete pair per main cell; historical differences are observational. Command kinds may overlap and count outer shell events, not inner CLI invocations. Output length is characters, not token billing.'}
 if confirmation:
  components=[overhead(new,qualified & {'game','app'}),overhead(confirmation,qualified & {'website'})]
  combined={k:sum(c[k] for c in components) for k in ['commands_containing_runtime','skill_reference_reads','skill_reference_output_characters']}
  for k in ['runtime_error_counts','compact_command_kinds']:
   combined[k]={}
   for c in components:
    for name,count in c[k].items():combined[k][name]=combined[k].get(name,0)+count
  result['overhead']['selected_complete_pairs']=combined
  result['overhead']['historical_complete_pairs']=overhead(old,qualified)
 (new/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'aggregates':aggregates,'overhead':result['overhead']},ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--confirmation',type=Path);a=p.parse_args();main(a.old,a.new,a.confirmation)
