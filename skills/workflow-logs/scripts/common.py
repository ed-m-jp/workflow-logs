"""Shared helpers for the workflow-logs scripts: the local data dir, date arguments, output files."""
import os
from datetime import date
from pathlib import Path


def data_dir():
    """Local cache and state, outside ~/.claude because Claude Code refuses tool writes there; the log itself lives in the artifact."""
    path = Path(os.environ.get('XDG_DATA_HOME', '~/.local/share')).expanduser().resolve() / 'workflow-logs'
    path.mkdir(parents=True, exist_ok=True)
    return path


def months_back(today, months):
    month = today.month - months
    year = today.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    for day in (today.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue


def parse_day(value, root):
    """Accepts YYYY-MM-DD, today, last-update (the day the log was last refreshed) or Nm (N months ago)."""
    today = date.today()
    if value == 'today':
        return today
    if value == 'last-update':
        state = root / 'state' / 'last-update'
        return date.fromisoformat(state.read_text().strip()) if state.exists() else today
    if value.endswith('m') and value[:-1].isdigit():
        return months_back(today, int(value[:-1]))
    return date.fromisoformat(value)


def resolve(path, root):
    """Relative paths go under the data dir's cache/."""
    path = Path(path).expanduser()
    return path if path.is_absolute() else root / 'cache' / path


def write_sections(sections, out, root, header):
    """Writes {day: [lines]} newest first; one file per month when out contains {month}."""
    groups = {}
    for day in sorted(sections, reverse=True):
        key = f'{day:%Y-%m}' if '{month}' in out else ''
        groups.setdefault(key, []).extend([f'## {day} ({day:%a})', *sections[day], ''])
    if not groups and '{month}' not in out:
        groups[''] = ['No activity in this range.']

    written = []
    for key, lines in groups.items():
        path = resolve(out.replace('{month}', key), root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join([*header, '', *lines]) + '\n', encoding='utf-8')
        written.append(str(path))
    return written


def report(root, since, until, written):
    print(f'data dir: {root}')
    print(f"artifact: {os.environ.get('WORKFLOW_LOGS_ARTIFACT_URL') or 'not set'}")
    print(f'range: {since}..{until}')
    print('wrote: ' + (', '.join(written) if written else 'nothing, no activity in this range'))
