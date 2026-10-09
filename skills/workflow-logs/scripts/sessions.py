#!/usr/bin/env python3
"""Per-day digest of your Claude Code sessions (title, prompts, last answer) for the workflow log."""
import argparse
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from common import parse_day, report, data_dir, write_sections

MAX_PROMPTS = 30
PROMPT_CHARS = 400
ANSWER_CHARS = 800
NOISE_PREFIXES = (
    '<local-command-stdout>', '<local-command-stderr>', '<local-command-caveat>', '<system-reminder>',
    '<task-notification>', '<bash-input>', '<bash-stdout>', '<bash-stderr>', '[Request interrupted',
)
COMPACTION_MARKER = 'This session is being continued from a previous conversation'
NOISE_COMMANDS = {
    '/agents', '/clear', '/compact', '/config', '/context', '/cost', '/doctor', '/effort', '/exit', '/fast',
    '/help', '/hooks', '/ide', '/login', '/logout', '/mcp', '/memory', '/model', '/permissions', '/plugin',
    '/rename', '/resume', '/status', '/theme', '/usage', '/vim',
}


def transcript_roots():
    configured = os.environ.get('WORKFLOW_LOGS_TRANSCRIPT_DIRS')
    if configured:
        return [Path(p).expanduser() for p in configured.split(':') if p]
    return [Path(os.environ.get('CLAUDE_CONFIG_DIR', '~/.claude')).expanduser() / 'projects']


def local_time(timestamp):
    return datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone()


def squash(text, limit):
    text = ' '.join(text.split())
    return text[:limit] + ('…' if len(text) > limit else '')


def prompt_text(entry):
    if entry.get('isMeta') or 'toolUseResult' in entry:
        return None
    content = entry.get('message', {}).get('content')
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
            return None
        content = '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
    if not isinstance(content, str) or content.strip().startswith(NOISE_PREFIXES) or COMPACTION_MARKER in content:
        return None

    command = re.search(r'<command-name>(.*?)</command-name>', content, re.S)
    if command:
        args = re.search(r'<command-args>(.*?)</command-args>', content, re.S)
        content = f"/{command.group(1).strip().lstrip('/')} {args.group(1) if args else ''}"
    name = content.split(maxsplit=1)[0] if content.strip() else ''
    if name in NOISE_COMMANDS or name.startswith(('/workflow-logs', '/worklog')):  # /worklog is this plugin's old name
        return None

    # Pasted blocks are bulky and the likeliest place for a secret.
    content = re.sub(r'<pasted_content\b[^>]*>.*?</pasted_content\b[^>]*>', '[pasted text]', content, flags=re.S)
    content = re.sub(r'<system-reminder>.*?</system-reminder>', '', content, flags=re.S)
    return squash(content, PROMPT_CHARS) or None


def answer_text(entry):
    content = entry.get('message', {}).get('content')
    if not isinstance(content, list):
        return None
    text = ' '.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
    return squash(text, ANSWER_CHARS) or None


def read_session(path, since, until):
    """Returns {day: session} for one transcript, main thread only."""
    title, days = None, {}
    with path.open(encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get('type') == 'ai-title':
                title = entry.get('aiTitle') or title
                continue
            if entry.get('type') not in ('user', 'assistant') or entry.get('isSidechain') or not entry.get('timestamp'):
                continue
            when = local_time(entry['timestamp'])
            if not since <= when.date() <= until:
                continue

            day = days.setdefault(when.date(), {'project': None, 'branches': set(), 'prompts': [], 'answer': None})
            day['project'] = day['project'] or Path(entry.get('cwd') or path.parent.name).name
            if entry['type'] == 'user':
                text = prompt_text(entry)
                if text:
                    day['prompts'].append((when, text))
                    if entry.get('gitBranch'):
                        day['branches'].add(entry['gitBranch'])
            else:
                day['answer'] = answer_text(entry) or day['answer']

    for session in days.values():
        session['title'] = title
    return {d: s for d, s in days.items() if s['prompts']}


def render(sid, session):
    prompts = session['prompts']
    first, last = prompts[0][0], prompts[-1][0]
    branches = ', '.join(sorted(session['branches'])) or 'no branch'
    lines = [
        f"### {session['project']} | {session['title'] or 'untitled'} | session {sid[:8]} | {branches}"
        f" | {first:%H:%M}-{last:%H:%M} | {len(prompts)} prompts"
    ]
    lines += [f'- {when:%H:%M} {text}' for when, text in prompts[:MAX_PROMPTS]]
    if len(prompts) > MAX_PROMPTS:
        lines.append(f'- (+{len(prompts) - MAX_PROMPTS} more prompts)')
    if session['answer']:
        lines.append(f"Last answer: {session['answer']}")
    return lines + ['']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', required=True, help='YYYY-MM-DD, today, last-update or Nm')
    parser.add_argument('--until', default='today')
    parser.add_argument('--out', required=True, help='file path; {month} splits it per month; relative goes under the data dir cache/')
    args = parser.parse_args()

    root = data_dir()
    since, until = parse_day(args.since, root), parse_day(args.until, root)
    since_ts = datetime.combine(since, datetime.min.time()).astimezone().timestamp()

    found, coverage = {}, []
    for folder in transcript_roots():
        paths = list(folder.glob('*/*.jsonl'))
        oldest = min((p.stat().st_mtime for p in paths), default=None)
        coverage.append(f"{folder}: {date.fromtimestamp(oldest) if oldest else 'none found'}")
        for path in paths:
            mtime = path.stat().st_mtime
            if mtime < since_ts:
                continue
            for day, session in read_session(path, since, until).items():
                found.setdefault(day, []).append((path.stem, session))

    sections = {
        day: [line for sid, s in sorted(sessions, key=lambda x: x[1]['prompts'][0][0]) for line in render(sid, s)]
        for day, sessions in found.items()
    }
    header = [
        f'# Claude sessions {since}..{until} (local time)',
        '',
        'Claude Code deletes transcripts after cleanupPeriodDays, so days before the oldest one have no session data.',
        'Oldest transcript per folder: ' + '; '.join(coverage),
    ]
    report(root, since, until, write_sections(sections, args.out, root, header))


if __name__ == '__main__':
    main()
