"""Optional live link check; reachability never implies build or legal clearance."""
import concurrent.futures
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Slopforge-link-review/1.0'})
    with urllib.request.urlopen(request,timeout=25) as response:
        return response.status,response.url,response.read()


def check(project):
    record={'id':project['id'],'repo':project['repo']}
    try:
        status,url,body=fetch(project['repo'])
        record.update(status=status,final_url=url,repository_sha256=hashlib.sha256(body).hexdigest())
        owner_repo='/'.join(url.rstrip('/').split('/')[-2:])
        for filename in ['README.md','readme.md','README.rst','README','README.txt','README.adoc']:
            readme='https://raw.githubusercontent.com/'+owner_repo+'/HEAD/'+filename
            try:
                _,readme_url,body=fetch(readme)
                record.update(readme_url=readme_url,readme_sha256=hashlib.sha256(body).hexdigest())
                # Keep source bodies in an ignored local folder only, for manual scope review.
                cache=ROOT/'test-results/upstream-readmes';cache.mkdir(parents=True,exist_ok=True)
                (cache/(project['id']+'.txt')).write_bytes(body)
                break
            except urllib.error.HTTPError as error:
                if error.code != 404:raise
        record['result']='reachable'
    except (urllib.error.URLError,TimeoutError) as error:
        record.update(result='check failed',error=str(error))
    return record


def main():
    projects=json.loads((ROOT/'data/projects.json').read_text())['projects']
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: records=list(pool.map(check,projects))
    output=ROOT/'data/link-check.json'
    output.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'scope':'Repository/README retrieval only. Not build, gameplay, legal, or claim verification.','records':records},indent=2)+'\n')
    for r in records:print(r['id'],r['result'],'README found' if r.get('readme_url') else 'No conventional README found')
    if any(r['result']!='reachable' for r in records):raise SystemExit(1)


if __name__=='__main__':main()
