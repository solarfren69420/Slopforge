"""Render the public automation queue as static, escaped HTML."""
from html import escape
from urllib.parse import urlparse


def safe_link(url):
    parsed = urlparse(url or '')
    return escape(url, quote=True) if parsed.scheme == 'https' and parsed.hostname == 'github.com' else '#'


def activity(report):
    records = list(report.get('upstream', {}).values())
    discovery = report.get('discovery', {})
    candidates = discovery.get('candidates', [])
    checked = escape(report.get('generated_at') or 'Awaiting the first scan')
    rows = []
    flag_labels = {'full_name': 'Repository identity changed', 'archived': 'Archive status changed',
                   'disabled': 'Availability status changed', 'default_branch': 'Default branch changed',
                   'latest_release': 'Release changed', 'readme_sha256': 'README changed', 'licenses': 'License files changed'}
    for record in records:
        flags = [flag_labels.get(flag, flag) for flag in record.get('changes', [])]
        if record.get('archived'): flags.append('archived')
        if record.get('disabled'): flags.append('disabled')
        if record.get('moved'): flags.append('Repository moved; catalog URL needs review')
        if record.get('result') != 'ok': flags.append(record.get('result', 'not checked'))
        rows.append(f'<tr><td><a href="{safe_link(record.get("repo") or record["requested_repo"])}">{escape(record["id"])}</a></td>'
                    f'<td>{escape(record.get("last_checked") or "No successful check")}</td>'
                    f'<td>{escape(", ".join(flags) or ("Baseline recorded" if record.get("baseline") else "No changes detected"))}</td></tr>')
    cards = []
    for c in candidates[:discovery.get('queue_display_limit', 100)]:
        cards.append(f'<article><h3><a href="{safe_link(c["repo"])}">{escape(c["full_name"])}</a></h3>'
                     f'<p>{escape(c.get("description") or "No upstream description supplied.")}</p>'
                     f'<small>UNREVIEWED · Found via {escape(", ".join(c["sources"]))}</small></article>')
    errors = ''.join('<li>' + escape(e['source'] + ': ' + e['error']) + '</li>' for e in discovery.get('errors', []))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Slopforge's upstream checks, discovery candidates, and submission inbox.">
<title>Activity &amp; review queue — Slopforge</title><link rel="icon" href="assets/icon.svg"><link rel="stylesheet" href="style.css"><link rel="stylesheet" href="activity.css"></head>
<body><main class="activity"><a class="text-link" href="./">← Back to Slopforge</a>
<h1>Activity &amp; review queue</h1><p>Last scan: {checked}</p>
<p>Weekly checks monitor repository moves, releases, archival status, and README/license changes. Check dates are separate from human listing reviews. Slopforge does not build or test the upstream software.</p>
<nav class="dialog-actions" aria-label="Review links"><a class="button primary" href="https://github.com/solarfren69420/Slopforge/issues">Submission inbox ↗</a><a class="button glass" href="https://github.com/solarfren69420/Slopforge/issues/new?template=add-project.yml">Submit a project ↗</a><a class="button glass" href="https://github.com/solarfren69420/Slopforge/actions/workflows/maintenance.yml">Scan history ↗</a></nav>
<section><h2>How submissions work</h2><p>Sign in to GitHub and complete the project form. It becomes an issue in the inbox above. The checker flags duplicates and opens a draft pull request for a new valid repository. A maintainer reviews the proposed listing and ticks “Approve and publish” in the PR. The workflow generates the catalog/docs/artwork, runs checks, and merges/deploys it. Missing information is shown in the PR and can be supplied by editing the form.</p></section>
<section><h2>Upstream checks ({len(records)})</h2><div class="table-scroll"><table><thead><tr><th>Project</th><th>Last successful check (UTC)</th><th>Attention</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>{'<p>The first scan has not completed yet.</p>' if not records else ''}</section>
<section><h2>Discovery candidates ({len(candidates)})</h2><p>These are leads from bounded GitHub searches and watched organizations. They may include libraries, unrelated software, and unsuitable projects. Each needs human review before listing. Search coverage is not exhaustive.</p><div class="candidate-grid">{''.join(cards)}</div>{'<p>No candidates recorded yet.</p>' if not candidates else ''}
<p>Full observations and remaining candidates: <a class="text-link" href="automation-report.json">machine-readable report</a>.</p></section>
<section><h2>Discovery scan errors</h2>{'<ul>' + errors + '</ul>' if errors else '<p>None recorded.</p>'}</section>
</main></body></html>'''
