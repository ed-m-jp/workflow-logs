#!/usr/bin/env python3
"""Builds the log's overview: a digest of every stored day for the model to read, then the checked overview document."""
import argparse
import json
import sys
from datetime import date, datetime

from common import data_dir, resolve

SIZES = ('big', 'medium')
MAX_ITEMS = 25
MAX_TITLE = 60
MAX_TEXT = 200


def stored_days(folder):
    """{day: items} from the day documents an ArtifactData query saved."""
    if not folder.is_dir():
        sys.exit(f'{folder} is missing: run the ArtifactData query on "days" with out_dir <data dir>/cache/db first')
    days = {}
    for path in sorted(folder.glob('*.json')):
        items = json.loads(path.read_text(encoding='utf-8')).get('items', [])
        if items:
            days[path.stem] = items
    return days


def invalid(item):
    """Why an overview item breaks items.md, or None."""
    if not isinstance(item, dict):
        return 'not an object'
    if item.get('size') not in SIZES:
        return f"size must be big or medium, not {item.get('size')!r}"
    for field, limit in (('title', MAX_TITLE), ('text', MAX_TEXT)):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            return f'no {field}'
        if len(value) > limit:
            return f'{field} is {len(value)} characters, shorten it to {limit} or fewer'
    try:
        start, end = date.fromisoformat(item.get('from', '')), date.fromisoformat(item.get('to', ''))
    except (TypeError, ValueError):
        return '"from" and "to" must be YYYY-MM-DD'
    if start > end:
        return '"from" is after "to"'
    return None


def digest(days, out):
    lines = ['# Workflow log, every stored day', '']
    for day in sorted(days):
        lines.append(f'## {day}')
        for item in days[day]:
            prs = sum('/pull/' in e for e in item.get('evidence', []))
            extra = ''.join([f" (for {item['for']})" if item.get('for') else '', f" [{prs} PR{'s' if prs > 1 else ''}]" if prs else ''])
            lines.append(f"- {item.get('category')}: {item.get('text', '')}{extra}")
        lines.append('')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8')
    print(f'wrote: {out}')
    print(f"{len(days)} days, {sum(len(i) for i in days.values())} items" + (f', {min(days)} to {max(days)}' if days else ''))


def build(days, draft, out):
    items = json.loads(draft.read_text(encoding='utf-8')).get('items', [])
    errors = [f'item {n + 1}: {problem}' for n, item in enumerate(items) if (problem := invalid(item))]
    if not items:
        errors.append('no items')
    if len(items) > MAX_ITEMS:
        errors.append(f'{len(items)} items, keep it to {MAX_ITEMS} or fewer')
    if errors:
        sys.exit('Fix the overview and run again:\n' + '\n'.join(errors))

    keep = ('size', 'title', 'from', 'to', 'text')
    doc = {
        'items': [{k: item[k] for k in keep} for item in items],
        'through': max(days) if days else None,
        'updated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'wrote: {out}')
    print(f"{sum(i['size'] == 'big' for i in items)} big, {sum(i['size'] == 'medium' for i in items)} medium, log through {doc['through']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing', default='db/days', help='folder of day documents saved by an ArtifactData query (out_dir/days)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('digest', help='every stored day as one short line per item').add_argument('--out', required=True)
    check = sub.add_parser('build', help='check a drafted overview and write the document to save')
    check.add_argument('--draft', required=True, help='JSON shaped {"items": [overview items]}')
    check.add_argument('--out', required=True)
    args = parser.parse_args()

    root = data_dir()
    days = stored_days(resolve(args.existing, root))
    if args.command == 'digest':
        digest(days, resolve(args.out, root))
    else:
        build(days, resolve(args.draft, root), resolve(args.out, root))


if __name__ == '__main__':
    main()
