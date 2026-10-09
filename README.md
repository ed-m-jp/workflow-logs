# Workflow-Logs

A personal workflow log for the work a commit history doesn't show: investigations, debugging, research, prototyping, data pulls, reviews, help given, meetings, and why decisions were made. It lives in one claude.ai artifact that keeps the same URL, so you can share it once and it stays current: a short overview of the big and medium work on top, the day-by-day log below. Entries come from GitHub, your Claude Code sessions, Linear, optionally Slack, and what you tell it.

## Install

In Claude Code, run:

```text
/plugin marketplace add ed-m-jp/workflow-logs
/plugin install workflow-logs@workflow-logs
```

Claude Code clones https://github.com/ed-m-jp/workflow-logs with your git credentials, so a private repo needs read access first. To work from a local clone instead, pass its path: `/plugin marketplace add /path/to/workflow-logs`.

Then add this to `~/.claude/settings.json` and restart Claude Code:

```json
{
  "env": {
    "WORKFLOW_LOGS_GH_OWNER": "your-github-org"
  },
  "cleanupPeriodDays": 365
}
```

- `WORKFLOW_LOGS_GH_OWNER`: the GitHub org whose PRs count as work.
- `cleanupPeriodDays`: Claude Code deletes session transcripts after 30 days by default, and they are the only record of work that never became a PR. Raise it now; what is already deleted is gone.
- `WORKFLOW_LOGS_TRANSCRIPT_DIRS` (optional): colon-separated transcript folders, when you run Claude Code in more than one place (WSL and Windows, say). Defaults to `~/.claude/projects`.

The first run publishes your log page and gives you its URL. Add it to the same `env` block as `WORKFLOW_LOGS_ARTIFACT_URL`, so every later run and every machine writes to that one artifact.

Needs `python3` (3.9+) and an authenticated `gh`. Linear and Slack are read through whatever MCP tools your Claude Code has; without them those sources are skipped and the run says so.

## Use

| Command                                  | What it does                                                                                  |
| ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| `/workflow-logs:workflow-logs backfill 6m`           | Builds the last 6 months (`12m` or a `YYYY-MM-DD` start work too), then asks you about the gaps |
| `/workflow-logs:workflow-logs backfill 6m --slack`   | The same, also reading what you wrote in Slack channels you can access, public or private (never DMs or group DMs) |
| `/workflow-logs:workflow-logs checkin`               | Shows what today's log has and asks about what Claude couldn't see (meetings, brainstorming)  |
| `/workflow-logs:workflow-logs add <note>`            | Adds one hand-written item for today; `add 2026-10-01 <note>` for another day                 |
| `/workflow-logs:workflow-logs update`                | Adds everything since the last refresh from GitHub and Claude sessions                         |
| `/workflow-logs:workflow-logs overview`              | Rebuilds the overview of big and medium work from the whole log (update does it once a day)    |

You don't need to run `update` yourself: a Stop hook runs it in the background at most once an hour, as a headless Sonnet run that may only run the plugin's four scripts, write your log and touch `~/.local/share/workflow-logs`. Its output is in `~/.local/share/workflow-logs/state/last-auto-run.log`. After 17:00 the same hook reminds you once a day to run `checkin`.

## How it works

- `scripts/sessions.py` and `scripts/github.py` pull the raw facts into per-day digests under `~/.local/share/workflow-logs/cache/`. No model is involved in this step.
- Backfill launches one `workflow-logs-collector` agent (Sonnet, high effort) per month, three at a time. Each turns its month into items, plus questions about what the sources hint at but can't show.
- `scripts/merge.py` combines new items with what the log already holds, and the skill writes the result to the artifact's database, one document per day. Nothing is ever deleted, and items you added by hand are never changed.
- `scripts/overview.py` gives the model the whole log in short form and checks the overview it writes, which replaces the one document at the top of the page.
- `skills/workflow-logs/items.md` is the item format and the writing rules; `skills/workflow-logs/page/workflow-logs.html` is the page.

## Limits

- Session data only goes back as far as your oldest transcript. Further back, the log comes from PRs, Linear and Slack only; the backfill asks you about the empty weekdays.
- Athena queries are only logged when they show up in a Claude session, a ticket or a Slack message.
- The log is yours: review it before you share it. It leaves out secrets and customer data by rule, but a model wrote it.
