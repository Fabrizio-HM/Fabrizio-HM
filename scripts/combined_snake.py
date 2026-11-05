#!/usr/bin/env python3
"""Animated GitHub+GitLab activity snake, publishing no private repository details."""
import datetime as dt
import html
import json
import math
import os
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

from activity_stats import GL, GH, GL_TOKEN, GH_TOKEN, GL_AUTHOR, GH_LOGIN, gl_pages, request_json

DAYS_BACK = 365
LOCAL_ZONE = ZoneInfo('America/Lima')
TODAY = dt.datetime.now(LOCAL_ZONE).date()
START = TODAY - dt.timedelta(days=DAYS_BACK - 1)


def github_calendar():
    query = '''query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) { contributionsCollection(from:$from, to:$to) {
        contributionCalendar { weeks { contributionDays { date contributionCount } } }
      } } }'''
    begin = dt.datetime.combine(START, dt.time.min, dt.timezone.utc)
    end = dt.datetime.combine(TODAY, dt.time.max, dt.timezone.utc)
    result = request_json(GH, {'Authorization': 'Bearer ' + GH_TOKEN}, {
        'query': query,
        'variables': {'login': GH_LOGIN, 'from': begin.isoformat(), 'to': end.isoformat()}
    })
    if result.get('errors'):
        raise RuntimeError('GitHub contribution calendar error: ' + str(result['errors']))
    calendar = result['data']['user']['contributionsCollection']['contributionCalendar']
    return {day['date']: int(day['contributionCount'])
            for week in calendar['weeks'] for day in week['contributionDays']}


def gitlab_daily_commits():
    projects = list(gl_pages('/projects', {'membership': 'true', 'simple': 'true'}))
    counts = Counter()
    seen = set()
    errors = 0
    since = dt.datetime.combine(START, dt.time.min, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    until = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for project in projects:
        if project.get('empty_repo'):
            continue
        project_id = project['id']
        try:
            for commit in gl_pages(f'/projects/{project_id}/repository/commits', {
                'all': 'true', 'since': since, 'until': until,
                'author': 'Fabrizio Mori', 'with_stats': 'false'
            }):
                if commit.get('author_name', '').strip().casefold() != GL_AUTHOR:
                    continue
                sha = commit.get('id')
                if not sha or (project_id, sha) in seen:
                    continue
                seen.add((project_id, sha))
                timestamp = commit.get('committed_date')
                if not timestamp:
                    continue
                day = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone(LOCAL_ZONE).date()
                if START <= day <= TODAY:
                    counts[day.isoformat()] += 1
        except Exception as exc:
            # Do not reveal private project identifiers in public SVG or logs.
            errors += 1
    return counts, len(projects), errors


def svg(github_days, gitlab_days):
    # Sunday-aligned columns, following a GitHub-style calendar layout.
    first_sunday = START - dt.timedelta(days=(START.weekday() + 1) % 7)
    last_saturday = TODAY + dt.timedelta(days=(5 - TODAY.weekday()) % 7)
    dates = [first_sunday + dt.timedelta(days=i)
             for i in range((last_saturday - first_sunday).days + 1)]
    weeks = len(dates) // 7
    pitch, sq, left, top = 15, 11, 28, 38
    width, height = left + weeks * pitch + 24, top + 7 * pitch + 40

    # Counts combine GitHub's calendar contributions and GitLab authored commits.
    combined = {}
    for day in dates:
        date = day.isoformat()
        combined[date] = (github_days.get(date, 0) if START <= day <= TODAY else 0) + gitlab_days.get(date, 0)

    levels = ['#161f2b', '#183d35', '#226c4e', '#2aa45b', '#50db7b']
    def shade(n):
        return levels[0 if n <= 0 else 1 if n == 1 else 2 if n <= 3 else 3 if n <= 7 else 4]

    result = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Animated combined GitHub contributions and GitLab authored commits over the last 365 days">',
              '<rect width="100%" height="100%" fill="none"/>',
              '<text x="28" y="21" font-size="12" font-family="Arial,sans-serif" font-weight="bold" fill="#c9d1d9">GitHub + GitLab activity</text>']

    for idx, day in enumerate(dates):
        x = left + (idx // 7) * pitch
        y = top + (idx % 7) * pitch
        n = combined[day.isoformat()]
        label = html.escape(f'{day.isoformat()}: {n} combined activities')
        result.append(f'<rect x="{x}" y="{y}" width="{sq}" height="{sq}" rx="2" fill="{shade(n)}"><title>{label}</title></rect>')

    # Travel across the grid; snake is five moving purple segments.
    # Sweep columns alternate vertical direction, keeping movement continuous.
    points = []
    for w in range(weeks):
        rows = range(7) if w % 2 == 0 else range(6, -1, -1)
        for r in rows:
            points.append((left + w * pitch + sq / 2, top + r * pitch + sq / 2))
    path = ' '.join(('M' if i == 0 else 'L') + f'{x:.1f},{y:.1f}' for i, (x, y) in enumerate(points))
    duration = 55
    for seg in range(5):
        radius = 5.4 if seg == 0 else 4.9 - seg * .5
        fill = '#d278f4' if seg == 0 else '#9c42bb'
        result.append(f'<circle r="{radius:.1f}" fill="{fill}" opacity="{max(.35, 1 - seg*.13):.2f}">')
        result.append(f'<animateMotion path="{path}" dur="{duration}s" begin="-{seg*.15:.2f}s" repeatCount="indefinite" rotate="auto"/>')
        result.append('</circle>')

    gh_total = sum(github_days.get(day.isoformat(), 0) for day in dates if START <= day <= TODAY)
    gl_total = sum(gitlab_days.values())
    result.append(f'<text x="28" y="{height - 14}" font-family="Arial,sans-serif" font-size="11" fill="#92a2b5">GitHub contributions: {gh_total}  ·  GitLab authored commits: {gl_total}  ·  Past 365 days</text>')
    result.append('</svg>')
    return '\n'.join(result)


def main():
    github_days = github_calendar()
    gitlab_days, project_count, errors = gitlab_daily_commits()
    target = Path('dist')
    target.mkdir(exist_ok=True)
    (target / 'github-gitlab-snake.svg').write_text(svg(github_days, gitlab_days), encoding='utf-8')
    print(f'Combined snake generated. GitLab projects scanned: {project_count}; days with GitLab commits: {len(gitlab_days)}.')
    if errors:
        print(f'WARNING: {errors} inaccessible project(s), possible undercount.')
    print('SVG includes daily aggregate counts, but no private project names, author emails, commit messages or tokens.')


if __name__ == '__main__':
    main()
