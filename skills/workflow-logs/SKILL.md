---
name: workflow-logs
description: Keep a personal workflow log, published as one claude.ai artifact, of what you did and why (shipped PRs, reviews, help given, investigations, research, data work, decisions, meetings), built from GitHub, Claude Code sessions, Linear, optionally Slack, and what you tell it. Use for /workflow-logs backfill <6m|12m|YYYY-MM-DD> [--slack], /workflow-logs update, /workflow-logs checkin [YYYY-MM-DD], /workflow-logs add [YYYY-MM-DD] <note>, or when the user asks to log, record or backfill their work.
argument-hint: "backfill <6m|12m|YYYY-MM-DD> [--slack] | update | checkin [YYYY-MM-DD] | add [YYYY-MM-DD] <note>"
---

# Workflow log

A paper trail of the work a commit history doesn't show: investigations, debugging, research, prototyping, data pulls, reviews, help given, meetings, and the reasoning behind decisions. The log is one artifact page that always keeps the same URL; each run adds rows to its database and never republishes the page. Read [items.md](items.md) before writing any items, and follow it exactly.

## Setup

- **Data dir:** `~/.local/share/workflow-logs` (under `$XDG_DATA_HOME` when set) holds the cache and state. Scripts print it.
- **`WORKFLOW_LOGS_GH_OWNER`:** the GitHub org whose PRs count as work. `github.py` fails without it: stop and point the user at the plugin README.
- **`WORKFLOW_LOGS_ARTIFACT_URL`:** the log's artifact. Every script prints it (or "not set"); in add and checkin get it with `printenv WORKFLOW_LOGS_ARTIFACT_URL`. When it is not set:
  1. Publish [page/workflow-logs.html](page/workflow-logs.html) with the Artifact tool: `icon` "notes", `description` "Running record of shipped work, reviews, investigations, research and decisions, each with a link to its evidence.", and `capabilities` `{"db": {"rules": [{"path": "", "read": "view", "write": "owner"}]}}`.
  2. Tell the user to add `"WORKFLOW_LOGS_ARTIFACT_URL": "<the new URL>"` to `env` in `~/.claude/settings.json`, so the hourly refresh and later sessions write to the same artifact. Use the URL for the rest of this run.
  3. In a headless run, stop instead: never publish a second artifact.

## Scripts

Call them as `python3 <this skill's folder>/scripts/<name>.py` with the absolute path, exactly as written, so the hourly run's permission rules match. A relative path lands in the data dir's `cache/`, and `{month}` in `--out` writes one file per month. `<day>` is `YYYY-MM-DD`, `today`, `last-update` or `6m` / `12m`.

- `sessions.py --since <day> --until <day> --out <file>`: your Claude Code sessions per day (title, prompts, last answer).
- `github.py --since <day> --until <day> --out <file>`: PRs you opened and reviewed per day, with the start of each description.
- `merge.py --items <file>... --out <dir> [--since <day> --until <day>]`: combines new items with the stored days and writes `plan.json`; with a range it also lists weekdays that still have nothing logged.

## Saving items

Every mode saves the same way. `ArtifactData` is often a deferred tool: when it isn't in your tool list, load it with `ToolSearch` (`select:ArtifactData`) before step 2.

1. Write the items to a JSON file in the data dir's `cache/`, shaped as in items.md.
2. `ArtifactData` `query` on collection `days`, `query` `{"where": [["date", ">=", "<first day>"], ["date", "<=", "<last day>"]], "limit": 1000}`, `out_dir` `<data dir>/cache/db`. Note each document's version from the reply.
3. Run `merge.py --items <your files> --out <dir>` (add `--since`/`--until` when you want the empty weekdays).
4. Read `plan.json` and send `ArtifactData` `batch` writes of up to 50 entries: `{"op": "set", "collection": "days", "doc_id": <doc_id>, "file_path": <file_path>}`, plus `"if_version": <version from step 2>` on every entry marked `"exists": true`.
5. If a batch is refused because a document changed, redo steps 2 to 4 once.

## Modes

Read the arguments and run one mode. With no arguments, run update.

### update

Adds what happened since the last refresh, from GitHub and Claude sessions. The Stop hook runs this headless every hour: never ask the user anything here, and use no other tools than these steps need.

1. `sessions.py --since last-update --until today --out update/sessions.md`
2. `github.py --since last-update --until today --out update/github.md`. If it fails, carry on with sessions only.
3. Turn both into items in `update/items.json`, then save them.
4. Write today's date (`YYYY-MM-DD`) to `<data dir>/state/last-update`.
5. Reply in at most five lines: items saved per day, and any source that failed.

### backfill <6m | 12m | YYYY-MM-DD> [--slack]

Builds a past range from GitHub, Claude sessions and Linear, plus public Slack channels only when `--slack` is given (never direct messages or private channels). Then asks the user about what none of them can show.

1. Run `sessions.py --since <arg> --until today --out 'backfill/{month}-sessions.md'` and `github.py` with the same range and `--out 'backfill/{month}-github.md'` (`{month}` stays literal). Sessions only reach back to the oldest transcript; each sessions file's header says how far.
2. Get the user's email with `git config --global user.email`.
3. Launch one `workflow-logs:workflow-logs-collector` agent per month, no more than three at a time. Brief each with: the month's first and last day inside the range, the paths of that month's two digests (or "none"), the items file to write (`<data dir>/cache/backfill/<YYYY-MM>-items.json`), the absolute path of items.md, the user's email, and "Slack: yes" or "Slack: no".
4. Save all the month items files together, with `--since <first day> --until today`.
5. Ask about the gaps, one month at a time, newest first. For each month, list in one short message the collectors' questions and the weekdays with nothing logged, and ask what happened: meetings, brainstorming, calls, help given in person, time off. Tell the user they can answer briefly, skip anything, or say stop. Turn each answer into `manual` items (a decision made in a meeting goes under `decisions`), keep their facts and add nothing, and save them before moving to the next month.
6. Write today's date to `<data dir>/state/last-update` if the file is missing or holds an earlier date.
7. Report a short table: month, items saved, sources a collector could not use. Say how far back session data went, and give the artifact link.

### checkin [YYYY-MM-DD]

Collects what the sources can't see for one day, today by default.

1. `ArtifactData` `get` on `days` / `<day>` and list what is logged for that day, one short line each.
2. Ask what else happened that you can't see: meetings, brainstorming, calls, whiteboard sessions, help given in person, interviews, things they read or learned. For each: what, with whom, and what came out of it. Then wait for the answer.
3. Turn the answer into `manual` items, keeping their facts and adding nothing, and save them.
4. When the day is today, write today's date to `<data dir>/state/last-checkin`.

### add [YYYY-MM-DD] <note>

Saves one hand-written item, today by default: a `manual` item in the category the note fits (`notes` when unsure), rewritten as one sentence in the items style, keeping the user's facts and adding nothing.
