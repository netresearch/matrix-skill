---
description: Send work summary to configured Matrix room
allowed-tools: Bash(git:*), Bash(uv run:*), Bash(cat:*)
---

# Matrix Work Update

Send a summary of recent work to a configured Matrix room.

## Usage

```
/work-update [options] [room]
```

**Options:**
- `-y`, `--yes` - Skip confirmation, send immediately
- `[room]` - Override target room (default: from config or `agent-work`)

**Examples:**
- `/work-update` - Compose and confirm before sending
- `/work-update -y` - Send immediately without confirmation
- `/work-update ops` - Send to #ops room
- `/work-update -y agent-work` - Send to agent-work immediately

## Context

- Current directory: !`pwd`
- Git branch: !`git branch --show-current 2>/dev/null || echo "not a git repo"`
- Git remote: !`git remote get-url origin 2>/dev/null | sed 's/.*[:/]\([^/]*\/[^/]*\)\.git/\1/' || echo "unknown"`
- Recent commits: !`git log --oneline -5 2>/dev/null || echo "no commits"`
- Matrix config: !`cat ~/.config/matrix/config.json 2>/dev/null | grep -E '"(default_update_room|user_id)"' || echo "not configured"`
- User args: !`echo "$ARGUMENTS"`

## Your Task

1. **Parse arguments** from user input:
   - Check for `-y`, `--yes`, or `--y` flag → sets `SKIP_CONFIRM=true`
   - Check for room name argument → overrides default room

2. **Compose a work summary** based on the git context above:
   ```
   🤖 **Work Update**

   **Project**: {repo} @ {branch}

   **Recent Changes**:
   - {commit summaries}
   ```

3. **If SKIP_CONFIRM is false** (no -y flag):
   - Ask user to confirm using AskUserQuestion
   - Show the composed message
   - Options: "Send", "Send to different room", "Edit message", "Cancel"

4. **If SKIP_CONFIRM is true** (has -y flag):
   - Skip AskUserQuestion
   - Send immediately to configured room

5. **Find skill directory** and send the message:
   ```bash
   SKILL_DIR=$(ls -td ~/.claude/plugins/cache/*/matrix-communication/*/skills/matrix-communication 2>/dev/null | head -1) && cd "$SKILL_DIR" && set +H && uv run scripts/matrix-send-e2ee.py ROOM "MESSAGE"
   ```

Use `default_update_room` from config if available, otherwise default to `agent-work`.
