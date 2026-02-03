---
description: Send work summary to configured Matrix room
allowed-tools: Bash(git:*), Bash(uv run:*), Bash(cat:*)
---

# Matrix Work Update

Send a summary of recent work to a configured Matrix room.

## Context

- Current directory: !`pwd`
- Git branch: !`git branch --show-current 2>/dev/null || echo "not a git repo"`
- Git remote: !`git remote get-url origin 2>/dev/null | sed 's/.*[:/]\([^/]*\/[^/]*\)\.git/\1/' || echo "unknown"`
- Recent commits: !`git log --oneline -5 2>/dev/null || echo "no commits"`
- Matrix config: !`cat ~/.config/matrix/config.json 2>/dev/null | grep -E '"(default_update_room|user_id)"' || echo "not configured"`

## Your Task

1. **Compose a work summary** based on the git context above:
   ```
   🤖 **Work Update**

   **Project**: {repo} @ {branch}

   **Recent Changes**:
   - {commit summaries}
   ```

2. **Ask user to confirm** using AskUserQuestion:
   - Show the composed message
   - Options: "Send to agent-work", "Send to different room", "Edit message", "Cancel"

3. **Send the message** using:
   ```bash
   cd /home/sme/.claude/plugins/cache/netresearch-claude-code-marketplace/matrix-communication/1.11.0 && set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "MESSAGE"
   ```

Use `default_update_room` from config if available, otherwise default to `agent-work`.
