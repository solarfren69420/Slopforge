"""Validate the catalog, build a portable static site, and update its index."""
import argparse
import json
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from art import generate
from reports import activity

ROOT = Path(__file__).resolve().parents[1]
METHODS = {
    'Reimplementation', 'Source port', 'Original open-source game',
    'Game creation platform', 'Independent open-source tool',
    'Game engine', 'Compatibility layer', 'Reverse engineering tool',
    'Clean-room rewrite', 'Source-available tool',
}


def validate(catalog):
    projects = catalog['projects']
    assert projects, 'Catalog must not be empty'
    assert len({p['id'] for p in projects}) == len(projects), 'Duplicate project ID'
    assert len({p['repo'].lower() for p in projects}) == len(projects), 'Duplicate repository'
    for p in projects:
        assert re.fullmatch(r'[a-z0-9-]+', p['id']), f"Invalid ID: {p['id']}"
        assert re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', p['repo']), f"Invalid repository URL: {p['repo']}"
        for field in ('name','description','data_note','source_note','category','language','monogram','art'):
            assert isinstance(p[field],str) and p[field].strip(), f"Missing {field} in {p['id']}"
        assert p['kind'] in ('games','tools'), f"Unknown kind in {p['id']}"
        assert p['method'] in METHODS, f"Unknown method in {p['id']}"
        assert p['platforms'] and set(p['platforms']) <= {'Windows','Linux','macOS'}, f"Unknown platform in {p['id']}"
        assert isinstance(p['tags'],list) and len(p['tags']) == len(set(p['tags'])), f"Invalid tags in {p['id']}"
        assert date.fromisoformat(p['reviewed']) <= date.today(), 'Review date is in the future'
        assert not any(k in p for k in ('completion','percent','stars')), 'Unsupported metrics are not catalog fields'
        if p['method'] in ('Clean-room rewrite','Source-available tool'):
            assert p.get('license_note') and p.get('source_urls'), f"Missing license or evidence in {p['id']}"
        for source in p.get('source_urls',[]):
            parsed=urlparse(source['url'])
            assert parsed.scheme=='https' and parsed.hostname in {'github.com','raw.githubusercontent.com'}, f"Invalid evidence URL in {p['id']}"
            assert source.get('label'), f"Missing evidence label in {p['id']}"
    return projects


def markdown(projects):
    lines = ['# Slopforge project catalog', '',
             'Descriptions and labels are directory metadata. Upstream links are the evidence for project identity and purpose. Platform families are upstream-listed targets, not builds tested by Slopforge. No completion or popularity scores are asserted.', '',
             '[Browse the storefront](https://solarfren69420.github.io/Slopforge/) · [Submit a project](https://github.com/solarfren69420/Slopforge/issues/new?template=add-project.yml)', '']
    for kind,title in [('games','Games'),('tools','Tools & software')]:
        lines += [f'## {title}', '', '| Project / source | Category | Type | Platforms | Data / scope | Reviewed |', '| --- | --- | --- | --- | --- | --- |']
        for p in projects:
            if p['kind'] != kind: continue
            note = p['data_note'] if kind == 'games' else p['source_note']
            if p.get('source_urls'):
                note += ' [Reviewed source]('+p['source_urls'][0]['url']+'). '+p['license_note']
            values = [f"[{p['name']}]({p['repo']})",p['category'],p['method'],', '.join(p['platforms']),note,p['reviewed']]
            lines.append('| ' + ' | '.join(v.replace('|','\\|').replace('\n',' ') for v in values) + ' |')
        lines.append('')
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--update-docs',action='store_true')
    args=parser.parse_args()
    catalog=json.loads((ROOT/'data/projects.json').read_text())
    projects=validate(catalog)
    generate(projects, ROOT/'web/assets/cards')
    output=ROOT/'_site'
    if output.exists(): shutil.rmtree(output)
    shutil.copytree(ROOT/'web', output)
    shutil.copyfile(ROOT/'data/projects.json',output/'projects.json')
    report=json.loads((ROOT/'data/automation-report.json').read_text())
    (output/'automation-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'activity.html').write_text(activity(report))
    (output/'.nojekyll').touch()
    (output/'404.html').write_text((output/'index.html').read_text().replace('<head>','<head>\n  <base href="/Slopforge/">'))
    (output/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: https://solarfren69420.github.io/Slopforge/sitemap.xml\n')
    (output/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://solarfren69420.github.io/Slopforge/</loc></url><url><loc>https://solarfren69420.github.io/Slopforge/activity.html</loc></url></urlset>')
    if args.update_docs:
        (ROOT/'CATALOG.md').write_text(markdown(projects))
        readme=ROOT/'README.md'
        if readme.exists():
            counts=Counter(p['kind'] for p in projects)
            stats=f"**{len(projects)} projects** · {counts['games']} games · {counts['tools']} tools & software"
            readme.write_text(re.sub(r'(?<=<!-- catalog-stats:start -->).*?(?=<!-- catalog-stats:end -->)', '\n'+stats+'\n',readme.read_text(),flags=re.S))
    print(f"Built {len(projects)} projects into {output}")


if __name__ == '__main__': main()
