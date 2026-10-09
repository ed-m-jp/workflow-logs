#!/usr/bin/env python3
"""Per-day digest of the pull requests you opened and reviewed, for the work log."""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

from common import parse_day, report, data_dir, write_sections

BODY_CHARS = 400
QUERY = '''
query($from: DateTime!, $to: DateTime!, $cursor: String) {
  viewer { login contributionsCollection(from: $from, to: $to) {
    %s(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { occurredAt %s }
    }
  } }
}'''
OPENED = 'pullRequestContributions', 'pullRequest { number title url state merged body repository { nameWithOwner owner { login } } }'
REVIEWED = 'pullRequestReviewContributions', 'pullRequestReview { state } pullRequest { number title url author { login } repository { nameWithOwner owner { login } } }'


def gh(query, start, end, cursor):
    args = ['gh', 'api', 'graphql', '-f', f'query={query}', '-f', f'from={start.isoformat()}', '-f', f'to={end.isoformat()}']
    args += ['-f', f'cursor={cursor}'] if cursor else ['-F', 'cursor=null']
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f'gh api graphql failed: {result.stderr.strip()}')
    return json.loads(result.stdout)['data']['viewer']


def fetch(kind, start, end):
    """Yields (viewer login, node) for one contributions connection; the API caps a range at one year."""
    connection, fields = kind
    query, cursor = QUERY % (connection, fields), None
    while True:
        viewer = gh(query, start, end, cursor)
        page = viewer['contributionsCollection'][connection]
        for node in page['nodes']:
            yield viewer['login'], node
        if not page['pageInfo']['hasNextPage']:
            return
        cursor = page['pageInfo']['endCursor']


def month_windows(since, until):
    """Local-midnight windows, a month at a time, padded a day each side; results are re-filtered by local date."""
    now = datetime.now().astimezone()
    start = since
    while start <= until:
        following = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = min(following - timedelta(days=1), until)
        lower = datetime.combine(start - timedelta(days=1), datetime.min.time()).astimezone()
        upper = datetime.combine(end + timedelta(days=2), datetime.min.time()).astimezone()
        yield lower, min(upper, now)
        start = following


def description(body):
    """The start of the PR body as prose, without headings, bold-only label lines or HTML."""
    if not body:
        return ''
    text = re.sub(r'<!--.*?-->|<[^>]+>', '', body, flags=re.S)
    lines = [line for line in text.splitlines() if not re.match(r'\s*(#|\*\*[^*]+\*\*\s*$)', line)]
    text = ' '.join(' '.join(lines).split())
    return text[:BODY_CHARS] + ('…' if len(text) > BODY_CHARS else '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', required=True, help='YYYY-MM-DD, today, last-update or Nm')
    parser.add_argument('--until', default='today')
    parser.add_argument('--out', required=True, help='file path; {month} splits it per month; relative goes under the data dir cache/')
    args = parser.parse_args()

    owner = os.environ.get('WORKLOG_GH_OWNER')
    if not owner:
        sys.exit('WORKLOG_GH_OWNER is not set: add the GitHub org to "env" in ~/.claude/settings.json')
    root = data_dir()
    since, until = parse_day(args.since, root), parse_day(args.until, root)

    opened, reviewed = {}, {}
    for lower, upper in month_windows(since, until):
        for login, node in fetch(OPENED, lower, upper):
            pr, day = node['pullRequest'], datetime.fromisoformat(node['occurredAt'].replace('Z', '+00:00')).astimezone().date()
            if since <= day <= until and pr['repository']['owner']['login'].lower() == owner.lower():
                opened.setdefault(day, {})[pr['url']] = pr
        for login, node in fetch(REVIEWED, lower, upper):
            pr, day = node['pullRequest'], datetime.fromisoformat(node['occurredAt'].replace('Z', '+00:00')).astimezone().date()
            author = (pr['author'] or {}).get('login', 'ghost')
            if since <= day <= until and author != login and pr['repository']['owner']['login'].lower() == owner.lower():
                states = reviewed.setdefault(day, {}).setdefault(pr['url'], (pr, author, []))[2]
                states.append(node['pullRequestReview']['state'].lower().replace('_', ' '))

    sections = {}
    for day in set(opened) | set(reviewed):
        lines = []
        if day in opened:
            lines.append('Opened:')
            for pr in opened[day].values():
                status = 'merged' if pr['merged'] else pr['state'].lower()
                lines.append(f"- {pr['repository']['nameWithOwner']}#{pr['number']} ({status}) {pr['title']} {pr['url']}")
                if description(pr['body']):
                    lines.append(f"  Description: {description(pr['body'])}")
        if day in reviewed:
            lines.append('Reviewed:')
            for pr, author, states in reviewed[day].values():
                summary = ', '.join(f'{s} x{states.count(s)}' for s in dict.fromkeys(states))
                lines.append(f"- {pr['repository']['nameWithOwner']}#{pr['number']} by {author} ({summary}) {pr['title']} {pr['url']}")
        sections[day] = lines

    header = [f'# GitHub activity in {owner} {since}..{until} (local time)']
    report(root, since, until, write_sections(sections, args.out, root, header))


if __name__ == '__main__':
    main()
