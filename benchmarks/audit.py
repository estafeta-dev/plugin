#!/usr/bin/env python3
"""Audit completed observations without invoking a model or changing products."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform

from run import ACTIVATION, LITE, PACK, REPO, SKILLS, balanced_order, case_name, read_order

STATE = '.agent-state/session-workflow/state.json'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text()) if path.exists() else None

def events(path):
    found = []
    for line in (path.read_text().splitlines() if path.exists() else []):
        try: found.append(json.loads(line))
        except json.JSONDecodeError: pass
    return found

def prompt_ok(arm, prompt, lite):
    """baseline: neither block; lite: lite text and no activation; workflow: activation and no lite text."""
    has_lite = bool(lite.strip()) and lite in prompt
    activated = ACTIVATION.strip() in prompt or any('$'+name in prompt for name in SKILLS)
    return {'baseline': not has_lite and not activated,
            'lite': has_lite and not activated,
            'workflow': ACTIVATION in prompt and not has_lite}.get(arm, False)

def copy_drift(root):
    changed = []
    for name in SKILLS:
        source = PACK/'skills'/name
        if not source.is_dir():
            changed.append(name+'/ (source missing)'); continue
        for p in source.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts: continue
            target = root/name/p.relative_to(source)
            if not target.exists() or digest(target) != digest(p): changed.append(str(target.relative_to(root)))
    return changed

def main(out):
    checks = []
    def record(name, passed, details=None):
        checks.append({'name': name, 'passed': bool(passed), 'details': details})

    protocol = json.loads((out/'protocol.json').read_text())
    order = read_order(protocol)
    arms, scenarios, reps = protocol['arms'], protocol['scenarios'], protocol['repetitions']
    frozen = json.loads((out/'source-hashes.json').read_text())
    drift = [name for name, expected in frozen.items()
             if not (REPO/name).exists() or digest(REPO/name) != expected]
    record('Frozen measured sources remain unchanged', not drift, drift)
    planned = sorted((s, a, r) for s in scenarios for a in arms for r in range(1, reps+1))
    covered = sorted(order) == planned
    record('Order holds every scenario, arm and repetition once', covered, None if covered else [list(x) for x in order])
    seed = protocol.get('seed')
    seeded = seed is not None and balanced_order(scenarios, arms, reps, seed) == [list(x) for x in order]
    record('Order matches the recorded seed', seeded, None if seeded else
           {'seed': seed, 'recorded_python': protocol.get('python_version'), 'audit_python': platform.python_version()})
    starts = []
    for entry in order:
        for stage in [1, 2]:
            invocation = load(out/'cases'/case_name(*entry)/f'invocation-{stage}.json')
            if invocation: starts.append((datetime.fromisoformat(invocation['started_at']), case_name(*entry), stage))
    in_order = [s[0] for s in starts] == sorted(s[0] for s in starts)
    record('Stages started in the recorded order', in_order,
           None if in_order else [[name, stage] for _, name, stage in sorted(starts)])
    lite = LITE.read_text() if LITE.exists() else ''
    threads = []
    cases = []
    for scenario in scenarios:
        starters = []
        for arm in arms:
            for rep in range(1, reps+1):
                key = case_name(scenario, arm, rep)
                case = out/'cases'/key
                cases.append(key)
                starters.append(load(case/'starter-hashes.json'))
                isolation = load(case/'skill-isolation.json')
                enabled = {s['name'] for s in isolation['skills'] if s['enabled']} if isolation else set()
                record(key+' skill isolation', isolation is not None and enabled == (set(SKILLS) if arm == 'workflow' else set()),
                       sorted(enabled) if isolation else 'missing skill-isolation.json')
                for stage in [1, 2]:
                    prompt = case/f'prompt-{stage}.md'
                    record(f'{key} stage {stage} prompt matches arm', prompt.exists() and prompt_ok(arm, prompt.read_text(), lite))
                    m = load(case/f'metrics-{stage}.json')
                    record(f'{key} stage {stage} completed', m is not None and m['exit_code'] == 0 and not m['timed_out'])
                    usage = m.get('usage') if m else None
                    record(f'{key} stage {stage} native usage', usage is not None and
                           0 <= usage['cached_input_tokens'] <= usage['input_tokens'] and usage['output_tokens'] > 0)
                    ids = [e['thread_id'] for e in events(case/f'events-{stage}.jsonl') if e.get('type') == 'thread.started']
                    record(f'{key} stage {stage} one fresh chat', len(ids) == 1)
                    threads.extend(ids)
                    read = set(m.get('skill_read_evidence', [])) if m else None
                    if arm == 'workflow':
                        record(f'{key} stage {stage} all four skills read', read == set(SKILLS))
                        changed = copy_drift(case/f'snapshot-{stage}'/'.agents/skills')
                        record(f'{key} stage {stage} exact plugin copy', not changed, changed)
                    else:
                        record(f'{key} stage {stage} no skill files read', read == set(), sorted(read) if read else None)
                state = load(case/'snapshot-2'/STATE) if arm == 'workflow' else None
                if arm == 'workflow' and state is None:
                    record(key+' sessions ended and claims released', False, 'missing snapshot-2/'+STATE)
                elif arm == 'workflow':
                    session_status = {k: v.get('status') for k, v in state.get('sessions', {}).items()}
                    phase_status = [{k: p.get(k) for k in ['id', 'state', 'owner']} for p in state.get('phases', [])]
                    record(key+' sessions ended and claims released', session_status
                           and all(s == 'ended' for s in session_status.values())
                           and all(not p['owner'] for p in phase_status), {'sessions': session_status, 'phases': phase_status})
        record(scenario+' identical functional starters', None not in starters and all(s == starters[0] for s in starters))
    expected = 2*len(order)
    record(f'{expected} distinct fresh chats', len(threads) == expected and len(set(threads)) == expected)
    result = {'arms': arms, 'scenarios': scenarios, 'repetitions': reps, 'cases': cases, 'chat_count': len(threads),
              'passed': sum(c['passed'] for c in checks), 'total': len(checks), 'checks': checks}
    (out/'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'passed': result['passed'], 'total': result['total'],
                      'failed': [c for c in checks if not c['passed']]}))
    if result['passed'] != result['total']: raise SystemExit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    main(Path(parser.parse_args().output).resolve())
