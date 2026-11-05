#!/usr/bin/env python3
"""Build public, aggregate GitHub/GitLab commit counters without revealing private repo names."""
import datetime as dt
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

GL = 'https://gitlab.com/api/v4'
GH = 'https://api.github.com/graphql'
TODAY = dt.datetime.now(dt.timezone.utc)
SINCE = TODAY - dt.timedelta(days=365)
GL_TOKEN = os.environ['GITLAB_TOKEN']
GH_TOKEN = os.environ['GITHUB_TOKEN']
GL_AUTHOR = os.getenv('GITLAB_AUTHOR_NAME', 'Fabrizio Mori').strip().casefold()
GH_LOGIN = 'Fabrizio-HM'


def request_json(url, headers=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {'Accept': 'application/json', 'User-Agent': 'odoo-portfolio-activity'}
    h.update(headers or {})
    if data is not None:
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, headers=h, data=data)
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.load(response)


def gl_pages(endpoint, params):
    page = 1
    while True:
        q = urllib.parse.urlencode({**params, 'page': page, 'per_page': 100})
        result = request_json(f'{GL}{endpoint}?{q}', {'PRIVATE-TOKEN': GL_TOKEN})
        if not isinstance(result, list):
            raise RuntimeError('Unexpected GitLab API response')
        yield from result
        if len(result) < 100:
            break
        page += 1
        if page > 300:
            raise RuntimeError('GitLab pagination safety limit reached')


def gitlab_commits():
    projects = list(gl_pages('/projects', {'membership': 'true', 'simple': 'true'}))
    seen = set()
    count_by_month = Counter()
    errors = []
    for proj in projects:
        if proj.get('empty_repo'):
            continue
        pid = proj['id']
        try:
            commits = gl_pages(f'/projects/{pid}/repository/commits', {
                'all': 'true', 'since': SINCE.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'until': TODAY.strftime('%Y-%m-%dT%H:%M:%SZ'), 'with_stats': 'false',
                'author': 'Fabrizio Mori',
            })
            for c in commits:
                if c.get('author_name', '').strip().casefold() != GL_AUTHOR:
                    continue
                key = (pid, c.get('id'))
                if key in seen:
                    continue
                seen.add(key)
                when = c.get('committed_date', '')[:7]
                if when:
                    count_by_month[when] += 1
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            # Some accessible projects may still disallow reading commits.
            errors.append(f'project {pid}: {getattr(exc, "code", type(exc).__name__)}')
    return sum(count_by_month.values()), count_by_month, len(projects), errors


def github_count():
    query = '''query($login:String!, $from:DateTime!, $to:DateTime!) {
        user(login:$login) { contributionsCollection(from:$from, to:$to) {
          totalCommitContributions } } }'''
    result = request_json(GH, {'Authorization': 'Bearer ' + GH_TOKEN}, {
        'query': query,
        'variables': {'login': GH_LOGIN, 'from': SINCE.isoformat(), 'to': TODAY.isoformat()}
    })
    if result.get('errors'):
        raise RuntimeError('GitHub GraphQL error: ' + str(result['errors']))
    return int(result['data']['user']['contributionsCollection']['totalCommitContributions'])


def svg(gl, gh, project_count):
    total = gl + gh
    # Does not disclose private project names or URLs.
    cols = [('GitHub', gh, '#72a5f9'), ('GitLab', gl, '#fca85d'), ('Combined', total, '#c6a5ff')]
    x_positions = [30, 267, 504]
    content = ['<svg xmlns="http://www.w3.org/2000/svg" width="738" height="222" viewBox="0 0 738 222" role="img" aria-label="GitHub and GitLab authored commit activity over the last 365 days">',
               '<rect width="738" height="222" rx="14" fill="#111827"/>',
               '<text x="30" y="36" font-family="Arial,sans-serif" font-size="20" font-weight="bold" fill="#f4f7fc">Developer activity</text>',
               '<text x="30" y="57" font-family="Arial,sans-serif" font-size="12" fill="#9eacc1">Last 365 days · Commit counts, not all contributions</text>']
    for (label, value, color), x in zip(cols, x_positions):
        content.extend([f'<rect x="{x}" y="75" width="207" height="100" rx="10" fill="#202b3c"/>',
                        f'<text x="{x+18}" y="103" fill="#b8c6d9" font-family="Arial,sans-serif" font-size="15">{html.escape(label)}</text>',
                        f'<text x="{x+18}" y="149" fill="{color}" font-family="Arial,sans-serif" font-weight="bold" font-size="36">{value:,}</text>'])
    content.append('<text x="30" y="200" fill="#8897aa" font-family="Arial,sans-serif" font-size="11">GitLab: authored commits across accessible projects · GitHub: counted commit contributions</text>')
    content.append('</svg>')
    return '\n'.join(content)


def main():
    gl, monthly, project_count, errs = gitlab_commits()
    gh = github_count()
    folder = Path('dist')
    folder.mkdir(exist_ok=True)
    (folder/'developer-activity.svg').write_text(svg(gl, gh, project_count), encoding='utf-8')
    print(f'GitLab commits: {gl}, GitHub counted commits: {gh}, scanned GitLab projects: {project_count}.')
    if errs:
        print(f'WARNING: {len(errs)} projects not fully readable; totals may be undercounted.')
    print('No project names, email addresses, tokens or commit titles were written to the public SVG.')

if __name__ == '__main__':
    main()
