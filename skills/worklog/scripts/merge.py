#!/usr/bin/env python3
"""Merges new work log items into the artifact's day documents and plans the database writes."""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from common import data_dir, parse_day, resolve

CATEGORIES = {'shipped', 'reviews', 'investigation', 'research', 'decisions', 'notes'}
MAX_TEXT = 140
MAX_FOR = 40


def invalid(item):
    """Why an item breaks items.md, or None."""
    if not isinstance(item, dict):
        return 'not an object'
    if item.get('category') not in CATEGORIES:
        return f"unknown category {item.get('category')!r}"
    if not isinstance(item.get('text'), str) or not item['text'].strip():
        return 'no text'
    if len(item['text']) > MAX_TEXT:
        return f"text is {len(item['text'])} characters, shorten it to {MAX_TEXT} or fewer"
    if len(str(item.get('for', ''))) > MAX_FOR:
        return f'"for" is longer than {MAX_FOR} characters, use a name or a team'
    evidence = item.get('evidence', [])
    if not isinstance(evidence, list) or not all(isinstance(e, str) and e for e in evidence):
        return 'evidence must be a list of strings'
    if not evidence and not item.get('manual'):
        return 'no evidence on an item that is not manual'
    return None


def merge_day(existing, new):
    """Adds new items to a day; an automatic item citing the same evidence is updated instead. Manual items are never changed."""
    items = [dict(i) for i in existing]
    for item in new:
        if item.get('manual'):
            if not any(i.get('manual') and i['text'] == item['text'] for i in items):
                items.append(item)
            continue
        keys = set(item['evidence'])
        match = next((i for i in items if not i.get('manual') and keys & set(i.get('evidence', []))), None)
        if match is None:
            items.append(item)
            continue
        match.update({k: v for k, v in item.items() if k != 'evidence'})
        match['evidence'] = list(dict.fromkeys([*match.get('evidence', []), *item['evidence']]))
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', required=True, nargs='+', help='JSON files shaped {"days": {"YYYY-MM-DD": [items]}}')
    parser.add_argument('--existing', default='db/days', help='folder of day documents saved by an ArtifactData query (out_dir/days)')
    parser.add_argument('--out', required=True, help='folder for the merged documents and plan.json')
    parser.add_argument('--since', help='with --until: also list weekdays that still have nothing logged')
    parser.add_argument('--until', default='today')
    args = parser.parse_args()

    root = data_dir()
    existing_dir, out = resolve(args.existing, root), resolve(args.out, root)

    new, errors = {}, []
    for path in args.items:
        days = json.loads(resolve(path, root).read_text(encoding='utf-8')).get('days', {})
        for day, items in days.items():
            date.fromisoformat(day)
            for n, item in enumerate(items):
                problem = invalid(item)
                if problem:
                    errors.append(f'{path} {day} item {n + 1}: {problem}')
                else:
                    new.setdefault(day, []).append({k: v for k, v in item.items() if k in ('category', 'text', 'for', 'evidence', 'manual')})
    if errors:
        sys.exit('Fix these items and run again:\n' + '\n'.join(errors))

    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().isoformat(timespec='seconds')
    plan, logged = [], set()
    for day in sorted(new):
        source = existing_dir / f'{day}.json'
        current = json.loads(source.read_text(encoding='utf-8')).get('items', []) if source.exists() else []
        merged = merge_day(current, new[day])
        if merged:
            logged.add(day)
        if merged == current:
            continue
        target = out / f'{day}.json'
        target.write_text(json.dumps({'date': day, 'items': merged, 'updated_at': now}, ensure_ascii=False, indent=2), encoding='utf-8')
        plan.append({'doc_id': day, 'file_path': str(target), 'exists': source.exists()})

    (out / 'plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    updates = [p['doc_id'] for p in plan if p['exists']]
    print(f'plan: {out / "plan.json"}')
    print(f'{len(plan)} day documents to write, {len(plan) - len(updates)} new')
    if updates:
        print('already exist, pin with the version from your query: ' + ', '.join(updates))

    if args.since:
        since, until = parse_day(args.since, root), parse_day(args.until, root)
        logged |= {p.stem for p in existing_dir.glob('*.json') if json.loads(p.read_text(encoding='utf-8')).get('items')}
        empty, day = [], since
        while day <= until:
            if day.weekday() < 5 and day.isoformat() not in logged:
                empty.append(day.isoformat())
            day += timedelta(days=1)
        print('weekdays with nothing logged: ' + (', '.join(empty) if empty else 'none'))


if __name__ == '__main__':
    main()
