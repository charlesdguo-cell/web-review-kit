"""Read-only verification of saved real acceptance evidence and project separation."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request

V = Path(os.environ['VALIDATION_PROJECT']).resolve()
assert V == Path('/Users/charles/.local/share/web-review-kit-validation')
M = Path('/Users/charles/Documents/codex/morsea-prototype')
OUT = V / 'artifacts/acceptance'
BACKUP = Path(os.environ['WORKER_EVIDENCE_BACKUP']).resolve()
checks = []
def read(path):
    return json.loads(path.read_text())
def get(port, path):
    return json.load(urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/__review/'+path))
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def inventory(root):
    return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
def check(name, value):
    assert value, name
    checks.append(name)
    print('PASS '+name)

before = read(OUT/'before-private.json')
check('Morsea original data inventory identical',before['morseaData']==inventory(M/'review-data'))
check('Morsea original jobs inventory identical',before['morseaJobs']==inventory(M/'artifacts/review-codex'))
check('Morsea original comments API identical',before['morseaCommentsSha256']==digest(get(8768,'comments')))
check('Morsea original job API identical',before['morseaCurrentJobSha256']==digest(get(8768,'codex')))
mh,vh=get(8768,'health'),get(8791,'health')
check('two live projects have separate identities',mh['projectId']=='morsea-prototype' and vh['projectId']=='field-notes-validation')
check('two live projects use same exact verified pin',mh['toolVersion']==vh['toolVersion']=='0.1.0-rc.3' and mh['versionMatches'] and vh['versionMatches'])
job=get(8791,'codex')['job'];directory=V/'.review/jobs'/job['id'];request=read(directory/'request.json')
frozen=read(OUT/'comment-1-frozen.json');comments=get(8791,'comments')['comments'];one,two=comments
check('real frozen request still contains only original comment',request['comments']==[frozen])
check('request file bytes unchanged from worker pre-edit copy',sha(directory/'request.json')==sha(BACKUP/'request.json'))
execution=request['executionConfig'];config=read(V/'review.config.json')
check('request freezes own source guidance and installed Skill',execution['projectId']=='field-notes-validation' and execution['guidance']==config['guidance'] and execution['installRoot']=='/Users/charles/.local/share/web-review-kit' and '0.1.0-rc.3/skills/web-review/SKILL.md' in execution['skillPath'])
check('original comment changed with nonempty technical explanation',one['status']=='changed' and bool(one['resolution']))
check('original comment evidence and fields preserved',all(one[key]==frozen[key] for key in frozen if key not in ('updatedAt','status','resolution')))
images={}
for path in (BACKUP/'review-data-backup').rglob('*'):
    if path.is_file() and path.suffix=='.png':
        relative=path.relative_to(BACKUP/'review-data-backup')
        assert sha(path)==sha(V/'review-data'/relative),str(relative)
        images[str(relative)]=sha(path)
check('all original screenshot and attachment bytes preserved',len(images)>=3)
backup_comments=read(BACKUP/'review-data-backup/comments.json')
check('new-during-run comment remains byte-for-byte record and open',two['status']=='open' and two==next(x for x in backup_comments if x['id']==two['id']))
check('no sample auto-resolved',all(c['status']!='resolved' for c in comments))
events=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
commands=[e.get('params',{}).get('item',{}) for e in events if e.get('method')=='item/completed']
commands=[e for e in commands if e.get('type')=='commandExecution' and e.get('exitCode')==0]
check('real worker read all configured required files',any('cat AGENTS.md README.md docs/review-guidance.md' in e.get('command','') and '# Specimen review guidance' in e.get('aggregatedOutput','') for e in commands))
check('real worker ran configured build successfully',any('python3 tools/build.py' in e.get('command','') and 'Built two static pages' in e.get('aggregatedOutput','') for e in commands))
check('real worker ran configured check successfully',any('python3 tools/check.py' in e.get('command','') and 'PASS: source/output equality' in e.get('aggregatedOutput','') for e in commands))
check('real worker used guarded mark-changed helper',any('mark-changed' in e.get('command','') and 'changed' in e.get('aggregatedOutput','') for e in commands))
first=read(OUT/'first-completed-job.json');follow=read(OUT/'followup-job.json')
new_assistants=[m for m in follow['messages'] if m['role']=='assistant' and m['id'] not in {x['id'] for x in first['messages']}]
check('real follow-up returned in same job and thread',job['status']=='completed' and first['id']==follow['id']==job['id'] and first['threadId']==follow['threadId']==job['threadId'] and bool(new_assistants))
summary=dict(checks=checks,evidenceHashes=images,jobId=job['id'],threadId=job['threadId'],morseaDataFiles=len(before['morseaData']),morseaJobFiles=len(before['morseaJobs']),realFollowup=new_assistants[-1]['text'])
(OUT/'preservation-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(str(len(checks))+' preservation and independence checks passed')
