"""Resume measured subjects, changing only external grader browser after a recorded incident."""
import hashlib,importlib.util,json,plistlib,subprocess,time
from pathlib import Path

OUT=Path(__file__).resolve().parent
SOURCE=Path('$SOURCE_REPO/benchmarks/run.py')
spec=importlib.util.spec_from_file_location('benchmark_runner',SOURCE)
run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
GRADER=OUT/'grade-edge.mjs'
PLAYWRIGHT=json.loads((OUT/'protocol.json').read_text())['playwright']

def grade(out,case,scenario,stage,work):
    started=time.monotonic()
    result=subprocess.run(['node',str(GRADER),str(work),scenario,str(stage),str(case/f'grade-{stage}.json'),PLAYWRIGHT],capture_output=True,text=True,timeout=100)
    elapsed=time.monotonic()-started
    (case/f'grader-{stage}.log').write_text(result.stdout+'\n'+result.stderr)
    metadata=plistlib.loads(Path('/Applications/Microsoft Edge.app/Contents/Info.plist').read_bytes())
    run.save(case/f'assessment-{stage}.json',{'browser_channel':'msedge','version':metadata.get('CFBundleShortVersionString'),
        'grader_sha256':hashlib.sha256(GRADER.read_bytes()).hexdigest(),'elapsed_seconds':elapsed,'exit_code':result.returncode,
        'product_source':str(work.relative_to(case)),'model_repeated':False})
    if result.returncode:raise RuntimeError('External Edge grader failed: '+result.stderr[-1200:])
    return elapsed

run.grade=grade
case=OUT/'cases/website-baseline'
if not (case/'grade-2.json').exists():
    original=json.loads((case/'metrics-2.json').read_text())
    run.save(case/'metrics-2-before-assessment-recovery.json',original)
    elapsed=grade(OUT,case,'website',2,case/'snapshot-2')
    run.save(case/'metrics-2.json',{**original,'grading_seconds':elapsed})
    print(json.dumps({'event':'assessment_recovered','case':case.name,'stage':2,'grade':json.loads((case/'grade-2.json').read_text())}),flush=True)
# Stage 1 Chrome and Edge results retained; require identical functional outcomes.
old=json.loads((case/'original-chrome-assessment/grade-1.json').read_text())
new=json.loads((case/'grade-1.json').read_text())
assert old['groups']==new['groups'], 'Browser change altered initial assessment; investigate before continuing'
run.execute(OUT)
