#!/usr/bin/env bash
# Stop hook: refreshes the work log in a background headless run at most once an hour, and nudges a daily checkin.
set -u

[ -n "${WORKLOG_RUNNING:-}" ] && exit 0 # the headless run's own Stop
if [ -z "${WORKLOG_GH_OWNER:-}" ] || [ -z "${WORKLOG_ARTIFACT_URL:-}" ]; then
  echo '{"systemMessage": "worklog: auto-refresh is off until WORKLOG_GH_OWNER and WORKLOG_ARTIFACT_URL are set in settings.json env"}'
  exit 0
fi

dir="${XDG_DATA_HOME:-$HOME/.local/share}/worklog"
state="$dir/state"
mkdir -p "$state" || exit 0
today="$(date +%F)"

# Once a day after 17:00, unless today's checkin is done.
if [ "$(date +%H)" -ge 17 ] && [ "$(cat "$state/last-checkin" 2>/dev/null)" != "$today" ] && [ "$(cat "$state/last-nudge" 2>/dev/null)" != "$today" ]; then
  echo "$today" >"$state/last-nudge"
  echo '{"systemMessage": "worklog: anything today Claude could not see, like meetings or brainstorming? Run /worklog:worklog checkin"}'
fi

[ -n "$(find "$state/last-auto-run" -mmin -60 2>/dev/null)" ] && exit 0

# mkdir is the lock because macOS has no flock; a lock older than 30 minutes is from a killed run.
lock="$state/lock"
[ -n "$(find "$lock" -maxdepth 0 -mmin +30 2>/dev/null)" ] && rmdir "$lock"
mkdir "$lock" 2>/dev/null || exit 0
touch "$state/last-auto-run"

# Runs from the data dir so no project CLAUDE.md loads; it may only run the three scripts, write the log and its own files.
# The explicit permission mode overrides a user default of plan, which would refuse every write.
scripts="$CLAUDE_PLUGIN_ROOT/skills/worklog/scripts"
cd "$dir" || exit 0
nohup bash -c '
  trap "rmdir \"$1\"" EXIT
  WORKLOG_RUNNING=1 claude -p "/worklog:worklog update" \
    --model sonnet --effort high --no-session-persistence --permission-mode default --add-dir "$4" \
    --allowedTools "Bash(python3 $2/sessions.py:*)" "Bash(python3 $2/github.py:*)" "Bash(python3 $2/merge.py:*)" \
      "ToolSearch" "ArtifactData" "Edit(/$3/**)"
' _ "$lock" "$scripts" "$dir" "$CLAUDE_PLUGIN_ROOT" >"$state/last-auto-run.log" 2>&1 </dev/null &
exit 0
