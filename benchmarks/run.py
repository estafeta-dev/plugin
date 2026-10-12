#!/usr/bin/env python3
"""Reproducible repeated, fresh-chat development benchmark. Python 3.9 stdlib.

Arms: baseline (no skills), lite (no skills, plus prompts/lite.md conventions)
and workflow (exactly the four project-local Session Workflow skills). A case is
scenario x arm x repetition; cases run in a recorded, seeded, balanced order.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import select
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PACK = REPO/'packs/session-workflow'
SKILLS = ['session-start', 'plan-and-orchestrate', 'session-handover', 'session-end']
ARMS = ['baseline', 'lite', 'workflow']
SCENARIOS = ['website', 'game', 'app']
REPETITIONS = 3
LITE = HERE/'prompts/lite.md'
# Arm block between the common prompt and the stage brief; lite puts its text here.
ACTIVATION = ('\nUse $session-start, $plan-and-orchestrate, $session-handover and $session-end as the session workflow. '
              'Load only needed references and use their bundled deterministic runtime.\n')
ORDER_METHOD = ('random.Random(seed): one shuffled arm sequence per scenario, rotated by repetition '
                '(cyclic Latin square: each arm takes each position equally often per scenario); '
                'scenario blocks shuffled per repetition')
MODEL = 'gpt-6.1-sol'
EFFORT = 'max'
LIMIT = 720
DISABLE = ['plugins','apps','memories','hooks','multi_agent','multi_agent_v2',
           'computer_use','browser_use','image_generation']

def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')

def stamp(): return datetime.now(timezone.utc).isoformat()

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def case_name(scenario, arm, rep): return f'{scenario}-{arm}-r{rep}'

def balanced_order(scenarios, arms, repetitions, seed):
    """Every scenario x repetition block runs each arm once, back to back. Rotating one
    seeded arm sequence per scenario balances arm position across repetitions."""
    rng = random.Random(seed)
    sequences = {}
    for scenario in scenarios:
        sequences[scenario] = list(arms)
        rng.shuffle(sequences[scenario])
    order = []
    for rep in range(1, repetitions+1):
        block = list(scenarios)
        rng.shuffle(block)
        for scenario in block:
            shift = (rep-1) % len(arms)
            group = sequences[scenario][shift:]+sequences[scenario][:shift]
            order += [[scenario, arm, rep] for arm in group]
    return order

def read_order(protocol):
    order = protocol.get('order') or []
    if 'repetitions' not in protocol or any(len(entry) != 3 for entry in order):
        raise RuntimeError('Output was prepared by the historical two-arm harness; use the commit recorded with it')
    return [(scenario, arm, int(rep)) for scenario, arm, rep in order]

def compose_prompt(common, arm, stage, brief, lite=''):
    if arm == 'workflow': block = ACTIVATION
    elif arm == 'lite': block = '\n'+lite+('' if lite.endswith('\n') else '\n')
    else: block = ''
    return common+block+'\nDevelopment brief (stage '+str(stage)+'):\n'+brief+'\n'

def choose(text, allowed, label):
    if text is None: return list(allowed)
    names = [x.strip() for x in text.split(',') if x.strip()]
    if not names or len(set(names)) != len(names) or any(x not in allowed for x in names):
        raise ValueError(f'--{label} needs distinct values from {",".join(allowed)}; got {text!r}')
    return [x for x in allowed if x in names]

def rpc_skills(cwd, config=None):
    argv=['codex','app-server']
    for feature in DISABLE: argv += ['-c',f'features.{feature}=false']
    if config is not None: argv += ['-c','skills.config='+config]
    p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL,text=True,bufsize=1)
    try:
        for obj in [{'id':1,'method':'initialize','params':{'clientInfo':{'name':'session_workflow_eval','version':'1.0'},'capabilities':{'experimentalApi':True}}},
                    {'method':'initialized'},
                    {'id':2,'method':'skills/list','params':{'cwds':[str(cwd)],'forceReload':True}}]:
            p.stdin.write(json.dumps(obj)+'\n'); p.stdin.flush()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if select.select([p.stdout],[],[],1)[0]:
                line=p.stdout.readline()
                if not line: break
                obj=json.loads(line)
                if obj.get('id')==2:
                    if 'error' in obj: raise RuntimeError(obj['error'])
                    return obj['result']['data'][0]
        raise RuntimeError('skills/list timed out')
    finally:
        p.terminate(); p.wait(timeout=5)

def disabled_config(paths):
    # TOML inline tables, not JSON objects.
    return '['+','.join('{path='+json.dumps(p)+',enabled=false}' for p in paths)+']'

def starter(work, scenario, brief):
    work.mkdir(parents=True)
    (work/'package.json').write_text(json.dumps({'name':'development-pilot','private':True,'type':'module','scripts':{'dev':'node server.js','test':'node --test'}},indent=2)+'\n')
    (work/'server.js').write_text("import http from 'node:http';\nimport fs from 'node:fs';\nimport path from 'node:path';\nconst i=process.argv.indexOf('--port'), port=i>=0?Number(process.argv[i+1]):4173;\nconst root=process.cwd();\nhttp.createServer((req,res)=>{let name=decodeURIComponent(new URL(req.url,'http://localhost').pathname); if(name==='/')name='/index.html';const file=path.resolve(root,'.'+name);if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}try{const data=fs.readFileSync(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'})[path.extname(file)]||'text/plain');res.end(data);}catch{res.writeHead(404).end('Not found');}}).listen(port,'127.0.0.1',()=>console.log('Preview ready',port));\n")
    (work/'index.html').write_text('<!doctype html>\n<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Development pilot</title><link rel="stylesheet" href="style.css"><body><main><h1>Starter</h1></main><script type="module" src="ui.js"></script></body></html>\n')
    (work/'style.css').write_text('/* Implement the design. */\n')
    (work/'ui.js').write_text('// Implement the application interface.\n')
    (work/'TASK.md').write_text('# Initial development brief\n\n'+brief+'\n')
    (work/'.gitignore').write_text('node_modules/\n.agent-state/\n')
    if scenario=='website':
        rows=[{'id':'w1','title':'Clay Basics','city':'Prague','category':'pottery','price':40},
              {'id':'w2','title':'Wheel Throwing','city':'Brno','category':'pottery','price':65},
              {'id':'w3','title':'Build a Stool','city':'Prague','category':'wood','price':65},
              {'id':'w4','title':'Photo Walk','city':'Łódź','category':'photo','price':20},
              {'id':'w5','title':'Joinery Lab','city':'Brno','category':'wood','price':80},
              {'id':'w6','title':'Night Photography','city':'Prague','category':'photo','price':40}]
        save(work/'workshops.json',rows)
        exports=['filterWorkshops','validateBooking']
        module='catalogue.js'
    elif scenario=='game':
        save(work/'deck.json',[{'id':str(i+1),'symbol':chr(65+i//2)} for i in range(8)])
        exports=['createGame','flip','resolveMismatch','restart'];module='game.js'
    else: exports=['createBoard','addTask','editTask','moveTask','deleteTask','listTasks','serialize','restore'];module='board.js'
    (work/module).write_text('\n'.join('export function '+name+'() { throw new Error("Not implemented"); }' for name in exports)+'\n')
    for argv in [['git','init','-q'],['git','add','.'],['git','-c','user.name=Benchmark Fixture','-c','user.email=benchmark@example.invalid','commit','-qm','Frozen starter']]:
        subprocess.run(argv,cwd=work,check=True,capture_output=True)

def prepare(out, playwright, arms, scenarios, repetitions, seed, seed_source):
    if (out/'protocol.json').exists(): raise RuntimeError('Output already prepared; use a new directory')
    briefs=json.loads((HERE/'scenarios.json').read_text())
    lite=LITE.read_text() if 'lite' in arms else ''
    if 'lite' in arms and not lite.strip(): raise RuntimeError('The lite arm needs a non-empty '+str(LITE))
    missing=[name for name in SKILLS if 'workflow' in arms and not (PACK/'skills'/name/'SKILL.md').is_file()]
    if missing: raise RuntimeError('Workflow skill sources are missing: '+', '.join(missing))
    order=balanced_order(scenarios,arms,repetitions,seed)
    out.mkdir(parents=True,exist_ok=True)
    common=(HERE/'prompts/common.md').read_text().replace('{playwright}',playwright)
    inventory=rpc_skills('/tmp')
    disable=disabled_config([s['path'] for s in inventory['skills']])
    (out/'disabled-skills.toml-value').write_text(disable)
    save(out/'discovered-skills.json',inventory)
    manifest={str(p.relative_to(REPO)):digest(p) for root in [HERE,PACK] for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    save(out/'source-hashes.json',manifest)
    protocol={'date':stamp(),'model':MODEL,'effort':EFFORT,'max_seconds_per_stage':LIMIT,
              'arms':arms,'scenarios':scenarios,'repetitions':repetitions,
              'seed':seed,'seed_source':seed_source,'order_method':ORDER_METHOD,
              'python_version':platform.python_version(),'order':order,'workflow_skills':SKILLS,
              'playwright':playwright,
              'codex_version':subprocess.check_output(['codex','--version'],text=True).strip(),
              'plugin_version':(PACK/'VERSION').read_text().strip(),
              'plugin_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              'features_disabled':DISABLE,'fresh_chats':True,'hidden_grading_feedback':True,'browser_channel':'chrome'}
    save(out/'protocol.json',protocol)
    for scenario,arm,rep in order:
        case=out/'cases'/case_name(scenario,arm,rep)
        work=case/'workspace'
        starter(work,scenario,briefs[scenario]['phase1'])
        if arm=='workflow':
            for name in SKILLS:
                shutil.copytree(PACK/'skills'/name,work/'.agents/skills'/name)
        audit=rpc_skills(work,disable)
        enabled=[s['name'] for s in audit['skills'] if s['enabled']]
        if sorted(enabled)!=sorted(SKILLS if arm=='workflow' else []):
            raise RuntimeError(case.name+': skill isolation failed: '+repr(enabled))
        save(case/'skill-isolation.json',audit)
        for stage in [1,2]:
            (case/f'prompt-{stage}.md').write_text(compose_prompt(common,arm,stage,briefs[scenario]['phase'+str(stage)],lite))
        save(case/'starter-hashes.json',{str(p.relative_to(work)):digest(p) for p in work.rglob('*') if p.is_file() and '.git' not in p.parts and '.agents' not in p.parts})
    print(json.dumps({'prepared':str(out),'cases':len(order),'stages':2*len(order),'seed':seed,'isolation':'verified'}),flush=True)

def grade(out, case, scenario, stage, work):
    argv=['node',str(HERE/'grade.mjs'),str(work),scenario,str(stage),str(case/f'grade-{stage}.json'),json.loads((out/'protocol.json').read_text())['playwright']]
    t=time.monotonic()
    p=subprocess.run(argv,capture_output=True,text=True,timeout=100)
    (case/f'grader-{stage}.log').write_text(p.stdout+'\n'+p.stderr)
    if p.returncode: raise RuntimeError('Evaluator infrastructure failed: '+p.stderr[-1200:])
    return time.monotonic()-t

def execute(out):
    protocol=json.loads((out/'protocol.json').read_text())
    order=read_order(protocol)
    config=(out/'disabled-skills.toml-value').read_text()
    hashes=json.loads((out/'source-hashes.json').read_text())
    for rel,expected in hashes.items():
        if digest(REPO/rel)!=expected: raise RuntimeError('Frozen source changed: '+rel)
    unprepared=[case_name(*entry) for entry in order if not (out/'cases'/case_name(*entry)/'starter-hashes.json').exists()]
    if unprepared: raise RuntimeError('Preparation incomplete; prepare a new output directory: '+', '.join(unprepared))
    for scenario,arm,rep in order:
        case=out/'cases'/case_name(scenario,arm,rep);work=case/'workspace'
        for stage in [1,2]:
            metricsfile=case/f'metrics-{stage}.json'
            if metricsfile.exists(): continue
            if (case/f'events-{stage}.jsonl').exists(): raise RuntimeError('Partial attempt exists; reconcile explicitly')
            argv=['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--json',
                  '-m',protocol['model'],'-c','model_reasoning_effort='+json.dumps(protocol['effort']),
                  '-c','approval_policy="never"','-s','workspace-write',
                  '-c','sandbox_workspace_write.network_access=false','-c','web_search="disabled"',
                  '-c','skills.config='+config,'-C',str(work),'-o',str(case/f'final-{stage}.md'),'-']
            for feature in DISABLE: argv[2:2]=['--disable',feature]
            save(case/f'invocation-{stage}.json',{'argv':argv,'prompt_sha256':digest(case/f'prompt-{stage}.md'),'started_at':stamp()})
            print(json.dumps({'event':'start','case':case.name,'stage':stage,'at':stamp()}),flush=True)
            t=time.monotonic();timed_out=False
            with (case/f'events-{stage}.jsonl').open('w') as stdout,(case/f'stderr-{stage}.log').open('w') as stderr:
                p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True,start_new_session=True)
                try: p.communicate((case/f'prompt-{stage}.md').read_text(),timeout=protocol['max_seconds_per_stage'])
                except subprocess.TimeoutExpired:
                    timed_out=True;os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            elapsed=time.monotonic()-t
            events=[]
            for line in (case/f'events-{stage}.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except json.JSONDecodeError:pass
            usage=[e['usage'] for e in events if e.get('type')=='turn.completed' and 'usage' in e]
            summed={k:sum(u.get(k,0) for u in usage) for k in ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens']} if usage else None
            commands=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution']
            metrics={'started_at':json.loads((case/f'invocation-{stage}.json').read_text())['started_at'],'finished_at':stamp(),'elapsed_seconds':elapsed,
                     'exit_code':p.returncode,'timed_out':timed_out,'usage':summed,'turns_completed':len(usage),
                     'command_count':len(commands),'failed_command_count':sum(c.get('exit_code',0)!=0 for c in commands),
                     'runtime_command_count':sum('session.py' in c.get('command','') for c in commands),
                     'skill_read_evidence':[n for n in SKILLS if any(n+'/SKILL.md' in c.get('command','') for c in commands)]}
            save(metricsfile,metrics)
            snapshot=case/f'snapshot-{stage}'
            shutil.copytree(work,snapshot,ignore=shutil.ignore_patterns('.git','node_modules'))
            # Grade live workspace so recorded paths/process assumptions stay intact.
            metrics['grading_seconds']=grade(out,case,scenario,stage,work)
            save(metricsfile,metrics)
            g=json.loads((case/f'grade-{stage}.json').read_text())
            print(json.dumps({'event':'complete','case':case.name,'stage':stage,'seconds':round(elapsed,1),'usage':summed,'passed':g['passed'],'total':g['total']}),flush=True)

def summarize(out):
    protocol=json.loads((out/'protocol.json').read_text())
    rows=[];incomplete=[]
    for scenario,arm,rep in read_order(protocol):
        key=case_name(scenario,arm,rep);case=out/'cases'/key
        if not all((case/f'metrics-{s}.json').exists() and (case/f'grade-{s}.json').exists() for s in [1,2]):
            incomplete.append(key);continue
        m=[json.loads((case/f'metrics-{s}.json').read_text()) for s in [1,2]]
        g=[json.loads((case/f'grade-{s}.json').read_text()) for s in [1,2]]
        u={k:sum(x['usage'].get(k,0) for x in m) for k in ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens']} if all(x['usage'] for x in m) else None
        row={'case':key,'scenario':scenario,'arm':arm,'rep':rep,'elapsed_seconds':sum(x['elapsed_seconds'] for x in m),
             'usage':u,'total_tokens':u['input_tokens']+u['output_tokens'] if u else None,
             'uncached_input_tokens':u['input_tokens']-u['cached_input_tokens'] if u else None,
             'phase1_passed':g[0]['passed'],'phase1_total':g[0]['total'],'final_passed':g[1]['passed'],'final_total':g[1]['total'],
             'failed_requirement_groups':[x for x in g[1]['groups'] if not x['passed']],
             'commands':sum(x['command_count'] for x in m),'failed_commands':sum(x['failed_command_count'] for x in m),
             'runtime_commands':sum(x['runtime_command_count'] for x in m),
             'stages':m,'grading_seconds':sum(x.get('grading_seconds',0) for x in m)}
        row['tokens_per_passed_requirement']=row['total_tokens']/row['final_passed'] if u and row['final_passed'] else None
        rows.append(row)
    save(out/'results.json',{'generated_at':stamp(),'rows':rows,'incomplete_cases':incomplete,
                             'limitations':f"{protocol['repetitions']} repetition(s) per scenario and arm in a recorded seeded order; descriptive comparison without statistical significance."})
    print(json.dumps(rows,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Prepare, execute and summarize the repeated three-arm benchmark.')
    parser.add_argument('action',choices=['prepare','execute','summarize']);parser.add_argument('--output',required=True);parser.add_argument('--playwright',default='playwright')
    parser.add_argument('--arms',help='prepare only: comma-separated subset of '+','.join(ARMS)+' (default: all)')
    parser.add_argument('--scenarios',help='prepare only: comma-separated subset of '+','.join(SCENARIOS)+' (default: all)')
    parser.add_argument('--repetitions',type=int,help=f'prepare only: repetitions per scenario and arm (default: {REPETITIONS})')
    parser.add_argument('--seed',type=int,help='prepare only: non-negative order seed (default: current UTC date as YYYYMMDD)')
    a=parser.parse_args();out=Path(a.output).resolve()
    if a.action=='prepare':
        try:arms=choose(a.arms,ARMS,'arms');scenarios=choose(a.scenarios,SCENARIOS,'scenarios')
        except ValueError as error:parser.error(str(error))
        repetitions=REPETITIONS if a.repetitions is None else a.repetitions
        if repetitions<1:parser.error('--repetitions must be at least 1')
        if a.seed is not None and a.seed<0:parser.error('--seed must be non-negative')
        seed,source=(a.seed,'argument') if a.seed is not None else (int(datetime.now(timezone.utc).strftime('%Y%m%d')),'utc-date')
        prepare(out,a.playwright,arms,scenarios,repetitions,seed,source)
    else:
        given=['--'+name for name in ['arms','scenarios','repetitions','seed'] if getattr(a,name) is not None]
        if given:parser.error('prepare-only option(s) '+', '.join(given)+': execute and summarize follow protocol.json')
        if a.action=='execute':execute(out)
        else:summarize(out)
